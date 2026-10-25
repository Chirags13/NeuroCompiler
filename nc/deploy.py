"""Deployment (Phase 8): `neurocompiler <source>` = model proposes top-k pipelines, they are
compiled, verified against the -O0 output and briefly timed together with -O3; the fastest wins
only if its paired lower bound beats -O3, otherwise -O3 is shipped. -O3 is always a candidate,
so the result is never knowingly slower than -O3.

The candidate library (genomes over the -O3 pass tree, so they transfer between programs):
  * pruned single edits from the knowledge base (results/passkb_actions.json), if present
  * genomes that won (confirmed CI > 1) on TRAINING programs
  * standard-level seeds
  * random action-space-v2 genomes
"""
from __future__ import annotations

import json
import random
import shutil
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

from .config import Config
from .db import Store
from .features import leaf_names, program_features, scan_features, static_features
from .pipeline import Genome, materialize, random_genome
from .search import LEVEL_SEEDS, ProgramSearch
from .timing import RunSpec, paired_speedup, run_spec
from .toolchain import Toolchain


def library(store: Store, ps: ProgramSearch, train_programs: set[str] | None, n_random: int,
            results_dir: Path, seed: int = 0) -> list[Genome]:
    gs: list[Genome] = []
    act = results_dir / "passkb_actions.json"
    if act.exists():
        for a in json.loads(act.read_text())["actions"]:
            gs.append(Genome([a["edit"]]))
    q = """SELECT DISTINCT c.genome_json, c.program_id FROM measurements m JOIN candidates c ON c.cand_id = m.cand_id
           WHERE m.stage IN ('confirm','confirm_min','validate') AND m.ci_lo > 1.0"""
    for r in store.rows(q):
        if train_programs is None or r["program_id"] in train_programs:
            g = Genome.from_json(r["genome_json"])
            gs.append(g)
    gs += [Genome([{"op": "backend", "value": b}], raw=p) for p, b in LEVEL_SEEDS]
    rng = random.Random(seed)
    for _ in range(n_random):
        gs.append(random_genome(ps.tree, ps.pools, ps.knobs, rng, space=ps.space))
    uniq, seen = [], set()
    for g in gs:
        k = g.to_json()
        if k not in seen:
            seen.add(k)
            uniq.append(g)
    return uniq


def select_topk(ps: ProgramSearch, scores: np.ndarray, lib: list[Genome], k: int, reps: int,
                method: str, overshoot: int = 3, confirm_reps: int = 20, margin: float = 0.01) -> dict:
    """Compile the best-scored genomes until k distinct verified binaries exist, time them with
    -O3 (interleaved, `reps` rounds), pick the fastest, and ship it only if a fresh confirmation run
    (`confirm_reps` rounds, with an A/A control) shows CI lower bound > 1 + margin. confirm_reps=0
    reproduces the original rule used in the first Phase 9 run (tag 'final')."""
    t0 = time.time()
    order = np.argsort(-scores)
    chosen_evs, bins = [], set()
    n_compiled = 0
    for start in range(0, len(order), k * overshoot):
        batch = [lib[i] for i in order[start:start + k * overshoot]]
        # compile + verify only (timing happens once, below, for all k together)
        mats = [materialize(ps.tree, g) for g in batch]
        with ThreadPoolExecutor(ps.cfg.compile_workers) as ex:
            builds = list(ex.map(lambda m: ps.tc.build(ps.src, m[0], m[2], ps.cflags, m[1]), mats))
        n_compiled += len(builds)
        for g, m, b in zip(batch, mats, builds):
            if not b.ok or b.bin_hash == ps.base.bin_hash or b.bin_hash in bins:
                continue
            v = run_spec(b.bin_path, ps.verify_spec, ps.helpers[0], ps.timeout)
            if v.status != "ok" or v.out_hash != ps.ref:
                continue
            bins.add(b.bin_hash)
            chosen_evs.append((g, m, b))
            if len(chosen_evs) >= k:
                break
        if len(chosen_evs) >= k:
            break
    t_compile = time.time() - t0
    out = {"method": method, "n_compiled": n_compiled, "n_timed": len(chosen_evs), "compile_s": round(t_compile, 1)}
    if not chosen_evs:
        out.update(choice="O3", reason="no distinct verified candidate")
        return out
    t1 = time.time()
    bm = {"BASE": ps.base.bin_path, **{f"c{i}": b.bin_path for i, (_g, _m, b) in enumerate(chosen_evs)}}
    ser = ps._measure(bm, reps, 1, seed=3)
    best, best_sp = None, None
    for i, (g, m, b) in enumerate(chosen_evs):
        sp = paired_speedup(ser["BASE"].wall_ms, ser[f"c{i}"].wall_ms) if ser[f"c{i}"].status == "ok" else {}
        if "speedup" in sp and (best_sp is None or sp["speedup"] > best_sp["speedup"]):
            best, best_sp = (g, m, b), sp
    if best is not None and best_sp.get("ci_lo", 0) > 1.0 and confirm_reps > 0:
        # Picking the best of k measurements overstates it (winner's curse; lencod in the first Phase 9
        # run shipped at 0.979x). A fresh run (pick, -O3, byte-identical copy of -O3) must confirm it
        # with a margin and a clean A/A control, otherwise -O3 ships.
        g, m, b = best
        cs = ps._measure({"BASE": ps.base.bin_path, "CTRL": ps.ctrl_path, "PICK": b.bin_path},
                         confirm_reps, 1, seed=11)
        csp = paired_speedup(cs["BASE"].wall_ms, cs["PICK"].wall_ms) if cs["PICK"].status == "ok" else {}
        ctl = paired_speedup(cs["BASE"].wall_ms, cs["CTRL"].wall_ms)
        out["confirm"] = {"speedup": csp.get("speedup"), "ci": [csp.get("ci_lo"), csp.get("ci_hi")],
                          "control": ctl.get("speedup")}
        ok_ctl = abs(ctl.get("speedup", 2) - 1) * 100 <= ps.cfg.control_max_dev_pct
        if not (csp.get("ci_lo", 0) > 1.0 + margin and ok_ctl):
            out["timing_s"] = round(time.time() - t1, 1)
            out.update(choice="O3", reason=f"pick not confirmed (fresh run {csp.get('speedup', float('nan')):.3f}x, "
                                           f"need CI > {1 + margin:.2f} and clean control)",
                       best_select=best_sp.get("speedup"))
            return out
    out["timing_s"] = round(time.time() - t1, 1)
    if best is not None and best_sp.get("ci_lo", 0) > 1.0:
        g, m, b = best
        out.update(choice="candidate", genome=g.to_json(), pipeline=m[0], flags=list(m[1]), backend=m[2],
                   bin_path=b.bin_path, text_size=b.text_size, select_speedup=best_sp["speedup"],
                   select_ci=[best_sp["ci_lo"], best_sp["ci_hi"]])
    else:
        out.update(choice="O3", reason="no candidate beat -O3 with CI > 1 in the selection run",
                   best_select=best_sp.get("speedup") if best_sp else None)
    return out


def quick_scan(tc: Toolchain, cfg: Config, rec: dict) -> dict:
    """Scan facts for a new program: one pinned run per level (labelled quick, not the corpus scan)."""
    times, builds = {}, {}
    for name, pipe, be in (("O0", "default<O0>", 0), ("O1", "default<O1>", 1), ("O2", "default<O2>", 2),
                           ("O3", "default<O3>", 3), ("Os", "default<Os>", 2)):
        b = tc.build(rec["src"], pipe, be, tuple(rec.get("cflags") or []))
        builds[name] = b
        s = run_spec(b.bin_path, RunSpec.from_dict(rec["time_spec"]), cfg.timing_cpu, cfg.timeout_s)
        times[name] = s.wall_ms
        if name == "O3":
            rec["o3_maxrss_mb"] = s.maxrss_kb / 1024
    rec["times_ms"] = times
    rec["level_spread"] = max(times[k] for k in ("O1", "O2", "O3", "Os")) / min(times[k] for k in ("O1", "O2", "O3", "Os"))
    rec["o3_text_bytes"] = builds["O3"].text_size
    rec["distinct_level_binaries"] = len({b.bin_hash for b in builds.values()})
    return rec


def deploy_source(tc: Toolchain, cfg: Config, src: list[str], args: list[str], stdin: str | None, cwd: str | None,
                  cflags: list[str], out: Path, meta_path: Path, k: int = 8, reps: int = 10, n_random: int = 300,
                  dynamic: bool = False, log=print, rl_policy: Path | None = None) -> dict:
    """RL + SL (default when a policy is given): the RL agent proposes pipelines for this program, they are
    pooled with the library, the supervised surrogate ranks the whole pool, the top-k are compiled, verified
    and timed against -O3, and the fastest ships only if a fresh confirmation run beats -O3 (else -O3 ships).
    Without a policy: SL only (surrogate ranks the library)."""
    from .model import Surrogate
    from .features import L2_SIM, cachegrind
    t0 = time.time()
    spec = RunSpec(args=args, stdin_path=stdin, cwd=cwd)
    s0 = src if len(src) > 1 else src[0]
    rec = {"program_id": f"user/{Path(src[0]).stem}", "src": s0, "cflags": cflags, "time_spec": spec.__dict__,
           "verify_spec": spec.__dict__}
    o0 = tc.build(s0, "default<O0>", 0, tuple(cflags))
    if not o0.ok:
        raise RuntimeError(f"-O0 build failed: {o0.error[:300]}")
    ref = run_spec(o0.bin_path, spec, cfg.timing_cpu, cfg.timeout_s)
    if ref.status != "ok":
        raise RuntimeError(f"-O0 reference run failed ({ref.status}); cannot verify candidates")
    rec["ref_output_hash"] = ref.out_hash
    sur = Surrogate(meta_path)
    pfeat = {**static_features(tc, rec), **scan_features(quick_scan(tc, cfg, rec))}
    if dynamic and any(f.startswith("sim_") for f in sur.fnames):
        import copy
        from .features import SIM_MARCH
        c2 = copy.copy(cfg)
        c2.march = SIM_MARCH
        b = Toolchain(c2, tc.work).build(s0, "default<O3>", 3, tuple(cflags))
        pfeat.update(cachegrind(b.bin_path, spec, cfg.timing_cpu))
        l2 = cachegrind(b.bin_path, spec, cfg.timing_cpu, ll=L2_SIM)       # same two passes as training
        pfeat.update({"sim_l2d_mpki": l2["sim_lld_mpki"], "sim_l2d_miss_rate": l2["sim_lld_miss_rate"]})
    store = Store(Path(cfg.results_dir) / "deploy.sqlite")
    ps = ProgramSearch(tc, cfg, store, rec, log=log)
    lib = library(Store(cfg.db_path), ps, set(sur.meta["train_programs"]), n_random, Path(cfg.results_dir))
    names = leaf_names(ps.tree)
    props: list[Genome] = []
    if rl_policy is not None and Path(rl_policy).exists():
        from . import rl
        meta = json.loads(Path(rl_policy).with_suffix(".json").read_text())
        train_pf = {p: v for p, v in program_features(Store(cfg.db_path)).items() if p in set(sur.meta["train_programs"])}
        env = rl.PassEnv(sur, names, meta["actions"], train_pf, meta.get("horizon", 4))   # scaling from training programs
        env.pf[rec["program_id"]] = pfeat
        pi = rl.load_policy(Path(rl_policy), env)
        props = rl.propose(env, pi, rec["program_id"], 3 * k, 0)
    pool = props + lib
    scores = sur.predict(pfeat, pool, names)
    res = select_topk(ps, scores, pool, k, reps, "deploy_rl_sl" if props else "deploy_sl")
    # provenance for reporting: did the shipped pipeline come from the RL agent or from the library?
    rl_keys = {g.to_json() for g in props}
    order = np.argsort(-scores)
    res["mode"] = "RL + SL" if props else "SL"
    res["rl_proposals"] = len(props)
    res["rl_in_top20_ranked"] = int(sum(1 for i in order[:20] if pool[i].to_json() in rl_keys))
    res["top_ranked"] = [{"rank": r + 1, "source": "RL" if pool[i].to_json() in rl_keys else "library",
                          "predicted_speedup": round(float(np.exp(scores[i])), 3), "n_edits": len(pool[i].edits)}
                         for r, i in enumerate(order[:10])]
    if res.get("choice") == "candidate":
        res["shipped_from"] = "RL agent" if res.get("genome") in rl_keys else "library"
        res["shipped_edits"] = Genome.from_json(res["genome"]).edits
    out.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(res["bin_path"] if res["choice"] == "candidate" else ps.base.bin_path, out)
    res.update(output=str(out), total_s=round(time.time() - t0, 1), library=len(lib), model=str(meta_path),
               rl_policy=str(rl_policy) if props else None)
    (out.with_suffix(out.suffix + ".json") if out.suffix else Path(str(out) + ".json")).write_text(json.dumps(res, indent=1, default=str))
    return res
