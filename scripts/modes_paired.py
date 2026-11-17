"""Modes comparison on the 33 frozen test programs (serial re-measurements only):
predict (RL + SL gated), predict_sl, predict_ungated  [results/predict.sqlite, tag predict_test_serial]
vs tune top-8 and ML-only top-1, GA@8, random@8         [results/dataset.sqlite, tag final_serial]
and tune RL + SL                                        [results/dataset.sqlite, tag rl_serial]
Each number is "vs -O3 measured in the same run"; pairs are formed per program across runs.
Also: success criteria for predict (recorded in CLAUDE.md before building) and time per program.
Run: .venv/bin/python scripts/modes_paired.py   (writes results/predict/modes_paired.txt)
"""
import json
import math
import sqlite3
from pathlib import Path

import numpy as np


def load(db, tag):
    d = {}
    for p, m, s, lo, hi, choice, ts, cs in sqlite3.connect(f"file:{db}?mode=ro", uri=True).execute(
            "SELECT program_id, method, speedup, ci_lo, ci_hi, choice, timing_s, compile_s FROM eval_results WHERE tag=?", (tag,)):
        d.setdefault(m, {})[p] = {"s": s or 1.0, "lo": lo, "hi": hi, "choice": choice, "timing_s": ts or 0, "compile_s": cs or 0}
    return d


pr = load("results/predict.sqlite", "predict_test_serial")
fi = load("results/dataset.sqlite", "final_serial")
rl = load("results/dataset.sqlite", "rl_serial")
methods = {"predict (RL+SL, gated)": pr["predict"], "predict_sl (gated)": pr["predict_sl"],
           "predict_ungated": pr["predict_ungated"], "tune top-8 (SL)": fi["topk"], "tune RL + SL": rl["rl_lib_topk"],
           "ML-only top-1": fi["ml_top1"], "GA@8": fi["ga@8"], "random@8": fi["random@8"]}
progs = sorted(set(pr["predict"]) & set(fi["topk"]))
rng = np.random.default_rng(0)
out = [f"Modes on {len(progs)} test programs (serial re-measurements; speedups vs -O3 measured in the same run)", ""]
out.append(f"{'method':<24s} {'geomean (95% CI)':<26s} {'excl. largest':>13s} {'>=5%':>6s} {'slower*':>8s} {'changed':>8s}")
for name, d in methods.items():
    v = np.array([d[p]["s"] for p in progs])
    lv = np.log(v)
    b = lv[rng.integers(0, len(lv), (4000, len(lv)))].mean(1)
    vs = np.sort(v)[::-1]
    slow = sum(1 for p in progs if d[p]["hi"] is not None and d[p]["hi"] < 1.0)
    changed = sum(1 for p in progs if d[p]["choice"] in ("candidate", "level"))
    out.append(f"{name:<24s} {100 * (math.exp(lv.mean()) - 1):+6.2f}% ({100 * (math.exp(np.quantile(b, .025)) - 1):+.2f}.."
               f"{100 * (math.exp(np.quantile(b, .975)) - 1):+.2f})   {100 * (math.exp(np.log(vs[1:]).mean()) - 1):+6.2f}%"
               f" {int((v >= 1.05).sum()):>6d} {slow:>8d} {changed:>8d}")
out.append("* measurably slower: serial 95% CI upper bound < 1.0")
wo = [p for p in progs if pr["predict_ungated"][p]["choice"] == "wrong_output"]
out.append(f"predict picks with WRONG OUTPUT (caught only by the evaluation's output check): {len(wo)} {wo}")
out += ["", "Paired vs predict (RL+SL, gated), per program:"]
base = methods["predict (RL+SL, gated)"]
for name, d in methods.items():
    if name.startswith("predict (RL"):
        continue
    x = np.array([math.log(d[p]["s"]) - math.log(base[p]["s"]) for p in progs])
    b = x[rng.integers(0, len(x), (4000, len(x)))].mean(1)
    out.append(f"  {name:<22s} vs predict: {100 * (math.exp(x.mean()) - 1):+6.2f}% (95% CI {100 * (math.exp(np.quantile(b, .025)) - 1):+.2f}.."
               f"{100 * (math.exp(np.quantile(b, .975)) - 1):+.2f})  better {int((x > 0.01).sum())} / worse {int((x < -0.01).sum())}")
tf = Path("results/predict/time_test.json")
crit_t = None
if tf.exists():
    t = json.loads(tf.read_text())
    crit_t = t["added_median_s"] <= 10
    out += ["", f"Time per program: predict adds median {t['added_median_s']:+.2f} s (max {t['added_max_s']:+.2f} s) over a plain "
                f"-O3 build (median {t['o3_build_median_s']:.2f} s); tune: "
                f"median {np.median([fi['topk'][p]['compile_s'] + fi['topk'][p]['timing_s'] for p in progs]):.0f} s of compiling + "
                f"timing per program in the selection run (plus confirmation in the current version)."]
v = np.array([base[p]["s"] for p in progs])
lv = np.log(v)
b = lv[rng.integers(0, len(lv), (4000, len(lv)))].mean(1)
c1 = math.exp(lv.mean()) >= 1.015 and math.exp(np.quantile(b, .025)) > 1.0
c2 = sum(1 for p in progs if base[p]["hi"] is not None and base[p]["hi"] < 1.0) <= 2
out += ["", "PREDICT SUCCESS CRITERIA (recorded before building):",
        f"  geomean >= +1.5% with CI above 0: {'MET' if c1 else 'NOT MET'}",
        f"  at most 2 programs measurably slower: {'MET' if c2 else 'NOT MET'}",
        f"  added time <= 10 s (median): {'MET' if crit_t else ('NOT MET' if crit_t is False else 'n/a')}",
        "  => " + ("predict ships as a recommended mode" if (c1 and c2 and crit_t) else
                   "predict ships as ADVISORY, -O3 by default (criteria not met)")]
txt = "\n".join(out)
print(txt)
Path("results/predict").mkdir(parents=True, exist_ok=True)
Path("results/predict/modes_paired.txt").write_text(txt + "\n")
