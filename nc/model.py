"""Supervised surrogate (Phase 7).

Rows = (program, candidate) pairs with a timing label: log speedup vs -O3, aggregated over all
measurements of that candidate with weights (confirmed/validated 3, screening with >=3 rounds 1,
1-round screening 0.3). Features = program features (static, simulated dynamic, scan) +
candidate encoding (nc.features.encode_genome).

Evaluation is ONLY by holding out whole families (leave-one-family-out over the development
families). If corpus/split.json exists, test families are excluded from everything here; they
are touched once, by `evaluate`.

Metrics per held-out program, then averaged over programs (and bootstrapped over families):
  spearman   within-program rank correlation between prediction and label
  recall@k   the program's best measured candidate is in the model's top-k
  gain@k     best label among the model's top-k (what a top-k-then-time loop would get offline),
             compared with random-k (expected) and the oracle
Baselines: random ranking; "transfer": score a candidate by the label of the identical genome on
the most similar development program (only possible for genomes shared across programs:
level seeds, single edits, knobs).
"""
from __future__ import annotations

import json
import math
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

from .db import Store
from .features import encode_genome, leaf_names, program_features
from .pipeline import Genome, parse_pipeline

STAGE_W = {"confirm": 3.0, "confirm_min": 3.0, "validate": 3.0, "passkb_confirm": 3.0}


LABEL_CAP = math.log(3.0)      # |log speedup| capped at 3x: compile-time-evaluation artifacts (mandel-text 130x) must not dominate
NOISY_WEIGHT = 0.3             # programs with a noisy ACCEPTED A/A control (>1%) count like 1-round screening data


def noisy_programs(store: Store, max_dev_pct: float = 1.0) -> set[str]:
    acc: dict[str, dict[str, float]] = {}
    for r in store.rows("SELECT program_id, speedup, note FROM measurements WHERE stage IN ('control','control_validate') "
                        "AND speedup IS NOT NULL ORDER BY id"):
        ctx = (json.loads(r["note"]).get("stage", "confirm") if r["note"] else "confirm")
        acc.setdefault(r["program_id"], {})[ctx] = abs(r["speedup"] - 1) * 100
    return {p for p, v in acc.items() if max(v.values()) > max_dev_pct}


def load_rows(store: Store, manifest: dict, tc, fsets=("static", "sim", "sim_l2", "scan"), compiled: bool = False):
    """Returns X (n x d), y, w, program ids, families, genome keys, feature names."""
    pf = program_features(store, fsets)
    noisy = noisy_programs(store)
    tree = parse_pipeline(tc.pipeline_string("O3"))
    names = leaf_names(tree)
    meas = store.rows("""SELECT m.program_id, m.cand_id, m.stage, m.n, m.speedup, c.genome_json, c.status, c.text_size
                         FROM measurements m JOIN candidates c ON c.cand_id = m.cand_id
                         WHERE m.stage IN ('screen','confirm','confirm_min','validate','passkb_confirm')
                           AND m.speedup > 0""")
    agg: dict[tuple, list] = defaultdict(lambda: [0.0, 0.0, None])
    for r in meas:
        pid = r["program_id"]
        if pid not in pf or manifest.get(pid, {}).get("status") != "ok":
            continue
        w = STAGE_W.get(r["stage"], 1.0 if (r["n"] or 0) >= 3 else 0.3)
        key = (pid, r["genome_json"])
        a = agg[key]
        a[0] += w * math.log(r["speedup"])
        a[1] += w
        a[2] = r["genome_json"]
    # identical-to-O3 candidates are free labels (exactly 0)
    for r in store.rows("SELECT program_id, genome_json FROM candidates WHERE same_as_o3=1 AND method != 'baseline'"):
        key = (r["program_id"], r["genome_json"])
        if r["program_id"] in pf and key not in agg and manifest.get(r["program_id"], {}).get("status") == "ok":
            agg[key] = [0.0, 1.0, r["genome_json"]]
    if not agg:
        return None
    # compiled-candidate features: what the edits did to THIS program's code (available at deployment
    # after compiling a candidate, which the top-k loop does anyway)
    base = {r["program_id"]: (r["ir_insts"], r["text_size"]) for r in
            store.rows("SELECT program_id, ir_insts, text_size FROM candidates WHERE cand_id LIKE 'baseline:%'")}
    comp: dict[tuple, tuple] = {}
    for r in store.rows("SELECT program_id, genome_json, ir_insts, text_size FROM candidates WHERE ir_insts > 0"):
        comp.setdefault((r["program_id"], r["genome_json"]), (r["ir_insts"], r["text_size"]))
    pnames = sorted({k for d in pf.values() for k in d})
    rows, y, w, pids, fams, gkeys = [], [], [], [], [], []
    cnames = None
    for (pid, gj), (s, ws, _g) in agg.items():
        enc = encode_genome(Genome.from_json(gj), names)
        if cnames is None:
            cnames = sorted(enc)
        if compiled:
            bi, bt = base.get(pid, (0, 0))
            ci, ct = comp.get((pid, gj), (0, 0))
            enc["cc_log_ir_ratio"] = math.log(ci / bi) if ci and bi else 0.0
            enc["cc_log_text_ratio"] = math.log(ct / bt) if ct and bt else 0.0
            if "cc_log_ir_ratio" not in cnames:
                cnames = sorted(enc)
        p = pf[pid]
        rows.append([p.get(k, np.nan) for k in pnames] + [enc[k] for k in cnames])
        y.append(max(-LABEL_CAP, min(LABEL_CAP, s / ws)))
        w.append(min(ws, 6.0) * (NOISY_WEIGHT if pid in noisy else 1.0))
        pids.append(pid)
        fams.append(manifest[pid]["family"])
        gkeys.append(gj)
    return (np.asarray(rows, float), np.asarray(y), np.asarray(w), np.asarray(pids), np.asarray(fams),
            gkeys, pnames + cnames, len(pnames))


def _grades(y: np.ndarray) -> np.ndarray:
    """Relevance grades for lambdarank from log speedup."""
    t = [math.log(0.98), math.log(1.005), math.log(1.02), math.log(1.05)]
    return np.digitize(y, t).astype(int)


def _fit(kind: str, X, y, w, groups_pid, seed=0):
    import lightgbm as lgb
    common = dict(n_estimators=300, learning_rate=0.05, num_leaves=15, min_child_samples=10, subsample=0.8,
                  subsample_freq=1, colsample_bytree=0.8, reg_lambda=1.0, random_state=seed, verbose=-1)
    if kind == "gbr":
        m = lgb.LGBMRegressor(**common)
        m.fit(X, y, sample_weight=w)
        return m
    if kind == "rank":
        order = np.argsort(groups_pid, kind="stable")
        Xs, ys, gs = X[order], y[order], groups_pid[order]
        _, counts = np.unique(gs, return_counts=True)
        m = lgb.LGBMRanker(objective="lambdarank", **common)
        m.fit(Xs, _grades(ys), group=counts)
        return m
    raise ValueError(kind)


def _program_metrics(pred, y, k_list=(1, 3, 5, 10), rng=None):
    out = {}
    n = len(y)
    if n >= 5 and np.std(y) > 0 and np.std(pred) > 0:
        from scipy.stats import spearmanr
        out["spearman"] = float(spearmanr(pred, y).statistic)
    best = np.max(y)
    order = np.argsort(-pred)
    for k in k_list:
        kk = min(k, n)
        top = order[:kk]
        out[f"recall@{k}"] = float(best in y[top])
        out[f"gain@{k}"] = float(np.max(y[top]))
        # expected best of a random k-subset (exact, via order statistics)
        ys = np.sort(y)
        probs = np.array([math.comb(i, kk - 1) / math.comb(n, kk) if i >= kk - 1 else 0.0 for i in range(n)])
        out[f"rand_gain@{k}"] = float((probs * ys).sum())
    out["oracle"] = float(best)
    out["n_cands"] = n
    return out


def cross_validate(data, kinds=("gbr", "rank", "transfer", "random"), exclude_families=(), seed=0, log=print):
    X, y, w, pids, fams, gkeys, fnames, n_prog_feats = data
    keep = ~np.isin(fams, list(exclude_families))
    X, y, w, pids, fams = X[keep], y[keep], w[keep], pids[keep], fams[keep]
    gkeys = [g for g, k in zip(gkeys, keep) if k]
    ufam = sorted(set(fams))
    log(f"leave-one-family-out over {len(ufam)} families, {len(set(pids))} programs, {len(y)} rows")
    res: dict[str, list[dict]] = {k: [] for k in kinds}
    rng = np.random.default_rng(seed)
    for f in ufam:
        te, tr = fams == f, fams != f
        if len(set(pids[tr])) < 3:
            continue
        preds = {}
        for kind in kinds:
            if kind in ("gbr", "rank"):
                m = _fit(kind, X[tr], y[tr], w[tr], pids[tr], seed)
                preds[kind] = m.predict(X[te])
            elif kind == "random":
                preds[kind] = rng.random(te.sum())
            elif kind == "transfer":
                # nearest development program by standardized program features
                P = X[:, :n_prog_feats]
                mu, sd = np.nanmean(P[tr], 0), np.nanstd(P[tr], 0) + 1e-9
                Z = np.nan_to_num((P - mu) / sd)
                tr_p = sorted(set(pids[tr]))
                centers = {p: Z[pids == p][0] for p in tr_p}
                lab = defaultdict(dict)
                for i in np.where(tr)[0]:
                    lab[pids[i]][gkeys[i]] = y[i]
                pr = np.zeros(te.sum())
                idx = np.where(te)[0]
                for j, i in enumerate(idx):
                    near = sorted(tr_p, key=lambda p: np.linalg.norm(centers[p] - Z[i]))
                    pr[j] = next((lab[p][gkeys[i]] for p in near[:5] if gkeys[i] in lab[p]), 0.0)
                preds[kind] = pr
        for p in sorted(set(pids[te])):
            mk = pids[te] == p
            for kind in kinds:
                if kind == "random":      # expectation over 20 draws, not one realization
                    draws = [_program_metrics(rng.random(mk.sum()), y[te][mk]) for _ in range(20)]
                    r = {k: float(np.mean([d[k] for d in draws if k in d])) for k in draws[0]}
                else:
                    r = _program_metrics(preds[kind][mk], y[te][mk])
                r.update(program=p, family=f)
                res[kind].append(r)
    return res


def summarize_cv(res: dict, k_list=(1, 3, 5, 10), n_boot=2000, seed=0) -> tuple[str, dict]:
    rng = np.random.default_rng(seed)
    lines, summ = [], {}
    hdr = f"{'model':<9s} {'spearman':>14s} " + " ".join(f"{'rec@' + str(k):>7s} {'gain@' + str(k):>8s}" for k in (1, 5))
    lines.append(hdr)
    for kind, rs in res.items():
        if not rs:
            continue
        fams = sorted({r["family"] for r in rs})

        def fam_mean(key, rows):
            per = defaultdict(list)
            for r in rows:
                if key in r:
                    per[r["family"]].append(r[key])
            return {f: float(np.mean(v)) for f, v in per.items()}

        sp = fam_mean("spearman", rs)
        vals = np.array([sp[f] for f in fams if f in sp])
        if len(vals):
            b = vals[rng.integers(0, len(vals), (n_boot, len(vals)))].mean(1)
            ci = (float(np.quantile(b, .025)), float(np.quantile(b, .975)))
        else:
            ci = (float("nan"), float("nan"))
        s = {"spearman": float(vals.mean()) if len(vals) else float("nan"), "spearman_ci": ci}
        for k in k_list:
            s[f"recall@{k}"] = float(np.mean([r[f"recall@{k}"] for r in rs]))
            s[f"gain@{k}"] = float(np.exp(np.mean([r[f"gain@{k}"] for r in rs])))
            s[f"rand_gain@{k}"] = float(np.exp(np.mean([r[f"rand_gain@{k}"] for r in rs])))
        s["oracle"] = float(np.exp(np.mean([r["oracle"] for r in rs])))
        summ[kind] = s
        lines.append(f"{kind:<9s} {s['spearman']:>+6.3f} [{ci[0]:+.2f},{ci[1]:+.2f}] "
                     + " ".join(f"{s[f'recall@{k}']:>7.2f} {s[f'gain@{k}']:>7.3f}x" for k in (1, 5)))
    any_s = next(iter(summ.values()), None)
    if any_s:
        lines.append(f"random-k expected gain: @1 {any_s['rand_gain@1']:.3f}x  @5 {any_s['rand_gain@5']:.3f}x  "
                     f"| oracle (best measured) {any_s['oracle']:.3f}x  (geomeans over held-out programs)")
    g = summ.get("gbr") or summ.get("rank")
    if g:
        better = g["spearman_ci"][0] > 0 and g["gain@5"] > g["rand_gain@5"]
        lines.append("GATE 7B (surrogate ranks unseen families better than random: Spearman CI > 0 and gain@5 > random): "
                     + ("PASS" if better else "NOT MET -> improve features/data, do not start RL"))
        summ["gate_7b"] = bool(better)
    return "\n".join(lines), summ


def train_final(data, out_dir: Path, exclude_families=(), meta_extra: dict | None = None, seed=0) -> Path:
    """Fit gbr + rank on all development rows (never test families) and save with metadata."""
    X, y, w, pids, fams, gkeys, fnames, n_prog = data
    keep = ~np.isin(fams, list(exclude_families))
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d-%H%M%S")
    paths = {}
    for kind in ("gbr", "rank"):
        m = _fit(kind, X[keep], y[keep], w[keep], pids[keep], seed)
        p = out_dir / f"surrogate_{kind}_{ts}.txt"
        m.booster_.save_model(str(p))
        paths[kind] = str(p)
    meta = {"created": ts, "features": fnames, "n_program_features": n_prog, "paths": paths,
            "train_programs": sorted(set(pids[keep])), "train_families": sorted(set(fams[keep])),
            "excluded_families": sorted(exclude_families), "rows": int(keep.sum()), **(meta_extra or {})}
    mp = out_dir / f"surrogate_{ts}.json"
    mp.write_text(json.dumps(meta, indent=1))
    (out_dir / "surrogate_latest.json").write_text(json.dumps(meta, indent=1))
    return mp


class Surrogate:
    """Loaded model: predict(program feature dict, list of genomes) -> scores (higher = faster)."""

    def __init__(self, meta_path: Path, kind: str = "gbr"):
        import lightgbm as lgb
        self.meta = json.loads(Path(meta_path).read_text())
        self.booster = lgb.Booster(model_file=self.meta["paths"][kind])
        self.fnames = self.meta["features"]
        self.np = self.meta["n_program_features"]

    def predict(self, pfeat: dict, genomes: list[Genome], names: dict[int, str]) -> np.ndarray:
        prog = [pfeat.get(k, np.nan) for k in self.fnames[:self.np]]
        cn = self.fnames[self.np:]
        X = np.asarray([prog + [encode_genome(g, names).get(k, 0.0) for k in cn] for g in genomes], float)
        return self.booster.predict(X)
