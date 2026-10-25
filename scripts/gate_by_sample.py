"""Validated headroom gate computed per sample (the built-in report pools every searched program).

Samples: ORIGINAL = the first 15 programs (searched 2026-10-22, seed 0, validated afterwards);
FRESH = the 15 programs sampled with --exclude-searched --seed 1 (never searched before; the
decisive, pre-registered sample). A program counts at its validated speedup when the validated
95% CI excludes 1.0, else 1.000. The noisy-control variant drops programs whose A/A control
deviated by more than 1% in their final measurements.
Run:  .venv/bin/python scripts/gate_by_sample.py
"""
import json
import math
import sqlite3

import numpy as np

DB = "results/dataset.sqlite"
FRESH = ("polybench/trisolv ss/Shootout/random ms/Benchmarks/NPB-serial/is ss/Shootout-C++/methcall "
         "ms/Benchmarks/Ptrdist/ft ss/BenchmarkGame/recursive ms/Applications/SIBsim4 ms/Applications/aha "
         "ms/Benchmarks/VersaBench/ecbdes ms/Benchmarks/BitBench/five11 ms/Applications/JM/lencod "
         "ms/Benchmarks/sim polybench/seidel-2d ms/Benchmarks/Trimaran/netbench-url "
         "ms/Benchmarks/MallocBench/cfrac").split()
NOISY = {"polybench/jacobi-1d", "ms/Benchmarks/Ptrdist/ft", "polybench/bicg"}

c = sqlite3.connect(DB)
ORIG = [r[0] for r in c.execute("SELECT DISTINCT program_id FROM runs WHERE method='levels' AND seed=0")]


def validated(pid: str) -> float:
    s = c.execute("SELECT summary_json FROM runs WHERE program_id=? AND method='final'", (pid,)).fetchone()
    if s:
        v = json.loads(s[0]).get("validated")
        return v["speedup"] if v and v["speedup"] and v["ci"][0] > 1 else 1.0
    rows = c.execute("SELECT cand_id, speedup, ci_lo FROM measurements WHERE program_id=? AND stage='validate' "
                     "ORDER BY id DESC", (pid,)).fetchall()
    if not rows:
        return 1.0
    r = next((x for x in rows if not x[0].startswith("minimize:")), rows[0])   # the validated winner
    return r[1] if r[2] > 1 else 1.0


def gate(name: str, pids: list[str]) -> None:
    v = sorted((validated(p) for p in pids), reverse=True)
    n = len(v)
    lv = np.log(v)
    g, gx = math.exp(lv.mean()), math.exp(lv[1:].mean())
    b = np.exp(lv[np.random.default_rng(0).integers(0, n, (4000, n))].mean(1))
    s5 = sum(x >= 1.05 for x in v)
    ok = gx >= 1.05 or s5 / n >= 0.30
    print(f"{name:<34s} n={n:>2d} geomean {100 * (g - 1):+6.2f}% (95% CI {100 * (np.quantile(b, .025) - 1):+.2f}.."
          f"{100 * (np.quantile(b, .975) - 1):+.2f}) excl. largest {100 * (gx - 1):+.2f}% | >=5%: {s5}/{n} "
          f"({100 * s5 / n:.1f}%) | GATE {'PASS' if ok else 'NOT MET'}")


gate("FRESH 15 (decisive)", FRESH)
gate("ORIGINAL 15", ORIG)
gate("ALL 30 pooled", ORIG + FRESH)
gate("ALL 30 without noisy controls", [p for p in ORIG + FRESH if p not in NOISY])
