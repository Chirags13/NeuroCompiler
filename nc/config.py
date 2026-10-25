from __future__ import annotations

import tomllib
from dataclasses import dataclass, fields
from pathlib import Path


@dataclass
class Config:
    machine_id: str = "wsl2-local"
    timing_cpu: int = 5
    llvm_bin_dir: str = "/usr/lib/llvm-18/bin"
    march: str = "native"
    reps: int = 30
    warmup: int = 5
    settle_s: float = 3.0
    no_aslr: bool = True
    timeout_s: float = 60.0
    work_dir: str = "work"
    results_dir: str = "results"
    corpus_dir: str = "corpus"
    floor_s: float = 0.35
    ceiling_s: float = 8.0
    scan_reps: int = 3
    db_path: str = "results/dataset.sqlite"
    budget: int = 60
    batch: int = 8
    screen_reps: int = 3
    compile_workers: int = 4
    size_cap: float = 1.10
    confirm_top: int = 3
    # --- speed / robustness (screening only; confirmation protocol unchanged)
    screen_halving: bool = True     # time every candidate 1 round, re-time only plausible winners
    screen_keep: float = 0.98       # ... i.e. those whose 1-round speedup is >= this
    screen_abort: float = 1.30      # kill a screening run slower than this x the -O3 runtime
    verify_parallel: bool = True    # output verification on helper CPUs while nothing is timed
    merged_confirm: bool = True     # one confirmation run per program for all methods' shortlists
    validate: bool = True           # re-measure the program winner in a fresh, independent run
    control_max_dev_pct: float = 1.0  # A/A control further from 1.0 than this => redo confirmation once
    # --- environment guards
    isolate_sibling: bool = False   # also keep the harness off timing_cpu's SMT sibling (changes conditions vs. old data)
    quiet_max_busy: float = 0.6     # wait before timing while other processes use more CPU cores than this (0 = off)
    quiet_max_wait_s: float = 1800.0
    layout_copies: int = 1          # >1: rotate K fresh copies of each binary across rounds (layout randomization; opt-in)
    max_ci_halfwidth_pct: float = 1.0
    max_aa_bias_pct: float = 1.0
    max_drift_pct: float = 2.0
    min_o0_o3_speedup: float = 1.2


def load_config(path: str | Path | None = None) -> Config:
    p = Path(path or "config.toml")
    cfg = Config()
    if not p.exists():
        return cfg
    data = tomllib.loads(p.read_text())
    flat: dict = {}
    for key, val in data.items():
        if isinstance(val, dict):
            flat.update(val)
        else:
            flat[key] = val
    known = {f.name for f in fields(Config)}
    unknown = set(flat) - known
    if unknown:
        raise ValueError(f"Unknown config keys in {p}: {sorted(unknown)}")
    for k, v in flat.items():
        setattr(cfg, k, v)
    return cfg
