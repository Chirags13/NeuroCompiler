"""Predict mode: an instant pipeline choice WITHOUT running the program (compile + analysis only).

RL + SL with its own models, fully separate from tune (results/models/predict/, own MANIFEST.json; never
reads results/models/tune or tune's surrogate/policy). Shared data is read-only: results/dataset.sqlite
(measured labels, knowledge base, 'static' features). Predict's own data and measurements live in
results/predict.sqlite (feature set 'remarks', evaluation tags predict_val / predict_test).

  features   'static' (IR counts) + 'remarks' (LLVM optimization remarks) + the pipeline encoding.
             No scan or cachegrind features: those need program runs.
  ensemble   N LightGBM regressors (different seeds, subsampling) on log speedup vs -O3 + a classifier for
             the 'harmful' label (measurably slower than -O3). Per candidate: mean, pessimistic estimate
             (mean - 1.28 std), share of members above 1 + margin, harm probability.
  pool       knowledge-base single edits that never appeared in a wrong-output candidate and are harmful on
             <= 10% of the programs they change, plus pairs of the best of them; plus RL proposals.
  RL         own PPO policy whose reward is the ensemble's PESSIMISTIC estimate, actions = safe edits only,
             horizon 3 (nc/rl.py code reused; separate policy file).
  decision   best pessimistic candidate; ship only if pessimistic > 1 + margin, >= 80% of members agree and
             harm probability <= tau; otherwise -O3. Thresholds come from out-of-fold predictions on
             train+val families only (recorded in CLAUDE.md before building).
Correctness: predict never runs the program, so the shipped binary is UNVERIFIED unless --verify is used.
"""
from __future__ import annotations

import hashlib
import json
import math
import random
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

from .db import Store
from .features import FEATURE_VERSION, encode_genome, leaf_names, program_features
from .model import LABEL_CAP, NOISY_WEIGHT, STAGE_W, noisy_programs
from .pipeline import Genome, materialize, parse_pipeline

PDIR = Path("results/models/predict")
PDB = Path("results/predict.sqlite")
N_MEMBERS = 7
AGREE = 0.8
PESS_Z = 1.28
HARM_SCREEN, HARM_ROUNDS = 0.97, 3
POOL_HARM_MAX, POOL_MIN_PROGRAMS, PAIR_TOP = 0.10, 3, 40
LGB = dict(n_estimators=300, learning_rate=0.05, num_leaves=15, min_child_samples=20, subsample=0.7,
           subsample_freq=1, colsample_bytree=0.7, reg_lambda=1.0, verbose=-1)


def _norm(e: dict) -> str:
    return json.dumps({k: v for k, v in e.items() if k != "nid"}, sort_keys=True)


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def pstore() -> Store:
    return Store(PDB)


# ---------------------------------------------------------------- features
def predict_features(main: Store, ps_: Store) -> dict[str, dict[str, float]]:
    """'static' from the shared DB (read-only) + 'remarks' from predict's own DB."""
    st = program_features(main, ("static",))
    rm = program_features(ps_, ("remarks",))
    return {p: {**st[p], **rm[p]} for p in st if p in rm}


# ---------------------------------------------------------------- training data
def load_training(main: Store, ps_: Store, manifest: dict, tc):
    """Rows = (program, genome) with aggregated log-speedup label, harmful label and weight."""
    pf = predict_features(main, ps_)
    noisy = noisy_programs(main)
    names = leaf_names(parse_pipeline(tc.pipeline_string("O3")))
    agg: dict[tuple, list] = defaultdict(lambda: [0.0, 0.0, 0])
    for r in main.rows("""SELECT m.program_id, m.stage, m.n, m.speedup, m.ci_hi, c.genome_json
                          FROM measurements m JOIN candidates c ON c.cand_id = m.cand_id
                          WHERE m.stage IN ('screen','confirm','confirm_min','validate','validate_serial','passkb_confirm')
                            AND m.speedup > 0"""):
        pid = r["program_id"]
        if pid not in pf or manifest.get(pid, {}).get("status") != "ok":
            continue
        w = STAGE_W.get(r["stage"], 3.0 if r["stage"] == "validate_serial" else (1.0 if (r["n"] or 0) >= 3 else 0.3))
        a = agg[(pid, r["genome_json"])]
        a[0] += w * math.log(r["speedup"])
        a[1] += w
        if (r["stage"] != "screen" and r["ci_hi"] is not None and r["ci_hi"] < 1.0) or \
                (r["stage"] == "screen" and (r["n"] or 0) >= HARM_ROUNDS and r["speedup"] < HARM_SCREEN):
            a[2] = 1
    for r in main.rows("SELECT program_id, genome_json, status FROM candidates WHERE method != 'baseline' "
                       "AND (same_as_o3=1 OR status='slow')"):
        key = (r["program_id"], r["genome_json"])
        if r["program_id"] in pf and manifest.get(r["program_id"], {}).get("status") == "ok" and key not in agg:
            agg[key] = [0.0 if r["status"] != "slow" else math.log(1 / 1.3), 1.0, int(r["status"] == "slow")]
    pnames = sorted({k for d in pf.values() for k in d})
    cnames = sorted(encode_genome(Genome([]), names))
    X, y, h, w, pids, fams, gk = [], [], [], [], [], [], []
    for (pid, gj), (s, ws, harm) in agg.items():
        enc = encode_genome(Genome.from_json(gj), names)
        X.append([pf[pid].get(k, np.nan) for k in pnames] + [enc[k] for k in cnames])
        y.append(max(-LABEL_CAP, min(LABEL_CAP, s / ws)))
        h.append(harm)
        w.append(min(ws, 6.0) * (NOISY_WEIGHT if pid in noisy else 1.0))
        pids.append(pid)
        fams.append(manifest[pid]["family"])
        gk.append(gj)
    return (np.asarray(X, float), np.asarray(y), np.asarray(h), np.asarray(w), np.asarray(pids), np.asarray(fams),
            gk, pnames + cnames, len(pnames))


# ---------------------------------------------------------------- ensemble
class Ensemble:
    def __init__(self, members=None, harm=None, fnames=None, n_prog=0):
        self.members, self.harm, self.fnames, self.np = members or [], harm, fnames or [], n_prog

    def fit(self, X, y, h, w, seed0: int = 0):
        import lightgbm as lgb
        self.members = []
        for s in range(N_MEMBERS):
            m = lgb.LGBMRegressor(random_state=seed0 + s, **LGB)
            m.fit(X, y, sample_weight=w)
            self.members.append(m.booster_)
        if h.sum() >= 5:
            c = lgb.LGBMClassifier(random_state=seed0 + 100, is_unbalance=True, **LGB)
            c.fit(X, h, sample_weight=w)
            self.harm = c.booster_
        return self

    def stats(self, X, margin: float) -> dict[str, np.ndarray]:
        P = np.stack([m.predict(X) for m in self.members])          # members x n (log speedup)
        mean, std = P.mean(0), P.std(0)
        lm = math.log(1 + margin)
        return {"mean": mean, "std": std, "pess": mean - PESS_Z * std, "agree": (P > lm).mean(0),
                "lo": P.min(0), "hi": P.max(0),
                "p_harm": self.harm.predict(X) if self.harm is not None else np.zeros(X.shape[0])}

    def save(self, d: Path, tag: str = "") -> dict[str, str]:
        d.mkdir(parents=True, exist_ok=True)
        paths = {}
        for i, b in enumerate(self.members):
            p = d / f"ensemble{tag}_m{i}.txt"
            b.save_model(str(p))
            paths[f"m{i}"] = str(p)
        if self.harm is not None:
            p = d / f"ensemble{tag}_harm.txt"
            self.harm.save_model(str(p))
            paths["harm"] = str(p)
        meta = d / f"ensemble{tag}.json"
        meta.write_text(json.dumps({"features": self.fnames, "n_program_features": self.np, "paths": paths}, indent=1))
        paths["meta"] = str(meta)
        return paths

    @staticmethod
    def load(meta: Path) -> "Ensemble":
        import lightgbm as lgb
        d = json.loads(meta.read_text())
        mem = [lgb.Booster(model_file=d["paths"][f"m{i}"]) for i in range(N_MEMBERS)]
        harm = lgb.Booster(model_file=d["paths"]["harm"]) if "harm" in d["paths"] else None
        return Ensemble(mem, harm, d["features"], d["n_program_features"])

    def matrix(self, pfeat: dict, genomes: list[Genome], names: dict[int, str]) -> np.ndarray:
        prog = [pfeat.get(k, np.nan) for k in self.fnames[:self.np]]
        cn = self.fnames[self.np:]
        return np.asarray([prog + [encode_genome(g, names).get(k, 0.0) for k in cn] for g in genomes], float)


class PessimisticScorer:
    """Adapter so nc/rl.py's PassEnv/PPO can use the ensemble: predict() returns the pessimistic estimate."""

    def __init__(self, ens: Ensemble, margin: float):
        self.ens, self.margin = ens, margin
        self.fnames, self.np = ens.fnames, ens.np

    def predict(self, pfeat, genomes, names):
        return self.ens.stats(self.ens.matrix(pfeat, genomes, names), self.margin)["pess"]


# ---------------------------------------------------------------- safe pool
def safe_pool(main: Store, out: Path | None = None) -> tuple[list[Genome], dict]:
    wrong = set()
    for r in main.rows("SELECT genome_json FROM candidates WHERE status='wrong_output'"):
        for e in json.loads(r["genome_json"])["edits"]:
            wrong.add(_norm(e))
    scr = {r["cand_id"]: (r["n"], r["speedup"]) for r in
           main.rows("SELECT cand_id, n, speedup FROM measurements WHERE stage='screen' AND cand_id LIKE 'passkb:%'")}
    by: dict[str, list] = defaultdict(list)
    for r in main.rows("SELECT label, edit_json, status, noop, screen_sp, ci_hi, cand_id FROM pass_effects"):
        by[r["label"]].append(r)
    singles = []
    for label, rs in by.items():
        edit = json.loads(rs[0]["edit_json"])
        ch = [r for r in rs if not r["noop"] and r["status"] in ("ok", "slow")]
        if len(ch) < POOL_MIN_PROGRAMS or _norm(edit) in wrong:
            continue
        harm, gains = 0, []
        for r in ch:
            n, s = scr.get("passkb:" + r["cand_id"], (0, None))
            if r["status"] == "slow" or (r["ci_hi"] is not None and r["ci_hi"] < 1.0) or \
                    ((n or 0) >= HARM_ROUNDS and s is not None and s < HARM_SCREEN):
                harm += 1
            if r["screen_sp"]:
                gains.append(math.log(r["screen_sp"]))
        if harm / len(ch) <= POOL_HARM_MAX:
            singles.append((label, edit, float(np.mean(gains)) if gains else 0.0, harm / len(ch), len(ch)))
    singles.sort(key=lambda t: -t[2])
    pool = [Genome([s[1]]) for s in singles]
    top = singles[:PAIR_TOP]
    for i in range(len(top)):
        for j in range(i + 1, len(top)):
            a, b = top[i][1], top[j][1]
            if a.get("op") == "knob" and b.get("op") == "knob" and a.get("name") == b.get("name"):
                continue                                          # same knob twice: second would override
            pool.append(Genome([a, b]))
    info = {"singles": len(singles), "pairs": len(pool) - len(singles), "wrong_output_edits_excluded": len(wrong),
            "rule": f"never in a wrong-output candidate; harmful on <= {POOL_HARM_MAX:.0%} of >= {POOL_MIN_PROGRAMS} "
                    f"programs it changes; pairs of the top {PAIR_TOP} by mean screening gain",
            "single_edits": [{"label": s[0], "edit": s[1], "mean_log_gain": round(s[2], 4), "harm_rate": round(s[3], 3),
                              "programs": s[4]} for s in singles]}
    if out:
        out.write_text(json.dumps({"info": info, "pool": [g.to_json() for g in pool]}, indent=1))
    return pool, info


def load_pool(path: Path) -> list[Genome]:
    return [Genome.from_json(g) for g in json.loads(path.read_text())["pool"]]


# ---------------------------------------------------------------- decision
def decide(ens: Ensemble, pfeat: dict, cands: list[Genome], sources: list[str], names: dict[int, str],
           margin: float, tau: float, gated: bool = True) -> dict:
    s = ens.stats(ens.matrix(pfeat, cands, names), margin)
    i = int(np.argmax(s["pess"]))
    lm = math.log(1 + margin)
    ok_pess, ok_agree, ok_harm = s["pess"][i] > lm, s["agree"][i] >= AGREE, s["p_harm"][i] <= tau
    ship = (ok_pess and ok_agree and ok_harm) or not gated
    res = {"genome": cands[i].to_json(), "source": sources[i], "predicted_speedup": round(math.exp(s["mean"][i]), 4),
           "range": [round(math.exp(s["pess"][i]), 4), round(math.exp(s["hi"][i]), 4)],
           "member_agreement": round(float(s["agree"][i]), 2), "p_harmful": round(float(s["p_harm"][i]), 3),
           "ship": bool(ship)}
    top = []
    for j in np.argsort(-s["pess"])[:10]:
        top.append({"edits": cands[j].edits, "source": sources[j], "predicted_speedup": round(math.exp(s["mean"][j]), 4),
                    "range": [round(math.exp(s["pess"][j]), 4), round(math.exp(s["hi"][j]), 4)],
                    "agreement": round(float(s["agree"][j]), 2), "p_harmful": round(float(s["p_harm"][j]), 3),
                    "checks": {"pessimistic": bool(s["pess"][j] > lm), "agreement": bool(s["agree"][j] >= AGREE),
                               "harm": bool(s["p_harm"][j] <= tau)}})
    res["top"] = top
    res["gate"] = {"margin": margin, "tau": tau, "agree": AGREE}
    if ship and gated:
        res["confidence"] = "high" if s["pess"][i] > 2 * lm and s["agree"][i] >= 0.95 else "medium"
        res["reason"] = (f"pessimistic estimate {math.exp(s['pess'][i]):.3f}x > {1 + margin:.3f}, "
                         f"{s['agree'][i]:.0%} of models agree, harm probability {s['p_harm'][i]:.2f}")
    elif ship:
        res["confidence"] = "ungated"
        res["reason"] = "ungated: best pessimistic candidate shipped without checks"
    else:
        why = [w for w, ok in (("pessimistic estimate too low", ok_pess), ("models disagree", ok_agree),
                               ("harm probability too high", ok_harm)) if not ok]
        res["confidence"] = "low"
        res["reason"] = "kept -O3: " + ", ".join(why)
    return res


# ---------------------------------------------------------------- out-of-fold threshold choice
MARGINS = [0.005, 0.01, 0.02, 0.03, 0.05]
TAUS = [0.2, 0.3, 0.5, 1.01]


def oof_thresholds(data, pool: list[Genome], log=print, exclude_families=()) -> dict:
    """Leave-one-family-out over train+val. Evaluated on held-out programs' LABELLED pool candidates (the
    candidate set predict can actually choose from); a decision realizes that candidate's measured label, or
    0 (-O3) if gated out. Objective: max mean log gain s.t. OOF regression rate <= 2/33."""
    X, y, h, w, pids, fams, gk, fnames, npf = data
    keep = ~np.isin(fams, list(exclude_families))
    X, y, h, w, pids, fams = X[keep], y[keep], h[keep], w[keep], pids[keep], fams[keep]
    gk = [g for g, k in zip(gk, keep) if k]
    pool_keys = {g.to_json() for g in pool}
    inpool = np.array([g in pool_keys for g in gk])
    ufam = sorted(set(fams))
    oof = []                                                     # (program, family, stats of its pool candidates)
    for f in ufam:
        te, tr = fams == f, fams != f
        if not (te & inpool).any():
            continue
        ens = Ensemble(fnames=fnames, n_prog=npf).fit(X[tr], y[tr], h[tr], w[tr])
        for p in sorted(set(pids[te & inpool])):
            mk = (pids == p) & inpool
            P = np.stack([m.predict(X[mk]) for m in ens.members])
            ph = ens.harm.predict(X[mk]) if ens.harm is not None else np.zeros(mk.sum())
            oof.append((p, f, P, ph, y[mk], h[mk]))
        log(f"  oof family {f}: {sum(1 for o in oof if o[1] == f)} programs with labelled pool candidates")
    grid = []
    for mg in MARGINS:
        lm = math.log(1 + mg)
        for tau in TAUS:
            gains, regress, shipped = [], 0, 0
            for p, f, P, ph, yy, hh in oof:
                mean, std = P.mean(0), P.std(0)
                pess, agree = mean - PESS_Z * std, (P > lm).mean(0)
                i = int(np.argmax(pess))
                if pess[i] > lm and agree[i] >= AGREE and ph[i] <= tau:
                    shipped += 1
                    gains.append(yy[i])
                    regress += int(yy[i] < math.log(0.99) or hh[i] == 1)
                else:
                    gains.append(0.0)
            n = len(oof)
            grid.append({"margin": mg, "tau": tau, "programs": n, "shipped": shipped, "regressions": regress,
                         "mean_log_gain": float(np.mean(gains)) if gains else 0.0,
                         "geomean_pct": (math.exp(np.mean(gains)) - 1) * 100 if gains else 0.0})
    ok = [g for g in grid if g["programs"] and g["regressions"] / g["programs"] <= 2 / 33]
    best = max(ok, key=lambda g: (g["mean_log_gain"], g["margin"])) if ok else \
        max(grid, key=lambda g: (-g["regressions"], g["margin"]))
    ungated = []
    for p, f, P, ph, yy, hh in oof:
        pess = P.mean(0) - PESS_Z * P.std(0)
        ungated.append(yy[int(np.argmax(pess))])
    return {"chosen": best, "grid": grid, "oof_programs": len(oof),
            "oof_ungated_geomean_pct": (math.exp(np.mean(ungated)) - 1) * 100 if ungated else None,
            "oof_ungated_regressions": int(sum(1 for v in ungated if v < math.log(0.99))) if ungated else None,
            "objective": "max mean log gain subject to OOF regression rate <= 2/33 (regression: label < 0.99x or harmful)"}


# ---------------------------------------------------------------- manifest
def write_manifest(entries: dict[str, str], extra: dict) -> Path:
    man = {"created": time.strftime("%Y-%m-%dT%H:%M:%S"), "mode": "predict",
           "files": {k: {"path": v, "sha256": _sha(Path(v))} for k, v in entries.items()}, **extra,
           "note": "Predict mode loads only these files and refuses to run if a hash differs. Never reads tune's models."}
    p = PDIR / "MANIFEST.json"
    p.write_text(json.dumps(man, indent=1))
    return p


def load_manifest_verified() -> dict:
    p = PDIR / "MANIFEST.json"
    if not p.exists():
        raise SystemExit(f"{p} missing: train predict mode first (python -m nc.cli predict-train)")
    man = json.loads(p.read_text())
    bad = [k for k, v in man["files"].items() if not Path(v["path"]).exists() or _sha(Path(v["path"])) != v["sha256"]]
    if bad:
        raise SystemExit(f"predict MANIFEST mismatch: {bad}; refusing to run.")
    if any("/tune/" in v["path"] or "rl_policy_latest" in v["path"] or "surrogate_" in v["path"] for v in man["files"].values()):
        raise SystemExit("predict MANIFEST references tune files; refusing.")
    return man


# ---------------------------------------------------------------- training procedure
def _rl_train(ens: Ensemble, margin: float, actions: list[dict], pf: dict, programs: list[str], names, out: Path,
              iters: int, log=print, seed: int = 0):
    from . import rl
    env = rl.PassEnv(PessimisticScorer(ens, margin), names, actions, {p: pf[p] for p in programs}, horizon=3)
    res = rl.train_ppo(env, programs, iters=iters, episodes=64, seed=seed, log=log)
    rl.save_policy(out, res, env, {"mode": "predict", "reward": "ensemble pessimistic estimate (mean - 1.28 std)",
                                   "margin": margin, "programs": len(programs)})
    return out


def train_all(tc, cfg, manifest: dict, split: dict, rl_iters: int = 150, log=print) -> dict:
    """OOF thresholds (train+val) -> train-only ensemble + RL (for the validation timing check) -> final
    ensemble + RL on train+val -> MANIFEST. Test families are never used."""
    main = Store(cfg.db_path)                    # read only: predict never writes to the shared DB
    ps_ = pstore()
    PDIR.mkdir(parents=True, exist_ok=True)
    data = load_training(main, ps_, manifest, tc)
    X, y, h, w, pids, fams, gk, fnames, npf = data
    groups = split["groups"]
    test_f, val_f = set(groups["test"]), set(groups["val"])
    log(f"training rows {len(y)} ({int(h.sum())} harmful), programs {len(set(pids))}, features {len(fnames)}")
    pool, info = safe_pool(main, PDIR / "safe_pool.json")
    log(f"safe pool: {info['singles']} single edits + {info['pairs']} pairs")
    cv = oof_thresholds(data, pool, log=log, exclude_families=test_f)
    (PDIR / "cv.json").write_text(json.dumps(cv, indent=1))
    mg, tau = cv["chosen"]["margin"], cv["chosen"]["tau"]
    log(f"chosen thresholds: margin {mg}, tau {tau}  OOF: {cv['chosen']}")
    names = leaf_names(parse_pipeline(tc.pipeline_string("O3")))
    pf = predict_features(main, ps_)
    actions = [json.loads(g.to_json())["edits"][0] for g in pool if len(g.edits) == 1]
    entries = {"safe_pool": str(PDIR / "safe_pool.json"), "cv": str(PDIR / "cv.json")}
    for tag, excl in (("_trainonly", test_f | val_f), ("", test_f)):
        keep = ~np.isin(fams, list(excl))
        ens = Ensemble(fnames=fnames, n_prog=npf).fit(X[keep], y[keep], h[keep], w[keep])
        paths = ens.save(PDIR, tag)
        progs = sorted(set(pids[keep]))
        pol = _rl_train(ens, mg, actions, pf, progs, names, PDIR / f"rl_policy{tag}.npz", rl_iters, log)
        for k, v in paths.items():
            entries[f"ensemble{tag}_{k}"] = v
        entries[f"rl_policy{tag}"] = str(pol)
        entries[f"rl_policy{tag}_meta"] = str(pol.with_suffix(".json"))
        log(f"trained ensemble{tag} on {len(progs)} programs + RL policy")
    man = write_manifest(entries, {"thresholds": {"margin": mg, "tau": tau, "agree": AGREE, "pess_z": PESS_Z},
                                   "pool": {k: v for k, v in info.items() if k != "single_edits"},
                                   "train_families_excluded": {"final": sorted(test_f), "trainonly": sorted(test_f | val_f)}})
    log(f"predict MANIFEST: {man}")
    return {"cv": cv, "manifest": str(man)}


# ---------------------------------------------------------------- runtime
class Predictor:
    """Loads predict's models from its verified MANIFEST (final, or the train-only set for validation)."""

    def __init__(self, tc, which: str = "final"):
        man = load_manifest_verified()
        tag = "" if which == "final" else "_trainonly"
        f = {k: Path(v["path"]) for k, v in man["files"].items()}
        self.ens = Ensemble.load(f[f"ensemble{tag}_meta"])
        self.pool = load_pool(f["safe_pool"])
        self.th = man["thresholds"]
        self.policy, self.policy_meta = f[f"rl_policy{tag}"], json.loads(f[f"rl_policy{tag}_meta"].read_text())
        self.names = leaf_names(parse_pipeline(tc.pipeline_string("O3")))
        self.which = which

    def proposals(self, pid: str, pfeat: dict, train_pf: dict, k: int = 24) -> list[Genome]:
        from . import rl
        env = rl.PassEnv(PessimisticScorer(self.ens, self.th["margin"]), self.names, self.policy_meta["actions"],
                         train_pf, self.policy_meta.get("horizon", 3))         # scaling from training programs only
        env.pf[pid] = pfeat
        return rl.propose(env, rl.load_policy(self.policy, env), pid, k, 0)

    def choose(self, pid: str, pfeat: dict, train_pf: dict, use_rl: bool = True, gated: bool = True) -> dict:
        props = self.proposals(pid, pfeat, train_pf) if use_rl else []
        cands = props + self.pool
        src = ["RL"] * len(props) + ["safe pool"] * len(self.pool)
        r = decide(self.ens, pfeat, cands, src, self.names, self.th["margin"], self.th["tau"], gated)
        r.update(mode=("RL + SL" if use_rl else "SL") + ("" if gated else " (ungated)"), rl_proposals=len(props))
        return r


def train_program_features(main: Store, ps_: Store, programs) -> dict:
    pf = predict_features(main, ps_)
    return {p: pf[p] for p in programs if p in pf}


ADVISORY = True     # test-set criteria not met (2026-10-26): predict writes -O3 unless --apply is given


def measure_pick(tc, cfg, s0, cflags: list[str], b3, genome: Genome, tree, spec, reps: int = 20, log=print) -> dict:
    """After the (compile-only) prediction: compile predict's top-ranked sequence, check its output against the
    -O0 build, and time it against -O3 (interleaved, `reps` rounds, with a byte-identical -O3 copy as A/A control).
    Reporting only: it never changes predict's choice or which binary is written."""
    import shutil
    from .timing import measure_interleaved, paired_speedup, run_spec
    t0 = time.perf_counter()
    pipe, fl, be = materialize(tree, genome)
    m = {"edits": genome.edits, "raw": genome.raw, "pipeline": pipe, "flags": list(fl), "backend": be, "rounds": reps}
    b = tc.build(s0, pipe, be, tuple(cflags), fl)
    if not b.ok:
        m.update(status="build_failed", note=f"the sequence failed to build ({b.status})")
        return m
    m["text_size"] = b.text_size
    o0 = tc.build(s0, "default<O0>", 0, tuple(cflags))
    log("[measure] checking the pick's output against the -O0 build ...")
    ref, got = run_spec(o0.bin_path, spec, cfg.timing_cpu, cfg.timeout_s), run_spec(b.bin_path, spec, cfg.timing_cpu, cfg.timeout_s)
    if ref.status != "ok":
        m.update(status="reference_failed", note=f"the -O0 build did not run cleanly ({ref.status}); check args/stdin")
        return m
    if got.status != "ok" or got.out_hash != ref.out_hash:
        m.update(status="wrong_output", note="the pick's output differs from the -O0 build (or it crashed): not timed")
        return m
    if b.bin_hash == b3.bin_hash:
        m.update(status="same_binary", speedup=1.0, ci=[1.0, 1.0], note="the pick compiles to the same binary as -O3")
        return m
    ctrl = str(Path(b.bin_path).with_name("o3_copy"))
    shutil.copy2(b3.bin_path, ctrl)
    log(f"[measure] timing the pick vs -O3: {reps} interleaved rounds on a pinned core, with an A/A control ...")
    ser = measure_interleaved({"BASE": b3.bin_path, "CTRL": ctrl, "PICK": b.bin_path}, spec.args, reps, 1,
                              cfg.timing_cpu, max(2.0, 5 * ref.wall_ms / 1000), seed=21, expected_hash=ref.out_hash,
                              stdin_path=spec.stdin_path, cwd=spec.cwd, log=log)
    if ser["PICK"].status != "ok" or ser["BASE"].status != "ok":
        m.update(status="timing_failed", note=f"timing failed (pick {ser['PICK'].status}, -O3 {ser['BASE'].status})")
        return m
    sp, ctl = paired_speedup(ser["BASE"].wall_ms, ser["PICK"].wall_ms), paired_speedup(ser["BASE"].wall_ms, ser["CTRL"].wall_ms)
    m.update(status="ok", speedup=sp.get("speedup"), ci=[sp.get("ci_lo"), sp.get("ci_hi")], control=ctl.get("speedup"),
             control_ok=abs(ctl.get("speedup", 2) - 1) * 100 <= cfg.control_max_dev_pct,
             o3_median_ms=float(np.nanmedian(ser["BASE"].wall_ms)), pick_median_ms=float(np.nanmedian(ser["PICK"].wall_ms)),
             measure_s=round(time.perf_counter() - t0, 1))
    m["verdict"] = ("faster" if sp.get("ci_lo", 0) > 1.0 else "slower" if sp.get("ci_hi", 2) < 1.0 else "no measurable difference")
    log(f"[measure] pick {m['speedup']:.3f}x vs -O3 [{m['ci'][0]:.3f}, {m['ci'][1]:.3f}]  {m['pick_median_ms']:.1f} ms vs "
        f"{m['o3_median_ms']:.1f} ms; A/A control {m['control']:.3f}x")
    return m


def predict_source(tc, cfg, src: list[str], cflags: list[str], out: Path, use_rl: bool = True,
                   verify_args: list[str] | None = None, verify: bool = False, log=print,
                   apply: bool | None = None, measure: bool = False, stdin: str | None = None,
                   cwd: str | None = None) -> dict:
    """Compile-only prediction for a user program. Times are measured in a FRESH work dir (no caches).
    Advisory by default (ADVISORY): the -O3 binary is written and the recommendation is only reported, unless
    apply=True. Timing/feature work is identical either way (time_check measures the same path)."""
    import shutil
    import tempfile
    from .features import static_features
    from .remarks import extract_one
    from .toolchain import Toolchain
    s0 = src if len(src) > 1 else src[0]
    pr = Predictor(tc, "final")
    main, ps_ = Store(cfg.db_path), pstore()
    train_pf = train_program_features(main, ps_, _final_train_programs())
    tree = parse_pipeline(tc.pipeline_string("O3"))
    with tempfile.TemporaryDirectory() as d:
        t0 = time.perf_counter()
        fresh = Toolchain(cfg, Path(d) / "o3")                   # plain -O3 build, for the time comparison
        b3 = fresh.build(s0, "default<O3>", 3, tuple(cflags))
        t_o3 = time.perf_counter() - t0
        if not b3.ok:
            raise RuntimeError(f"-O3 build failed: {b3.error[:300]}")
        t1 = time.perf_counter()
        tcp = Toolchain(cfg, Path(d) / "p")
        rec = {"src": s0, "cflags": cflags}
        pfeat = {**static_features(tcp, rec), **extract_one(tcp, s0, tuple(cflags))}
        res = pr.choose("user/" + Path(src[0]).stem, pfeat, train_pf, use_rl=use_rl)
        top_genome = res["genome"]                                 # top-ranked sequence, gate passed or not
        if res["ship"]:
            g = Genome.from_json(res["genome"])
            pipe, fl, be = materialize(tree, g)
            b = tcp.build(s0, pipe, be, tuple(cflags), fl)
            if not b.ok:
                res.update(ship=False, reason=f"kept -O3: chosen pipeline failed to build ({b.status})")
                b = b3
        else:
            b = b3
        t_pred = time.perf_counter() - t1
        applied = res["ship"] and (apply if apply is not None else not ADVISORY)
        res["recommended"] = res["ship"]
        res["applied"] = bool(applied)
        if res["ship"] and not applied:
            res["reason"] += " (advisory mode: -O3 written; use --apply to use this pipeline)"
            b = b3
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(b.bin_path, out)
        res.update(output=str(out), verified=False, o3_build_s=round(t_o3, 2), predict_total_s=round(t_pred, 2),
                   added_over_o3_s=round(t_pred - t_o3, 2), o3_pipeline=tc.pipeline_string("O3"),
                   o3_text_size=b3.text_size)
        if res.get("recommended"):
            rg = Genome.from_json(res["genome"])
            res["recommended_edits"] = rg.edits
            res["recommended_pipeline"], res["recommended_flags"], res["recommended_backend"] = materialize(tree, rg)
        if verify and applied:
            from .timing import RunSpec, run_spec
            o0 = tcp.build(s0, "default<O0>", 0, tuple(cflags))
            spec = RunSpec(args=verify_args or [])
            a, c = run_spec(o0.bin_path, spec, None, cfg.timeout_s), run_spec(str(out), spec, None, cfg.timeout_s)
            res["verified"] = a.status == "ok" and c.status == "ok" and a.out_hash == c.out_hash
            if not res["verified"]:
                shutil.copy2(b3.bin_path, out)
                res.update(ship=False, reason="kept -O3: --verify found different output from the -O0 build")
        if measure:                                                # after t_pred: not part of predict's cost
            from .timing import RunSpec
            g = Genome.from_json(top_genome)
            res["measured"] = measure_pick(tcp, cfg, s0, cflags, b3, g, tree,
                                           RunSpec(args=verify_args or [], stdin_path=stdin, cwd=cwd), log=log)
            res["measured"]["which"] = "recommendation (passed the gate)" if res.get("recommended") else \
                "top prediction (did not pass the gate)"
            res["measured"]["predicted_speedup"] = res["predicted_speedup"]
    if not res["ship"]:
        res.pop("genome", None)
    Path(str(out) + ".json").write_text(json.dumps(res, indent=1, default=str))
    return res


def _final_train_programs() -> list[str]:
    split = json.loads(Path("corpus/split.json").read_text())["program_split"]
    return [p for p, t in split.items() if t in ("train", "val")]


def _trainonly_programs() -> list[str]:
    split = json.loads(Path("corpus/split.json").read_text())["program_split"]
    return [p for p, t in split.items() if t == "train"]


# ---------------------------------------------------------------- evaluation (val / test)
PRED_METHODS = {"predict": (True, True), "predict_ungated": (True, False), "predict_sl": (False, True)}


def eval_program(tc, cfg, rec: dict, tag: str, which: str, log=print) -> None:
    """Predict's picks for one program (no timing in the choice), output check (evaluation only), then one
    interleaved measurement vs -O3 with an A/A control. Stored in results/predict.sqlite eval_results."""
    from .evaluate import SCHEMA as ESCHEMA
    from .search import ProgramSearch
    from .timing import paired_speedup, run_spec
    ps_ = pstore()
    ps_.con.executescript(ESCHEMA)
    ps_.con.executescript(DETAILS_SCHEMA)
    pid = rec["program_id"]
    if ps_.rows("SELECT 1 FROM eval_results WHERE tag=? AND program_id=? AND method='O3'", (tag, pid)):
        log(f"[{pid}] already evaluated under {tag}")
        return
    t0 = time.time()
    main = Store(cfg.db_path)
    pr = Predictor(tc, which)
    pf = predict_features(main, ps_)
    train_pf = {p: pf[p] for p in (_trainonly_programs() if which != "final" else _final_train_programs()) if p in pf}
    srch = ProgramSearch(tc, cfg, ps_, rec, log=log)
    picks, bins = {}, {"BASE": srch.base.bin_path, "CTRL": srch.ctrl_path}
    for m, (use_rl, gated) in PRED_METHODS.items():
        tp = time.perf_counter()
        r = pr.choose(pid, pf[pid], train_pf, use_rl=use_rl, gated=gated)
        r["decide_s"] = round(time.perf_counter() - tp, 3)
        if r["ship"]:
            pipe, fl, be = materialize(srch.tree, Genome.from_json(r["genome"]))
            b = tc.build(srch.src, pipe, be, srch.cflags, fl)
            if not b.ok:
                r.update(ship=False, choice="build_fail")
            else:
                v = run_spec(b.bin_path, srch.verify_spec, srch.helpers[0], srch.timeout)
                r["wrong_output"] = not (v.status == "ok" and v.out_hash == srch.ref)
                r["bin_path"], r["text_size"] = b.bin_path, b.text_size
                if b.bin_hash == srch.base.bin_hash:
                    r["same_as_o3"] = True
                elif not r["wrong_output"]:
                    bins[m] = b.bin_path
        picks[m] = r
    ser = srch._measure(bins, cfg.reps, cfg.warmup, seed=5151)
    ctrl = paired_speedup(ser["BASE"].wall_ms, ser["CTRL"].wall_ms)
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    rows = [(tag, pid, rec["family"], "O3", "O3", None, 1.0, 1.0, 1.0, 1.0, 0, 0, 0, 0, None, ctrl.get("speedup"), now)]
    for m, r in picks.items():
        if m in bins:
            sp = paired_speedup(ser["BASE"].wall_ms, ser[m].wall_ms)
            s, lo, hi = sp.get("speedup"), sp.get("ci_lo"), sp.get("ci_hi")
            choice = "candidate"
        else:
            s = lo = hi = 1.0
            choice = "wrong_output" if r.get("wrong_output") else ("O3" if not r["ship"] else "same_as_o3")
        tr = (r.get("text_size") or 0) / max(srch.base.text_size, 1) if m in bins else 1.0
        rows.append((tag, pid, rec["family"], m, choice, r.get("genome") if r["ship"] else None, s, lo, hi, tr,
                     0, r["decide_s"], 0, 0, r.get("predicted_speedup"), ctrl.get("speedup"), now))
        ps_.con.execute("INSERT OR REPLACE INTO predict_details VALUES(?,?,?,?)", (tag, pid, m, json.dumps(r, default=str)))
    ps_.con.executemany("INSERT OR REPLACE INTO eval_results VALUES(" + ",".join("?" * 17) + ")", rows)
    ps_.con.commit()
    log(f"[{pid}] " + " | ".join(f"{r[3]} {r[6]:.3f}x {r[4]}" for r in rows[1:]) +
        f" | ctrl {ctrl.get('speedup', float('nan')):.3f} ({time.time() - t0:.0f}s)")


DETAILS_SCHEMA = """CREATE TABLE IF NOT EXISTS predict_details(tag TEXT, program_id TEXT, method TEXT, json TEXT,
                    PRIMARY KEY(tag, program_id, method));"""


def time_check(tc, cfg, recs: list[dict], use_rl: bool = True, log=print) -> list[dict]:
    """Predict's added time over a plain -O3 build, measured from scratch (fresh work dirs) per program."""
    import tempfile
    out = []
    for rec in recs:
        with tempfile.TemporaryDirectory() as d:
            res = predict_source(tc, cfg, rec["src"] if isinstance(rec["src"], list) else [rec["src"]],
                                 list(rec.get("cflags") or []), Path(d) / "prog", use_rl=use_rl, log=log)
        out.append({"program": rec["program_id"], "o3_build_s": res["o3_build_s"],
                    "predict_total_s": res["predict_total_s"], "added_over_o3_s": res["added_over_o3_s"],
                    "ship": res["ship"]})
        log(f"[{rec['program_id']}] -O3 build {res['o3_build_s']:.1f}s, predict {res['predict_total_s']:.1f}s, "
            f"added {res['added_over_o3_s']:+.1f}s, ship {res['ship']}")
    return out


# ---------------------------------------------------------------- compare
def compare(tc, cfg, src: list[str], args: list[str], stdin, cwd, cflags: list[str], k: int = 8, log=print,
            json_out: Path | None = None) -> dict:
    """One serial interleaved run of -O3, -O2, -Os, predict's pick, tune's pick, random@k and GA@k, with an
    A/A control. Tune runs with its frozen MANIFEST files; predict with its own."""
    import tempfile
    from .deploy import deploy_source
    from .evaluate import _search_pick
    from .features import static_features
    from .remarks import extract_one
    from .search import ProgramSearch
    from .timing import RunSpec, paired_speedup, run_spec
    from . import tunelock
    s0 = src if len(src) > 1 else src[0]
    spec = RunSpec(args=args, stdin_path=stdin, cwd=cwd)
    o0 = tc.build(s0, "default<O0>", 0, tuple(cflags))
    ref = run_spec(o0.bin_path, spec, cfg.timing_cpu, cfg.timeout_s)
    if ref.status != "ok":
        raise RuntimeError(f"-O0 reference run failed ({ref.status})")
    rec = {"program_id": f"user/{Path(src[0]).stem}", "src": s0, "cflags": cflags, "time_spec": spec.__dict__,
           "verify_spec": spec.__dict__, "ref_output_hash": ref.out_hash}
    ps_ = pstore()
    srch = ProgramSearch(tc, cfg, ps_, rec, log=log)
    bins = {"BASE": srch.base.bin_path, "CTRL": srch.ctrl_path}
    notes = {}
    for lv, (pipe, be) in {"O2": ("default<O2>", 2), "Os": ("default<Os>", 2)}.items():
        bins[lv] = tc.build(s0, pipe, be, tuple(cflags)).bin_path
    # predict (no runs)
    pr = Predictor(tc, "final")
    pfeat = {**static_features(tc, rec), **extract_one(tc, s0, tuple(cflags))}
    r = pr.choose(rec["program_id"], pfeat, train_program_features(Store(cfg.db_path), ps_, _final_train_programs()))
    notes["predict"] = r
    if r["ship"]:
        pipe, fl, be = materialize(srch.tree, Genome.from_json(r["genome"]))
        b = tc.build(s0, pipe, be, tuple(cflags), fl)
        v = run_spec(b.bin_path, srch.verify_spec, srch.helpers[0], srch.timeout)
        notes["predict"]["wrong_output"] = not (v.status == "ok" and v.out_hash == srch.ref)
        if not notes["predict"]["wrong_output"] and b.bin_hash != srch.base.bin_hash:
            bins["predict"] = b.bin_path
    # tune (frozen files, its own timing and confirmation)
    files = tunelock.load_verified(cfg.db_path)
    with tempfile.TemporaryDirectory() as d:
        t = deploy_source(tc, cfg, src, args, stdin, cwd, cflags, Path(d) / "tune_prog", files["surrogate"], k=k,
                          rl_policy=files["rl_policy"], log=log)
        notes["tune"] = {kk: v for kk, v in t.items() if kk in ("choice", "shipped_from", "select_speedup", "confirm", "reason")}
        if t.get("choice") == "candidate":
            bins["tune"] = t["bin_path"]
    for m, name in (("random", f"random@{k}"), ("evo", f"ga@{k}")):
        p = _search_pick(srch, m, k, 0)
        if p.get("choice") == "candidate":
            bins[name] = p["bin_path"]
    ser = srch._measure(bins, cfg.reps, cfg.warmup, seed=8888)
    rows = []
    for m in ["O2", "Os", "predict", "tune", f"random@{k}", f"ga@{k}", "CTRL"]:
        if m in bins:
            sp = paired_speedup(ser["BASE"].wall_ms, ser[m].wall_ms)
            rows.append({"method": "A/A control" if m == "CTRL" else m, "speedup": sp.get("speedup"),
                         "ci": [sp.get("ci_lo"), sp.get("ci_hi")], "median_ms": float(np.nanmedian(ser[m].wall_ms))})
        else:
            rows.append({"method": m, "speedup": 1.0, "ci": None, "note": "kept -O3 (no change shipped)"})
    res = {"program": rec["program_id"], "rows": rows, "notes": notes,
           "o3_median_ms": float(np.nanmedian(ser["BASE"].wall_ms))}
    res["o3_pipeline"] = tc.pipeline_string("O3")
    out = json_out or Path(cfg.results_dir) / "compare" / f"{Path(src[0]).stem}_{time.strftime('%Y%m%d-%H%M%S')}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, indent=1, default=str))
    res["saved"] = str(out)
    return res
