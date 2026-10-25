"""Parallel timing: one worker process per timing core, each running whole programs.

Timing stays exactly as in the serial harness (pinned, interleaved, paired against the program's
own -O3 baseline on the SAME core), so frequency and thermal changes still hit both sides of every
comparison. What parallelism adds is contention between cores (shared L3, memory bandwidth, lower
all-core turbo); `aatest` measures whether that hurts before parallel timing is used for data.

Layout: each timing core's SMT sibling stays idle; compiles, verification and the harness run on
the remaining "helper" CPUs. Workers share the launcher's session, so the quiet guard ignores
them (it only counts load from other sessions).
"""
from __future__ import annotations

import json
import math
import multiprocessing as mp
import os
import shutil
import sys
import time
import traceback
from pathlib import Path

import numpy as np


def helper_set(timing_cpus: list[int]) -> list[int]:
    from .timing import smt_siblings
    busy: set[int] = set()
    for c in timing_cpus:
        busy |= smt_siblings(c)
    return sorted(set(os.sched_getaffinity(0)) - busy)


def _setup(cfg_path: str, cpu: int, timing_cpus: list[int], compile_workers: int):
    from .config import load_config
    from .timing import configure
    from .toolchain import Toolchain
    cfg = load_config(cfg_path)
    cfg.timing_cpu = cpu
    cfg.compile_workers = compile_workers
    helpers = helper_set(timing_cpus)
    os.sched_setaffinity(0, set(helpers) | {cpu})      # compiles inherit helpers; benchmark runs pin to cpu
    configure(no_aslr=cfg.no_aslr, settle_s=cfg.settle_s, isolate_sibling=cfg.isolate_sibling,
              quiet_max_busy=cfg.quiet_max_busy, quiet_max_wait_s=cfg.quiet_max_wait_s,
              layout_copies=cfg.layout_copies)
    return cfg, Toolchain(cfg)


MEM_MPKI = 20.0    # simulated L2 data misses per 1000 instructions (traffic reaching the shared L3/memory) above which a program counts as memory-heavy


def _take(pool, mem_running, lock, max_mem: int):
    """Next program, longest first, never letting more than max_mem memory-bound programs run at
    once (two memory-bound programs on different cores distort each other's timings; aatest).
    Returns None when nothing is left, "wait" when only memory-bound programs remain and the slot is busy."""
    with lock:
        if len(pool) == 0:
            return None
        for i in range(len(pool)):
            rec = pool[i]
            if not rec.get("_mem") or mem_running.value < max_mem:
                pool.pop(i)
                if rec.get("_mem"):
                    mem_running.value += 1
                return rec
        return "wait"


def _worker(job: str, cfg_path: str, cpu: int, timing_cpus: list[int], pool, mem_running, lock, max_mem: int,
            kw: dict, compile_workers: int):
    from .db import Store
    cfg, tc = _setup(cfg_path, cpu, timing_cpus, compile_workers)
    store = Store(cfg.db_path)
    tag = f"[cpu{cpu}]"

    def log(*a, **k):
        print(tag, *a, flush=True)

    while True:
        rec = _take(pool, mem_running, lock, max_mem)
        if rec is None:
            break
        if rec == "wait":
            time.sleep(5)
            continue
        pid = rec["program_id"]
        log(f"start {pid}{' (memory-bound)' if rec.get('_mem') else ''}")
        t0 = time.time()
        try:
            if job in ("search", "collect"):
                from .search import run_program
                run_program(tc, cfg, store, rec, kw["methods"], kw["budget"], kw["seed"], kw.get("force", False), log=log)
            if job == "evaluate":
                from .evaluate import run_eval
                run_eval(tc, cfg, store, [rec], Path(kw["meta"]), kw["k"], kw["tag"],
                         Path(kw["nodyn"]) if kw.get("nodyn") else None, Path(kw["rl"]) if kw.get("rl") else None,
                         budget=kw.get("budget"), log=log,
                         only=set(kw["only"]) if kw.get("only") else None, confirm_reps=kw.get("confirm_reps", 0))
            if job in ("passkb", "collect") and not kw.get("no_passkb"):
                from .passkb import run_passkb
                run_passkb(tc, cfg, store, rec, force=kw.get("force", False), add_one=kw.get("add_one", True), log=log)
        except Exception as e:
            log(f"[{pid}] FAILED: {e!r}\n{traceback.format_exc()[-800:]}")
        finally:
            if rec.get("_mem"):
                with lock:
                    mem_running.value -= 1
        log(f"done {pid} ({time.time() - t0:.0f}s)")


def mark_memory_bound(recs: list[dict], db_path: str) -> list[dict]:
    """Tag each record with _mem from the simulated cachegrind LL miss rate (unknown => memory-bound,
    the safe side)."""
    from .db import Store
    from .features import program_features
    pf = program_features(Store(db_path), ("sim_l2",))
    out = []
    for r in recs:
        r = dict(r)
        m = pf.get(r["program_id"], {}).get("sim_l2d_mpki")
        r["_mem"] = True if m is None else m >= MEM_MPKI
        out.append(r)
    return out


def run_parallel(job: str, cfg_path: str, recs: list[dict], timing_cpus: list[int], kw: dict,
                 max_mem: int = 1) -> None:
    """Distribute programs (longest -O3 runtime first) over one worker per timing core, with at
    most `max_mem` memory-bound programs running at any time."""
    from .config import load_config
    helpers = helper_set(timing_cpus)
    if not helpers:
        sys.exit("no helper CPUs left for compiles; use fewer timing cores")
    cw = max(1, (len(helpers) * 2) // len(timing_cpus))
    recs = mark_memory_bound(recs, load_config(cfg_path).db_path)
    ctx = mp.get_context("spawn")
    mgr = ctx.Manager()
    pool = mgr.list(sorted(recs, key=lambda r: -(r.get("times_ms") or {}).get("O3", 0)))
    mem_running, lock = ctx.Value("i", 0), ctx.Lock()
    n_mem = sum(1 for r in recs if r["_mem"])
    print(f"parallel {job}: {len(recs)} programs ({n_mem} memory-bound, at most {max_mem} at a time) on timing "
          f"cores {timing_cpus}, helpers {helpers}, {cw} compile threads per worker", flush=True)
    ps = [ctx.Process(target=_worker, args=(job, cfg_path, c, timing_cpus, pool, mem_running, lock, max_mem, kw, cw))
          for c in timing_cpus]
    for p in ps:
        p.start()
        time.sleep(0.5)
    for p in ps:
        p.join()


# ---------------------------------------------------------------------- multi-core A/A test
def _aa_job(cfg_path: str, cpu: int, timing_cpus: list[int], rec: dict, win_key: str | None,
            reps: int, seed: int, barrier, out_q, done=None):
    """One measurement on one core: BASE (-O3), CTRL (byte-identical copy of BASE) and, if
    available, the program's validated winner, interleaved."""
    from .db import Store
    from .search import ProgramSearch
    from .timing import paired_speedup
    cfg, tc = _setup(cfg_path, cpu, timing_cpus, 1)
    store = Store(cfg.db_path)
    ps = ProgramSearch(tc, cfg, store, rec, log=lambda *a: None)
    bins = {"BASE": ps.base.bin_path, "CTRL": ps.ctrl_path}
    if win_key:
        e = ps._eval_from_db(win_key)
        if e and not e.same_as_o3:
            bins["WIN"] = e.bin_path
    if barrier is not None:
        barrier.wait()
    t0 = time.time()
    ser = ps._measure(bins, reps, cfg.warmup, seed)
    res = {"program": rec["program_id"], "cpu": cpu, "wall_s": round(time.time() - t0, 1),
           "base_median_ms": float(np.nanmedian(ser["BASE"].wall_ms)),
           "aa": paired_speedup(ser["BASE"].wall_ms, ser["CTRL"].wall_ms)}
    a = np.log(np.asarray(ser["BASE"].wall_ms, float) / np.asarray(ser["CTRL"].wall_ms, float))
    res["aa_iqr_pct"] = float(np.subtract(*np.nanpercentile(a, [75, 25])) * 100)
    if "WIN" in bins:
        res["win"] = paired_speedup(ser["BASE"].wall_ms, ser["WIN"].wall_ms)
    out_q.put(res)
    if done is not None:
        # keep this core loaded until every core has finished, so contention stays constant
        from .timing import RunSpec, run_spec
        with done.get_lock():
            done.value += 1
        spec = RunSpec.from_dict(rec["time_spec"])
        while done.value < len(timing_cpus):
            run_spec(ps.base.bin_path, spec, cpu, ps.timeout)


def aatest(cfg_path: str, recs: list[dict], win_keys: dict[str, str | None], timing_cpus: list[int],
           reps: int, rounds: int, out_dir: Path) -> str:
    """Serial reference (one core at a time, others idle) vs all cores at once, rotating programs
    across cores each round. Pass = in parallel mode every A/A is within 1% of 1.000 with its CI
    containing 1.000 (the selftest rule), A/A noise does not grow by more than 2x, and known
    speedups agree with the serial measurement within 1%."""
    ctx = mp.get_context("spawn")
    n = len(timing_cpus)
    if len(recs) != n:
        raise SystemExit(f"aatest needs exactly one program per timing core ({n}), got {len(recs)}")
    rows = []
    for r in range(rounds):
        assign = [(timing_cpus[(i + r) % n], recs[i]) for i in range(len(recs))]
        for mode in ("serial", "parallel"):
            q = ctx.Queue()
            if mode == "serial":
                for cpu, rec in assign:
                    p = ctx.Process(target=_aa_job, args=(cfg_path, cpu, timing_cpus, rec, win_keys.get(rec["program_id"]),
                                                          reps, 100 * r + 1, None, q))
                    p.start()
                    p.join()
            else:
                bar = ctx.Barrier(len(assign))
                done = ctx.Value("i", 0)
                ps = [ctx.Process(target=_aa_job, args=(cfg_path, cpu, timing_cpus, rec, win_keys.get(rec["program_id"]),
                                                        reps, 100 * r + 2, bar, q, done)) for cpu, rec in assign]
                for p in ps:
                    p.start()
                for p in ps:
                    p.join()
            for _ in assign:
                res = q.get()
                res.update(mode=mode, round=r)
                rows.append(res)
                aa = res["aa"]
                w = res.get("win", {})
                print(f"  round {r} {mode:<8s} cpu{res['cpu']:<3d} {res['program']:<36s} A/A {aa.get('speedup', float('nan')):.4f} "
                      f"[{aa.get('ci_lo', float('nan')):.4f},{aa.get('ci_hi', float('nan')):.4f}] iqr {res['aa_iqr_pct']:.2f}% "
                      f"base {res['base_median_ms']:.0f}ms" + (f" | winner {w['speedup']:.3f}x" if w.get("speedup") else ""),
                      flush=True)
    # verdict
    lines = ["", f"{'program':<36s} {'mode':<8s} {'A/A bias% (max)':>15s} {'CI has 1':>9s} {'A/A IQR%':>9s} "
                 f"{'runtime vs serial':>18s} {'winner':>8s}"]
    ok = True
    by = {}
    for x in rows:
        by.setdefault((x["program"], x["mode"]), []).append(x)
    for rec in recs:
        p = rec["program_id"]
        ser, par = by.get((p, "serial"), []), by.get((p, "parallel"), [])
        base_ser = np.median([x["base_median_ms"] for x in ser]) if ser else float("nan")
        for mode, xs in (("serial", ser), ("parallel", par)):
            bias = max(abs(x["aa"].get("speedup", 2) - 1) * 100 for x in xs)
            has1 = all(x["aa"].get("ci_lo", 2) <= 1 <= x["aa"].get("ci_hi", 0) for x in xs)
            iqr = np.median([x["aa_iqr_pct"] for x in xs])
            infl = np.median([x["base_median_ms"] for x in xs]) / base_ser
            wins = [x["win"]["speedup"] for x in xs if x.get("win", {}).get("speedup")]
            wcell = f"{np.median(wins):.3f}x" if wins else "-"
            lines.append(f"{p:<36s} {mode:<8s} {bias:>15.2f} {str(has1):>9s} {iqr:>9.2f} {infl:>17.3f}x {wcell:>8s}")
            if mode == "parallel":
                if bias > 1.0 or not has1:
                    ok = False
                ser_iqr = np.median([x["aa_iqr_pct"] for x in ser]) if ser else float("nan")
                if iqr > 2 * max(ser_iqr, 0.2):
                    ok = False
                sw = [x["win"]["speedup"] for x in ser if x.get("win", {}).get("speedup")]
                if wins and sw and abs(math.log(np.median(wins) / np.median(sw))) > 0.01:
                    ok = False
    verdict = "PASS: parallel timing on these cores is as trustworthy as serial" if ok else \
        "FAIL: parallel timing distorts measurements (see rows above); use fewer cores or stay serial"
    lines += ["", f"MULTI-CORE A/A ({len(timing_cpus)} cores {timing_cpus}, {rounds} rounds, {reps} reps): {verdict}"]
    out_dir.mkdir(parents=True, exist_ok=True)
    p = out_dir / f"aatest_{len(timing_cpus)}cores_{time.strftime('%Y%m%d-%H%M%S')}.json"
    p.write_text(json.dumps({"timing_cpus": timing_cpus, "reps": reps, "rounds": rounds, "rows": rows,
                             "pass": ok}, indent=1, default=str))
    lines.append(f"saved {p}")
    return "\n".join(lines)
