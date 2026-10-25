"""Evaluation (Phase 9): the frozen held-out test set, run once.

For every test program each method picks ONE binary by its own procedure and cost:
  O2, Os                standard levels (clang mapping: llc -O2)
  topk                  surrogate ranks the library, k compiled+verified, timed with -O3, fastest wins (CI > 1)
  ml_top1               surrogate's single best candidate, shipped without any timing (ML only)
  random_topk           k random library candidates, same timing step (ablation: no surrogate)
  topk_nodyn            topk with a surrogate trained without simulated dynamic features (if present)
  rl_topk               PPO proposals instead of the library, same timing step (if a policy exists)
  random@B, ga@B        random search / (6+18) evolution with B timed binaries (B = k: equal budget)
Then ONE final interleaved measurement per program (30 rounds, A/A control): -O3, its copy, and
every method's chosen binary. Methods that keep -O3 score exactly 1.0. Results go to the
eval_results table and a JSON + Markdown report in results/.

The surrogate must not have seen any test family (checked against the model's metadata).
"""
from __future__ import annotations

import json
import math
import random
import time
from pathlib import Path

import numpy as np

from .config import Config
from .db import Store
from .deploy import library, select_topk
from .features import leaf_names, program_features
from .pipeline import Genome, materialize
from .search import Budget, ProgramSearch, _boot_geomean_ci, _geomean
from .timing import paired_speedup, run_spec
from .toolchain import Toolchain

SCHEMA = """
CREATE TABLE IF NOT EXISTS eval_results(
  tag TEXT, program_id TEXT, family TEXT, method TEXT, choice TEXT, genome_json TEXT,
  speedup REAL, ci_lo REAL, ci_hi REAL, text_ratio REAL, compile_s REAL, timing_s REAL,
  n_compiled INTEGER, n_timed INTEGER, select_speedup REAL, control REAL, ts TEXT,
  PRIMARY KEY(tag, program_id, method));
"""


def _search_pick(ps: ProgramSearch, method: str, budget: int, seed: int) -> dict:
    t0 = time.time()
    cache, bud = {}, Budget()
    rng = random.Random(f"eval:{seed}:{ps.pid}:{method}")
    (ps.search_random if method.startswith("random") else ps.search_evo)(method, budget, rng, bud, cache)
    good = ps.pick_candidates(cache, 1, 1.01)
    out = {"method": f"{'random' if method.startswith('random') else 'ga'}@{budget}", "n_timed": bud.timed,
           "n_compiled": bud.attempts, "compile_s": round(ps.stage_s.get("compile", 0), 1),
           "timing_s": round(time.time() - t0, 1)}
    if good:
        e = good[0]
        out.update(choice="candidate", genome=e.genome.to_json(), bin_path=e.bin_path, text_size=e.text_size,
                   select_speedup=e.speedup)
    else:
        out.update(choice="O3")
    return out


def run_eval(tc: Toolchain, cfg: Config, store: Store, recs: list[dict], meta_path: Path, k: int, tag: str,
             nodyn_meta: Path | None = None, rl_policy: Path | None = None, n_random: int = 300,
             budget: int | None = None, reps_select: int = 10, seed: int = 0, log=print,
             only: set[str] | None = None, confirm_reps: int = 0) -> None:
    """`only` restricts the methods computed (others are skipped; -O3 is always measured). confirm_reps=0 is
    the selection procedure of the reported run (tag 'final'); keep it for comparable follow-up runs."""
    from .model import Surrogate
    want = (lambda m: True) if not only else (lambda m: m in only)

    def sel(scores, cands, method):
        return select_topk(ps, scores, cands, k, reps_select, method, confirm_reps=confirm_reps)
    store.con.executescript(SCHEMA)
    sur = Surrogate(meta_path)
    test_fams = {r["family"] for r in recs}
    leak = test_fams & set(sur.meta["train_families"])
    if leak:
        raise SystemExit(f"Surrogate was trained on test families {sorted(leak)}; retrain excluding them.")
    sur_nd = Surrogate(nodyn_meta) if nodyn_meta else None
    B = budget or k
    pf_all = program_features(store)
    for rec in recs:
        pid = rec["program_id"]
        if store.rows("SELECT 1 FROM eval_results WHERE tag=? AND program_id=? AND method='O3'", (tag, pid)):
            log(f"[{pid}] already evaluated under tag {tag}")
            continue
        if pid not in pf_all:
            log(f"[{pid}] no features; run `features extract` first")
            continue
        t0 = time.time()
        ps = ProgramSearch(tc, cfg, store, rec, log=log)
        names = leaf_names(ps.tree)
        lib = library(store, ps, set(sur.meta["train_programs"]), n_random, Path(cfg.results_dir), seed)
        picks: list[dict] = []
        for lv, (pipe, be) in {"O2": ("default<O2>", 2), "Os": ("default<Os>", 2)}.items():
            if not want(lv):
                continue
            b = tc.build(ps.src, pipe, be, ps.cflags)
            picks.append({"method": lv, "choice": "level", "genome": Genome([{"op": "backend", "value": be}], raw=pipe).to_json(),
                          "bin_path": b.bin_path, "text_size": b.text_size, "n_timed": 0, "n_compiled": 1})
        sc = sur.predict(pf_all[pid], lib, names)
        if want("topk"):
            picks.append(sel(sc, lib, "topk"))
        # ML only: the single top-scored distinct binary, no timing at all
        top1 = None
        order = np.argsort(-sc) if want("ml_top1") else []
        for i in order[:20]:
            pipe, fl, be = materialize(ps.tree, lib[i])
            b = tc.build(ps.src, pipe, be, ps.cflags, fl)
            if b.ok and b.bin_hash != ps.base.bin_hash:
                v = run_spec(b.bin_path, ps.verify_spec, ps.helpers[0], ps.timeout)
                if v.status == "ok" and v.out_hash == ps.ref:
                    top1 = {"method": "ml_top1", "choice": "candidate", "genome": lib[i].to_json(), "bin_path": b.bin_path,
                            "text_size": b.text_size, "n_timed": 0, "n_compiled": 1}
                    break
        if want("ml_top1"):
            picks.append(top1 or {"method": "ml_top1", "choice": "O3"})
        rng = np.random.default_rng(seed)
        if want("random_topk"):
            picks.append(sel(rng.random(len(lib)), lib, "random_topk"))
        if sur_nd is not None and want("topk_nodyn"):
            picks.append(sel(sur_nd.predict(pf_all[pid], lib, names), lib, "topk_nodyn"))
        if rl_policy is not None and Path(rl_policy).exists() and (want("rl_topk") or want("rl_lib_topk")):
            from . import rl
            # standardization statistics from training programs only; the test program is added afterwards
            env = rl.PassEnv(sur, names, json.loads(Path(rl_policy).with_suffix(".json").read_text())["actions"],
                             {p: pf_all[p] for p in sur.meta["train_programs"] if p in pf_all})
            env.pf[pid] = pf_all[pid]
            pi = rl.load_policy(Path(rl_policy), env)
            props = rl.propose(env, pi, pid, 3 * k, seed)
            if props and want("rl_topk"):         # (A) RL proposals only, in the policy's own order
                picks.append(sel(np.arange(len(props), 0, -1, dtype=float), props, "rl_topk"))
            if props and want("rl_lib_topk"):     # (B) RL proposals pooled with the library, surrogate ranks all
                pool = props + lib
                picks.append(sel(sur.predict(pf_all[pid], pool, names), pool, "rl_lib_topk"))
        if want("random@"):
            picks.append(_search_pick(ps, "random", B, seed))
        if want("ga@"):
            picks.append(_search_pick(ps, "evo", B, seed))
        # final interleaved measurement of everything chosen
        bins = {"BASE": ps.base.bin_path, "CTRL": ps.ctrl_path}
        for p in picks:
            if p.get("choice") in ("candidate", "level") and p.get("bin_path"):
                bins[p["method"]] = p["bin_path"]
        ser = ps._measure(bins, cfg.reps, cfg.warmup, seed=4242 + seed)
        ctrl = paired_speedup(ser["BASE"].wall_ms, ser["CTRL"].wall_ms)
        rows = [(tag, pid, rec["family"], "O3", "O3", None, 1.0, 1.0, 1.0, 1.0, 0, 0, 0, 0, None,
                 ctrl.get("speedup"), time.strftime("%Y-%m-%dT%H:%M:%S"))]
        for p in picks:
            m = p["method"]
            if m in bins and m not in ("BASE", "CTRL"):
                sp = paired_speedup(ser["BASE"].wall_ms, ser[m].wall_ms) if ser[m].status == "ok" else {}
                s, lo, hi = sp.get("speedup"), sp.get("ci_lo"), sp.get("ci_hi")
                tr = (p.get("text_size") or 0) / max(ps.base.text_size, 1)
            else:
                s = lo = hi = tr = 1.0
            rows.append((tag, pid, rec["family"], m, p.get("choice", "O3"), p.get("genome"), s, lo, hi, tr,
                         p.get("compile_s", 0), p.get("timing_s", 0), p.get("n_compiled", 0), p.get("n_timed", 0),
                         p.get("select_speedup"), ctrl.get("speedup"), time.strftime("%Y-%m-%dT%H:%M:%S")))
        store.con.executemany("INSERT OR REPLACE INTO eval_results VALUES(" + ",".join("?" * 17) + ")", rows)
        store.con.commit()
        log(f"[{pid}] " + " | ".join(f"{r[3]} {r[6]:.3f}x" for r in rows if r[6]) +
            f" | ctrl {ctrl.get('speedup', float('nan')):.3f}  ({time.time() - t0:.0f}s)")


def ir_runtime_correlation(store: Store) -> str:
    """Does a smaller IR instruction count predict a faster program? (explains IR-objective failures)"""
    from scipy.stats import spearmanr
    base = {r["program_id"]: r["ir_insts"] for r in store.rows("SELECT program_id, ir_insts FROM candidates WHERE cand_id LIKE 'baseline:%'")}
    xs, ys = [], []
    for r in store.rows("""SELECT c.program_id, c.ir_insts, m.speedup FROM measurements m JOIN candidates c ON c.cand_id=m.cand_id
                           WHERE m.stage IN ('screen','confirm','validate') AND m.speedup > 0 AND c.ir_insts > 0"""):
        b = base.get(r["program_id"])
        if b:
            xs.append(math.log(r["ir_insts"] / b))
            ys.append(math.log(r["speedup"]))
    if len(xs) < 10:
        return "IR-count vs runtime: not enough data."
    rho = spearmanr(xs, ys).statistic
    xs, ys = np.array(xs), np.array(ys)
    fewer = xs < -0.01
    return (f"IR-count vs runtime over {len(xs)} measured candidates: Spearman rho(log IR ratio, log speedup) = {rho:+.3f}. "
            f"Candidates with >1% fewer IR instructions than -O3: {fewer.mean() * 100:.0f}%, of which faster than -O3: "
            f"{(ys[fewer] > 0).mean() * 100:.0f}%; median speedup {math.exp(np.median(ys[fewer])):.3f}x.")


def _scatter_svg(pts: dict[str, list[tuple[float, float]]], path: Path) -> None:
    """Runtime (speedup vs -O3) vs binary size (ratio vs -O3), one colour per method."""
    W, H, pad = 640, 420, 50
    allp = [p for v in pts.values() for p in v] + [(1.0, 1.0)]
    xs = [p[0] for p in allp]
    ys = [p[1] for p in allp]
    x0, x1 = min(xs) * 0.95, max(xs) * 1.05
    y0, y1 = min(ys) * 0.98, max(ys) * 1.02
    sx = lambda x: pad + (math.log(x) - math.log(x0)) / (math.log(x1) - math.log(x0)) * (W - 2 * pad)
    sy = lambda y: H - pad - (math.log(y) - math.log(y0)) / (math.log(y1) - math.log(y0)) * (H - 2 * pad)
    cols = ["#2f6fdf", "#e0702b", "#2aa876", "#c2449f", "#8a6d1f", "#5b5bd6", "#d6455d", "#3b9ab2", "#777"]
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" font-family="sans-serif" font-size="11">',
           f'<rect width="{W}" height="{H}" fill="white"/>',
           f'<line x1="{sx(1)}" y1="{pad}" x2="{sx(1)}" y2="{H - pad}" stroke="#bbb" stroke-dasharray="4"/>',
           f'<line x1="{pad}" y1="{sy(1)}" x2="{W - pad}" y2="{sy(1)}" stroke="#bbb" stroke-dasharray="4"/>',
           f'<text x="{W / 2}" y="{H - 12}" text-anchor="middle">binary .text size vs -O3 (log)</text>',
           f'<text x="14" y="{H / 2}" transform="rotate(-90 14 {H / 2})" text-anchor="middle">speedup vs -O3 (log)</text>']
    for i, (m, v) in enumerate(sorted(pts.items())):
        c = cols[i % len(cols)]
        out += [f'<circle cx="{sx(x):.1f}" cy="{sy(y):.1f}" r="3.5" fill="{c}" fill-opacity="0.75"/>' for x, y in v]
        out.append(f'<rect x="{W - pad - 110}" y="{pad + i * 16 - 9}" width="10" height="10" fill="{c}"/>'
                   f'<text x="{W - pad - 95}" y="{pad + i * 16}">{m}</text>')
    out.append("</svg>")
    path.write_text("\n".join(out))


def report_eval(store: Store, tag: str, out_dir: Path) -> str:
    store.con.executescript(SCHEMA)
    rows = store.rows("SELECT * FROM eval_results WHERE tag=?", (tag,))
    if not rows:
        return f"No evaluation results for tag {tag}."
    by: dict[str, list] = {}
    for r in rows:
        by.setdefault(r["method"], []).append(r)
    progs = sorted({r["program_id"] for r in rows})
    lines = [f"# Evaluation `{tag}`: {len(progs)} held-out programs in {len({r['family'] for r in rows})} families", "",
             "| method | geomean (95% CI) | excl. largest | >=3% | >=5% | regressions | size (geomean) | compiled | timed |",
             "|---|---|---|---|---|---|---|---|---|"]
    summ = {}
    for m in ["O2", "Os", "topk", "topk_nodyn", "ml_top1", "random_topk", "rl_topk", "rl_lib_topk"] + sorted(k for k in by if "@" in k):
        if m not in by:
            continue
        rs = by[m]
        v = [r["speedup"] or 1.0 for r in rs]
        g, (lo, hi) = _geomean(v), _boot_geomean_ci(v)
        vs = sorted(v, reverse=True)
        gx = _geomean(vs[1:]) if len(vs) > 1 else float("nan")
        reg = sum(1 for r in rs if r["ci_hi"] is not None and r["ci_hi"] < 1.0)
        size = _geomean([r["text_ratio"] or 1.0 for r in rs])
        summ[m] = {"geomean": g, "ci": [lo, hi], "excl_largest": gx, "regressions": reg, "size": size}
        lines.append(f"| {m} | {(g - 1) * 100:+.2f}% ({(lo - 1) * 100:+.2f}..{(hi - 1) * 100:+.2f}) | {(gx - 1) * 100:+.2f}% | "
                     f"{sum(x >= 1.03 for x in v)}/{len(v)} | {sum(x >= 1.05 for x in v)}/{len(v)} | {reg} | {size:.3f} | "
                     f"{np.mean([r['n_compiled'] or 0 for r in rs]):.0f} | {np.mean([r['n_timed'] or 0 for r in rs]):.0f} |")
    ctrl = [abs((r["control"] or 1) - 1) * 100 for r in by.get("O3", [])]
    lines += ["", f"A/A control in the final runs: worst {max(ctrl):.2f}%, median {np.median(ctrl):.2f}%." if ctrl else "",
              "Regressions = the method shipped a binary whose final 95% CI lies below -O3.",
              "", ir_runtime_correlation(store)]
    pts = {m: [(r["text_ratio"] or 1.0, r["speedup"] or 1.0) for r in by[m]]
           for m in by if m in ("O2", "Os", "topk") or m.startswith("ga@")}
    out_dir.mkdir(parents=True, exist_ok=True)
    svg = out_dir / f"eval_{tag}_runtime_vs_size.svg"
    _scatter_svg(pts, svg)
    md = out_dir / f"eval_{tag}.md"
    md.write_text("\n".join(lines) + f"\n\n![runtime vs size]({svg.name})\n")
    (out_dir / f"eval_{tag}.json").write_text(json.dumps({"tag": tag, "programs": progs, "summary": summ}, indent=1))
    return "\n".join(lines) + f"\n\nSaved {md}, {svg}"


def repro(tc: Toolchain, cfg: Config, store: Store, recs: dict, tag: str, log=print) -> str:
    """Re-measure every shipped binary of an evaluation SERIALLY in a fresh run (new seed). Results are
    stored under tag '<tag>_serial' (methods that kept -O3 are copied at 1.000), so the reported numbers
    come from the serial protocol even when selection ran in parallel. Resumable per program."""
    store.con.executescript(SCHEMA)
    stag = f"{tag}_serial"
    allrows = store.rows("SELECT * FROM eval_results WHERE tag=?", (tag,))
    done = {r["program_id"] for r in store.rows("SELECT DISTINCT program_id FROM eval_results WHERE tag=?", (stag,))}
    out, diffs = [], []
    for pid in sorted({r["program_id"] for r in allrows} - done):
        prow = [r for r in allrows if r["program_id"] == pid]
        ps = ProgramSearch(tc, cfg, store, recs[pid], log=log)
        bins = {"BASE": ps.base.bin_path, "CTRL": ps.ctrl_path}
        for r in prow:
            if r["choice"] not in ("candidate", "level") or not r["genome_json"]:
                continue
            g = Genome.from_json(r["genome_json"])
            pipe, fl, be = (g.raw, (), next((e["value"] for e in g.edits if e["op"] == "backend"), 3)) if g.raw else materialize(ps.tree, g)
            b = tc.build(ps.src, pipe, be, ps.cflags, fl)
            if b.ok:
                bins[r["method"]] = b.bin_path
        ser = ps._measure(bins, cfg.reps, cfg.warmup, seed=777)
        ctrl = paired_speedup(ser["BASE"].wall_ms, ser["CTRL"].wall_ms)
        new_rows = []
        for r in prow:
            d = dict(r)
            d["tag"] = stag
            d["control"] = ctrl.get("speedup")
            d["ts"] = time.strftime("%Y-%m-%dT%H:%M:%S")
            if r["method"] in bins:
                sp = paired_speedup(ser["BASE"].wall_ms, ser[r["method"]].wall_ms)
                d["speedup"], d["ci_lo"], d["ci_hi"] = sp.get("speedup"), sp.get("ci_lo"), sp.get("ci_hi")
                if sp.get("speedup") and r["speedup"]:
                    diffs.append(abs(math.log(sp["speedup"] / r["speedup"])) * 100)
                    out.append(f"{pid:<40s} {r['method']:<12s} parallel {r['speedup']:.3f}x  serial {sp['speedup']:.3f}x "
                               f"[{sp['ci_lo']:.3f},{sp['ci_hi']:.3f}]")
            new_rows.append(tuple(d[k] for k in ("tag", "program_id", "family", "method", "choice", "genome_json",
                                                 "speedup", "ci_lo", "ci_hi", "text_ratio", "compile_s", "timing_s",
                                                 "n_compiled", "n_timed", "select_speedup", "control", "ts")))
        store.con.executemany("INSERT OR REPLACE INTO eval_results VALUES(" + ",".join("?" * 17) + ")", new_rows)
        store.con.commit()
        log(f"[{pid}] serial re-measurement stored under {stag} (ctrl {ctrl.get('speedup', float('nan')):.3f})")
    out.append(f"\nMedian |difference| {np.median(diffs):.2f}%, max {max(diffs):.2f}% over {len(diffs)} shipped binaries."
               if diffs else "Nothing (more) to reproduce.")
    return "\n".join(out)
