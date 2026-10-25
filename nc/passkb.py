"""Per-pass knowledge base (Phase 4): single edits around the -O3 pipeline, per program.

Edits tried (each alone, on top of -O3):
  loo        delete one pass instance                       (leave-one-out)
  flip       flip one option of one pass instance           (e.g. simplifycfg sink-common-insts)
  family     delete / flip an option on EVERY instance of a pass
  add        insert one pass from the context's pool at the first and last position of that context
  knob       one opt/llc knob value
  backend    llc -O0/-O1/-O2
Most edits are no-ops for a given program: identical IR or binary is detected by hashing and costs
no timing (and "no-op on this program" is itself recorded). Distinct binaries are verified and
screened like search candidates; the ones with a clear screening effect are confirmed together
in one interleaved run with an A/A control.

Effects are kept per program. The attribution report shows their DISTRIBUTION across programs
(no averaging into one number, no "top passes" list): passes interact, and the same deletion can
speed one program up and slow another down.
"""
from __future__ import annotations

import csv
import json
import math
import time
from pathlib import Path

from .config import Config
from .db import Store
from .pipeline import KNOBS_V2, Genome, _ctx_of, _opts, _walk, pass_name
from .search import Budget, ProgramSearch
from .toolchain import Toolchain

SCHEMA = """
CREATE TABLE IF NOT EXISTS pass_effects(
  program_id TEXT, kind TEXT, label TEXT, pass TEXT, ctx TEXT, edit_json TEXT, cand_id TEXT,
  status TEXT, noop INTEGER, screen_sp REAL, screen_n INTEGER, conf_sp REAL, ci_lo REAL, ci_hi REAL,
  text_ratio REAL, opt_ms_ratio REAL, ir_ratio REAL, ts TEXT,
  PRIMARY KEY(program_id, label));
"""


def single_edits(ps: ProgramSearch, add_one: bool = True) -> list[tuple[str, str, str, str, dict]]:
    """(kind, label, pass, ctx, edit). Labels are stable across programs (they name the pass
    instance by its position in the -O3 pipeline, not by the program)."""
    tree, sp = ps.tree, ps.space
    out = []
    leaves = [(p, i, n) for p, i, n in _walk(tree) if n.is_leaf]
    by_ctx: dict[str, list] = {}
    for p, i, n in sorted(leaves, key=lambda t: t[2].id):
        ctx = _ctx_of(p, tree)
        by_ctx.setdefault(ctx, []).append(n)
        name = pass_name(n.text)
        out.append(("loo", f"del #{n.id} {name}", name, ctx, {"op": "del", "id": n.id}))
        for f in sp.params:
            if f["pass"] == name and f["ctx"] == ctx and f["tok"] in _opts(n.text):
                out.append(("flip", f"#{n.id} {name} {f['tok']}->{f['new']}", name, ctx,
                            {"op": "param", "id": n.id, "tok": f["tok"], "new": f["new"]}))
    for name in sp.multi:
        out.append(("family", f"del EVERY {name}", name, "*", {"op": "del_all", "pass": name}))
    seen = set()
    for f in sp.params:
        k = (f["pass"], f["tok"], f["new"])
        if k not in seen:
            seen.add(k)
            out.append(("family", f"EVERY {f['pass']} {f['tok']}->{f['new']}", f["pass"], "*",
                        {"op": "param_all", "pass": f["pass"], "tok": f["tok"], "new": f["new"]}))
    if add_one:
        for ctx, nodes in by_ctx.items():
            anchors = {nodes[0].id: "first", nodes[-1].id: "last"}
            for passname in sp.pools.get(ctx, []):
                for aid, where in anchors.items():
                    out.append(("add", f"add {passname} @{where} {ctx}", pass_name(passname), ctx,
                                {"op": "ins", "after": aid, "pass": passname, "ctx": ctx, "nid": 900000000 + len(out)}))
    for k, vs in sp.knobs.items():
        for v in vs:
            out.append(("knob", f"{k}={v}", k, "llc" if k.startswith("llc:") else "opt",
                        {"op": "knob", "name": k, "value": v}))
    for b in (0, 1, 2):
        out.append(("backend", f"llc -O{b}", "llc", "backend", {"op": "backend", "value": b}))
    return out


def run_passkb(tc: Toolchain, cfg: Config, store: Store, rec: dict, confirm_thr: float = 0.02,
               confirm_max: int = 10, force: bool = False, add_one: bool = True, log=print) -> None:
    store.con.executescript(SCHEMA)
    pid = rec["program_id"]
    if not force and store.rows("SELECT 1 FROM runs WHERE program_id=? AND method='passkb' AND finished IS NOT NULL", (pid,)):
        log(f"[{pid}] passkb already done, skipping")
        return
    t0 = time.time()
    started = time.strftime("%Y-%m-%dT%H:%M:%S")
    ps = ProgramSearch(tc, cfg, store, rec, log=log)
    edits = single_edits(ps, add_one=add_one)
    cache: dict = {}
    bud = Budget()
    evs = ps.evaluate([Genome([e[4]]) for e in edits], "passkb", 0, cache, bud)
    base_row = store.get_candidate(f"baseline:{pid}")
    base_opt = (base_row["opt_ms"] or 1.0) if base_row else 1.0
    base_ir = (base_row["ir_insts"] or 1) if base_row else 1
    # confirm the clearest effects (both directions) in one interleaved run
    timed = [ev for ev in evs if ev.status == "ok" and not ev.same_as_o3 and ev.speedup]
    uniq: dict[str, object] = {}
    for ev in sorted(timed, key=lambda e: -abs(math.log(e.speedup))):
        if abs(math.log(ev.speedup)) >= math.log(1 + confirm_thr) and ev.bin_hash not in uniq:
            uniq[ev.bin_hash] = ev
    conf: dict = {}
    if uniq:
        items = [("passkb", ev) for ev in list(uniq.values())[:confirm_max]]
        with ps.stage("confirm"):
            res = ps.confirm_many(items, "passkb_confirm", seed=11)
        for _m, ev in items:
            r = res.get(f"passkb:{ev.cand_id}", {})
            if "speedup" in r:
                conf[ev.bin_hash] = r
    rows = []
    for (kind, label, pname, ctx, edit), ev in zip(edits, evs):
        c = store.get_candidate(f"passkb:{ev.cand_id}")
        r = conf.get(ev.bin_hash, {})
        rows.append((pid, kind, label, pname, ctx, json.dumps(edit), ev.cand_id, ev.status, int(ev.same_as_o3),
                     ev.speedup, None, r.get("speedup"), r.get("ci_lo"), r.get("ci_hi"),
                     (ev.text_size / ps.base.text_size) if ev.text_size and ps.base.text_size else None,
                     ((c["opt_ms"] or 0) / base_opt) if c else None,
                     ((c["ir_insts"] or 0) / base_ir) if c else None, time.strftime("%Y-%m-%dT%H:%M:%S")))
    store.con.executemany("INSERT OR REPLACE INTO pass_effects VALUES(" + ",".join("?" * 18) + ")", rows)
    store.con.commit()
    n_noop = sum(1 for ev in evs if ev.same_as_o3)
    summary = {"edits": len(edits), "noop": n_noop, "timed": bud.timed, "confirmed": len(conf),
               "stage_s": {k: round(v, 1) for k, v in ps.stage_s.items()}}
    store.put_run({"run_id": f"{pid}:passkb:0", "program_id": pid, "method": "passkb", "seed": 0, "budget": 0,
                   "started": started, "finished": time.strftime("%Y-%m-%dT%H:%M:%S"),
                   "config_json": json.dumps({"confirm_thr": confirm_thr, "confirm_max": confirm_max, "add_one": add_one}),
                   "summary_json": json.dumps(summary)})
    log(f"[{pid}] passkb: {len(edits)} edits, {n_noop} no-op (identical binary), {bud.timed} timed, "
        f"{len(conf)} confirmed  ({time.time() - t0:.0f}s: " +
        " ".join(f"{k} {v:.0f}s" for k, v in ps.stage_s.items()) + ")")


def report_passkb(store: Store, out_dir: Path, sig_screen: float = 0.02) -> str:
    """Attribution table (per edit: how many programs it is a no-op on / significantly faster /
    significantly slower, plus the spread of screening effects) and the pruned action set."""
    store.con.executescript(SCHEMA)
    rows = store.rows("SELECT * FROM pass_effects")
    if not rows:
        return "No pass-effect data yet. Run: python -m nc.cli passkb run ..."
    by: dict[str, list] = {}
    for r in rows:
        by.setdefault(r["label"], []).append(r)
    progs = sorted({r["program_id"] for r in rows})
    table = []
    for label, rs in by.items():
        eff = [math.log(r["screen_sp"]) for r in rs if r["screen_sp"] and not r["noop"] and r["status"] == "ok"]
        fast = sum(1 for r in rs if r["ci_lo"] and r["ci_lo"] > 1.0)
        slow = sum(1 for r in rs if r["ci_hi"] and r["ci_hi"] < 1.0)
        noop = sum(1 for r in rs if r["noop"])
        broken = sum(1 for r in rs if r["status"] not in ("ok", "slow"))
        bigs = sum(1 for e in eff if abs(e) >= math.log(1 + sig_screen))
        q = sorted(eff)
        table.append({"label": label, "kind": rs[0]["kind"], "pass": rs[0]["pass"], "programs": len(rs),
                      "noop": noop, "broken": broken, "slow_killed": sum(1 for r in rs if r["status"] == "slow"),
                      "conf_faster": fast, "conf_slower": slow, "screen_big": bigs,
                      "screen_min": math.exp(q[0]) if q else None, "screen_med": math.exp(q[len(q) // 2]) if q else None,
                      "screen_max": math.exp(q[-1]) if q else None,
                      "edit": rs[0]["edit_json"]})
    # pruned action set: edits that change the binary somewhere AND matter somewhere
    keep = [t for t in table if t["noop"] < t["programs"] and (t["conf_faster"] or t["conf_slower"] or t["screen_big"] >= 2)]
    ranked = sorted(keep, key=lambda t: (t["conf_faster"], t["conf_faster"] + t["conf_slower"], t["screen_big"]), reverse=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d-%H%M%S")
    csv_path = out_dir / f"passkb_attribution_{ts}.csv"
    with csv_path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(table[0]))
        w.writeheader()
        for t in sorted(table, key=lambda t: (t["kind"], t["label"])):
            w.writerow(t)
    act_path = out_dir / "passkb_actions.json"
    act_path.write_text(json.dumps({"created": ts, "programs": progs,
                                    "actions": [{"label": t["label"], "kind": t["kind"], "edit": json.loads(t["edit"]),
                                                 "conf_faster": t["conf_faster"], "conf_slower": t["conf_slower"],
                                                 "screen_big": t["screen_big"]} for t in ranked]}, indent=1))
    kinds: dict[str, list[int]] = {}
    for t in table:
        k = kinds.setdefault(t["kind"], [0, 0, 0])
        k[0] += 1
        k[1] += t["noop"] == t["programs"]
        k[2] += t in keep
    lines = [f"Pass-effect experiments on {len(progs)} programs, {len(table)} distinct edits.",
             f"{'kind':<8s} {'edits':>6s} {'no-op everywhere':>17s} {'kept':>5s}"]
    lines += [f"{k:<8s} {v[0]:>6d} {v[1]:>17d} {v[2]:>5d}" for k, v in sorted(kinds.items())]
    lines += ["", f"Pruned action set: {len(keep)} edits -> {act_path}",
              "Top mutation targets (programs where confirmed faster / slower / big screening effect, screening range):"]
    for t in ranked[:25]:
        rng = f"{t['screen_min']:.3f}..{t['screen_max']:.3f}" if t["screen_min"] else "-"
        lines.append(f"  {t['label']:<60s} +{t['conf_faster']} -{t['conf_slower']} big {t['screen_big']}  [{rng}]  of {t['programs']}")
    lines.append(f"\nFull table: {csv_path}")
    return "\n".join(lines)
