"""Compile-time features from LLVM optimization remarks (feature set 'remarks'; predict mode).

One `opt -passes=default<O3>` run with -pass-remarks-output records what -O3 decided for the program:
which loops were vectorized (width, interleave), which were not and why, unrolling (full / partial /
runtime, counts), SLP vectorization, LICM, inlining. No program run is needed. Counts are per program;
rates are normalized by the number of loop-vectorizer decisions. Stored next to (not inside) 'static'.
"""
from __future__ import annotations

import json
import re
import subprocess
import tempfile
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .db import Store
from .features import FEATURE_VERSION, SCHEMA
from .timing import helper_cpus
from .toolchain import Toolchain

FILTER = "loop-vectorize|loop-unroll|slp-vectorizer|licm|inline"
VEC_REASONS = {
    "CantReorderFPOps": "fp_order", "CantReorderMemOps": "mem_order", "CantVectorizeLibcall": "libcall",
    "CantVectorizeCall": "call", "CantComputeNumberOfIterations": "unknown_tripcount",
    "UnsafeDep": "unsafe_dep", "UnsafeMemDep": "unsafe_dep", "UnknownLoopCountComplexCFG": "complex_cfg",
    "NoCFGForSelect": "complex_cfg", "CFGNotUnderstood": "complex_cfg", "NotBeneficial": "not_beneficial",
    "VectorizationNotBeneficial": "not_beneficial", "InterleavingNotBeneficial": "interleave_not_beneficial",
    "NonReductionValueUsedOutsideLoop": "outside_use", "CantIdentifyArrayBounds": "array_bounds",
    "CantVectorizeInstructionReturnType": "type", "CantVectorizeStoreToLoopInvariantAddress": "invariant_store",
}


def parse(text: str) -> list[dict]:
    """Minimal parser for LLVM's YAML remark stream: kind, pass, name, and scalar Args."""
    out = []
    for doc in re.split(r"^--- ", text, flags=re.M):
        if not doc.strip():
            continue
        lines = doc.splitlines()
        r = {"kind": lines[0].strip().lstrip("!"), "args": {}}
        for ln in lines[1:]:
            m = re.match(r"^(Pass|Name|Function):\s+(.*)$", ln)
            if m:
                r[m.group(1).lower()] = m.group(2).strip().strip("'")
                continue
            m = re.match(r"^\s+-\s+(\w+):\s+'?([^']*)'?\s*$", ln)
            if m and m.group(1) not in ("String", "DebugLoc"):
                r["args"][m.group(1)] = m.group(2)
        out.append(r)
    return out


def _num(x, default=0.0):
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def summarize(rems: list[dict]) -> dict[str, float]:
    f: Counter = Counter()
    widths, ilv, ucount = [], [], []
    for r in rems:
        p, n, k = r.get("pass", ""), r.get("name", ""), r["kind"]
        if p == "loop-vectorize":
            if n == "Vectorized":
                f["vec_vectorized"] += 1
                widths.append(_num(r["args"].get("VectorizationFactor"), 1))
                ilv.append(_num(r["args"].get("InterleaveCount"), 1))
            elif n == "Interleaved":
                f["vec_interleaved_only"] += 1
            elif k.startswith("Missed"):
                f["vec_missed"] += 1
            elif k.startswith("Analysis"):
                f["vec_reason_" + VEC_REASONS.get(n, "other")] += 1
        elif p == "loop-unroll":
            if n == "FullyUnrolled":
                f["unroll_full"] += 1
            elif n == "PartialUnrolled":
                f["unroll_partial"] += 1
                ucount.append(_num(r["args"].get("UnrollCount"), 0))
            elif "Runtime" in n:
                f["unroll_runtime"] += 1
            elif k.startswith("Missed"):
                f["unroll_missed"] += 1
        elif p == "slp-vectorizer":
            f["slp_vectorized" if k == "Passed" else "slp_missed"] += 1
        elif p == "licm":
            if n == "Hoisted":
                f["licm_hoisted"] += 1
            elif n.startswith("Promote"):
                f["licm_promoted"] += 1
            elif k == "Missed":
                f["licm_missed"] += 1
        elif p == "inline":
            if k == "Passed":
                f["inline_inlined"] += 1
            elif n == "NoDefinition":
                f["inline_nodef"] += 1
            elif n == "NeverInline":
                f["inline_never"] += 1
            elif k == "Missed":
                f["inline_too_costly"] += 1
    out = {f"rm_{k}": float(v) for k, v in f.items()}
    for key in ["vec_vectorized", "vec_missed", "vec_interleaved_only", "unroll_full", "unroll_partial",
                "unroll_runtime", "unroll_missed", "slp_vectorized", "slp_missed", "licm_hoisted", "licm_promoted",
                "licm_missed", "inline_inlined", "inline_nodef", "inline_never", "inline_too_costly"] + \
            ["vec_reason_" + v for v in sorted(set(VEC_REASONS.values()) | {"other"})]:
        out.setdefault(f"rm_{key}", 0.0)
    dec = out["rm_vec_vectorized"] + out["rm_vec_missed"]
    out["rm_vec_frac"] = out["rm_vec_vectorized"] / dec if dec else 0.0
    out["rm_vec_width_mean"] = sum(widths) / len(widths) if widths else 0.0
    out["rm_vec_width_max"] = max(widths) if widths else 0.0
    out["rm_vec_interleave_mean"] = sum(ilv) / len(ilv) if ilv else 0.0
    out["rm_unroll_count_mean"] = sum(ucount) / len(ucount) if ucount else 0.0
    out["rm_total"] = float(len(rems))
    return out


def extract_one(tc: Toolchain, src, cflags: tuple[str, ...], cpu: int | None = None) -> dict[str, float]:
    ir = tc.start_ir(src, cflags)
    with tempfile.TemporaryDirectory(dir=tc.work / "tmp") as d:
        y = Path(d) / "remarks.yaml"
        cmd = [tc.tool("opt"), "-passes=default<O3>", f"-pass-remarks-output={y}", f"-pass-remarks-filter={FILTER}",
               "-disable-output", str(ir)]
        if cpu is not None:
            cmd = ["taskset", "-c", str(cpu)] + cmd
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
        if r.returncode != 0:
            raise RuntimeError(f"opt remarks failed: {r.stderr[-300:]}")
        return summarize(parse(y.read_text() if y.exists() else ""))


def extract_all(tc: Toolchain, cfg, store: Store, recs: list[dict], force: bool = False, log=print) -> None:
    """Compile-only, in parallel on the helper CPUs; stores feature set 'remarks'."""
    store.con.executescript(SCHEMA)
    have = {r["program_id"] for r in store.rows("SELECT program_id FROM features WHERE fset='remarks' AND version=?",
                                                (FEATURE_VERSION,))}
    todo = [r for r in recs if force or r["program_id"] not in have]
    cpus = helper_cpus(cfg.timing_cpu)
    for r in todo:                                    # start IR once per program before threads race
        tc.start_ir(r["src"], tuple(r.get("cflags") or []))
    log(f"remarks: {len(todo)} programs on {len(cpus)} helper CPUs")

    def job(ir):
        i, rec = ir
        return rec["program_id"], extract_one(tc, rec["src"], tuple(rec.get("cflags") or []), cpus[i % len(cpus)])

    with ThreadPoolExecutor(len(cpus)) as ex:
        for fut in [ex.submit(job, x) for x in enumerate(todo)]:
            try:
                pid, feats = fut.result()
                store.con.execute("INSERT OR REPLACE INTO features VALUES(?,?,?,?,?)",
                                  (pid, "remarks", FEATURE_VERSION, json.dumps(feats), time.strftime("%Y-%m-%dT%H:%M:%S")))
                store.con.commit()
            except Exception as e:
                log(f"remarks failed: {e!r}"[:300])
