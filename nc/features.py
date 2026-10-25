"""Features (Phase 6).

Program features (one vector per program):
  c_*    static counts from the start IR after a light canonicalization (sroa, early-cse,
         simplifycfg, instcombine at function level): what the source looks like
  o3_*   the same counts on the -O3 IR: what -O3 made of it
  sim_*  SIMULATED dynamic rates from valgrind cachegrind on an -O3 binary built for
         -march=x86-64-v3 (valgrind 3.26 cannot execute the AVX-512 code -march=native emits on
         this Zen 4 CPU). WSL2 has no perf counters; these are a simulator's numbers, not hardware's.
  scan_* facts from the corpus scan (runtime ratios between levels, memory, size)
Candidate features: the edit genome encoded by pass family (deleted / inserted / duplicated /
option-flipped counts per family), knob values (O3 default when unset), llc level and flags,
and which standard level a raw seed is.

LLVM 18 release builds do not print -stats (checked: no output), so counts come from the IR text.
"""
from __future__ import annotations

import json
import math
import os
import re
import subprocess
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .config import Config
from .db import Store
from .pipeline import KNOBS, KNOBS_V2, Genome, Node, _walk, pass_name
from .timing import RunSpec, helper_cpus
from .toolchain import Toolchain

SCHEMA = """
CREATE TABLE IF NOT EXISTS features(
  program_id TEXT, fset TEXT, version TEXT, json TEXT, ts TEXT, PRIMARY KEY(program_id, fset));
"""
FEATURE_VERSION = "f1"
SIM_MARCH = "x86-64-v3"
# no-verify-fixpoint as in -O3 itself: LLVM 18 aborts on 18 corpus programs otherwise (identical output when a fixpoint is reached)
CANON = "function(sroa<modify-cfg>,early-cse,simplifycfg,instcombine<no-verify-fixpoint>)"

INT_OPS = {"add", "sub", "mul", "udiv", "sdiv", "urem", "srem", "shl", "lshr", "ashr", "and", "or", "xor"}
FP_OPS = {"fadd", "fsub", "fmul", "fdiv", "frem", "fneg"}
CAST_OPS = {"trunc", "zext", "sext", "fptrunc", "fpext", "fptoui", "fptosi", "uitofp", "sitofp", "ptrtoint",
            "inttoptr", "bitcast", "addrspacecast"}
VEC_OPS = {"extractelement", "insertelement", "shufflevector"}


# ---------------------------------------------------------------- static
def ir_counts(text: str) -> dict[str, float]:
    c = {k: 0 for k in ("funcs", "blocks", "insts", "load", "store", "alloca", "gep", "call", "intrinsic",
                        "indirect_call", "br", "condbr", "switch", "indirectbr", "ret", "phi", "select",
                        "icmp", "fcmp", "intop", "fpop", "div", "cast", "vecop", "vector_typed", "atomic",
                        "memintrin", "globals", "max_func_insts", "unreachable")}
    cur = 0
    in_fn = False
    for ln in text.splitlines():
        if ln.startswith("define "):
            in_fn, cur = True, 0
            c["funcs"] += 1
            c["blocks"] += 1
            continue
        if ln.startswith("@") and " = " in ln and not in_fn:
            c["globals"] += 1
        if ln.startswith("}"):
            in_fn = False
            c["max_func_insts"] = max(c["max_func_insts"], cur)
            continue
        if not in_fn:
            continue
        if ln and not ln.startswith(" ") and ln.rstrip().endswith(":") or re.match(r"^[\w.$-]+:\s*(;.*)?$", ln):
            c["blocks"] += 1
            continue
        s = ln.strip()
        if not s or s.startswith(";") or "@llvm.dbg." in s or "@llvm.lifetime." in s:
            continue
        cur += 1
        c["insts"] += 1
        body = s.split(" = ", 1)[1] if " = " in s.split("(")[0] else s
        op = body.split()[0] if body else ""
        if op in ("tail", "musttail", "notail"):
            op = body.split()[1]
        if op in ("load", "store", "alloca", "phi", "select", "icmp", "fcmp", "switch", "indirectbr", "ret", "unreachable"):
            c[op] += 1
        elif op == "getelementptr":
            c["gep"] += 1
        elif op in ("call", "invoke"):
            c["call"] += 1
            if "@llvm." in body:
                c["intrinsic"] += 1
                if re.search(r"@llvm\.mem(cpy|set|move)", body):
                    c["memintrin"] += 1
            elif re.search(r"\s%[\w.]+\(", body):
                c["indirect_call"] += 1
        elif op == "br":
            c["br"] += 1
            if body.startswith("br i1"):
                c["condbr"] += 1
        elif op in INT_OPS:
            c["intop"] += 1
        elif op in FP_OPS:
            c["fpop"] += 1
        elif op in CAST_OPS:
            c["cast"] += 1
        elif op in VEC_OPS:
            c["vecop"] += 1
        elif op in ("atomicrmw", "cmpxchg", "fence"):
            c["atomic"] += 1
        if op in ("udiv", "sdiv", "urem", "srem", "fdiv", "frem"):
            c["div"] += 1
        if re.search(r"<\d+ x ", body):
            c["vector_typed"] += 1
    n = max(c["insts"], 1)
    out = {f"n_{k}": float(v) for k, v in c.items()}
    for k in ("load", "store", "alloca", "gep", "call", "intrinsic", "indirect_call", "condbr", "switch", "phi",
              "select", "icmp", "fcmp", "intop", "fpop", "div", "cast", "vecop", "vector_typed"):
        out[f"r_{k}"] = c[k] / n
    out["log_insts"] = math.log1p(c["insts"])
    out["insts_per_block"] = c["insts"] / max(c["blocks"], 1)
    out["blocks_per_func"] = c["blocks"] / max(c["funcs"], 1)
    return out


def loop_counts(tc: Toolchain, ir: Path) -> dict[str, float]:
    r = subprocess.run([tc.tool("opt"), "-passes=print<loops>", "-disable-output", str(ir)],
                       capture_output=True, text=True, timeout=300)
    depths = [int(m.group(1)) for m in re.finditer(r"Loop at depth (\d+)", r.stderr)]
    return {"n_loops": float(len(depths)), "max_loop_depth": float(max(depths, default=0)),
            "n_inner_loops": float(sum(1 for d in depths if d >= 2))}


def static_features(tc: Toolchain, rec: dict) -> dict[str, float]:
    cflags = tuple(rec.get("cflags") or [])
    ir0 = tc.start_ir(rec["src"], cflags)
    out: dict[str, float] = {}
    with tempfile.TemporaryDirectory(dir=tc.work / "tmp") as d:
        for tag, pipe in (("c", CANON), ("o3", "default<O3>")):
            p = Path(d) / f"{tag}.ll"
            r = subprocess.run([tc.tool("opt"), f"-passes={pipe}", "-S", str(ir0), "-o", str(p)],
                               capture_output=True, text=True, timeout=600)
            if r.returncode != 0:
                raise RuntimeError(f"opt {pipe} failed: {r.stderr[-300:]}")
            f = {**ir_counts(p.read_text()), **loop_counts(tc, p)}
            out.update({f"{tag}_{k}": v for k, v in f.items()})
    out["o3_vs_c_insts"] = out["o3_n_insts"] / max(out["c_n_insts"], 1)
    return out


# ---------------------------------------------------------------- simulated dynamic
_CG = {"I refs": "ir", "I1  misses": "i1m", "LLi misses": "llim", "D refs": "dr", "D1  misses": "d1m",
       "LLd misses": "lldm", "Branches": "br", "Mispredicts": "mp"}


def _num(s: str) -> float:
    return float(s.replace(",", "").split()[0])


def cachegrind(binary: str, spec: RunSpec, cpu: int, timeout_s: float = 3600, ll: str | None = None) -> dict[str, float]:
    """Simulated cache/branch statistics (valgrind cachegrind, cache + branch simulation).
    `ll` overrides the simulated last-level cache (size,assoc,line), e.g. the 1 MB private L2."""
    cmd = ["taskset", "-c", str(cpu), "valgrind", "--tool=cachegrind", "--cache-sim=yes", "--branch-sim=yes",
           "--cachegrind-out-file=/dev/null", *([f"--LL={ll}"] if ll else []), binary, *spec.args]
    stdin = open(spec.stdin_path, "rb") if spec.stdin_path else subprocess.DEVNULL
    try:
        r = subprocess.run(cmd, stdin=stdin, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
                           timeout=timeout_s, cwd=spec.cwd)
    finally:
        if spec.stdin_path:
            stdin.close()
    if r.returncode != 0 or "Process terminating" in r.stderr:
        tail = [x for x in r.stderr.splitlines() if "terminating" in x or "Illegal" in x or "signal" in x]
        raise RuntimeError(f"program did not finish under valgrind (exit {r.returncode}): {' | '.join(tail)[:200]}")
    v: dict[str, float] = {}
    for ln in r.stderr.splitlines():
        body = re.sub(r"^==\d+==\s*", "", ln)
        for key, name in _CG.items():
            if body.startswith(key + ":") and name not in v:
                try:
                    v[name] = _num(body.split(":", 1)[1])
                except (ValueError, IndexError):
                    pass
        m = re.match(r"(Cond|Ind) branches?:?\s+([\d,]+)\s+\(\s*([\d,]+)\s+cond\s+\+\s+([\d,]+)\s+ind\)", body)
        if body.startswith("Branches:"):
            m2 = re.search(r"\(\s*([\d,]+)\s+cond\s+\+\s+([\d,]+)\s+ind\)", body)
            if m2:
                v["br_cond"], v["br_ind"] = _num(m2.group(1)), _num(m2.group(2))
        if body.startswith("Mispredicts:"):
            m2 = re.search(r"\(\s*([\d,]+)\s+cond\s+\+\s+([\d,]+)\s+ind\)", body)
            if m2:
                v["mp_cond"], v["mp_ind"] = _num(m2.group(1)), _num(m2.group(2))
    if "ir" not in v or v["ir"] <= 0:
        raise RuntimeError(f"cachegrind produced no summary: {r.stderr[-300:]}")
    ir = v["ir"]
    return {
        "sim_log_instr": math.log(ir),
        "sim_data_refs_per_instr": v.get("dr", 0) / ir,
        "sim_d1_miss_rate": v.get("d1m", 0) / max(v.get("dr", 1), 1),
        "sim_lld_miss_rate": v.get("lldm", 0) / max(v.get("dr", 1), 1),
        "sim_lld_mpki": v.get("lldm", 0) / ir * 1000,
        "sim_i1_mpki": v.get("i1m", 0) / ir * 1000,
        "sim_branches_per_instr": v.get("br", 0) / ir,
        "sim_cond_mispredict_rate": v.get("mp_cond", 0) / max(v.get("br_cond", 1), 1),
        "sim_ind_branch_share": v.get("br_ind", 0) / max(v.get("br", 1), 1),
        "sim_ind_mispredict_rate": v.get("mp_ind", 0) / max(v.get("br_ind", 1), 1),
        "sim_branch_mpki": v.get("mp", 0) / ir * 1000,
    }


def scan_features(rec: dict) -> dict[str, float]:
    t = rec.get("times_ms") or {}
    o3 = t.get("O3") or 1.0
    return {"scan_log_o3_ms": math.log(o3), "scan_o0_over_o3": (t.get("O0") or o3) / o3,
            "scan_o1_over_o3": (t.get("O1") or o3) / o3, "scan_o2_over_o3": (t.get("O2") or o3) / o3,
            "scan_os_over_o3": (t.get("Os") or o3) / o3, "scan_level_spread": rec.get("level_spread", 1.0),
            "scan_log_maxrss_mb": math.log1p(rec.get("o3_maxrss_mb") or 0),
            "scan_log_text": math.log1p(rec.get("o3_text_bytes") or 0),
            "scan_distinct_levels": float(rec.get("distinct_level_binaries") or 0)}


def extract(tc: Toolchain, cfg: Config, store: Store, recs: list[dict], dynamic: bool = True,
            force: bool = False, workers: int = 0, log=print) -> None:
    """Compute and store feature sets per program (static+scan always; sim if dynamic)."""
    store.con.executescript(SCHEMA)
    have = {(r["program_id"], r["fset"]) for r in store.rows("SELECT program_id, fset FROM features WHERE version=?",
                                                             (FEATURE_VERSION,))}
    cpus = helper_cpus(cfg.timing_cpu)

    def put(pid, fset, d):
        store.con.execute("INSERT OR REPLACE INTO features VALUES(?,?,?,?,?)",
                          (pid, fset, FEATURE_VERSION, json.dumps(d), time.strftime("%Y-%m-%dT%H:%M:%S")))
        store.con.commit()

    for rec in recs:
        pid = rec["program_id"]
        if force or (pid, "static") not in have:
            try:
                put(pid, "static", static_features(tc, rec))
            except Exception as e:
                log(f"[{pid}] static features failed: {e}")
        if force or (pid, "scan") not in have:
            put(pid, "scan", scan_features(rec))
    if not dynamic:
        return
    # pass 1: default caches ("sim"); pass 2: last level = the 1 MB private L2 ("sim_l2"), whose misses
    # are the traffic that reaches the SHARED L3/memory (used to schedule parallel timing safely)
    for fset, ll in (("sim", None), ("sim_l2", L2_SIM)):
        _cachegrind_pass(tc, cfg, recs, fset, ll, have, force, workers, cpus, put, log)


L2_SIM = "1048576,8,64"


def _cachegrind_pass(tc, cfg, recs, fset, ll, have, force, workers, cpus, put, log):
    todo = [r for r in recs if force or (r["program_id"], fset) not in have]
    if not todo:
        return
    log(f"cachegrind ({fset}) on {len(todo)} programs, {workers or len(cpus)} parallel (helper CPUs {cpus}); "
        "never run this while a timing job runs")

    import copy
    from .toolchain import Toolchain as _TC
    cfg_sim = copy.copy(cfg)
    cfg_sim.march = SIM_MARCH
    tc_sim = _TC(cfg_sim, tc.work)

    def job(ir):
        i, rec = ir
        b = tc_sim.build(rec["src"], "default<O3>", 3, tuple(rec.get("cflags") or []))
        if not b.ok:
            raise RuntimeError(f"{rec['program_id']}: {SIM_MARCH} build failed: {b.error[:200]}")
        t0 = time.time()
        d = cachegrind(b.bin_path, RunSpec.from_dict(rec["time_spec"]), cpus[i % len(cpus)], ll=ll)
        if fset == "sim_l2":
            d = {"sim_l2d_mpki": d["sim_lld_mpki"], "sim_l2d_miss_rate": d["sim_lld_miss_rate"]}
        return rec["program_id"], d, time.time() - t0

    with ThreadPoolExecutor(workers or len(cpus)) as ex:
        futs = [ex.submit(job, x) for x in enumerate(todo)]
        for f in futs:
            try:
                pid, d, dt = f.result()
                put(pid, fset, d)
                log(f"[{pid}] cachegrind {fset} ok ({dt:.0f}s)")
            except Exception as e:
                log(f"cachegrind failed: {e!r}"[:300])


def program_features(store: Store, sets=("static", "sim", "sim_l2", "scan")) -> dict[str, dict[str, float]]:
    store.con.executescript(SCHEMA)
    out: dict[str, dict[str, float]] = {}
    for r in store.rows("SELECT program_id, fset, json FROM features WHERE version=?", (FEATURE_VERSION,)):
        if r["fset"] in sets:
            out.setdefault(r["program_id"], {}).update(json.loads(r["json"]))
    return out


# ---------------------------------------------------------------- candidate encoding
FAMILY_OF = {
    "simplifycfg": "cfg", "jump-threading": "cfg", "loop-simplifycfg": "cfg", "dfa-jump-threading": "cfg",
    "instcombine": "combine", "instsimplify": "combine", "aggressive-instcombine": "combine",
    "early-cse": "cse", "gvn": "cse", "gvn-hoist": "cse", "gvn-sink": "cse", "newgvn": "cse",
    "sroa": "mem", "memcpyopt": "mem", "dse": "mem", "mldst-motion": "mem", "infer-alignment": "mem",
    "inline": "inline", "always-inline": "inline", "partial-inliner": "inline", "inliner-wrapper": "inline",
    "loop-unroll": "unroll", "loop-unroll-full": "unroll", "loop-unroll-and-jam": "unroll",
    "loop-vectorize": "vector", "slp-vectorizer": "vector", "load-store-vectorizer": "vector",
    "vector-combine": "vector", "licm": "licm", "loop-sink": "licm", "loop-versioning-licm": "licm",
    "loop-rotate": "loopx", "simple-loop-unswitch": "loopx", "loop-idiom": "loopx", "loop-deletion": "loopx",
    "indvars": "loopx", "loop-distribute": "loopx", "loop-interchange": "loopx", "loop-fusion": "loopx",
    "loop-flatten": "loopx", "loop-load-elim": "loopx", "loop-instsimplify": "loopx", "loop-data-prefetch": "loopx",
    "sccp": "const", "ipsccp": "const", "correlated-propagation": "const", "constraint-elimination": "const",
    "float2int": "const", "globalopt": "ipo", "globaldce": "ipo", "deadargelim": "ipo", "constmerge": "ipo",
    "mergefunc": "ipo", "argpromotion": "ipo", "elim-avail-extern": "ipo", "called-value-propagation": "ipo",
    "function-attrs": "attrs", "rpo-function-attrs": "attrs", "inferattrs": "attrs",
    "reassociate": "arith", "nary-reassociate": "arith", "div-rem-pairs": "arith", "speculative-execution": "arith",
    "tailcallelim": "calls", "callsite-splitting": "calls", "libcalls-shrinkwrap": "calls",
    "adce": "dce", "bdce": "dce", "dce": "dce", "hotcoldsplit": "layout",
}
FAMILIES = sorted(set(FAMILY_OF.values())) + ["other"]
KNOB_DEFAULT = {"-inline-threshold": 250, "-unroll-threshold": 300, "-unroll-count": 0, "-force-vector-width": 0,
                "-force-vector-interleave": 0, "-slp-threshold": 0, "-jump-threading-threshold": 6,
                "-vectorizer-min-trip-count": 16, "-unroll-max-count": 0, "-phi-node-folding-threshold": 2,
                "llc:-tail-dup-size": 2, "llc:-tail-dup-indirect-size": 20, "llc:-align-loops": 16,
                "llc:-min-jump-table-entries": 4}
BOOL_KNOBS = ["-unroll-runtime", "-simplifycfg-sink-common", "-simplifycfg-hoist-common", "llc:-enable-tail-merge",
              "llc:-x86-cmov-converter", "llc:-enable-misched"]
LEVELS = ["default<O0>", "default<O1>", "default<O2>", "default<O3>", "default<Os>"]


def _fam(name: str) -> str:
    return FAMILY_OF.get(name, "other")


def encode_genome(g: Genome, names: dict[int, str]) -> dict[str, float]:
    """Fixed-length encoding of an edit genome. `names` maps -O3 leaf id -> pass name."""
    f = {f"{op}_{fam}": 0.0 for op in ("del", "ins", "dup", "flip") for fam in FAMILIES}
    f.update({"swap": 0.0, "del_all": 0.0, "flip_all": 0.0, "n_edits": float(len(g.edits))})
    nm = dict(names)
    for k, d in KNOB_DEFAULT.items():
        f[f"knob{k}"] = float(d)
    for k in BOOL_KNOBS:
        f[f"knob{k}"] = 1.0
    f["llc_level"] = 3.0
    for lv in LEVELS:
        f[f"raw_{lv}"] = 0.0
    if g.raw is not None:
        f[f"raw_{g.raw}"] = 1.0
    for e in g.edits:
        op = e["op"]
        if op == "del":
            f[f"del_{_fam(nm.get(e['id'], ''))}"] += 1
        elif op == "dup":
            n = nm.get(e["id"], "")
            nm[e["nid"]] = n
            f[f"dup_{_fam(n)}"] += 1
        elif op == "ins":
            n = pass_name(e["pass"])
            nm[e["nid"]] = n
            f[f"ins_{_fam(n)}"] += 1
        elif op == "swap":
            f["swap"] += 1
        elif op == "param":
            f[f"flip_{_fam(nm.get(e['id'], ''))}"] += 1
        elif op == "param_all":
            f["flip_all"] += 1
            f[f"flip_{_fam(e['pass'])}"] += 3
        elif op == "del_all":
            f["del_all"] += 1
            f[f"del_{_fam(e['pass'])}"] += 3
        elif op == "knob":
            k, v = e["name"], e["value"]
            if k in BOOL_KNOBS:
                f[f"knob{k}"] = 0.0 if str(v).lower() == "false" else 1.0
            else:
                try:
                    f[f"knob{k}"] = float(v)
                except (TypeError, ValueError):
                    pass
        elif op == "backend":
            f["llc_level"] = float(e["value"])
    return f


def leaf_names(tree: Node) -> dict[int, str]:
    return {n.id: pass_name(n.text) for _p, _i, n in _walk(tree) if n.is_leaf}
