"""Compile-time-evaluation check for large Phase 5 winners.

A program with NO runtime input (no args, no stdin) always computes the same thing. Aggressive
unrolling/propagation can let the compiler evaluate much of that work at compile time: output stays
byte-identical, runtime collapses, and the "speedup" would not transfer to real programs whose input
arrives at run time. For each winner >= MIN_SPEEDUP this runs -O3 and the winner under cachegrind
(instruction counts; -march=x86-64-v3 binaries, since valgrind cannot run AVX-512) and flags it as a
suspect if the program is input-free AND executed instructions drop >= 10x (AVX2 vectorization alone
cuts instructions by at most ~8x: 8 floats per instruction).
Run after all timing has finished (uses the helper CPUs in parallel):
    .venv/bin/python scripts/artifact_check.py
"""
import copy
import json
import re
import sqlite3
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from nc.config import load_config          # noqa: E402
from nc.corpus import load_manifest        # noqa: E402
from nc.timing import RunSpec, helper_cpus  # noqa: E402
from nc.toolchain import Toolchain         # noqa: E402

MIN_SPEEDUP, FOLD_RATIO = 1.5, 10.0
cfg = load_config("config.toml")
c2 = copy.copy(cfg)
c2.march = "x86-64-v3"
tc = Toolchain(c2)
man = load_manifest(Path(cfg.corpus_dir) / "manifest.jsonl")
db = sqlite3.connect(cfg.db_path)


def winners():
    out = []
    for pid, s in db.execute("SELECT program_id, summary_json FROM runs WHERE method='final' AND seed=2"):
        d = json.loads(s)
        if "winner" not in d:
            continue
        key = d["winner"]["key"]
        r = db.execute("SELECT speedup FROM measurements WHERE stage='validate_serial' AND cand_id=? ORDER BY id DESC",
                       (key,)).fetchone()
        sp = r[0] if r else (d.get("validated") or {}).get("speedup") or 0
        if sp >= MIN_SPEEDUP:
            row = db.execute("SELECT pipeline, opt_flags, backend FROM candidates WHERE cand_id=?", (key,)).fetchone()
            out.append((pid, key, sp, tuple(row)))
    return out


def irefs(binary: str, spec: RunSpec, cpu: int) -> tuple[int, str]:
    stdin = open(spec.stdin_path, "rb") if spec.stdin_path else subprocess.DEVNULL
    r = subprocess.run(["taskset", "-c", str(cpu), "valgrind", "--tool=cachegrind", "--cache-sim=no",
                        "--cachegrind-out-file=/dev/null", binary, *spec.args], stdin=stdin,
                       capture_output=True, cwd=spec.cwd, timeout=7200)
    m = re.search(rb"I\s+refs:\s+([\d,]+)", r.stderr)
    import hashlib
    return (int(m.group(1).replace(b",", b"")) if m else -1), hashlib.sha256(r.stdout).hexdigest()[:16]


def check(job):
    i, (pid, key, sp, row) = job
    rec = man[pid]
    cf = tuple(rec.get("cflags") or [])
    spec = RunSpec.from_dict(rec["time_spec"])
    cpu = helper_cpus(cfg.timing_cpu)[i % len(helper_cpus(cfg.timing_cpu))]
    b3 = tc.build(rec["src"], "default<O3>", 3, cf)
    bw = tc.build(rec["src"], row[0], row[2], cf, tuple(row[1].split()) if row[1] else ())
    i3, h3 = irefs(b3.bin_path, spec, cpu)
    iw, hw = irefs(bw.bin_path, spec, cpu)
    input_free = not spec.args and not spec.stdin_path
    ratio = i3 / iw if iw > 0 else float("inf")
    return {"program": pid, "speedup": sp, "input_free": input_free, "irefs_o3": i3, "irefs_winner": iw,
            "instr_ratio": ratio, "same_output": h3 == hw,
            "suspect_compile_time_eval": input_free and ratio >= FOLD_RATIO}


ws = winners()
print(f"{len(ws)} winners >= {MIN_SPEEDUP}x to check", flush=True)
with ThreadPoolExecutor(len(helper_cpus(cfg.timing_cpu))) as ex:
    res = list(ex.map(check, enumerate(ws)))
for r in sorted(res, key=lambda r: -r["speedup"]):
    print(f"{r['program']:44s} {r['speedup']:7.2f}x  instr ratio {r['instr_ratio']:7.1f}  "
          f"input-free {str(r['input_free']):5s}  same output {r['same_output']}  "
          f"{'SUSPECT compile-time evaluation' if r['suspect_compile_time_eval'] else ''}")
out = Path(cfg.results_dir) / "artifact_check.json"
out.write_text(json.dumps({"created": time.strftime("%Y-%m-%dT%H:%M:%S"), "rule": {"min_speedup": MIN_SPEEDUP,
                           "fold_ratio": FOLD_RATIO}, "rows": res}, indent=1))
print(f"saved {out}")
