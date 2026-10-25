"""Does memory layout bias A/A measurements, and does layout randomization remove it?

For each program, repeat an A/A measurement (-O3 vs a FRESH byte-identical copy, so each repeat
gets a new physical placement) several times, with layout_copies = 1 (current protocol) and with
layout_copies = K (each binary rotated over K fresh copies). If layout matters, K=1 shows A/A
results spread far beyond their CIs; randomization should pull them back to ~1.000.
Run:  .venv/bin/python scripts/layout_test.py polybench/jacobi-1d ss/BenchmarkGame/fannkuch
"""
import json
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from nc.config import load_config                                  # noqa: E402
from nc.corpus import load_manifest                                # noqa: E402
from nc.timing import RunSpec, configure, measure_interleaved, paired_speedup  # noqa: E402
from nc.toolchain import Toolchain                                 # noqa: E402

REPEATS, REPS, K = 4, 20, 4
cfg = load_config("config.toml")
tc = Toolchain(cfg)
man = load_manifest(Path(cfg.corpus_dir) / "manifest.jsonl")
out = {}
for pid in sys.argv[1:]:
    rec = man[pid]
    spec = RunSpec.from_dict(rec["time_spec"])
    base = tc.build(rec["src"], "default<O3>", 3, tuple(rec.get("cflags") or []))
    for k in (1, K):
        configure(no_aslr=cfg.no_aslr, settle_s=cfg.settle_s, quiet_max_busy=cfg.quiet_max_busy,
                  quiet_max_wait_s=cfg.quiet_max_wait_s, layout_copies=k)
        vals = []
        for r in range(REPEATS):
            ctrl = tc.work / "tmp" / f"layout_ctrl_{r}"
            shutil.copy2(base.bin_path, ctrl)          # fresh file => new physical placement
            ser = measure_interleaved({"A": base.bin_path, "B": str(ctrl)}, spec.args, REPS, cfg.warmup,
                                      cfg.timing_cpu, 60, seed=r, stdin_path=spec.stdin_path, cwd=spec.cwd)
            sp = paired_speedup(ser["A"].wall_ms, ser["B"].wall_ms)
            vals.append(sp)
            print(f"{pid:<32s} copies={k} repeat {r}: A/A {sp['speedup']:.4f} [{sp['ci_lo']:.4f},{sp['ci_hi']:.4f}]",
                  flush=True)
            ctrl.unlink()
        dev = max(abs(v["speedup"] - 1) for v in vals) * 100
        excl = sum(1 for v in vals if not (v["ci_lo"] <= 1 <= v["ci_hi"]))
        print(f"  -> copies={k}: worst A/A deviation {dev:.2f}%, CIs excluding 1.0: {excl}/{REPEATS}\n", flush=True)
        out[f"{pid}|copies={k}"] = {"worst_dev_pct": dev, "ci_excl": excl, "runs": vals}
p = Path(cfg.results_dir) / f"layout_test_{time.strftime('%Y%m%d-%H%M%S')}.json"
p.write_text(json.dumps(out, indent=1))
print(f"saved {p}")
