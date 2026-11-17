"""Export everything the dashboard's Research page shows into dashboard/static/data/research.json.

Reads result files and the databases READ-ONLY; every number on the page comes from here, and every block
names its source. Re-run after new results:   .venv/bin/python scripts/export_dashboard_data.py [--quick]
(--quick skips refitting the predict model for the train-vs-held-out comparison.)
"""
import csv
import glob
import json
import math
import sqlite3
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
OUT = Path("dashboard/static/data/research.json")
RNG = np.random.default_rng(0)


def ro(db):
    return sqlite3.connect(f"file:{db}?mode=ro", uri=True)


def jload(p):
    return json.loads(Path(p).read_text())


def geo(v):
    v = np.asarray(v, float)
    return float(math.exp(np.log(v).mean())) if len(v) else float("nan")


def boot(v):
    lv = np.log(np.asarray(v, float))
    b = lv[RNG.integers(0, len(lv), (4000, len(lv)))].mean(1)
    return [float(math.exp(np.quantile(b, .025))), float(math.exp(np.quantile(b, .975)))]


def summ(vals, his=None):
    v = sorted(vals, reverse=True)
    return {"n": len(v), "geomean": geo(v), "ci": boot(v) if len(v) > 2 else None,
            "excl_largest": geo(v[1:]) if len(v) > 1 else None, "median": float(np.median(v)),
            "ge5": int(sum(x >= 1.05 for x in v)), "ge3": int(sum(x >= 1.03 for x in v)),
            "no_gain": int(sum(x == 1.0 for x in v)),
            "slower": int(sum(1 for h in (his or []) if h is not None and h < 1.0))}


D = {"generated": time.strftime("%Y-%m-%d %H:%M"), "sources": {}}
man = [json.loads(l) for l in open("corpus/manifest.jsonl")]
ok = [r for r in man if r["status"] == "ok"]
split = jload("corpus/split.json")
psplit = split["program_split"]

# ---------------- corpus
rej = Counter(r["reject_reason"] for r in man if r["status"] != "ok")
D["corpus"] = {
    "scanned": len(man), "usable": len(ok), "families": len({r["family"] for r in ok}),
    "rejections": rej.most_common(),
    "by_suite": {s: sum(1 for r in ok if r["suite"] == s) for s in ("polybench", "singlesource", "multisource")},
    "family_sizes": Counter(r["family"] for r in ok).most_common(),
    "programs": [{"id": r["program_id"], "suite": r["suite"], "family": r["family"], "o3_ms": r["times_ms"]["O3"],
                  "loc": r.get("loc"), "level_spread": r.get("level_spread"), "split": psplit.get(r["program_id"]),
                  "o0_over_o3": r.get("o0_over_o3")} for r in ok],
    "split": {"counts": split["counts"], "groups": split["groups"], "seed": split["seed"]},
    "level_beats_o3": sum(1 for r in ok if min(r["times_ms"][k] for k in ("O1", "O2", "Os")) <= r["times_ms"]["O3"] / 1.03),
    "levels_differ_3pct": sum(1 for r in ok if r["level_spread"] >= 1.03),
}
D["sources"]["corpus"] = "corpus/manifest.jsonl, corpus/split.json"

# ---------------- harness
def selftest(p):
    j = jload(p)
    return {"file": Path(p).name, "verdict": j["verdict"], "median_ms": j["repeatability"]["summary"].get("median_ms"),
            "ci_halfwidth_pct": j["repeatability"]["summary"].get("ci_halfwidth_pct"),
            "drift_pct": j["repeatability"].get("drift_pct"), "aa": j["aa"]["paired"].get("speedup"),
            "o0_vs_o3": j["sensitivity"]["paired"].get("speedup"), "fidelity_gap_pct": (j.get("fidelity") or {}).get("gap_pct")}


v8 = [p for p in sorted(glob.glob("results/selftest_wsl2-ryzen9-270_*.json"))]
v14 = [p for p in sorted(glob.glob("results/selftest_wsl2-ryzen9-270-v14_*.json"))]
aat = []
for p in sorted(glob.glob("results/aatest_*.json")):
    j = jload(p)
    rows = defaultdict(lambda: defaultdict(list))
    for r in j["rows"]:
        rows[r["program"]][r["mode"]].append(r)
    progs = []
    for prog, mm in rows.items():
        e = {"program": prog}
        for mode, rs in mm.items():
            e[mode] = {"aa_bias_pct": max(abs((x["aa"].get("speedup") or 1) - 1) * 100 for x in rs),
                       "iqr_pct": float(np.median([x["aa_iqr_pct"] for x in rs])),
                       "base_ms": float(np.median([x["base_median_ms"] for x in rs])),
                       "winner": float(np.median([x["win"]["speedup"] for x in rs if x.get("win", {}).get("speedup")]))
                       if any(x.get("win", {}).get("speedup") for x in rs) else None}
        progs.append(e)
    aat.append({"file": Path(p).name, "cores": j["timing_cpus"], "pass": j["pass"], "programs": progs})
D["harness"] = {"selftest_v8": [selftest(p) for p in v8[-1:]], "selftest_v14": [selftest(p) for p in v14],
                "aatests": aat, "layout": jload(sorted(glob.glob("results/layout_test_*.json"))[-1])}
D["sources"]["harness"] = "results/selftest_*.json, results/aatest_*.json, results/layout_test_*.json"

# ---------------- phase 3 gate
c = ro("results/dataset.sqlite")
FRESH = ("polybench/trisolv ss/Shootout/random ms/Benchmarks/NPB-serial/is ss/Shootout-C++/methcall "
         "ms/Benchmarks/Ptrdist/ft ss/BenchmarkGame/recursive ms/Applications/SIBsim4 ms/Applications/aha "
         "ms/Benchmarks/VersaBench/ecbdes ms/Benchmarks/BitBench/five11 ms/Applications/JM/lencod "
         "ms/Benchmarks/sim polybench/seidel-2d ms/Benchmarks/Trimaran/netbench-url "
         "ms/Benchmarks/MallocBench/cfrac").split()
ORIG = [r[0] for r in c.execute("SELECT DISTINCT program_id FROM runs WHERE method='levels' AND seed=0")]


def validated(pid):
    s = c.execute("SELECT summary_json FROM runs WHERE program_id=? AND method='final' AND seed=1", (pid,)).fetchone()
    if s:
        v = json.loads(s[0]).get("validated")
        return v["speedup"] if v and v["speedup"] and v["ci"][0] > 1 else 1.0
    rows = c.execute("SELECT cand_id, speedup, ci_lo FROM measurements WHERE program_id=? AND stage='validate' ORDER BY id DESC",
                     (pid,)).fetchall()
    if not rows:
        return 1.0
    r = next((x for x in rows if not x[0].startswith("minimize:")), rows[0])
    return r[1] if r[2] > 1 else 1.0


D["gate3"] = {"fresh": [{"id": p, "speedup": validated(p)} for p in FRESH],
              "original": [{"id": p, "speedup": validated(p)} for p in ORIG],
              "text": Path("results/gate_by_sample_20261023.txt").read_text()}
D["gate3"]["fresh_summary"] = summ([x["speedup"] for x in D["gate3"]["fresh"]])
D["gate3"]["original_summary"] = summ([x["speedup"] for x in D["gate3"]["original"]])
D["sources"]["gate3"] = "scripts/gate_by_sample.py -> results/gate_by_sample_20261023.txt"

# ---------------- phase 5
p5 = jload("results/phase5_report.json")
art = jload("results/artifact_check.json")
D["phase5"] = {"values": [{"id": k, "speedup": v, **p5["meta"][k]} for k, v in p5["values"].items()],
               "report": Path("results/phase5_report.txt").read_text(), "artifact": art["rows"], "rule": art["rule"]}
D["phase5"]["summary_all"] = summ([v for k, v in p5["values"].items() if not p5["meta"][k]["suspect"]])
fam = defaultdict(list)
for k, v in p5["values"].items():
    if not p5["meta"][k]["suspect"]:
        fam[p5["meta"][k]["family"]].append(v)
D["phase5"]["summary_family"] = summ([float(np.median(v)) for v in fam.values()])
D["sources"]["phase5"] = "scripts/phase5_report.py -> results/phase5_report.json; scripts/artifact_check.py"

# ---------------- knowledge base
att = sorted(glob.glob("results/passkb_attribution_*.csv"))[-1]
kb = []
with open(att) as f:
    for r in csv.DictReader(f):
        kb.append({"label": r["label"], "kind": r["kind"], "programs": int(r["programs"]), "noop": int(r["noop"]),
                   "faster": int(r["conf_faster"]), "slower": int(r["conf_slower"]), "big": int(r["screen_big"]),
                   "min": float(r["screen_min"]) if r["screen_min"] else None,
                   "max": float(r["screen_max"]) if r["screen_max"] else None})
kb.sort(key=lambda t: (-t["faster"], -(t["faster"] + t["slower"])))
D["kb"] = {"top": kb[:20], "edits": len(kb), "by_kind": Counter(t["kind"] for t in kb),
           "programs": len(jload("results/passkb_actions.json")["programs"])}
D["sources"]["kb"] = att

# ---------------- models
D["models"] = {"tune_cv": jload("results/models/cv_latest.json"),
               "tune_cv_nodyn": jload("results/models/cv_static-scan_latest.json"),
               "predict_cv": jload("results/models/predict/cv.json"),
               "rl_tune_history": jload("results/models/rl_policy_latest.json").get("history"),
               "rl_predict_history": jload("results/models/predict/rl_policy.json").get("history"),
               "rl_tune_actions": len(jload("results/models/rl_policy_latest.json")["actions"]),
               "predict_pool": jload("results/models/predict/MANIFEST.json")["pool"],
               "predict_thresholds": jload("results/models/predict/MANIFEST.json")["thresholds"]}
fs = defaultdict(int)
for r in c.execute("SELECT fset, json FROM features WHERE program_id=(SELECT program_id FROM features LIMIT 1)"):
    fs[r[0]] = len(json.loads(r[1]))
rm = ro("results/predict.sqlite").execute("SELECT json FROM features WHERE fset='remarks' LIMIT 1").fetchone()
fs["remarks"] = len(json.loads(rm[0])) if rm else 0
D["models"]["feature_sets"] = dict(fs)
if "--quick" not in sys.argv:
    from scipy.stats import spearmanr
    from nc.config import load_config
    from nc.corpus import load_manifest
    from nc.db import Store
    from nc.toolchain import Toolchain
    from nc import predict as P
    cfg = load_config("config.toml")
    X, y, h, w, pids, fams, gk, fn, npf = P.load_training(Store(cfg.db_path), P.pstore(),
                                                          load_manifest(Path("corpus/manifest.jsonl")), Toolchain(cfg))
    tr = ~np.isin(fams, list(set(split["groups"]["test"]) | set(split["groups"]["val"])))
    va = np.isin(fams, list(split["groups"]["val"]))
    ens = P.Ensemble(fnames=fn, n_prog=npf).fit(X[tr], y[tr], h[tr], w[tr])

    def within(mk):
        p = np.stack([b.predict(X[mk]) for b in ens.members]).mean(0)
        rs = []
        for q in set(pids[mk]):
            s = pids[mk] == q
            if s.sum() >= 5 and np.std(y[mk][s]) > 0:
                rs.append(spearmanr(p[s], y[mk][s]).statistic)
        return float(np.mean(rs)), len(rs)
    D["models"]["predict_train_vs_heldout"] = {"train": within(tr), "heldout": within(va)}
D["sources"]["models"] = "results/models/cv_*.json, results/models/predict/cv.json, rl_policy*.json"

# ---------------- evaluation
def evalrows(db, tag):
    d = defaultdict(dict)
    for p, m, s, lo, hi, ch, ts, cs, nc_, nt in ro(db).execute(
            "SELECT program_id, method, speedup, ci_lo, ci_hi, choice, timing_s, compile_s, n_compiled, n_timed "
            "FROM eval_results WHERE tag=?", (tag,)):
        d[m][p] = {"s": s or 1.0, "lo": lo, "hi": hi, "choice": ch, "time_s": (ts or 0) + (cs or 0), "n_compiled": nc_, "n_timed": nt}
    return d


fi, rl_, pr = evalrows("results/dataset.sqlite", "final_serial"), evalrows("results/dataset.sqlite", "rl_serial"), \
    evalrows("results/predict.sqlite", "predict_test_serial")
methods = {"-O2": fi["O2"], "-Os": fi["Os"], "tune top-8 (SL)": fi["topk"], "tune RL + SL": rl_["rl_lib_topk"],
           "RL only": rl_["rl_topk"], "no dynamic features": fi["topk_nodyn"], "ML-only top-1": fi["ml_top1"],
           "random top-8": fi["random_topk"], "random search@8": fi["random@8"], "GA@8": fi["ga@8"],
           "predict (gated)": pr["predict"], "predict ungated": pr["predict_ungated"]}
progs = sorted(fi["topk"])
D["eval"] = {"programs": [{"id": p, "family": next(r["family"] for r in ok if r["program_id"] == p),
                           **{m: d[p]["s"] for m, d in methods.items() if p in d}} for p in progs],
             "summary": {m: summ([d[p]["s"] for p in progs if p in d], [d[p]["hi"] for p in progs if p in d])
                         for m, d in methods.items()}}
base = methods["tune top-8 (SL)"]
paired = {}
for m, d in methods.items():
    if m == "tune top-8 (SL)":
        continue
    x = np.array([math.log(base[p]["s"]) - math.log(d[p]["s"]) for p in progs if p in d])
    b = x[RNG.integers(0, len(x), (4000, len(x)))].mean(1)
    paired[m] = {"mean": float(math.exp(x.mean())), "ci": [float(math.exp(np.quantile(b, .025))), float(math.exp(np.quantile(b, .975)))],
                 "better": int((x > 0.01).sum()), "worse": int((x < -0.01).sum())}
D["eval"]["paired_vs_tune_top8"] = paired
size = [{"id": p, "method": m, "size": None, "speedup": d[p]["s"]} for m, d in (("tune top-8 (SL)", fi["topk"]),) for p in progs]
srows = ro("results/dataset.sqlite").execute("SELECT program_id, method, text_ratio, speedup FROM eval_results WHERE tag='final_serial' "
                                             "AND method IN ('topk','O2','Os','ga@8')").fetchall()
D["eval"]["size_scatter"] = [{"id": r[0], "method": r[1], "size": r[2], "speedup": r[3]} for r in srows]
D["eval"]["predict_time"] = jload("results/predict/time_test.json")
D["eval"]["modes_text"] = Path("results/predict/modes_paired.txt").read_text()
D["sources"]["eval"] = "eval_results tags final_serial, rl_serial (dataset.sqlite) and predict_test_serial (predict.sqlite)"

# ---------------- IR count vs runtime
base_ir = {r[0]: r[1] for r in c.execute("SELECT program_id, ir_insts FROM candidates WHERE cand_id LIKE 'baseline:%'")}
pts = []
for pid, ir, sp in c.execute("""SELECT c.program_id, c.ir_insts, m.speedup FROM measurements m JOIN candidates c ON c.cand_id=m.cand_id
                                WHERE m.stage IN ('screen','confirm','validate') AND m.speedup > 0 AND c.ir_insts > 0"""):
    if base_ir.get(pid):
        pts.append((math.log(ir / base_ir[pid]), math.log(sp)))
pts = np.array(pts)
from scipy.stats import spearmanr  # noqa: E402
sel = RNG.choice(len(pts), min(2500, len(pts)), replace=False)
D["ir"] = {"n": len(pts), "rho": float(spearmanr(pts[:, 0], pts[:, 1]).statistic),
           "sample": [[round(float(math.exp(a)), 4), round(float(math.exp(b)), 4)] for a, b in pts[sel]],
           "fewer_ir_faster_pct": float((pts[pts[:, 0] < -0.01][:, 1] > 0).mean() * 100)}

# ---------------- headline + timeline
D["headline"] = {"tune_rlsl": D["eval"]["summary"]["tune RL + SL"], "tune_top8": D["eval"]["summary"]["tune top-8 (SL)"],
                 "predict": D["eval"]["summary"]["predict (gated)"], "phase5": D["phase5"]["summary_all"]}
D["timeline"] = [
    {"date": "2026-10-18", "phase": "1", "title": "Measurement harness passes selftest", "detail": "A/A bias 0.30%, CI 0.41% at 400 ms (8 vCPUs)."},
    {"date": "2026-10-22", "phase": "2", "title": "Corpus: PolyBench + SingleSource", "detail": "56 usable programs, 11 families."},
    {"date": "2026-10-22", "phase": "3", "title": "evalloop root cause", "detail": "SimplifyCFG sink-common-insts merges 31 dispatch jumps; fix found by action space v2."},
    {"date": "2026-10-23", "phase": "2", "title": "Corpus expanded with MultiSource + C++", "detail": "146 usable programs, 35 families."},
    {"date": "2026-10-23", "phase": "3", "title": "Headroom gate NOT MET", "detail": "Fresh 15: +4.0% geomean, 4/15 >= +5%. Re-scoped to the 'good' tier.", "kind": "fail"},
    {"date": "2026-10-23", "phase": "1", "title": "14 vCPUs; 3 parallel timing cores", "detail": "Selftest CI 0.12%; 5 cores rejected by the multi-core A/A test."},
    {"date": "2026-10-24", "phase": "5", "title": "Wider search: large out-of-sample headroom", "detail": "+15.6% geomean, 54/115 programs >= +5% (serial)."},
    {"date": "2026-10-24", "phase": "7", "title": "Gate 7B (surrogate vs random)", "detail": "NOT MET before Phase 4 data; narrowly met after."},
    {"date": "2026-10-25", "phase": "9", "title": "Test set: tune top-8 +7.5%", "detail": "Beats random top-8 (+5.8%) and GA (+5.3%) at equal budget.", "kind": "ok"},
    {"date": "2026-10-25", "phase": "8", "title": "RL (PPO) evaluated", "detail": "RL only -4.2% vs top-8; RL + SL +0.2% (n.s.). Final version RL + SL (user choice)."},
    {"date": "2026-10-26", "phase": "+", "title": "Predict mode: advisory", "detail": "+0.64% (CI includes 0), +0.6 s; criteria not met -> -O3 by default.", "kind": "fail"},
]
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(D, default=lambda o: o.tolist() if hasattr(o, "tolist") else str(o)))
print(f"wrote {OUT} ({OUT.stat().st_size / 1024:.0f} KB)")
