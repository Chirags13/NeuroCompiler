# NeuroCompiler: A Hybrid ML + RL Guided Optimization Framework for LLVM

NeuroCompiler is a runtime-grounded ML + RL compiler optimization framework. The project now follows a three-phase rebuild:

1. Phase 1 — runtime-grounded dataset generation.
2. Phase 2 — supervised learning plus reinforcement learning.
3. Phase 3 — LLVM integration and final evaluation.

## Phase 1 is now the controlled foundation

The dataset specification in `data/DATASET_SPEC.md` makes measured execution runtime the primary target. IR size and code size remain important observations, but a smaller IR is not treated as a successful optimization when execution gets slower.

The runtime corpus is built from diverse benchmark families and is split at the project level to prevent leakage. Each training example records a program, workload, current optimization history, candidate pass, correctness, repeated runtime measurements, compile time, binary size, IR features, and optional hardware performance counters.

## Repository structure

- `data/DATASET_SPEC.md` — final dataset contract.
- `data/schema/` — machine-readable schema.
- `data/config/` — measurement and sampling policy.
- `data/pass_catalog.json` — initial 32-action optimization space.
- `data/benchmark_sources.json` — benchmark-source policy and roles.
- `data/manifests/` — concrete runnable benchmark manifests.
- `tools/` — dataset generation, feature extraction, environment and quality checks.
- `scripts/` — reproducible generation entry points.
- `benchmarks/smoke/` — tiny controlled benchmarks used only to validate the infrastructure.

## Important limitation

The final runtime-labelled corpus is not generated inside GitHub. It must be produced on a controlled machine with one internally consistent LLVM installation, stable CPU measurement conditions, the benchmark sources materialized and pinned, and sufficient execution time. This repository contains the reproducible machinery and contract; it does not pretend that runtime labels exist before those measurements are actually executed.

See `scripts/README.md` for generation instructions.
