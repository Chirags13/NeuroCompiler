"""Phase 5 headroom report (out-of-sample: programs never searched before Phase 5).

Per program: the winner's SERIAL re-validated speedup (stage validate_serial) if its 95% CI excludes
1.0, else 1.000 (the fallback keeps -O3). Programs without a winner count as 1.000. Views:
  all                        every Phase 5 program
  no compile-time-eval       drops suspects from results/artifact_check.json
  capped at 2x               outliers capped (robustness of the geomean)
  per family                 one value per family (median of its programs), so TSVC's 33 near-duplicate
                             kernels count once
  train / val / test         by the frozen split (corpus/split.json)
Run: .venv/bin/python scripts/phase5_report.py   (writes results/phase5_report.txt + .json)
"""
import json
import math
import sqlite3
import statistics as st
import time
from pathlib import Path

import numpy as np

db = sqlite3.connect("results/dataset.sqlite")
man = {json.loads(l)["program_id"]: json.loads(l) for l in open("corpus/manifest.jsonl")}
split = json.loads(Path("corpus/split.json").read_text())["program_split"] if Path("corpus/split.json").exists() else {}
art = Path("results/artifact_check.json")
suspects = {r["program"] for r in json.loads(art.read_text())["rows"] if r["suspect_compile_time_eval"]} if art.exists() else set()

vals, meta = {}, {}
for pid, s in db.execute("SELECT program_id, summary_json FROM runs WHERE method='final' AND seed=2"):
    d = json.loads(s)
    v, src = 1.0, "no winner"
    if "winner" in d:
        r = db.execute("SELECT speedup, ci_lo, ci_hi FROM measurements WHERE stage='validate_serial' AND cand_id=? "
                       "ORDER BY id DESC", (d["winner"]["key"],)).fetchone()
        if r:
            v, src = (r[0] if r[1] > 1.0 else 1.0), "serial"
        else:
            pv = d.get("validated") or {}
            v, src = (pv["speedup"] if pv.get("ci") and pv["ci"][0] and pv["ci"][0] > 1 else 1.0), "parallel (no serial yet)"
    vals[pid] = v
    meta[pid] = {"source": src, "family": man[pid]["family"], "split": split.get(pid, "?"),
                 "o3_mismatch": bool(d.get("o3_mismatch")), "suspect": pid in suspects}


def summary(name, xs):
    xs = sorted(xs, reverse=True)
    n = len(xs)
    if n < 2:
        return f"{name:<34s} n={n}"
    lv = np.log(xs)
    b = np.exp(lv[np.random.default_rng(0).integers(0, n, (4000, n))].mean(1))
    g, gx = math.exp(lv.mean()), math.exp(lv[1:].mean())
    s5, s3 = sum(x >= 1.05 for x in xs), sum(x >= 1.03 for x in xs)
    return (f"{name:<34s} n={n:>3d}  geomean {100 * (g - 1):+6.2f}% (95% CI {100 * (np.quantile(b, .025) - 1):+.2f}.."
            f"{100 * (np.quantile(b, .975) - 1):+.2f})  excl. largest {100 * (gx - 1):+6.2f}%  median {100 * (st.median(xs) - 1):+5.2f}%  "
            f">=5%: {s5}/{n} ({100 * s5 / n:.0f}%)  >=3%: {s3}/{n}  no gain: {sum(x == 1.0 for x in xs)}")


lines = [f"Phase 5 headroom report ({time.strftime('%Y-%m-%d %H:%M')}): wider search (evo+evo2, budget 50 each), "
         f"{len(vals)} programs never searched before; speedups vs -O3, serial re-validation.",
         f"sources: {dict((k, sum(1 for m in meta.values() if m['source'] == k)) for k in set(m['source'] for m in meta.values()))}",
         f"compile-time-evaluation suspects: {sorted(suspects) or 'none (or artifact_check.json missing)'}", ""]
allv = list(vals.values())
lines.append(summary("all", allv))
lines.append(summary("no compile-time-eval suspects", [v for p, v in vals.items() if p not in suspects]))
lines.append(summary("capped at 2x", [min(v, 2.0) for v in allv]))
fam = {}
for p, v in vals.items():
    if p not in suspects:
        fam.setdefault(meta[p]["family"], []).append(v)
lines.append(summary("per family (median), no suspects", [st.median(v) for v in fam.values()]))
for sp in ("train", "val", "test"):
    lines.append(summary(f"split={sp}, no suspects", [v for p, v in vals.items() if meta[p]["split"] == sp and p not in suspects]))
lines += ["", "Top 15:"]
for p, v in sorted(vals.items(), key=lambda kv: -kv[1])[:15]:
    lines.append(f"  {p:46s} {v:7.3f}x  {meta[p]['split']:<5s} {meta[p]['source']}"
                 + ("  SUSPECT" if meta[p]["suspect"] else "") + ("  o3_mismatch" if meta[p]["o3_mismatch"] else ""))
txt = "\n".join(lines)
print(txt)
Path("results/phase5_report.txt").write_text(txt + "\n")
Path("results/phase5_report.json").write_text(json.dumps({"values": vals, "meta": meta}, indent=1))
