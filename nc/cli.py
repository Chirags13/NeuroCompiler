"""Command line entry points:  python -m nc.cli {env,o3pipeline,baselines,selftest}"""
from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import sys
import time
from pathlib import Path

from .config import load_config
from . import corpus as corp
from . import search as srch
from .db import Store
from .envcheck import collect_env, format_env
from .timing import (aslr_disabled_for_children, configure, drift_pct, measure_interleaved,
                     measure_sequential, measurement_env, paired_speedup, reference_hash, summarize)
from .toolchain import Toolchain

# name -> (opt pipeline, llc backend level). Mirrors clang's level -> backend mapping.
LEVELS = {
    "O0": ("default<O0>", 0),
    "O1": ("default<O1>", 1),
    "O2": ("default<O2>", 2),
    "O3": ("default<O3>", 3),
    "Os": ("default<Os>", 2),
}


def _save(cfg, name: str, payload: dict) -> Path:
    d = Path(cfg.results_dir)
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{name}_{cfg.machine_id}_{time.strftime('%Y%m%d-%H%M%S')}.json"
    p.write_text(json.dumps(payload, indent=2))
    return p


def _must_build(tc: Toolchain, src, pipeline, backend):
    b = tc.build(src, pipeline, backend)
    if not b.ok:
        sys.exit(f"Build failed ({b.status}) for {pipeline}:\n{b.error}")
    return b


# ------------------------------------------------------------------ env
def cmd_env(cfg, tc, _a):
    print(format_env(collect_env(cfg, tc)))


def cmd_o3pipeline(cfg, tc, _a):
    s = tc.pipeline_string("O3")
    out = Path(cfg.results_dir) / f"o3_pipeline_llvm{tc.version()}.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(s + "\n")
    print(s)
    print(f"\nSaved to {out}  (LLVM {tc.version()}, {len(s)} chars)")


# ------------------------------------------------------------------ baselines
def cmd_baselines(cfg, tc, a):
    args = shlex.split(a.args)
    builds = {k: _must_build(tc, a.src, p, bo) for k, (p, bo) in LEVELS.items()}
    cl = tc.build_clang_direct(a.src, "-O3")
    if cl.ok:
        builds["clang-O3"] = cl
    ref = reference_hash(builds["O0"].bin_path, args, cfg.timing_cpu, cfg.timeout_s)
    ser = measure_interleaved({k: b.bin_path for k, b in builds.items()}, args,
                              a.reps or cfg.reps, cfg.warmup, cfg.timing_cpu,
                              cfg.timeout_s, expected_hash=ref)
    base = ser["O3"].wall_ms
    print(f"\nBaselines for {a.src}  args={args}  LLVM {tc.version()}  machine={cfg.machine_id}\n")
    print(f"{'level':9s} {'median ms':>10s} {'ci95 +-%':>9s} {'vs O3':>16s} {'text B':>8s} {'IR inst':>8s} {'opt+llc ms':>10s}  status")
    rows = {}
    for k, b in builds.items():
        s = summarize(ser[k].wall_ms)
        sp = paired_speedup(base, ser[k].wall_ms) if k != "O3" else {}
        vs = f"{sp['speedup']:.3f}x [{sp['ci_lo']:.2f},{sp['ci_hi']:.2f}]" if sp.get("n") else "-"
        med = f"{s['median_ms']:.1f}" if "median_ms" in s else "-"
        hw = f"{s['ci_halfwidth_pct']:.2f}" if "median_ms" in s else "-"
        print(f"{k:9s} {med:>10s} {hw:>9s} {vs:>16s} {b.text_size:>8d} {b.ir_inst_count:>8d} {b.opt_ms + b.backend_ms:>10.0f}  {ser[k].status}")
        rows[k] = {"build": b.to_dict(), "summary": s, "vs_O3": sp, "status": ser[k].status,
                   "raw_wall_ms": ser[k].wall_ms}
    print("\n'vs O3' > 1 means faster than O3. Brackets are 95% bootstrap CIs on paired rounds.")
    p = _save(cfg, "baselines", {"src": a.src, "args": args, "llvm": tc.version(), "rows": rows})
    print(f"Saved {p}")


# ------------------------------------------------------------------ selftest
def _verdict(ok: bool) -> str:
    return "PASS" if ok else "FAIL"


def cmd_selftest(cfg, tc, a):
    args = shlex.split(a.args)
    reps = a.reps or cfg.reps
    env = collect_env(cfg, tc)
    print("== Environment ==")
    print(format_env(env))
    if env["llvm_version"] == "missing":
        sys.exit("LLVM not found.")

    o3 = _must_build(tc, a.src, *LEVELS["O3"])
    o0 = _must_build(tc, a.src, *LEVELS["O0"])
    cl = tc.build_clang_direct(a.src, "-O3")
    ref = reference_hash(o0.bin_path, args, cfg.timing_cpu, cfg.timeout_s)
    with measurement_env(cfg.timing_cpu):
        aslr_off = aslr_disabled_for_children()
    print(f"\nBenchmark settings: ASLR disabled for children = {aslr_off} (requested: {cfg.no_aslr}), "
          f"settle {cfg.settle_s}s, warmup {cfg.warmup}, pinned vCPU {cfg.timing_cpu}")
    results: dict = {"env": env, "src": a.src, "args": args, "reps": reps,
                     "aslr_disabled": aslr_off, "settle_s": cfg.settle_s, "warmup": cfg.warmup}
    passed = []

    # 1. repeatability + drift of one binary
    print(f"\n== 1. Repeatability: one binary, {reps + 10} back-to-back runs ==")
    seq = measure_sequential(o3.bin_path, args, reps + 10, cfg.warmup, cfg.timing_cpu, cfg.timeout_s)
    s = summarize(seq.wall_ms)
    dr = drift_pct(seq.wall_ms)
    ok1 = s.get("ci_halfwidth_pct", 99) <= cfg.max_ci_halfwidth_pct and abs(dr) <= cfg.max_drift_pct
    print(f"   median {s.get('median_ms', float('nan')):.1f} ms | CI half-width {s.get('ci_halfwidth_pct', float('nan')):.2f}% "
          f"(limit {cfg.max_ci_halfwidth_pct}%) | IQR {s.get('iqr_pct', float('nan')):.2f}% | drift {dr:+.2f}% (limit +-{cfg.max_drift_pct}%)  -> {_verdict(ok1)}")
    if s.get("median_ms", 1e9) < 100:
        print("   note: runtime < 100 ms; timer noise dominates. Increase the program's input size.")
    results["repeatability"] = {"summary": s, "drift_pct": dr, "pass": ok1, "raw": seq.wall_ms}
    passed.append(ok1)

    # 2. A/A: the same binary under two paths, interleaved
    print("\n== 2. A/A test: identical binary at two paths, interleaved ==")
    copy = Path(cfg.work_dir) / "tmp" / "prog_copy"
    shutil.copy2(o3.bin_path, copy)
    aa = measure_interleaved({"A": o3.bin_path, "B": copy}, args, reps, cfg.warmup, cfg.timing_cpu,
                             cfg.timeout_s, seed=1, expected_hash=ref)
    sp = paired_speedup(aa["A"].wall_ms, aa["B"].wall_ms)
    bias = abs(sp.get("speedup", 9) - 1) * 100
    ok2 = bias <= cfg.max_aa_bias_pct and sp.get("ci_lo", 2) <= 1 <= sp.get("ci_hi", 0)
    print(f"   A/B = {sp.get('speedup', float('nan')):.4f} [{sp.get('ci_lo', float('nan')):.4f}, {sp.get('ci_hi', float('nan')):.4f}] "
          f"| bias {bias:.2f}% (limit {cfg.max_aa_bias_pct}%), CI must contain 1.0  -> {_verdict(ok2)}")
    results["aa"] = {"paired": sp, "pass": ok2}
    passed.append(ok2)

    # 3. sensitivity + correctness across levels
    print("\n== 3. Sensitivity: -O0 vs -O3, outputs must match ==")
    names = {"O0": o0.bin_path, "O3": o3.bin_path}
    if cl.ok:
        names["clang-O3"] = cl.bin_path
    ser = measure_interleaved(names, args, reps, cfg.warmup, cfg.timing_cpu, cfg.timeout_s,
                              seed=2, expected_hash=ref)
    sp = paired_speedup(ser["O0"].wall_ms, ser["O3"].wall_ms)
    ok3 = sp.get("ci_lo", 0) >= cfg.min_o0_o3_speedup and all(v.status == "ok" for v in ser.values())
    print(f"   O3 vs O0: {sp.get('speedup', float('nan')):.2f}x [{sp.get('ci_lo', float('nan')):.2f}, {sp.get('ci_hi', float('nan')):.2f}] "
          f"(need CI lower bound >= {cfg.min_o0_o3_speedup}) | statuses {[v.status for v in ser.values()]}  -> {_verdict(ok3)}")
    results["sensitivity"] = {"paired": sp, "pass": ok3,
                              "status": {k: v.status for k, v in ser.items()}}
    passed.append(ok3)

    # 4. fidelity: our opt+llc path vs plain clang -O3 (informational)
    print("\n== 4. Pipeline fidelity (info): opt default<O3> + llc  vs  clang -O3 ==")
    if cl.ok:
        fp = paired_speedup(ser["clang-O3"].wall_ms, ser["O3"].wall_ms)
        gap = abs(fp.get("speedup", 1) - 1) * 100
        note = "OK" if gap <= 3 else "WARN: use our own O3 path as the baseline everywhere, and tell me"
        print(f"   ours / clang = {fp.get('speedup', float('nan')):.3f}x [{fp.get('ci_lo', float('nan')):.3f}, {fp.get('ci_hi', float('nan')):.3f}] "
              f"| gap {gap:.1f}%  -> {note}")
        results["fidelity"] = {"paired": fp, "gap_pct": gap}
    else:
        print("   clang -O3 reference build failed; skipped.")

    all_ok = all(passed)
    print("\n== Verdict ==")
    if all_ok:
        print("   PASS: this environment is usable for the pilot. Measured noise floor above is what any result must beat.")
    else:
        print("   FAIL: do not collect training data yet. Try, in order:"
              "\n   1) python -m nc.cli cpusweep " + a.src + "   (finds the quietest vCPU; then set timing_cpu in config.toml)"
              "\n   2) plug in + Windows 'Best performance' mode; close browsers, AV scans, Docker Desktop, games"
              "\n   3) raise --reps (shrinks CI width, but not bias) or use a longer-running input"
              "\n   Then re-run.")
    results["verdict"] = "PASS" if all_ok else "FAIL"
    p = _save(cfg, "selftest", results)
    print(f"   report saved: {p}")
    return 0 if all_ok else 1


# ------------------------------------------------------------------ cpusweep
def cmd_cpusweep(cfg, tc, a):
    args = shlex.split(a.args)
    allowed = sorted(os.sched_getaffinity(0))
    cands = allowed if a.include0 else [c for c in allowed if c != 0]
    if not cands:
        sys.exit("Only one CPU is visible; nothing to sweep. Raise `processors` in .wslconfig.")
    o3 = _must_build(tc, a.src, *LEVELS["O3"])
    runs = a.reps or 30
    print(f"Sweeping vCPUs {cands}: {runs} runs each, settle {cfg.settle_s}s. Keep the machine idle.\n")
    print(f"{'cpu':>4s} {'median ms':>10s} {'ci +-%':>8s} {'IQR %':>7s} {'drift %':>8s}   score")
    rows = []
    for c in cands:
        ser = measure_sequential(o3.bin_path, args, runs, cfg.warmup, c, cfg.timeout_s)
        s = summarize(ser.wall_ms)
        if "median_ms" not in s:
            print(f"{c:>4d}  failed: {ser.status}")
            continue
        dr = drift_pct(ser.wall_ms)
        score = s["ci_halfwidth_pct"] + abs(dr) / 2
        rows.append((score, c, s, dr))
        print(f"{c:>4d} {s['median_ms']:>10.1f} {s['ci_halfwidth_pct']:>8.2f} {s['iqr_pct']:>7.2f} {dr:>+8.2f}   {score:.2f}")
    rows.sort(key=lambda r: r[0])
    best = rows[0]
    print(f"\nQuietest: vCPU {best[1]} (score {best[0]:.2f}; lower is better).")
    print(f"Set  timing_cpu = {best[1]}  in config.toml, then re-run selftest.")
    print("Re-run the sweep a couple of times: if the winner keeps changing, differences are just noise.")
    _save(cfg, "cpusweep", {"src": a.src, "rows": [{"cpu": r[1], "score": r[0], "summary": r[2], "drift_pct": r[3]} for r in rows]})


# ------------------------------------------------------------------ corpus
def cmd_corpus(cfg, tc, a):
    root = Path(cfg.corpus_dir) / "suites"
    manifest_path = Path(cfg.corpus_dir) / "manifest.jsonl"
    suites = corp.SUITES if a.suite == "all" else [a.suite]
    pre_path = Path(cfg.corpus_dir) / "prescan.jsonl"
    floor_s = a.floor if a.floor is not None else cfg.floor_s
    ceil_s = a.ceiling if a.ceiling is not None else cfg.ceiling_s
    if a.action == "prescan":
        manifest = corp.load_manifest(manifest_path)
        cands = [c for c in corp.gather(root, suites) if c.program_id not in manifest]
        if a.only:
            cands = [c for c in cands if a.only in c.program_id]
        pre = corp.prescan(tc, cfg, cands, floor_s, pre_path, workers=a.workers)
        from collections import Counter
        print("\nprescan:", dict(Counter(r["reject"] or "ok" for r in pre.values())))
        return 0
    if a.action == "fetch":
        corp.fetch(root, suites)
        return 0
    if a.action == "report":
        print(corp.report(corp.load_manifest(manifest_path)))
        return 0
    if a.action == "split":
        try:
            sp = corp.make_split(corp.load_manifest(manifest_path), Path(cfg.corpus_dir) / "split.json",
                                 seed=a.seed, force=a.force)
        except (FileExistsError, ValueError) as e:
            sys.exit(str(e))
        print(f"Split frozen: {sp['counts']} (by family). Test families: {sp['groups']['test']}")
        return 0
    # scan
    cands = corp.gather(root, suites)
    if a.only:
        cands = [c for c in cands if a.only in c.program_id]
    manifest = corp.load_manifest(manifest_path)
    todo = [c for c in cands if a.force or c.program_id not in manifest
            or manifest[c.program_id].get("reject_reason") == "harness_error"]
    pre = corp.load_manifest(pre_path)
    pre_rej = 0
    for c in list(todo):           # prescan rejections are final (they cannot be caused by load)
        r = pre.get(c.program_id)
        if r and r.get("reject") and r["reject"] != "harness_error" and not a.force:
            manifest[c.program_id] = {"program_id": c.program_id, "suite": c.suite, "family": c.family,
                                      "src": c.src, "status": "rejected", "reject_reason": r["reject"],
                                      "detail": (r.get("detail") or "") + " (prescan)"}
            todo.remove(c)
            pre_rej += 1
    if pre_rej:
        corp.save_manifest(manifest_path, manifest)
    if a.limit:
        todo = todo[:a.limit]
    print(f"{len(cands)} candidates, {len(todo)} to scan, {pre_rej} rejected by prescan (floor {floor_s}s, "
          f"ceiling {ceil_s}s, pinned vCPU {cfg.timing_cpu}). Keep the machine idle.\n")
    for i, c in enumerate(todo, 1):
        t0 = time.time()
        try:
            start = (pre.get(c.program_id) or {}).get("start", 0) if not a.force else 0
            rec = corp.scan_one(tc, cfg, c, floor_s, ceil_s, cfg.scan_reps, start=start)
        except Exception as e:                       # never lose the whole scan to one program
            rec = {"program_id": c.program_id, "suite": c.suite, "family": c.family, "src": c.src,
                   "status": "rejected", "reject_reason": "harness_error", "detail": repr(e)[:300]}
        manifest[c.program_id] = rec
        corp.save_manifest(manifest_path, manifest)
        if rec["status"] == "ok":
            msg = (f"OK  {rec['dataset']:<18s} O3 {rec['times_ms']['O3']:>8.0f} ms  "
                   f"O0/O3 {rec['o0_over_o3']:.2f}x  level-spread {rec['level_spread']:.3f}")
        else:
            msg = f"--  {rec['reject_reason']:<18s} {rec.get('detail', '')[:60]}"
        print(f"[{i:>3d}/{len(todo)}] {c.program_id:<42s} {msg}  ({time.time() - t0:.0f}s)")
    print("\n" + corp.report(manifest))
    print(f"\nManifest: {manifest_path}")
    return 0


# ------------------------------------------------------------------ search
def _pick_programs(cfg, a) -> list[dict]:
    manifest = corp.load_manifest(Path(cfg.corpus_dir) / "manifest.jsonl")
    ok = {k: v for k, v in manifest.items() if v["status"] == "ok"}
    if getattr(a, "max_runtime", 0):
        ok = {k: v for k, v in ok.items() if v["times_ms"]["O3"] <= a.max_runtime * 1000}
    if getattr(a, "exclude_searched", False):
        done = {r["program_id"] for r in Store(cfg.db_path).rows("SELECT DISTINCT program_id FROM runs")}
        ok = {k: v for k, v in ok.items() if k not in done}
    if a.programs:
        names = [x.strip() for x in a.programs.split(",") if x.strip()]
        missing = [n for n in names if n not in ok]
        if missing:
            sys.exit(f"Not usable/unknown programs: {missing}")
        return [ok[n] for n in names]
    if a.sample:
        import random as _r
        rng = _r.Random(a.seed)
        fams: dict[str, list[str]] = {}
        for k, v in sorted(ok.items()):
            fams.setdefault(v["family"], []).append(k)
        for f in fams.values():
            rng.shuffle(f)
        order = sorted(fams, key=lambda f: rng.random())
        picked: list[str] = []
        while len(picked) < min(a.sample, len(ok)):
            for f in order:
                if fams[f] and len(picked) < a.sample:
                    picked.append(fams[f].pop())
        return [ok[k] for k in picked]
    sys.exit("Give --programs a,b,c or --sample N")


def cmd_search(cfg, tc, a):
    store = Store(cfg.db_path)
    if a.action == "report":
        print(srch.report(store))
        return 0
    if a.action == "show":
        if not a.program:
            sys.exit("Give --program <program_id>")
        print(srch.show(store, tc, a.program))
        return 0
    if a.action == "revalidate":
        manifest = corp.load_manifest(Path(cfg.corpus_dir) / "manifest.jsonl")
        pids = sorted({r["program_id"] for r in store.rows("SELECT program_id FROM runs WHERE method='final' AND seed=?", (a.seed,))})
        srch.revalidate_serial(tc, cfg, store, [manifest[p] for p in pids if p in manifest], a.seed)
        return 0
    if a.action == "validate":
        manifest = corp.load_manifest(Path(cfg.corpus_dir) / "manifest.jsonl")
        pids = [x for x in a.programs.split(",") if x] if a.programs else \
            sorted({r["program_id"] for r in store.rows("SELECT DISTINCT program_id FROM measurements WHERE stage='confirm'")})
        srch.validate_existing(tc, cfg, store, [manifest[p] for p in pids if p in manifest])
        print("\n" + srch.report(store))
        return 0
    if a.action == "pools":
        from .pipeline import build_pools, parse_pipeline, validate_extras
        root = parse_pipeline(tc.pipeline_string("O3"))
        extras, knobs = validate_extras(tc.tool("opt"), tc.work, tc.version())
        print({k: len(v) for k, v in build_pools(root, extras).items()}, "| knobs:", {k: v for k, v in knobs.items()})
        return 0
    progs = _pick_programs(cfg, a)
    methods = [m for m in a.methods.split(",") if m]
    budget = a.budget or cfg.budget
    if a.timing_cpus:
        from .parallel import run_parallel
        run_parallel("search", a.config, progs, _cpus(a.timing_cpus),
                     {"methods": methods, "budget": budget, "seed": a.seed, "force": a.force})
        print("\n" + srch.report(store))
        return 0
    print(f"{len(progs)} programs, methods {methods}, budget {budget} unique timed binaries per method, "
          f"pinned vCPU {cfg.timing_cpu}. Keep the machine idle. Results: {cfg.db_path}")
    for i, rec in enumerate(progs, 1):
        print(f"\n=== program {i}/{len(progs)} ===")
        try:
            srch.run_program(tc, cfg, store, rec, methods, budget, a.seed, force=a.force)
        except Exception as e:
            print(f"[{rec['program_id']}] FAILED: {e!r}")
    print("\n" + srch.report(store))
    return 0


def _cpus(x: str) -> list[int]:
    return [int(c) for c in x.split(",") if c.strip()]


def _winner_keys(store) -> dict[str, str]:
    """program -> cand_id of its validated winner (new-style final runs or legacy validate rows)."""
    out = {}
    for r in store.rows("SELECT program_id, cand_id, ci_lo FROM measurements WHERE stage='validate' ORDER BY id"):
        if not r["cand_id"].startswith("minimize:") and (r["ci_lo"] or 0) > 1.0:
            out[r["program_id"]] = r["cand_id"]
    return out


def cmd_aatest(cfg, tc, a):
    from .parallel import aatest
    store = Store(cfg.db_path)
    m = _manifest(cfg)
    pids = [p for p in a.programs.split(",") if p]
    missing = [p for p in pids if p not in m]
    if missing:
        sys.exit(f"unknown programs: {missing}")
    print(aatest(a.config, [m[p] for p in pids], _winner_keys(store), _cpus(a.cpus), a.reps, a.rounds,
                 Path(cfg.results_dir)))
    return 0


# ------------------------------------------------------------------ phases 4-9
def _manifest(cfg):
    return corp.load_manifest(Path(cfg.corpus_dir) / "manifest.jsonl")


def _split(cfg) -> dict | None:
    p = Path(cfg.corpus_dir) / "split.json"
    return json.loads(p.read_text()) if p.exists() else None


def _test_families(cfg) -> set[str]:
    sp = _split(cfg)
    return set(sp["groups"]["test"]) if sp else set()


def _recs(cfg, a, store=None) -> list[dict]:
    """--programs a,b | --winners (programs with a confirmed/validated gain) | --all (usable programs,
    test families excluded unless --include-test) | --sample N (stratified)."""
    m = {k: v for k, v in _manifest(cfg).items() if v.get("status") == "ok"}
    if getattr(a, "programs", ""):
        return [m[p] for p in a.programs.split(",") if p in m]
    test = set() if getattr(a, "include_test", False) else _test_families(cfg)
    if getattr(a, "winners", False):
        st = store or Store(cfg.db_path)
        w = {r["program_id"] for r in st.rows("SELECT DISTINCT program_id FROM measurements WHERE stage IN ('confirm','validate') AND ci_lo > 1.0")}
        return [m[p] for p in sorted(w) if p in m and m[p]["family"] not in test]
    if getattr(a, "all", False):
        return [v for k, v in sorted(m.items()) if v["family"] not in test]
    if getattr(a, "sample", 0):
        return _pick_programs(cfg, a)
    sys.exit("Give --programs a,b | --winners | --all | --sample N")


def cmd_passkb(cfg, tc, a):
    from . import passkb
    store = Store(cfg.db_path)
    if a.action == "report":
        print(passkb.report_passkb(store, Path(cfg.results_dir)))
        return 0
    recs = _recs(cfg, a, store)
    if a.timing_cpus:
        from .parallel import run_parallel
        run_parallel("passkb", a.config, recs, _cpus(a.timing_cpus), {"force": a.force, "add_one": not a.no_add})
        print("\n" + passkb.report_passkb(store, Path(cfg.results_dir)))
        return 0
    print(f"passkb on {len(recs)} programs (add-one {'off' if a.no_add else 'on'}). Keep the machine idle.")
    for i, rec in enumerate(recs, 1):
        print(f"\n=== program {i}/{len(recs)} ===")
        try:
            passkb.run_passkb(tc, cfg, store, rec, force=a.force, add_one=not a.no_add)
        except Exception as e:
            print(f"[{rec['program_id']}] FAILED: {e!r}")
    print("\n" + passkb.report_passkb(store, Path(cfg.results_dir)))
    return 0


def cmd_collect(cfg, tc, a):
    from . import collect, passkb
    store = Store(cfg.db_path)
    if a.action == "quality":
        print(collect.quality(store, _manifest(cfg), cfg, tc, Path.cwd()))
        return 0
    recs = _recs(cfg, a, store)
    methods = [x for x in a.methods.split(",") if x]
    if a.timing_cpus:
        from .parallel import run_parallel
        run_parallel("collect", a.config, recs, _cpus(a.timing_cpus),
                     {"methods": methods, "budget": a.budget or cfg.budget, "seed": a.seed, "no_passkb": a.no_passkb})
        print("\n" + collect.quality(store, _manifest(cfg), cfg, tc, Path.cwd()))
        return 0
    print(f"collect: {len(recs)} programs, methods {methods}, budget {a.budget or cfg.budget}, passkb {not a.no_passkb}. "
          "Keep the machine idle. Resumable.")
    for i, rec in enumerate(recs, 1):
        print(f"\n=== program {i}/{len(recs)} ===", flush=True)
        try:
            srch.run_program(tc, cfg, store, rec, methods, a.budget or cfg.budget, a.seed)
            if not a.no_passkb:
                passkb.run_passkb(tc, cfg, store, rec)
        except Exception as e:
            print(f"[{rec['program_id']}] FAILED: {e!r}")
    print("\n" + collect.quality(store, _manifest(cfg), cfg, tc, Path.cwd()))
    return 0


def cmd_features(cfg, tc, a):
    from . import features
    store = Store(cfg.db_path)
    a.include_test = True                    # features are inputs, not labels: compute for every program
    recs = _recs(cfg, a, store)
    features.extract(tc, cfg, store, recs, dynamic=not a.no_dynamic, force=a.force, workers=a.workers)
    pf = features.program_features(store)
    print(f"features stored for {len(pf)} programs; {len(next(iter(pf.values()), {}))} values per program")
    return 0


def cmd_model(cfg, tc, a):
    from . import model
    store = Store(cfg.db_path)
    fsets = tuple(x for x in a.fsets.split(",") if x)
    test = _test_families(cfg)
    if not test:
        print("NOTE: corpus/split.json does not exist yet; cross-validation uses every family (development only).")
    data = model.load_rows(store, _manifest(cfg), tc, fsets, compiled=a.compiled)
    if data is None:
        sys.exit("No labelled rows yet.")
    out = Path(cfg.results_dir) / "models"
    if a.action == "cv":
        res = model.cross_validate(data, exclude_families=test)
        txt, summ = model.summarize_cv(res)
        print(txt)
        out.mkdir(parents=True, exist_ok=True)
        (out / f"cv_{'-'.join(fsets)}_latest.json").write_text(json.dumps({"fsets": fsets, "summary": summ,
                                                                           "excluded": sorted(test)}, indent=1))
        (out / "cv_latest.json").write_text(json.dumps({"fsets": fsets, "summary": summ}, indent=1))
        return 0
    mp = model.train_final(data, out, exclude_families=test, meta_extra={"fsets": fsets})
    print(f"surrogate saved: {mp}")
    return 0


def cmd_rl(cfg, tc, a):
    from . import features, model, rl
    from .pipeline import build_pools, build_space, parse_pipeline, validate_extras
    out = Path(cfg.results_dir) / "models"
    cv = out / "cv_latest.json"
    if not a.force and (not cv.exists() or not json.loads(cv.read_text())["summary"].get("gate_7b")):
        sys.exit("Gate 7B not passed (see `model cv`): the surrogate does not rank unseen families better than "
                 "random, so RL on its reward is pointless. Use --force only to test the code.")
    meta = Path(a.model) if a.model else out / "surrogate_latest.json"
    sur = model.Surrogate(meta)
    store = Store(cfg.db_path)
    tree = parse_pipeline(tc.pipeline_string("O3"))
    ex, kn = validate_extras(tc.tool("opt"), tc.work, tc.version())
    sp = build_space(tree, tc.tool("opt"), tc.tool("llc"), tc.work, tc.version(), build_pools(tree, ex), kn)
    pf = {p: v for p, v in features.program_features(store).items() if p in set(sur.meta["train_programs"])}
    env = rl.PassEnv(sur, features.leaf_names(tree), rl.macro_actions(sp, Path(cfg.results_dir)), pf, a.horizon)
    res = rl.train_ppo(env, sorted(pf), iters=a.iters, episodes=a.episodes, seed=a.seed)
    path = out / f"rl_policy_{time.strftime('%Y%m%d-%H%M%S')}.npz"
    gate = json.loads(cv.read_text())["summary"].get("gate_7b") if cv.exists() else None
    rl.save_policy(path, res, env, {"surrogate": str(meta), "gate_7b_passed": gate,
                                    "exploratory": bool(a.force and not gate), "programs": len(pf)})
    shutil.copy2(path, out / "rl_policy_latest.npz")
    shutil.copy2(path.with_suffix(".json"), out / "rl_policy_latest.json")
    print(f"policy saved: {path}")
    return 0


def cmd_deploy(cfg, tc, a):
    from . import deploy
    base = Path(os.environ.get("NC_CALLER_CWD", "."))
    fix = lambda x: str((base / x).resolve()) if x else x
    a.src, a.out, a.stdin, a.cwd = [fix(x) for x in a.src], fix(a.out), fix(a.stdin), fix(a.cwd)
    meta = Path(a.model) if a.model else Path(cfg.results_dir) / "models" / "surrogate_latest.json"
    if not meta.exists():
        sys.exit(f"No surrogate at {meta}; run `model train` first.")
    pol = None if a.no_rl else Path(a.rl_policy)
    if pol is not None and not pol.exists():
        print(f"note: no RL policy at {pol}; running SL only (train one with `python -m nc.cli rl train`)")
        pol = None
    res = deploy.deploy_source(tc, cfg, a.src, shlex.split(a.args), a.stdin, a.cwd, shlex.split(a.cflags),
                               Path(a.out), meta, k=a.k, reps=a.reps, dynamic=a.dynamic, rl_policy=pol)
    print(json.dumps({k: v for k, v in res.items() if k not in ("genome", "pipeline")}, indent=1, default=str))
    # short summary for humans
    print(f"\n== neurocompiler ({res.get('mode')}) ==")
    print(f"candidates: {res.get('rl_proposals', 0)} RL proposals + {res.get('library')} library pipelines, ranked by the "
          f"supervised model; {res.get('rl_in_top20_ranked', 0)} RL proposals in its top 20; {res.get('n_timed')} timed")
    print("top of the ranking: " + ", ".join(f"#{t['rank']} {t['source']} (pred {t['predicted_speedup']:.2f}x)"
                                             for t in (res.get("top_ranked") or [])[:8]))
    if res.get("choice") == "candidate":
        c = res.get("confirm") or {}
        print(f"shipped: pipeline from the {res.get('shipped_from')}, selection {res.get('select_speedup', 0):.3f}x vs -O3"
              + (f", confirmed {c['speedup']:.3f}x [{c['ci'][0]:.3f},{c['ci'][1]:.3f}]" if c.get("speedup") else ""))
        for e in res.get("shipped_edits") or []:
            print(f"   edit: {json.dumps({k: v for k, v in e.items() if k != 'nid'})}")
    else:
        print(f"shipped: -O3 ({res.get('reason')})")
    print(f"binary: {res.get('output')}   total {res.get('total_s')} s")
    return 0


def cmd_evaluate(cfg, tc, a):
    from . import evaluate
    store = Store(cfg.db_path)
    if a.action == "report":
        print(evaluate.report_eval(store, a.tag, Path(cfg.results_dir)))
        return 0
    sp = _split(cfg)
    if sp is None:
        sys.exit("No frozen split (corpus/split.json). Evaluation runs only on the frozen test set.")
    m = _manifest(cfg)
    if a.action == "repro":
        print(evaluate.repro(tc, cfg, store, m, a.tag))
        return 0
    recs = [m[p] for p, t in sorted(sp["program_split"].items()) if t == "test" and p in m]
    meta = Path(a.model) if a.model else Path(cfg.results_dir) / "models" / "surrogate_latest.json"
    if a.timing_cpus:
        from .parallel import run_parallel
        run_parallel("evaluate", a.config, recs, _cpus(a.timing_cpus),
                     {"meta": str(meta), "k": a.k, "tag": a.tag, "nodyn": a.nodyn_model or None,
                      "rl": a.rl or None, "budget": a.budget or None,
                      "only": [m for m in a.methods.split(",") if m] or None, "confirm_reps": a.confirm_reps})
    else:
        evaluate.run_eval(tc, cfg, store, recs, meta, a.k, a.tag, Path(a.nodyn_model) if a.nodyn_model else None,
                          Path(a.rl) if a.rl else None, budget=a.budget or None,
                          only={m for m in a.methods.split(",") if m} or None, confirm_reps=a.confirm_reps)
    print(evaluate.report_eval(store, a.tag, Path(cfg.results_dir)))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="nc")
    ap.add_argument("--config", default="config.toml")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("env")
    sub.add_parser("o3pipeline")
    for name in ("baselines", "selftest", "cpusweep"):
        sp = sub.add_parser(name)
        if name == "cpusweep":
            sp.add_argument("--include0", action="store_true", help="also test vCPU 0")
        sp.add_argument("src")
        sp.add_argument("--args", default="", help="program arguments as one string")
        sp.add_argument("--reps", type=int, default=0)
    cp = sub.add_parser("corpus")
    cp.add_argument("action", choices=["fetch", "prescan", "scan", "report", "split"])
    cp.add_argument("--suite", default="all", choices=["all", "polybench", "singlesource", "multisource"])
    cp.add_argument("--workers", type=int, default=0, help="prescan: parallel jobs (default: helper CPUs - 1)")
    cp.add_argument("--only", default="", help="substring filter on program_id")
    cp.add_argument("--limit", type=int, default=0)
    cp.add_argument("--floor", type=float, default=None)
    cp.add_argument("--ceiling", type=float, default=None)
    cp.add_argument("--force", action="store_true", help="rescan known programs / overwrite a frozen split")
    cp.add_argument("--seed", type=int, default=0)
    sp2 = sub.add_parser("search")
    sp2.add_argument("action", choices=["run", "report", "show", "pools", "validate", "revalidate"])
    sp2.add_argument("--program", default="")
    sp2.add_argument("--programs", default="")
    sp2.add_argument("--sample", type=int, default=0)
    sp2.add_argument("--methods", default="random,evo", help="any of random,evo (action space v1), random2,evo2 (v2)")
    sp2.add_argument("--max-runtime", type=float, default=0.0, help="--sample: only programs whose -O3 time <= this (s)")
    sp2.add_argument("--budget", type=int, default=0)
    sp2.add_argument("--seed", type=int, default=0)
    sp2.add_argument("--force", action="store_true")
    sp2.add_argument("--exclude-searched", action="store_true", help="--sample: skip programs already in the DB")
    sp2.add_argument("--timing-cpus", default="", help="parallel timing, one worker per core, e.g. 2,4,6,8,10")
    def sel(p):
        p.add_argument("--programs", default="")
        p.add_argument("--winners", action="store_true", help="programs with a confirmed gain")
        p.add_argument("--all", action="store_true", help="all usable programs (test families excluded)")
        p.add_argument("--include-test", action="store_true")
        p.add_argument("--sample", type=int, default=0)
        p.add_argument("--seed", type=int, default=0)
        p.add_argument("--force", action="store_true")
    pk = sub.add_parser("passkb")
    pk.add_argument("action", choices=["run", "report"])
    pk.add_argument("--no-add", action="store_true", help="skip add-one inserts (the largest group)")
    pk.add_argument("--timing-cpus", default="")
    sel(pk)
    co = sub.add_parser("collect")
    co.add_argument("action", choices=["run", "quality"])
    co.add_argument("--methods", default="random,evo,evo2")
    co.add_argument("--budget", type=int, default=0)
    co.add_argument("--no-passkb", action="store_true")
    co.add_argument("--timing-cpus", default="")
    aa = sub.add_parser("aatest", help="multi-core A/A test: is parallel timing as trustworthy as serial?")
    aa.add_argument("--cpus", required=True, help="timing cores, e.g. 2,4,6,8,10")
    aa.add_argument("--programs", required=True, help="one program per core")
    aa.add_argument("--reps", type=int, default=30)
    aa.add_argument("--rounds", type=int, default=2)
    sel(co)
    fe = sub.add_parser("features")
    fe.add_argument("action", choices=["extract"])
    fe.add_argument("--no-dynamic", action="store_true", help="skip cachegrind (simulated dynamic features)")
    fe.add_argument("--workers", type=int, default=0)
    sel(fe)
    mo = sub.add_parser("model")
    mo.add_argument("action", choices=["cv", "train"])
    mo.add_argument("--fsets", default="static,sim,sim_l2,scan")
    mo.add_argument("--compiled", action="store_true", help="add compiled-candidate features (IR / code size vs -O3)")
    rp = sub.add_parser("rl")
    rp.add_argument("action", choices=["train"])
    rp.add_argument("--model", default="")
    rp.add_argument("--iters", type=int, default=60)
    rp.add_argument("--episodes", type=int, default=32)
    rp.add_argument("--horizon", type=int, default=4)
    rp.add_argument("--seed", type=int, default=0)
    rp.add_argument("--force", action="store_true")
    de = sub.add_parser("deploy")
    de.add_argument("src", nargs="+")
    de.add_argument("--out", required=True)
    de.add_argument("--args", default="")
    de.add_argument("--stdin", default=None)
    de.add_argument("--cwd", default=None)
    de.add_argument("--cflags", default="")
    de.add_argument("--model", default="")
    de.add_argument("--k", type=int, default=8)
    de.add_argument("--reps", type=int, default=10)
    de.add_argument("--dynamic", action="store_true", help="also compute simulated (cachegrind) features")
    de.add_argument("--rl-policy", default="results/models/rl_policy_latest.npz", help="RL policy used for RL + SL")
    de.add_argument("--no-rl", action="store_true", help="SL only: the supervised model ranks the library")
    ev = sub.add_parser("evaluate")
    ev.add_argument("action", choices=["run", "report", "repro"])
    ev.add_argument("--tag", default="final")
    ev.add_argument("--k", type=int, default=8)
    ev.add_argument("--budget", type=int, default=0, help="random/GA timed budget (default: k, equal budget)")
    ev.add_argument("--model", default="")
    ev.add_argument("--nodyn-model", default="")
    ev.add_argument("--rl", default="")
    ev.add_argument("--timing-cpus", default="", help="parallel selection (final numbers come from `evaluate repro`)")
    ev.add_argument("--methods", default="", help="only these methods, e.g. topk,rl_topk,rl_lib_topk (default: all)")
    ev.add_argument("--confirm-reps", type=int, default=0, help="selection confirmation rounds (0 = procedure of tag 'final')")
    a = ap.parse_args(argv)
    cfg = load_config(a.config)
    tc = Toolchain(cfg)
    configure(no_aslr=cfg.no_aslr, settle_s=cfg.settle_s, isolate_sibling=cfg.isolate_sibling,
              quiet_max_busy=cfg.quiet_max_busy, quiet_max_wait_s=cfg.quiet_max_wait_s,
              layout_copies=cfg.layout_copies)
    fn = {"env": cmd_env, "o3pipeline": cmd_o3pipeline, "baselines": cmd_baselines,
          "selftest": cmd_selftest, "cpusweep": cmd_cpusweep, "corpus": cmd_corpus, "search": cmd_search,
          "passkb": cmd_passkb, "collect": cmd_collect, "features": cmd_features, "model": cmd_model,
          "rl": cmd_rl, "deploy": cmd_deploy, "evaluate": cmd_evaluate, "aatest": cmd_aatest}[a.cmd]
    sys.exit(fn(cfg, tc, a) or 0)


if __name__ == "__main__":
    main()
