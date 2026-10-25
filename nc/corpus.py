"""Program corpus: fetch suites, scan candidates through quality filters, freeze a split.

Funnel (each stage is recorded, so the three counts stay separate):
    candidates found  ->  builds + runs ok  ->  output deterministic and identical across
    -O0..-O3/-Os  ->  runtime inside [floor, ceiling] on THIS machine  ->  usable program

Correctness oracle: the -O0 build's output hash. PolyBench prints nothing normally, so its
arrays are dumped by running the SAME binary with argv[0]="" and 42 extra args (PolyBench's own
runtime switch); stdout and stderr are hashed together.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from .config import Config
from .timing import EMPTY_OUTPUT_HASH, RunSpec, helper_cpus, measure_interleaved, run_spec, summarize
from .toolchain import Toolchain

POLYBENCH_URL = "https://github.com/MatthiasJReisinger/PolyBenchC-4.2.1.git"
LLVM_TS_URL = "https://github.com/llvm/llvm-test-suite.git"
POLYBENCH_DATASETS = ["SMALL_DATASET", "MEDIUM_DATASET", "LARGE_DATASET", "EXTRALARGE_DATASET"]
# Old test-suite programs use K&R C; modern clang rejects these by default. Demote to warnings.
LEGACY_C_FLAGS = ["-Wno-error=implicit-int", "-Wno-error=implicit-function-declaration",
                  "-Wno-error=int-conversion", "-Wno-error=incompatible-pointer-types"]
MAX_RSS_MB = 3072   # reject programs that need more memory than this (WSL2 has ~11 GB shared with Windows)
LEVELS = [("O0", "default<O0>", 0), ("O1", "default<O1>", 1), ("O2", "default<O2>", 2),
          ("O3", "default<O3>", 3), ("Os", "default<Os>", 2)]


@dataclass
class Candidate:
    program_id: str
    suite: str
    family: str
    src: str
    variants: list[list[str]]              # cflags alternatives, ordered small -> large input
    time_spec: RunSpec = field(default_factory=RunSpec)
    verify_spec: RunSpec = field(default_factory=RunSpec)
    loc: int = 0
    common: list[str] = field(default_factory=list)      # flags shared by every variant
    presets: dict = field(default_factory=dict)          # dataset name -> {dim: value} (PolyBench)
    run_variants: list[RunSpec] = field(default_factory=list)  # per-variant run spec (time == verify)
    labels: list[str] = field(default_factory=list)            # per-variant dataset label


SUITES = ["polybench", "singlesource", "multisource"]


# ---------------------------------------------------------------- fetch
def _run(cmd, cwd=None, timeout=900):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd)}\n{r.stderr[-1500:]}")
    return r.stdout


def fetch(root: Path, which: list[str]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    if "polybench" in which:
        d = root / "polybench"
        if d.exists():
            print(f"polybench: already present at {d}")
        else:
            print("polybench: cloning ...")
            _run(["git", "clone", "--depth", "1", POLYBENCH_URL, str(d)])
    if "singlesource" in which:
        d = root / "llvm-test-suite"
        if (d / "SingleSource" / "Benchmarks").exists():
            print(f"singlesource: already present at {d}")
        else:
            print("singlesource: sparse clone of llvm-test-suite (SingleSource/Benchmarks only) ...")
            _run(["git", "clone", "--depth", "1", "--filter=blob:none", "--sparse", LLVM_TS_URL, str(d)])
            _run(["git", "sparse-checkout", "set", "SingleSource/Benchmarks"], cwd=str(d))
    if "multisource" in which:
        d = root / "llvm-test-suite"
        if (d / "MultiSource" / "Benchmarks").exists():
            print(f"multisource: already present at {d}")
        else:
            if not d.exists():
                _run(["git", "clone", "--depth", "1", "--filter=blob:none", "--sparse", LLVM_TS_URL, str(d)])
                _run(["git", "sparse-checkout", "set", "SingleSource/Benchmarks"], cwd=str(d))
            print("multisource: adding MultiSource/Benchmarks and MultiSource/Applications ...")
            _run(["git", "sparse-checkout", "add", "MultiSource/Benchmarks", "MultiSource/Applications"], cwd=str(d))


# ---------------------------------------------------------------- adapters
def _loc(p: Path) -> int:
    try:
        return sum(1 for _ in p.open(errors="ignore"))
    except OSError:
        return 0


def polybench_candidates(root: Path, gen_dir: Path) -> list[Candidate]:
    base = (root / "polybench").resolve()
    lst = base / "utilities" / "benchmark_list"
    if not lst.exists():
        raise FileNotFoundError(f"{lst} missing. Run: python -m nc.cli corpus fetch")
    gen_dir.mkdir(parents=True, exist_ok=True)
    out = []
    for line in lst.read_text().split():
        rel = Path(line)
        kernel = (base / rel).resolve()
        name = kernel.stem
        parts = [x for x in rel.parts[:-2] if x != "."]
        family = "polybench/" + "/".join(parts)
        wrapper = (gen_dir / f"{name}.c").resolve()
        wrapper.write_text(f'#include "{base / "utilities" / "polybench.c"}"\n#include "{kernel}"\n')
        common = [f"-I{base / 'utilities'}", f"-I{kernel.parent}"]
        header = kernel.with_suffix(".h")
        presets = parse_polybench_presets(header) if header.exists() else {}
        presets = {k: presets[k] for k in POLYBENCH_DATASETS if k in presets}
        out.append(Candidate(
            program_id=f"polybench/{name}", suite="polybench", family=family, src=str(wrapper),
            common=common, presets=presets,
            variants=[common + [f"-D{ds}"] for ds in POLYBENCH_DATASETS],
            time_spec=RunSpec(),
            verify_spec=RunSpec(args=["x"] * 42, argv0="", merge_stderr=True),
            loc=_loc(kernel)))
    return out


# `n = argc > 1 ? atoi(argv[1]) : 100` and close variants: programs whose size comes from argv[1]
_ARGN = re.compile(r"argc\s*(?:==\s*2|>\s*1|>=\s*2)\s*\)?\s*\?\s*(?:atoi|atol|strtol)\s*\(\s*argv\s*\[\s*1\s*\][^:]*:\s*\(?\s*(\d+)")


def _arg_sizes(default: int) -> list[int]:
    """Candidate argv[1] values, small -> large: +1 steps (exponential programs such as
    ackermann), then doublings (linear/polynomial ones). The scan keeps the first in range."""
    xs = sorted({default + k for k in range(0, 7)} | {default * 2 ** j for j in range(1, 13)})
    return [x for x in xs if x > 0]


def singlesource_candidates(root: Path) -> list[Candidate]:
    base = (root / "llvm-test-suite" / "SingleSource" / "Benchmarks").resolve()
    if not base.exists():
        raise FileNotFoundError(f"{base} missing. Run: python -m nc.cli corpus fetch")
    out = []
    for p in sorted([*base.rglob("*.c"), *base.rglob("*.cpp"), *base.rglob("*.cc")]):
        rel = p.relative_to(base)
        if rel.parts[0] == "Polybench":          # duplicates the PolyBench suite
            continue
        flags = list(LEGACY_C_FLAGS) if p.suffix == ".c" else []
        c = Candidate(
            program_id="ss/" + str(rel.with_suffix("")), suite="singlesource",
            family=f"ss/{rel.parts[0]}" if len(rel.parts) > 1 else "ss/root",   # top-level dir: related programs stay together
            src=str(p), variants=[flags], loc=_loc(p))
        m = _ARGN.search(p.read_text(errors="ignore"))
        if m:
            ns = _arg_sizes(int(m.group(1)))
            c.variants = [flags] * len(ns)
            c.run_variants = [RunSpec(args=[str(n)]) for n in ns]
            c.labels = [f"argv {n}" for n in ns]
        out.append(c)
    return out


def _run_dir(gen: Path, pid: str, data: list[list[str]]) -> Path:
    """Per-program working directory: input files symlinked at the relative paths the
    program expects, plus an Output/ dir (some programs write there)."""
    d = (gen / "run" / pid.replace("/", "__")).resolve()
    (d / "Output").mkdir(parents=True, exist_ok=True)
    for rel, src in data:
        dst = d / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if not dst.exists() and Path(src).exists():
            os.symlink(src, dst)
    return d


def multisource_candidates(root: Path, gen_dir: Path) -> list[Candidate]:
    from .msource import find_programs
    base = (root / "llvm-test-suite" / "MultiSource").resolve()
    if not base.exists():
        raise FileNotFoundError(f"{base} missing. Run: python -m nc.cli corpus fetch --suite multisource")
    out = []
    for prog in find_programs(base):
        rel = prog.dir.relative_to(base)
        pid = "ms/" + str(rel)
        # Benchmarks/<suite>/... share a family; each Application is its own family
        family = f"ms/{rel.parts[1]}" if rel.parts[0] == "Benchmarks" and len(rel.parts) > 2 else f"ms/{'/'.join(rel.parts[:2])}"
        if prog.unsupported or not prog.variants:
            out.append(Candidate(pid, "multisource", family, "", [], loc=0,
                                 labels=[f"UNSUPPORTED {prog.unsupported or 'no variants'}"]))
            continue
        variants, specs, labels = [], [], []
        for v in prog.variants:
            missing = [r for r, a in v.data if not Path(a).exists()]
            if missing:
                continue
            rd = _run_dir(gen_dir, pid, v.data)
            stdin = str((rd / v.stdin).resolve()) if v.stdin else None
            if stdin and not Path(stdin).exists():
                continue
            variants.append(list(LEGACY_C_FLAGS) + v.cflags)
            specs.append(RunSpec(args=v.args, stdin_path=stdin, cwd=str(rd)))
            labels.append(v.size)
        srcs = prog.variants[-1].sources
        if not variants:
            out.append(Candidate(pid, "multisource", family, "", [], labels=["UNSUPPORTED missing input data"]))
            continue
        out.append(Candidate(pid, "multisource", family, srcs if len(srcs) > 1 else srcs[0], variants,
                             loc=sum(_loc(Path(x)) for x in srcs), run_variants=specs, labels=labels))
    return out


def gather(root: Path, suites: list[str]) -> list[Candidate]:
    out: list[Candidate] = []
    if "polybench" in suites:
        out += polybench_candidates(root, root.parent / "generated" / "polybench")
    if "singlesource" in suites:
        out += singlesource_candidates(root)
    if "multisource" in suites:
        out += multisource_candidates(root, root.parent / "generated")
    return out


def parse_polybench_presets(header: Path) -> dict[str, dict[str, int]]:
    """Read '#ifdef X_DATASET / #define DIM n' blocks from a PolyBench kernel header."""
    out: dict[str, dict[str, int]] = {}
    cur = None
    for ln in header.read_text(errors="ignore").splitlines():
        m = re.match(r"\s*#\s*ifdef\s+(\w+_DATASET)\b", ln)
        if m:
            cur = m.group(1)
            out[cur] = {}
            continue
        if cur and re.match(r"\s*#\s*endif", ln):
            cur = None
            continue
        m = re.match(r"\s*#\s*define\s+([A-Z_0-9]+)\s+(\d+)\s*$", ln)
        if cur and m:
            out[cur][m.group(1)] = int(m.group(2))
    return {k: v for k, v in out.items() if v}


def _dims_flags(dims: dict[str, int], s: float) -> list[str]:
    return [f"-D{k}={max(1, int(round(v * s)))}" for k, v in dims.items()]


def _scale_search(tc: Toolchain, cfg: Config, c: Candidate, hist: list[tuple[int, float]],
                  floor_s: float, ceiling_s: float, max_iter: int = 6):
    """PolyBench presets jump in size by large factors. Find a continuous scale factor of one
    preset's dimensions that lands the -O3 runtime inside [floor, ceiling]."""
    names = list(c.presets)
    times = dict(hist)
    fast = [i for i, t in hist if t < floor_s]
    base_i = max(fast) if fast else 0
    base = c.presets[names[base_i]]
    target = 1.0
    pts: list[tuple[float, float]] = [(1.0, times[base_i])]
    s = (target / times[base_i]) ** 0.5
    for _ in range(max_iter):
        s = min(max(s, 0.05), 32.0)
        flags = c.common + _dims_flags(base, s)
        b = tc.build(c.src, "default<O3>", 3, tuple(flags))
        if not b.ok:
            return None
        smp = run_spec(b.bin_path, c.time_spec, cfg.timing_cpu, cfg.timeout_s)
        if smp.status != "ok":
            return None
        t = smp.wall_ms / 1000
        pts.append((s, t))
        if floor_s * 1.1 <= t <= ceiling_s * 0.6:
            return flags, b, t, f"scaled x{s:.2f} of {names[base_i]}"
        (s1, t1), (s2, t2) = pts[-2], pts[-1]
        ls = math.log(s2 / s1) if s1 > 0 and s2 > 0 else 0.0
        k = math.log(t2 / t1) / ls if abs(ls) > 1e-6 and t1 > 0 and t2 > 0 else 2.0
        k = min(max(k, 0.8), 4.0)
        s = s2 * (target / t2) ** (1.0 / k)
    return None


# ---------------------------------------------------------------- scan
def _reject(rec: dict, reason: str, detail: str = "") -> dict:
    rec["status"], rec["reject_reason"], rec["detail"] = "rejected", reason, detail[:300]
    return rec


def scan_one(tc: Toolchain, cfg: Config, c: Candidate, floor_s: float, ceiling_s: float,
             reps: int, start: int = 0) -> dict:
    cpu, to = cfg.timing_cpu, cfg.timeout_s
    rec = {"program_id": c.program_id, "suite": c.suite, "family": c.family, "src": c.src,
           "loc": c.loc, "time_spec": c.time_spec.__dict__, "verify_spec": c.verify_spec.__dict__,
           "llvm": tc.version(), "machine_id": cfg.machine_id, "floor_s": floor_s,
           "ceiling_s": ceiling_s, "scanned_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
           "status": "ok", "reject_reason": "", "detail": ""}
    if not c.variants:
        return _reject(rec, "unsupported", (c.labels or [""])[0])

    # stage 1: choose the input size by O3 runtime (presets first, then continuous scaling)
    chosen, o3b, t_o3, label = None, None, 0.0, "fixed"
    hist: list[tuple[int, float]] = []
    for i, cf in enumerate(c.variants):
        if i < start:
            continue
        if c.run_variants:
            c.time_spec = c.verify_spec = c.run_variants[i]
            rec["time_spec"] = rec["verify_spec"] = c.time_spec.__dict__
        b = tc.build(c.src, "default<O3>", 3, tuple(cf))
        if not b.ok:
            return _reject(rec, "build_fail", f"{b.status}: {b.error}")
        s = run_spec(b.bin_path, c.time_spec, cpu, to)
        if s.status != "ok":
            return _reject(rec, f"run_{s.status}", f"variant {c.labels[i] if c.labels else cf}")
        t = s.wall_ms / 1000
        hist.append((i, t))
        chosen, o3b, t_o3 = cf, b, t
        label = c.labels[i] if c.labels else next((f[2:] for f in cf if f.endswith("_DATASET")), "fixed")
        if t >= floor_s:
            break
    if not (floor_s <= t_o3 <= ceiling_s) and c.presets:
        found = _scale_search(tc, cfg, c, hist, floor_s, ceiling_s)
        if found:
            chosen, o3b, t_o3, label = found
    if t_o3 < floor_s:
        return _reject(rec, "too_fast", f"{t_o3 * 1000:.0f} ms at largest input tried")
    if t_o3 > ceiling_s:
        return _reject(rec, "too_slow", f"{t_o3:.1f} s at smallest sufficient input")
    rec["cflags"] = chosen
    rec["dataset"] = label

    # stage 2: all five levels build, output deterministic and identical to the -O0 reference
    builds = {"O3": o3b}
    for name, pipe, bo in LEVELS:
        if name == "O3":
            continue
        b = tc.build(c.src, pipe, bo, tuple(chosen))
        if not b.ok:
            return _reject(rec, "build_fail", f"{name}: {b.status}: {b.error}")
        builds[name] = b
    ref = run_spec(builds["O0"].bin_path, c.verify_spec, cpu, to)
    if ref.status != "ok":
        return _reject(rec, f"run_{ref.status}", "O0 reference")
    if ref.out_hash == EMPTY_OUTPUT_HASH:
        return _reject(rec, "no_output", "empty output cannot serve as a correctness oracle")
    rec["ref_output_hash"] = ref.out_hash
    again = run_spec(builds["O0"].bin_path, c.verify_spec, cpu, to)
    if again.out_hash != ref.out_hash:
        return _reject(rec, "nondeterministic", "O0 output differs between two runs")
    for name, b in builds.items():
        v = run_spec(b.bin_path, c.verify_spec, cpu, to)
        if v.status != "ok" or v.out_hash != ref.out_hash:
            return _reject(rec, "output_mismatch", f"{name}: {v.status}; possible UB or miscompile")

    # stage 3: level timings (O0 once; others interleaved)
    o3run = run_spec(builds["O3"].bin_path, c.time_spec, cpu, to)
    rec["o3_maxrss_mb"] = round(o3run.maxrss_kb / 1024, 1)
    if rec["o3_maxrss_mb"] > MAX_RSS_MB:
        return _reject(rec, "too_big", f"{rec['o3_maxrss_mb']:.0f} MB resident (limit {MAX_RSS_MB})")
    o0 = run_spec(builds["O0"].bin_path, c.time_spec, cpu, to)
    ser = measure_interleaved({k: builds[k].bin_path for k in ("O1", "O2", "O3", "Os")},
                              c.time_spec.args, reps, 1, cpu, to,
                              stdin_path=c.time_spec.stdin_path, cwd=c.time_spec.cwd)
    med = {k: summarize(v.wall_ms).get("median_ms") for k, v in ser.items()}
    if any(m is None for m in med.values()):
        return _reject(rec, "timing_failed", str({k: v.status for k, v in ser.items()}))
    times = {"O0": o0.wall_ms, **med}
    rec["times_ms"] = {k: round(v, 2) for k, v in times.items()}
    rec["o0_over_o3"] = round(times["O0"] / times["O3"], 3)
    rec["level_spread"] = round(max(med.values()) / min(med.values()), 3)
    rec["o3_text_bytes"] = builds["O3"].text_size
    rec["o3_ir_insts"] = builds["O3"].ir_inst_count
    rec["distinct_level_binaries"] = len({b.bin_hash for b in builds.values()})
    return rec


# ---------------------------------------------------------------- prescan (fast, parallel, untimed)
def prescan_one(tc: Toolchain, cfg: Config, c: Candidate, floor_s: float, cpu: int) -> dict:
    """Cheap filter before the pinned scan: builds, O0 oracle, O3 output match and a ROUGH
    unpinned O3 runtime per variant (small -> large). Only rejects what load cannot fake:
    build/run failures, empty or mismatching output, and programs that are fast even when
    measured under load (rough time < floor/2 at the largest variant). Returns the variant
    index the real scan should start from."""
    out = {"program_id": c.program_id, "reject": "", "detail": "", "start": 0, "rough_s": None}
    if not c.variants:
        out.update(reject="unsupported", detail=(c.labels or [""])[0])
        return out
    for i, cf in enumerate(c.variants):
        ts = c.run_variants[i] if c.run_variants else c.time_spec
        vs = c.run_variants[i] if c.run_variants else c.verify_spec
        o3 = tc.build(c.src, "default<O3>", 3, tuple(cf))
        o0 = tc.build(c.src, "default<O0>", 0, tuple(cf))
        if not (o3.ok and o0.ok):
            b = o3 if not o3.ok else o0
            out.update(reject="build_fail", detail=f"{b.status}: {b.error[:200]}")
            return out
        r0 = run_spec(o0.bin_path, vs, cpu, cfg.timeout_s)
        r3 = run_spec(o3.bin_path, vs, cpu, cfg.timeout_s)
        if r0.status != "ok" or r3.status != "ok":
            if r0.status == "timeout" and i > 0:       # bigger input than needed; earlier variant was the last usable
                break
            out.update(reject=f"run_{r0.status if r0.status != 'ok' else r3.status}",
                       detail=c.labels[i] if c.labels else "")
            return out
        if r0.out_hash == EMPTY_OUTPUT_HASH:
            out.update(reject="no_output", detail="empty output cannot serve as a correctness oracle")
            return out
        if r3.out_hash != r0.out_hash:
            out.update(reject="output_mismatch", detail="O3 vs O0 (prescan)")
            return out
        t = run_spec(o3.bin_path, ts, cpu, cfg.timeout_s).wall_ms / 1000 if ts is not vs else r3.wall_ms / 1000
        out["start"], out["rough_s"] = i, round(t, 3)
        if t >= floor_s * 0.8:
            return out
    if (out["rough_s"] or 0) < floor_s * 0.5 and not c.presets:
        out.update(reject="too_fast", detail=f"rough {out['rough_s']}s under load at largest input (prescan)")
    return out


def prescan(tc: Toolchain, cfg: Config, cands: list[Candidate], floor_s: float, path: Path,
            workers: int = 0, log=print) -> dict[str, dict]:
    """Run prescan_one on helper CPUs in parallel (NEVER while a timing job runs)."""
    done = load_manifest(path)
    todo = [c for c in cands if c.program_id not in done]
    cpus = helper_cpus(cfg.timing_cpu)
    workers = workers or max(1, len(cpus) - 1)
    log(f"prescan: {len(todo)} candidates on CPUs {cpus} with {workers} workers")

    def job(ic):
        i, c = ic
        try:
            return prescan_one(tc, cfg, c, floor_s, cpus[i % len(cpus)])
        except Exception as e:
            return {"program_id": c.program_id, "reject": "harness_error", "detail": repr(e)[:200], "start": 0}

    with ThreadPoolExecutor(workers) as ex:
        for k, r in enumerate(ex.map(job, enumerate(todo)), 1):
            done[r["program_id"]] = r
            save_manifest(path, done)
            log(f"[{k:>3d}/{len(todo)}] {r['program_id']:<50s} {r['reject'] or 'ok'} {r.get('rough_s') or ''}")
    return done


# ---------------------------------------------------------------- manifest / split / report
def load_manifest(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    return {r["program_id"]: r for r in (json.loads(x) for x in path.read_text().splitlines() if x.strip())}


def save_manifest(path: Path, recs: dict[str, dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text("\n".join(json.dumps(r) for r in recs.values()) + "\n")
    tmp.replace(path)


def make_split(manifest: dict[str, dict], out: Path, seed: int = 0, test_frac: float = 0.22,
               val_frac: float = 0.15, force: bool = False) -> dict:
    if out.exists() and not force:
        raise FileExistsError(f"{out} exists and is FROZEN. Re-splitting after seeing results "
                              "invalidates the test set. Use --force only on purpose.")
    ok = [r for r in manifest.values() if r["status"] == "ok"]
    if len(ok) < 10:
        raise ValueError(f"Only {len(ok)} usable programs; scan more before splitting.")
    groups: dict[str, list[str]] = {}
    for r in ok:
        groups.setdefault(r["family"], []).append(r["program_id"])
    order = sorted(groups, key=lambda g: hashlib.sha256(f"{seed}:{g}".encode()).hexdigest())
    n = len(ok)
    split_of: dict[str, str] = {}
    counts = {"test": 0, "val": 0, "train": 0}
    # A family joins test/val only if it fits in the remaining budget (whole families, hash order);
    # otherwise it falls through. One huge family (TSVC: 33 programs, more than the whole test budget)
    # can therefore never become the entire test set.
    for g in order:
        size = len(groups[g])
        if counts["test"] + size <= math.ceil(test_frac * n):
            tag = "test"
        elif counts["val"] + size <= math.ceil(val_frac * n):
            tag = "val"
        else:
            tag = "train"
        for pid in groups[g]:
            split_of[pid] = tag
        counts[tag] += len(groups[g])
    payload = {"seed": seed, "test_frac": test_frac, "val_frac": val_frac, "n_programs": n,
               "counts": counts, "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
               "groups": {t: sorted(g for g in groups if split_of[groups[g][0]] == t)
                          for t in ("train", "val", "test")},
               "program_split": split_of,
               "note": "Split by family (whole groups, a family enters test/val only if it fits the remaining budget), frozen before any model tuning."}
    out.write_text(json.dumps(payload, indent=2))
    return payload


def report(manifest: dict[str, dict]) -> str:
    recs = list(manifest.values())
    ok = [r for r in recs if r["status"] == "ok"]
    lines = [f"Candidates scanned: {len(recs)}   usable: {len(ok)}", "", "Rejection reasons:"]
    reasons: dict[str, int] = {}
    for r in recs:
        if r["status"] != "ok":
            reasons[r["reject_reason"]] = reasons.get(r["reject_reason"], 0) + 1
    for k, v in sorted(reasons.items(), key=lambda kv: -kv[1]):
        lines.append(f"  {k:20s} {v}")
    lines += ["", "Usable programs per family:"]
    fam: dict[str, int] = {}
    for r in ok:
        fam[r["family"]] = fam.get(r["family"], 0) + 1
    for k, v in sorted(fam.items()):
        lines.append(f"  {k:40s} {v}")
    if ok:
        sp = sorted(r["level_spread"] for r in ok)
        lines += ["", f"Level spread (slowest/fastest of O1,O2,O3,Os) median {sp[len(sp) // 2]:.3f}, "
                      f"max {sp[-1]:.3f}",
                  f"Programs whose levels differ by >=3%: {sum(1 for s in sp if s >= 1.03)} of {len(sp)}"]
    return "\n".join(lines)
