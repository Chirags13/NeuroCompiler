"""Search over pass pipelines for one program: random mutation and (mu+lambda) evolution.

Cost model: compiling is cheap and parallel, timing is expensive and serial. So
  1. a batch of genomes is compiled in parallel (identical IR / identical binaries are free),
  2. new binaries are verified against the -O0 output hash on helper CPUs while nothing is timed
     (wrong output is never selected),
  3. unique binaries are screened against the -O3 baseline: one interleaved round for all, two
     more only for plausible winners (successive halving); clearly slow runs are killed early,
  4. the shortlists of all methods are CONFIRMED together in one fresh 30-round interleaved run
     that also contains an A/A control (-O3 vs a copy of -O3); a control further than
     control_max_dev_pct from 1.0 makes the run repeat once,
  5. the program winner is pass-minimized (edits reverted while the gain survives), and
  6. VALIDATED: re-measured in a fresh, independent run. Picking the best of several confirmed
     candidates is itself a winner's curse; only the validated number is used by the gate.
The search budget counts UNIQUE TIMED BINARIES, the expensive resource.
Methods: levels (standard-level seeds), random / evo (action space v1), random2 / evo2 (v2).
"""
from __future__ import annotations

import json
import math
import random
import shutil
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass

import numpy as np

from .config import Config
from .db import Store
from .pipeline import (Genome, _ctx_of, _walk, build_pools, build_space, cand_id, materialize, parse_pipeline,
                       random_edit, random_edit_v2, random_genome, validate_extras)
from .timing import (LAST_BUSY, RunSpec, helper_cpus, measure_interleaved, paired_speedup, run_spec,
                     wait_quiet)
from .toolchain import Toolchain

LEVEL_SEEDS = [("default<O1>", 3), ("default<O2>", 3), ("default<Os>", 3), ("default<O0>", 3),
               ("default<O0>", 0), ("default<O3>", 0), ("default<O3>", 1), ("default<O3>", 2),
               ("default<O1>", 1)]
V2_METHODS = {"random2", "evo2"}
SEARCH_METHODS = ["random", "evo", "random2", "evo2"]


@dataclass
class Budget:
    timed: int = 0          # unique binaries that received a timing measurement
    attempts: int = 0       # genomes compiled


@dataclass
class Eval:
    cand_id: str
    genome: Genome
    pipeline: str
    flags: tuple
    backend: int
    status: str = "pending"
    speedup: float | None = None       # screening speedup vs -O3 (>1 = faster)
    fitness: float | None = None
    bin_hash: str = ""
    bin_path: str = ""
    text_size: int = 0
    same_as_o3: bool = False
    method: str = ""


def _chunks(xs, n):
    for i in range(0, len(xs), n):
        yield xs[i:i + n]


class ProgramSearch:
    def __init__(self, tc: Toolchain, cfg: Config, store: Store, rec: dict, log=print):
        self.tc, self.cfg, self.store, self.rec, self.log = tc, cfg, store, rec, log
        self.pid, self.src = rec["program_id"], rec["src"]
        self.cflags = tuple(rec.get("cflags") or [])
        self.time_spec = RunSpec.from_dict(rec["time_spec"])
        self.verify_spec = RunSpec.from_dict(rec["verify_spec"])
        self.ref = rec["ref_output_hash"]
        self.expected = self.ref if self.time_spec.__dict__ == self.verify_spec.__dict__ else None
        self.stage_s: dict[str, float] = defaultdict(float)
        tc.version()
        tc.start_ir(self.src, self.cflags)             # build the start IR once, before threads
        self.tree = parse_pipeline(tc.pipeline_string("O3"))
        extras, self.knobs = validate_extras(tc.tool("opt"), tc.work, tc.version())
        self.pools = build_pools(self.tree, extras)
        self._space = None
        with self.stage("compile"):
            self.base = tc.build(self.src, "default<O3>", 3, self.cflags)
            if not self.base.ok:
                raise RuntimeError(f"baseline build failed: {self.base.error[:200]}")
            pipe, _, _ = materialize(self.tree, Genome([]))
            chk = tc.build(self.src, pipe, 3, self.cflags)
        # Speedups are always measured against the real default<O3> binary. If the printed pipeline
        # does not reproduce it, edits are applied to a slightly different starting point: the
        # unedited printed pipeline is then timed as its own candidate and the program is flagged.
        self.o3_mismatch = chk.ir_hash != self.base.ir_hash
        self.o3_text = pipe
        if self.o3_mismatch:
            log(f"[{self.pid}] WARNING: printed -O3 pipeline does not reproduce default<O3> (o3_mismatch); "
                "timing it as a candidate so gains from the mismatch itself are visible")
        s = run_spec(self.base.bin_path, self.time_spec, cfg.timing_cpu, cfg.timeout_s)
        self.base_s = s.wall_ms / 1000
        self.timeout = max(2.0, 5 * self.base_s)
        self.ctrl_path = str(tc.work / "tmp" / f"ctrl_{self.base.bin_hash[:16]}")
        shutil.copy2(self.base.bin_path, self.ctrl_path)
        self.helpers = helper_cpus(cfg.timing_cpu)
        self._write_cand(f"baseline:{self.pid}", "baseline", 0, Genome([]), "default<O3>", (), 3,
                         self.base, "ok", True)

    @property
    def space(self):
        if self._space is None:
            self._space = build_space(self.tree, self.tc.tool("opt"), self.tc.tool("llc"), self.tc.work,
                                      self.tc.version(), self.pools, self.knobs)
        return self._space

    @contextmanager
    def stage(self, name: str):
        t0 = time.perf_counter()
        try:
            yield
        finally:
            self.stage_s[name] += time.perf_counter() - t0

    def _measure(self, bins: dict, reps: int, warmup: int, seed: int, timeouts=None, settle_s=None):
        return measure_interleaved(bins, self.time_spec.args, reps, warmup, self.cfg.timing_cpu, self.timeout,
                                   seed=seed, expected_hash=self.expected, stdin_path=self.time_spec.stdin_path,
                                   cwd=self.time_spec.cwd, timeouts=timeouts, settle_s=settle_s, log=self.log)

    # ------------------------------------------------------------------ helpers
    def _fitness(self, sp: float, text_size: int) -> float:
        f = math.log(sp)
        if self.base.text_size and text_size:
            over = math.log(text_size / self.base.text_size) - math.log(self.cfg.size_cap)
            if over > 0:
                f -= 0.5 * over
        return f

    def _write_cand(self, cid, method, gen, genome, pipe, flags, backend, build, status, same):
        self.store.put_candidate({
            "cand_id": cid, "program_id": self.pid, "method": method, "generation": gen,
            "genome_json": genome.to_json(), "pipeline": pipe, "opt_flags": " ".join(flags),
            "backend": backend, "ir_hash": getattr(build, "ir_hash", ""),
            "bin_hash": getattr(build, "bin_hash", ""), "status": status, "same_as_o3": int(same),
            "ir_insts": getattr(build, "ir_inst_count", 0), "text_size": getattr(build, "text_size", 0),
            "bin_size": getattr(build, "bin_size", 0), "opt_ms": getattr(build, "opt_ms", 0.0),
            "backend_ms": getattr(build, "backend_ms", 0.0), "n_edits": len(genome.edits),
            "machine_id": self.cfg.machine_id, "llvm_version": self.tc.version()})

    def _put_meas(self, key: str, stage: str, ser, base, sp: dict, note: dict | None = None):
        n = dict(note or {})
        if not math.isnan(getattr(ser, "busy_cores", float("nan"))):
            n["busy_cores"] = round(ser.busy_cores, 2)
        self.store.put_measurement({
            "cand_id": key, "program_id": self.pid, "stage": stage, "n": sp.get("n", 0),
            "median_ms": float(np.nanmedian(ser.wall_ms)) if len(ser.wall_ms) else None,
            "base_median_ms": float(np.nanmedian(base.wall_ms)), "speedup": sp.get("speedup"),
            "ci_lo": sp.get("ci_lo"), "ci_hi": sp.get("ci_hi"), "raw_ms": ser.wall_ms,
            "base_raw_ms": base.wall_ms, "machine_id": self.cfg.machine_id, "cpu": self.cfg.timing_cpu,
            "note": json.dumps(n) if n else ""})

    # ------------------------------------------------------------------ evaluate
    def evaluate(self, genomes: list[Genome], method: str, gen: int, cache: dict, bud: Budget,
                 screen_reps: int | None = None, halving: bool | None = None) -> list[Eval]:
        reps = screen_reps or self.cfg.screen_reps
        halving = self.cfg.screen_halving if halving is None else halving
        out: list[Eval] = []
        new: list[Eval] = []
        seen: dict[str, Eval] = {}
        for g in genomes:
            pipe, flags, be = materialize(self.tree, g)
            cid = cand_id(self.pid, pipe, flags, be)
            if cid in cache:
                out.append(cache[cid])
            elif cid in seen:
                out.append(seen[cid])
            else:
                ev = Eval(cid, g, pipe, flags, be, method=method)
                seen[cid] = ev
                new.append(ev)
                out.append(ev)
        bud.attempts += len(new)
        if not new:
            return out

        with self.stage("compile"), ThreadPoolExecutor(self.cfg.compile_workers) as ex:
            builds = list(ex.map(lambda e: self.tc.build(self.src, e.pipeline, e.backend, self.cflags, e.flags), new))

        to_time: dict[str, list[Eval]] = {}
        build_of: dict[str, object] = {}
        for ev, b in zip(new, builds):
            build_of[ev.cand_id] = b
            if not b.ok:
                ev.status = b.status
                continue
            ev.bin_hash, ev.bin_path, ev.text_size = b.bin_hash, b.bin_path, b.text_size
            if b.bin_hash == self.base.bin_hash:
                ev.status, ev.same_as_o3, ev.speedup, ev.fitness = "ok", True, 1.0, 0.0
            else:
                to_time.setdefault(b.bin_hash, []).append(ev)

        # Output check. Nothing is being timed now, so it runs on helper CPUs in parallel
        # (serially when the program writes files into its working directory).
        hashes = list(to_time)
        par = self.cfg.verify_parallel and not self.verify_spec.cwd
        with self.stage("verify"):
            if par:
                with ThreadPoolExecutor(max(1, len(self.helpers))) as ex:
                    vs = list(ex.map(lambda ih: run_spec(to_time[ih[1]][0].bin_path, self.verify_spec,
                                                         self.helpers[ih[0] % len(self.helpers)], self.timeout),
                                     enumerate(hashes)))
            else:
                vs = [run_spec(to_time[h][0].bin_path, self.verify_spec, self.cfg.timing_cpu, self.timeout)
                      for h in hashes]
        verified = []
        for h, v in zip(hashes, vs):
            if v.status != "ok" or v.out_hash != self.ref:
                for e in to_time[h]:
                    e.status = "wrong_output" if v.status == "ok" else v.status
            else:
                verified.append(h)

        meas_rows = []
        abort = {h: max(self.base_s * self.cfg.screen_abort, self.base_s + 0.05) for h in verified} \
            if self.cfg.screen_abort > 0 else None
        with self.stage("screen"):
            for chunk in _chunks(verified, self.cfg.batch):
                bins = {"BASE": self.base.bin_path, **{h: to_time[h][0].bin_path for h in chunk}}
                if halving and reps > 1:
                    r1 = self._measure(bins, 1, 0, bud.timed, timeouts=abort)
                    keep = []
                    for h in chunk:
                        a, b = r1["BASE"].wall_ms[0], r1[h].wall_ms[0] if r1[h].wall_ms else math.nan
                        if r1[h].status == "ok" and a == a and b == b and a / b >= self.cfg.screen_keep:
                            keep.append(h)
                    ser = r1
                    if keep:
                        r2 = self._measure({"BASE": self.base.bin_path, **{h: bins[h] for h in keep}},
                                           reps - 1, 0, bud.timed + 7919, timeouts=abort, settle_s=0.0)
                        for h in keep:
                            r1[h].wall_ms += r2[h].wall_ms
                            r1[h].status = r2[h].status
                        base_k = r1["BASE"].wall_ms + r2["BASE"].wall_ms
                    pairs = {}
                    for h in chunk:
                        if h in keep:
                            pairs[h] = (base_k, r1[h].wall_ms)
                        else:
                            pairs[h] = (r1["BASE"].wall_ms[:1], r1[h].wall_ms[:1])
                else:
                    ser = self._measure(bins, reps, 1, bud.timed, timeouts=abort)
                    pairs = {h: (ser["BASE"].wall_ms, ser[h].wall_ms) for h in chunk}
                for h in chunk:
                    s = ser[h]
                    a, b = pairs[h]
                    bud.timed += 1
                    if s.status == "timeout" and abort:
                        for e in to_time[h]:
                            e.status, e.fitness = "slow", math.log(1 / self.cfg.screen_abort)
                        continue
                    if s.status != "ok":
                        for e in to_time[h]:
                            e.status = s.status
                        continue
                    if len(a) >= 3:
                        sp = paired_speedup(a, b)
                    else:
                        ra = np.asarray(a, float) / np.asarray(b, float)
                        sp = {"n": len(ra), "speedup": float(np.exp(np.mean(np.log(ra))))} if len(ra) else {}
                    if "speedup" not in sp:
                        for e in to_time[h]:
                            e.status = "timing_failed"
                        continue
                    for e in to_time[h]:
                        e.status, e.speedup = "ok", sp["speedup"]
                        e.fitness = self._fitness(sp["speedup"], e.text_size)
                    meas_rows.append((to_time[h][0], b, a, sp))

        for ev in new:
            self._write_cand(f"{method}:{ev.cand_id}", method, gen, ev.genome, ev.pipeline, ev.flags,
                             ev.backend, build_of[ev.cand_id], ev.status, ev.same_as_o3)
            cache[ev.cand_id] = ev
        for ev, b, a, sp in meas_rows:
            self.store.put_measurement({
                "cand_id": f"{method}:{ev.cand_id}", "program_id": self.pid, "stage": "screen",
                "n": sp["n"], "median_ms": float(np.nanmedian(b)),
                "base_median_ms": float(np.nanmedian(a)), "speedup": sp["speedup"],
                "ci_lo": None, "ci_hi": None, "raw_ms": list(b), "base_raw_ms": list(a),
                "machine_id": self.cfg.machine_id, "cpu": self.cfg.timing_cpu, "note": ""})
        return out

    # ------------------------------------------------------------------ search algorithms
    def _edit(self, g: Genome, rng, v2: bool) -> dict:
        return random_edit_v2(self.tree, g, self.space, rng) if v2 else \
            random_edit(self.tree, g, self.pools, self.knobs, rng)

    def search_random(self, method: str, budget: int, rng, bud: Budget, cache: dict) -> None:
        sp = self.space if method in V2_METHODS else None
        gen, n = 0, self.cfg.batch * 3
        while bud.timed < budget and bud.attempts < 12 * budget:
            gs = [random_genome(self.tree, self.pools, self.knobs, rng, space=sp) for _ in range(n)]
            self.evaluate(gs, method, gen, cache, bud)
            gen += 1

    def search_evo(self, method: str, budget: int, rng, bud: Budget, cache: dict,
                   mu: int = 6, lam: int = 18) -> None:
        v2 = method in V2_METHODS
        sp = self.space if v2 else None
        gs = [random_genome(self.tree, self.pools, self.knobs, rng, max_edits=3, space=sp) for _ in range(lam)]
        evs = self.evaluate(gs, method, 0, cache, bud)
        pop = [e for e in evs if e.fitness is not None]
        root = Eval("root", Genome([]), "", (), 3, "ok", 1.0, 0.0)
        gen = 1
        while bud.timed < budget and bud.attempts < 12 * budget:
            pool = sorted(pop + [root], key=lambda e: (e.fitness, rng.random()), reverse=True)[:mu + 1]
            kids = []
            for _ in range(lam):
                a, b = rng.choice(pool), rng.choice(pool)
                parent = a if a.fitness >= b.fitness else b
                g = Genome(list(parent.genome.edits))
                for _ in range(rng.choice([1, 1, 2])):
                    g.edits.append(self._edit(g, rng, v2))
                kids.append(g)
            evs = self.evaluate(kids, method, gen, cache, bud)
            merged = {e.cand_id: e for e in pop + [e for e in evs if e.fitness is not None]}
            pop = sorted(merged.values(), key=lambda e: e.fitness, reverse=True)[:mu]
            gen += 1

    # ------------------------------------------------------------------ confirm / minimize / validate
    def confirm_many(self, items: list[tuple[str, Eval]], stage: str, seed: int,
                     note: dict | None = None) -> dict:
        """One interleaved run: BASE, CTRL (copy of BASE) and every candidate. Repeats once if the
        A/A control deviates by more than control_max_dev_pct (noise burst during the run)."""
        bins = {"BASE": self.base.bin_path, "CTRL": self.ctrl_path}
        bins.update({f"{m}:{e.cand_id}": e.bin_path for m, e in items})
        res: dict = {}
        for attempt in range(2):
            ser = self._measure(bins, self.cfg.reps, self.cfg.warmup, seed + 101 * attempt)
            base = ser["BASE"]
            ctrl = paired_speedup(base.wall_ms, ser["CTRL"].wall_ms)
            dev = abs(ctrl.get("speedup", 2.0) - 1) * 100
            res = {"control": ctrl, "noisy": dev > self.cfg.control_max_dev_pct, "attempt": attempt}
            self._put_meas(f"CTRL:{self.pid}", "control" if stage != "validate" else "control_validate",
                           ser["CTRL"], base, ctrl, {"stage": stage, "attempt": attempt})
            for m, e in items:
                k = f"{m}:{e.cand_id}"
                s = ser[k]
                sp = paired_speedup(base.wall_ms, s.wall_ms) if s.status == "ok" else {"status": s.status}
                res[k] = sp
                if "speedup" in sp:
                    self._put_meas(k, stage, s, base, sp, {"method": (note or {}).get("method", m),
                                                           "orig": (note or {}).get("orig", e.cand_id),
                                                           "attempt": attempt,
                                                           "noisy": res["noisy"]})
            if not res["noisy"]:
                break
            self.log(f"  [{self.pid}] A/A control {ctrl.get('speedup', float('nan')):.3f}x deviates "
                     f"{dev:.1f}% > {self.cfg.control_max_dev_pct}%: {'repeating once' if attempt == 0 else 'flagged noisy'}")
            wait_quiet(self.log)
        return res

    def pick_candidates(self, cache: dict, top: int, min_speedup: float = 1.01) -> list[Eval]:
        good = [e for e in cache.values() if e.status == "ok" and not e.same_as_o3
                and e.speedup and e.speedup > min_speedup and e.fitness is not None]
        good.sort(key=lambda e: e.fitness, reverse=True)
        out, bins = [], set()
        for e in good:
            if e.bin_hash not in bins:
                bins.add(e.bin_hash)
                out.append(e)
            if len(out) >= top:
                break
        return out

    def minimize(self, win: Eval, win_sp: float) -> tuple[Eval | None, dict]:
        """Batched: try reverting every edit at once (one screening batch, 5 rounds); then revert
        all individually-harmless edits together, falling back to greedy over those if needed."""
        cur = list(win.genome.edits)
        cache: dict = {}
        # The winner is re-screened in the same batch as its trials, and the tolerance is relative
        # (an absolute 0.01 would be far below the noise at large speedups).
        trials = [Genome(cur[:i] + cur[i + 1:]) for i in range(len(cur))]
        evs = self.evaluate(trials + [Genome(cur)], "minimize", 0, cache, Budget(), screen_reps=5, halving=False)
        ref = evs[-1].speedup if evs[-1].status == "ok" and evs[-1].speedup else win_sp
        thr = ref * 0.99
        evs = evs[:-1]
        removable = [i for i, te in enumerate(evs) if te.status == "ok" and te.speedup is not None and te.speedup >= thr]
        if removable:
            joint = Genome([e for i, e in enumerate(cur) if i not in removable])
            je = self.evaluate([joint], "minimize", 0, cache, Budget(), screen_reps=5, halving=False)[0]
            if je.status == "ok" and je.speedup is not None and je.speedup >= thr:
                cur = joint.edits
            else:      # interactions: greedy, most harmless first
                order = sorted(removable, key=lambda i: -(evs[i].speedup or 0))
                keep = set(range(len(cur)))
                for i in order:
                    t = Genome([e for j, e in enumerate(cur) if j in keep - {i}])
                    te = self.evaluate([t], "minimize", 0, cache, Budget(), screen_reps=5, halving=False)[0]
                    if te.status == "ok" and te.speedup is not None and te.speedup >= thr:
                        keep.discard(i)
                cur = [e for j, e in enumerate(cur) if j in keep]
        info = {"orig_edits": len(win.genome.edits), "min_edits": len(cur), "min_genome": cur}
        if len(cur) < len(win.genome.edits):
            me = self.evaluate([Genome(cur)], "minimize", 0, cache, Budget(), screen_reps=5, halving=False)[0]
            if me.status == "ok" and not me.same_as_o3 and me.bin_hash != win.bin_hash:
                return me, info
        return None, info

    def _eval_from_db(self, key: str) -> Eval | None:
        r = self.store.get_candidate(key)
        if r is None:
            return None
        g = Genome.from_json(r["genome_json"])
        flags = tuple(r["opt_flags"].split()) if r["opt_flags"] else ()
        b = self.tc.build(self.src, r["pipeline"], r["backend"], self.cflags, flags)
        if not b.ok:
            return None
        return Eval(key.split(":", 1)[1], g, r["pipeline"], flags, r["backend"], "ok", None, None,
                    b.bin_hash, b.bin_path, b.text_size, b.bin_hash == self.base.bin_hash, key.split(":", 1)[0])

    def finalize(self, methods: list[str], seed: int) -> dict:
        """Merged confirmation of all methods' shortlists, minimization and validation."""
        items: list[tuple[str, Eval]] = []
        bins = set()
        for m in methods:
            rows = self.store.rows("SELECT summary_json FROM runs WHERE program_id=? AND method=? AND seed=?",
                                   (self.pid, m, seed))
            if not rows:
                continue
            for key in json.loads(rows[0]["summary_json"] or "{}").get("shortlist", []):
                with self.stage("compile"):
                    e = self._eval_from_db(key)
                if e and not e.same_as_o3 and e.bin_hash not in bins:
                    bins.add(e.bin_hash)
                    items.append((m, e))
        summary: dict = {"n_confirmed": len(items)}
        if not items:
            summary["result"] = "no candidate above threshold (O3 stays)"
            return summary
        with self.stage("confirm"):
            res = self.confirm_many(items, "confirm", seed=7)
        summary["control"] = res["control"].get("speedup")
        summary["noisy_confirm"] = res["noisy"]
        conf = []
        for m, e in items:
            r = res.get(f"{m}:{e.cand_id}", {})
            if "speedup" in r:
                conf.append({"key": f"{m}:{e.cand_id}", "method": m, "speedup": r["speedup"],
                             "ci": [r["ci_lo"], r["ci_hi"]], "fit": self._fitness(r["speedup"], e.text_size), "e": e})
        summary["confirmed"] = [{k: v for k, v in c.items() if k not in ("e", "fit")} for c in conf]
        wins = [c for c in conf if c["ci"][0] > 1.0]
        if not wins:
            summary["result"] = "no confirmed gain (O3 stays)"
            return summary
        w = max(wins, key=lambda c: c["fit"])
        summary["winner"] = {"key": w["key"], "method": w["method"], "speedup": w["speedup"], "ci": w["ci"],
                             "n_edits": len(w["e"].genome.edits), "raw": w["e"].genome.raw}
        val_items = [(w["method"], w["e"])]
        if w["e"].genome.raw is None and w["e"].genome.edits:
            with self.stage("minimize"):
                me, info = self.minimize(w["e"], w["speedup"])
            summary["minimize"] = {k: v for k, v in info.items()}
            if me is not None:
                val_items.append(("minimize", me))
                summary["minimize"]["key"] = f"minimize:{me.cand_id}"
        if self.cfg.validate:
            with self.stage("validate"):
                vres = self.confirm_many(val_items, "validate", seed=1009 + seed,
                                         note=None)
            v = vres.get(w["key"], {})
            summary["validated"] = {"speedup": v.get("speedup"), "ci": [v.get("ci_lo"), v.get("ci_hi")],
                                    "control": vres["control"].get("speedup"), "noisy": vres["noisy"]}
            if len(val_items) > 1:
                mv = vres.get(f"minimize:{val_items[1][1].cand_id}", {})
                summary["validated_min"] = {"speedup": mv.get("speedup"), "ci": [mv.get("ci_lo"), mv.get("ci_hi")]}
        return summary


# ---------------------------------------------------------------------- driver
def _already_done(store: Store, pid: str, method: str, seed: int | None = None) -> bool:
    if seed is None:
        q, a = "SELECT 1 FROM runs WHERE program_id=? AND method=? AND finished IS NOT NULL", (pid, method)
    else:
        q, a = "SELECT 1 FROM runs WHERE program_id=? AND method=? AND seed=? AND finished IS NOT NULL", (pid, method, seed)
    return bool(store.rows(q, a))


def _fmt_stages(st: dict) -> str:
    return " ".join(f"{k} {v:.0f}s" for k, v in sorted(st.items(), key=lambda kv: -kv[1]) if v >= 0.5)


def run_program(tc: Toolchain, cfg: Config, store: Store, rec: dict, methods: list[str],
                budget: int, seed: int, force: bool = False, log=print) -> None:
    pid = rec["program_id"]
    stages = ["levels"] + methods
    todo = [m for m in stages if force or not _already_done(store, pid, m)]
    merged = cfg.merged_confirm
    legacy = not todo and not any("shortlist" in json.loads(r["summary_json"] or "{}") for r in
                                  store.rows("SELECT summary_json FROM runs WHERE program_id=?", (pid,)))
    if legacy:
        log(f"[{pid}] searched with the old per-method confirmation; use `search validate` for it")
        return
    need_final = merged and (bool(todo) or not _already_done(store, pid, "final", seed))
    if not todo and not need_final:
        log(f"[{pid}] already done, skipping")
        return
    t_prog = time.time()
    ps = ProgramSearch(tc, cfg, store, rec, log=log)
    log(f"\n[{pid}] baseline -O3 {ps.base_s * 1000:.0f} ms | pools "
        + ", ".join(f"{k} {len(v)}" for k, v in sorted(ps.pools.items())) + f" | knobs {len(ps.knobs)}")
    for m in todo:
        t0 = time.time()
        st0 = dict(ps.stage_s)
        started = time.strftime("%Y-%m-%dT%H:%M:%S")
        bud, cache = Budget(), {}
        rng = random.Random(f"{seed}:{pid}:{m}")
        if m == "levels":
            gs = [Genome([{"op": "backend", "value": b}], raw=p) for p, b in LEVEL_SEEDS]
            if ps.o3_mismatch:
                gs.append(Genome([{"op": "backend", "value": 3}], raw=ps.o3_text))
            ps.evaluate(gs, "levels", 0, cache, bud)
            top = 2
        else:
            (ps.search_random if m.startswith("random") else ps.search_evo)(m, budget, rng, bud, cache)
            top = cfg.confirm_top
        cands = ps.pick_candidates(cache, top, 1.02 if m == "levels" else 1.01)
        best_screen = max((e.speedup for e in cache.values() if e.speedup), default=1.0)
        n_slow = sum(1 for e in cache.values() if e.status == "slow")
        summary = {"attempts": bud.attempts, "timed": bud.timed, "best_screen": best_screen,
                   "candidates_confirmed": len(cands), "shortlist": [f"{m}:{e.cand_id}" for e in cands],
                   "slow_killed": n_slow, "action_space": "v2" if m in V2_METHODS else "v1",
                   "o3_mismatch": ps.o3_mismatch}
        line = (f"[{pid}] {m:<7s} attempts {bud.attempts:>3d} timed {bud.timed:>3d} slow {n_slow:>3d} "
                f"best-screen {best_screen:.3f}x shortlist {len(cands)}")
        if cands and not merged:
            res = ps.confirm_many([(m, e) for e in cands], "confirm", seed=7)
            ranked = sorted(((res[f'{m}:{e.cand_id}'].get("speedup", 0), e) for e in cands), key=lambda t: t[0], reverse=True)
            sp_best, e_best = ranked[0]
            r = res[f"{m}:{e_best.cand_id}"]
            summary.update({"confirmed_best": {"cand_id": e_best.cand_id, "speedup": sp_best,
                                               "ci": [r.get("ci_lo"), r.get("ci_hi")]},
                            "control": res["control"].get("speedup")})
            line += f" -> confirmed {sp_best:.3f}x [{r.get('ci_lo', 0):.3f},{r.get('ci_hi', 0):.3f}]"
        summary["stage_s"] = {k: round(v - st0.get(k, 0), 1) for k, v in ps.stage_s.items()}
        store.put_run({"run_id": f"{pid}:{m}:{seed}", "program_id": pid, "method": m, "seed": seed,
                       "budget": budget, "started": started,
                       "finished": time.strftime("%Y-%m-%dT%H:%M:%S"),
                       "config_json": json.dumps({"screen_reps": cfg.screen_reps, "reps": cfg.reps,
                                                  "batch": cfg.batch, "size_cap": cfg.size_cap,
                                                  "screen_halving": cfg.screen_halving,
                                                  "screen_keep": cfg.screen_keep, "screen_abort": cfg.screen_abort,
                                                  "isolate_sibling": cfg.isolate_sibling}),
                       "summary_json": json.dumps(summary)})
        log(line + f"  ({time.time() - t0:.0f}s: {_fmt_stages(summary['stage_s'])})")
    if need_final:
        t0 = time.time()
        st0 = dict(ps.stage_s)
        started = time.strftime("%Y-%m-%dT%H:%M:%S")
        all_methods = [m for m in ["levels"] + SEARCH_METHODS if _already_done(store, pid, m, seed)]
        summ = ps.finalize(all_methods, seed)
        summ["stage_s"] = {k: round(v - st0.get(k, 0), 1) for k, v in ps.stage_s.items()}
        store.put_run({"run_id": f"{pid}:final:{seed}", "program_id": pid, "method": "final", "seed": seed,
                       "budget": budget, "started": started, "finished": time.strftime("%Y-%m-%dT%H:%M:%S"),
                       "config_json": json.dumps({"reps": cfg.reps, "warmup": cfg.warmup,
                                                  "control_max_dev_pct": cfg.control_max_dev_pct,
                                                  "methods": all_methods}),
                       "summary_json": json.dumps(summ, default=str)})
        line = f"[{pid}] final   confirmed {summ.get('n_confirmed', 0)}"
        if "winner" in summ:
            w = summ["winner"]
            line += f" -> winner {w['method']} {w['speedup']:.3f}x [{w['ci'][0]:.3f},{w['ci'][1]:.3f}] ctrl {summ.get('control', 0):.3f}"
            if "minimize" in summ:
                line += f" | edits {summ['minimize']['orig_edits']}->{summ['minimize']['min_edits']}"
            if "validated" in summ and summ["validated"]["speedup"]:
                v = summ["validated"]
                line += f" | VALIDATED {v['speedup']:.3f}x [{v['ci'][0]:.3f},{v['ci'][1]:.3f}]" + (" NOISY" if v["noisy"] else "")
        else:
            line += f" -> {summ.get('result', '')}"
        log(line + f"  ({time.time() - t0:.0f}s: {_fmt_stages(summ['stage_s'])})")
    log(f"[{pid}] program total {time.time() - t_prog:.0f}s | stages: {_fmt_stages(ps.stage_s)}")


def revalidate_serial(tc: Toolchain, cfg: Config, store: Store, recs: list[dict], seed: int, log=print) -> None:
    """Re-measure each program's winner from a (parallel) search run in a fresh SERIAL run on one
    core with nothing else timing: stage 'validate_serial'. Parallel timing passed the multi-core A/A
    test, but these are the numbers reported, so they are taken under the original serial protocol."""
    for rec in recs:
        pid = rec["program_id"]
        if store.rows("SELECT 1 FROM measurements WHERE program_id=? AND stage='validate_serial'", (pid,)):
            log(f"[{pid}] already re-validated serially, skipping")
            continue
        r = store.rows("SELECT summary_json FROM runs WHERE program_id=? AND method='final' AND seed=?", (pid, seed))
        s = json.loads(r[0]["summary_json"]) if r else {}
        if "winner" not in s:
            continue
        t0 = time.time()
        ps = ProgramSearch(tc, cfg, store, rec, log=log)
        items = []
        for key in [s["winner"]["key"]] + ([s["minimize"]["key"]] if s.get("minimize", {}).get("key") else []):
            e = ps._eval_from_db(key)
            if e is not None and not e.same_as_o3:
                items.append((key.split(":", 1)[0], e))
        if not items:
            log(f"[{pid}] could not rebuild the winner")
            continue
        with ps.stage("validate"):
            res = ps.confirm_many(items, "validate_serial", seed=2003 + seed)
        v = res.get(s["winner"]["key"], {})
        log(f"[{pid}] parallel-validated {(s.get('validated') or {}).get('speedup') or float('nan'):.3f}x -> serial "
            f"{v.get('speedup', float('nan')):.3f}x [{v.get('ci_lo', float('nan')):.3f},{v.get('ci_hi', float('nan')):.3f}] "
            f"ctrl {res['control'].get('speedup', float('nan')):.3f}{' NOISY' if res['noisy'] else ''}  ({time.time() - t0:.0f}s)")


def validate_existing(tc: Toolchain, cfg: Config, store: Store, recs: list[dict], log=print) -> None:
    """For programs searched before validation existed: re-measure the best confirmed candidate
    (the one the old report picked) in a fresh, independent run, so the gate can use it."""
    for rec in recs:
        pid = rec["program_id"]
        if store.rows("SELECT 1 FROM measurements WHERE program_id=? AND stage='validate'", (pid,)):
            log(f"[{pid}] already validated, skipping")
            continue
        rows = store.rows("""SELECT m.cand_id, m.speedup, m.ci_lo, m.ci_hi FROM measurements m
                             WHERE m.program_id=? AND m.stage IN ('confirm','confirm_min') AND m.ci_lo > 1.0
                             ORDER BY m.speedup DESC""", (pid,))
        if not rows:
            log(f"[{pid}] no confirmed gain; nothing to validate (counts as 1.000)")
            continue
        t0 = time.time()
        ps = ProgramSearch(tc, cfg, store, rec, log=log)
        top = rows[0]
        e = ps._eval_from_db(top["cand_id"])
        if e is None:
            log(f"[{pid}] could not rebuild {top['cand_id']}")
            continue
        m = top["cand_id"].split(":", 1)[0]
        with ps.stage("validate"):
            res = ps.confirm_many([(m, e)], "validate", seed=1009)
        v = res.get(top["cand_id"], {})
        log(f"[{pid}] confirmed {top['speedup']:.3f}x [{top['ci_lo']:.3f},{top['ci_hi']:.3f}] -> validated "
            f"{v.get('speedup', float('nan')):.3f}x [{v.get('ci_lo', float('nan')):.3f},{v.get('ci_hi', float('nan')):.3f}] "
            f"ctrl {res['control'].get('speedup', float('nan')):.3f}{' NOISY' if res['noisy'] else ''}  ({time.time() - t0:.0f}s)")


def _describe_edits(edits: list[dict], names: dict[int, str], ctxs: dict[int, str]) -> list[str]:
    nm, cx = dict(names), dict(ctxs)
    out = []
    for e in edits:
        op = e["op"]
        if op == "del":
            out.append(f"delete    {nm.get(e['id'], '?')}  [{cx.get(e['id'], '?')}]")
        elif op == "dup":
            nm[e["nid"]], cx[e["nid"]] = nm.get(e["id"], "?"), cx.get(e["id"], "?")
            out.append(f"duplicate {nm.get(e['id'], '?')}  [{cx.get(e['id'], '?')}]")
        elif op == "swap":
            out.append(f"swap      {nm.get(e['id'], '?')} with the pass after it  [{cx.get(e['id'], '?')}]")
        elif op == "ins":
            nm[e["nid"]], cx[e["nid"]] = e["pass"], e["ctx"]
            out.append(f"insert    {e['pass']} after {nm.get(e['after'], '?')}  [{e['ctx']}]")
        elif op == "knob":
            out.append(f"{'llc flag ' if str(e['name']).startswith('llc:') else 'opt flag '} "
                       f"{str(e['name']).removeprefix('llc:')}={e['value']}")
        elif op == "backend":
            out.append(f"llc -O{e['value']}")
        elif op == "param":
            out.append(f"option    {e['tok']} -> {e['new']} on {nm.get(e['id'], '?').split('<')[0]} #{e['id']}")
        elif op == "param_all":
            out.append(f"option    {e['tok']} -> {e['new']} on EVERY {e['pass']}")
        elif op == "del_all":
            out.append(f"delete    EVERY {e['pass']}")
    return out


def show(store: Store, tc: Toolchain, program_id: str) -> str:
    tree = parse_pipeline(tc.pipeline_string("O3"))
    names, ctxs = {}, {}
    for p, _i, n in _walk(tree):
        if n.is_leaf:
            names[n.id], ctxs[n.id] = n.text, _ctx_of(p, tree)
    base = store.rows("SELECT text_size FROM candidates WHERE cand_id=?", (f"baseline:{program_id}",))
    base_sz = (base[0]["text_size"] if base else 0) or 1
    rows = store.rows("""SELECT m.stage, m.speedup, m.ci_lo, m.ci_hi, m.n, c.method, c.genome_json, c.pipeline,
                                c.backend, c.text_size, m.note
                         FROM measurements m JOIN candidates c ON c.cand_id = m.cand_id
                         WHERE m.program_id=? AND m.stage IN ('confirm','confirm_min','validate')
                         ORDER BY m.stage='validate' DESC, m.speedup DESC""",
                     (program_id,))
    if not rows:
        return f"No confirmed results for {program_id}."
    lines = [f"Confirmed candidates for {program_id} (speedup vs -O3, 95% CI, binary size vs -O3):"]
    for r in rows:
        g = Genome.from_json(r["genome_json"])
        note = json.loads(r["note"]) if r["note"] else {}
        who = note.get("method", r["method"])
        tag = {"confirm_min": "minimized", "validate": f"VALIDATED {who}"}.get(r["stage"], who)
        lines.append(f"\n  [{tag}] {r['speedup']:.3f}x [{r['ci_lo']:.3f}, {r['ci_hi']:.3f}]  "
                     f"size {r['text_size'] / base_sz:.2f}x  (n={r['n']})" + ("  NOISY" if note.get("noisy") else ""))
        if g.raw is not None:
            be = next((e["value"] for e in g.edits if e["op"] == "backend"), 3)
            lines.append(f"      pipeline {g.raw}, llc -O{be}")
        else:
            for d in _describe_edits(g.edits, names, ctxs) or ["(no edits: identical to -O3)"]:
                lines.append(f"      {d}")
    return "\n".join(lines)


# ---------------------------------------------------------------------- report
def _geomean(xs):
    xs = list(xs)
    return math.exp(sum(math.log(x) for x in xs) / len(xs)) if xs else float("nan")


def _boot_geomean_ci(vals, n=4000, seed=0):
    if len(vals) < 3:
        return float("nan"), float("nan")
    rng = np.random.default_rng(seed)
    lv = np.log(np.asarray(vals, float))
    b = np.exp(lv[rng.integers(0, len(lv), (n, len(lv)))].mean(axis=1))
    return float(np.quantile(b, 0.025)), float(np.quantile(b, 0.975))


def _gate_lines(vals: list[float], label: str) -> list[str]:
    vals = sorted(vals, reverse=True)
    n = len(vals)
    g_all, g_ex = _geomean(vals), (_geomean(vals[1:]) if n > 1 else float("nan"))
    lo, hi = _boot_geomean_ci(vals)
    share5 = sum(1 for v in vals if v >= 1.05) / n
    share3 = sum(1 for v in vals if v >= 1.03) / n
    out = [f"[{label}] programs {n} | geomean {(g_all - 1) * 100:+.2f}% (95% CI {(lo - 1) * 100:+.2f}%..{(hi - 1) * 100:+.2f}%)"
           f" | excluding largest {(g_ex - 1) * 100:+.2f}% | median {(vals[n // 2] - 1) * 100:+.2f}%"
           f" | >=3%: {share3 * 100:.0f}% | >=5%: {share5 * 100:.0f}% | largest {vals[0]:.3f}x"]
    passed = (g_ex >= 1.05 if n > 1 else False) or share5 >= 0.30
    verdict = (f"INCONCLUSIVE (only {n} programs; need >= 10)" if n < 10 else ("PASS" if passed else "NOT MET"))
    out.append(f"[{label}] HEADROOM GATE (geomean excl. largest >= +5%, or >= 30% of programs >= +5%): {verdict}")
    return out


def report(store: Store) -> str:
    rows = store.rows("""SELECT m.program_id, m.stage, m.speedup, m.ci_lo, m.ci_hi, m.note, c.method, c.n_edits,
                                c.text_size, m.cand_id, m.id
                         FROM measurements m LEFT JOIN candidates c ON c.cand_id = m.cand_id
                         WHERE m.stage IN ('confirm','confirm_min','control','validate')
                         ORDER BY m.id""")
    base_sz = {r["program_id"]: r["text_size"] for r in
               store.rows("SELECT program_id, text_size FROM candidates WHERE cand_id LIKE 'baseline:%'")}
    searched = {r["program_id"] for r in store.rows("SELECT DISTINCT program_id FROM runs WHERE method != 'final'")}
    progs: dict[str, dict] = {p: {"control": [], "best": {}, "validated": None} for p in searched}
    for r in rows:
        d = progs.setdefault(r["program_id"], {"control": [], "best": {}, "validated": None})
        note = json.loads(r["note"]) if r["note"] else {}
        if r["stage"] == "control":
            if r["speedup"]:
                d["control"].append(r["speedup"])
            continue
        if r["stage"] == "validate":
            if str(r["cand_id"]).startswith("minimize:") and d["validated"]:
                continue
            d["validated"] = {"speedup": r["speedup"], "ci": (r["ci_lo"], r["ci_hi"]), "noisy": note.get("noisy"),
                              "method": note.get("method", r["method"])}
            continue
        method = note.get("method") or r["method"]
        if r["ci_lo"] and r["ci_lo"] > 1.0:
            cur = d["best"].get(method)
            if cur is None or r["speedup"] > cur["speedup"]:
                d["best"][method] = {"speedup": r["speedup"], "ci": (r["ci_lo"], r["ci_hi"]),
                                     "size": (r["text_size"] or 0) / (base_sz.get(r["program_id"]) or 1),
                                     "edits": r["n_edits"]}
    if not progs:
        return "No confirmed results yet."
    methods = [m for m in ["levels"] + SEARCH_METHODS if any(m in d["best"] for d in progs.values())] or ["levels", "random", "evo"]
    hdr = f"{'program':<40s} " + " ".join(f"{m:>8s}" for m in methods) + f"  {'best':>8s} {'valid.':>8s} {'size':>5s} {'ctrl':>6s}"
    lines = [hdr]
    best_of, valid_of, ctrl_dev, noisy, curse = {}, {}, [], [], []
    for pid in sorted(progs):
        d = progs[pid]
        cells, allv = [], []
        for m in methods:
            b = d["best"].get(m)
            cells.append(f"{b['speedup']:.3f}x" if b else "   -   ")
            if b:
                allv.append((b["speedup"], b))
        top = max(allv, key=lambda t: t[0]) if allv else None
        best_of[pid] = top[0] if top else 1.0
        v = d["validated"]
        if top is None:
            valid_of[pid] = 1.0
            vcell = "   -   "
        elif v and v["speedup"]:
            valid_of[pid] = v["speedup"] if v["ci"][0] and v["ci"][0] > 1.0 else 1.0
            vcell = f"{v['speedup']:.3f}x" + ("*" if not (v["ci"][0] and v["ci"][0] > 1.0) else "")
            if v["ci"][1] and v["ci"][1] < 1.0:
                curse.append(pid)
            if v.get("noisy"):
                noisy.append(pid)
        else:
            vcell = "  n/a  "
        ctrl = _geomean(d["control"]) if d["control"] else float("nan")
        if d["control"]:
            ctrl_dev.append(abs(ctrl - 1))
            if abs(ctrl - 1) > 0.01:
                noisy.append(pid)
        lines.append(f"{pid:<40s} " + " ".join(f"{c:>8s}" for c in cells)
                     + f"  {best_of[pid]:>7.3f}x {vcell:>8s} {top[1]['size'] if top else 1.0:>5.2f} {ctrl:>6.3f}")
    noise = max(ctrl_dev) * 100 if ctrl_dev else float("nan")
    lines += ["", "best = max over confirmed candidates (optimistic: a winner's curse over several candidates).",
              "valid. = the best candidate re-measured in a fresh independent run; * = CI includes 1.0 (counts as 1.000).",
              "Programs with no confirmed gain count as 1.000 (the fallback keeps -O3).",
              f"Measured noise floor (A/A control, worst program): {noise:.2f}%"]
    if noisy:
        lines.append(f"Programs with an A/A control off by >1% (treat with care): {', '.join(sorted(set(noisy)))}")
    if curse:
        lines.append(f"Confirmed winners that were SLOWER than -O3 on validation: {', '.join(curse)}")
    mism = sorted({r["program_id"] for r in store.rows("SELECT program_id, summary_json FROM runs")
                   if '"o3_mismatch": true' in (r["summary_json"] or "")})
    if mism:
        lines.append(f"Printed -O3 pipeline != default<O3> (gains may partly come from that; still measured vs real -O3): "
                     f"{', '.join(mism)}")
    lines.append("")
    lines += _gate_lines(list(best_of.values()), "confirmed best (old metric)")
    need = [p for p in progs if best_of[p] > 1.0 and not progs[p]["validated"]]
    if need:
        lines.append(f"[validated] not available for {len(need)} program(s) with a confirmed gain: "
                     "run `python -m nc.cli search validate` (gate decision should use validated numbers)")
    else:
        lines += _gate_lines(list(valid_of.values()), "validated (use this)")
    return "\n".join(lines)
