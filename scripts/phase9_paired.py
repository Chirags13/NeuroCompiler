"""Phase 9 paired comparison: model top-k vs each baseline, program by program (serial re-measurement).
Mean of per-program log-speedup differences with a bootstrap 95% CI; counts of programs better/worse by
more than 1%; regressions (final 95% CI entirely below -O3).
Run: .venv/bin/python scripts/phase9_paired.py [tag]   (default tag final_serial; writes results/phase9_paired.txt)
"""
import math
import sqlite3
import sys
from pathlib import Path

import numpy as np

tag = sys.argv[1] if len(sys.argv) > 1 else "final_serial"
c = sqlite3.connect("results/dataset.sqlite")
d = {}
for p, m, s, lo, hi in c.execute("SELECT program_id, method, speedup, ci_lo, ci_hi FROM eval_results WHERE tag=?", (tag,)):
    d.setdefault(m, {})[p] = (s or 1.0, lo, hi)
progs = sorted(d["topk"])
rng = np.random.default_rng(0)
out = [f"Phase 9 paired comparison, tag {tag}, {len(progs)} test programs"]
for b in ("random_topk", "random@8", "ga@8", "topk_nodyn", "ml_top1", "O2", "Os"):
    if b not in d:
        continue
    x = np.array([math.log(d["topk"][p][0]) - math.log(d[b][p][0]) for p in progs])
    bs = x[rng.integers(0, len(x), (4000, len(x)))].mean(1)
    out.append(f"topk vs {b:<12s} mean {100 * (math.exp(x.mean()) - 1):+6.2f}% (95% CI {100 * (math.exp(np.quantile(bs, .025)) - 1):+.2f}.."
               f"{100 * (math.exp(np.quantile(bs, .975)) - 1):+.2f})  better {int((x > 0.01).sum())} / worse {int((x < -0.01).sum())} by >1%")
out.append("\nRegressions (final 95% CI below -O3):")
for m in sorted(d):
    for p, (s, lo, hi) in sorted(d[m].items()):
        if hi is not None and hi < 1.0:
            out.append(f"  {m:<12s} {p:<42s} {s:.3f} [{lo:.3f},{hi:.3f}]")
out.append("\nModel top-k per program:")
for p in sorted(progs, key=lambda p: -d["topk"][p][0]):
    out.append(f"  {p:<42s} topk {d['topk'][p][0]:.3f}   random_topk {d['random_topk'][p][0]:.3f}   "
               f"random@8 {d['random@8'][p][0]:.3f}   ga@8 {d['ga@8'][p][0]:.3f}")
txt = "\n".join(out)
print(txt)
Path("results/phase9_paired.txt").write_text(txt + "\n")
