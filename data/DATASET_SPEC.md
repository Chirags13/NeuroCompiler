# NeuroCompiler 2.0 — Final Dataset Specification

## Objective

The dataset is built for one primary research question:

> Can program-specific LLVM pass selection improve measured execution runtime over fixed LLVM pipelines on unseen programs, while controlling compilation overhead and secondary code-size effects?

The previous project over-weighted IR/code-size reduction. In this rebuild, IR counts are observations/features; runtime is the primary target and reward.

## Canonical training example

One row represents:
program + project + workload/input + target + current pass history + candidate next pass

with measured outcome:
correctness + runtime-before + runtime-after + speedup + compile-time + code-size + IR statistics + optional hardware counters.

This directly supports supervised runtime-delta prediction; pass ranking; behavior cloning from high-performing trajectories; RL state/action/reward training; and post-hoc analysis of why a pass was beneficial.

## Dataset tiers

### Tier A — Structural corpus
Large and diverse, possibly compile-only.

Keep source hash and immutable source revision; project identity; LLVM IR; CFG/DFG artifacts where extracted; deterministic static IR features; language/compiler/target metadata.

Use AnghaBench and other large open-source corpora here.

Do not invent runtime labels for programs that cannot be executed reproducibly.

### Tier B — Optimization corpus
Runnable programs across many workload classes.

For every program/workload collect O0, O1, O2, O3, Os, Oz baselines; single-pass transitions; pairwise/order-sensitive transitions; random short sequences; search-generated candidates; and intermediate state for every step.

### Tier C — Performance corpus
Highest-quality records only.

Training-eligible records must have successful compilation; successful correctness validation; stable repeated runtime; complete feature vector; compiler/LLVM version; target and hardware metadata; immutable source/workload hashes.

## Benchmark diversity

Prefer all of: numerical/compute-bound; memory-bound/streaming; branch-heavy; vectorizable; pointer-heavy; recursive; integer-heavy; floating-point-heavy; cache-sensitive; function-call-heavy; small kernels; medium whole programs; larger MultiSource applications.

Recommended sources: LLVM Test Suite as the primary runtime corpus; PolyBench/C for numerical and loop diversity; cBench for embedded/application workloads; MiBench for embedded/application workloads; Rodinia for heterogeneous/HPC workload diversity on the CPU side; open-source C/C++ projects for real-world diversity; AnghaBench for structural pretraining only; SPEC CPU for final external evaluation where licensing permits.

External sources are not vendored into this repository.

## Workload/input policy

A benchmark identity is (program, workload) rather than only (program).

For each program, capture multiple input sizes where possible: small, medium, large. Where meaningful, include behaviorally distinct inputs such as random, sorted, reverse-sorted, or pathological. The source of an input must be pinned or hashed.

## Measurement protocol

Default configuration: 3 warmups; 10 timed repetitions; median runtime as primary estimate; mean, standard deviation, coefficient of variation retained; runtime instability threshold CV <= 10%; correctness before timing; timeout at 120 s by default; optional Linux perf counters.

The benchmark runner must record the full sample vector, not only the median.

## Correctness

A candidate is training-eligible only if the benchmark's correctness contract passes.

Never convert a crash, wrong output, timeout, or compiler failure into a runtime score.

Store output hashes so that repeated runs can be audited.

## Baselines

Collect O0, O1, O2, O3, Os, and Oz. O3 is the primary performance baseline for the final speedup table. Keep the other levels because they show how learned search relates to LLVM's fixed optimization spectrum.

## Optimization trajectory policy

Use several trajectory sources: single-pass experiments; pair/order experiments; random sequences; greedy/beam/search-generated sequences; RL-generated sequences after the first model exists.

For RL, each prefix is a state. Record:
S_t + action_t -> S_(t+1) + reward_t

where reward_t = log(runtime_before / runtime_after). Positive reward means faster.

## Secondary observations

Retain object text size; full executable size when available; IR instruction count; function/basic-block/loop proxies; load/store/branch/call/vector operation counts; compile time.

Optional: cycles; instructions; IPC; branch misses; cache references/misses; RSS; energy.

## Leakage control

The split is by project_id, not by file or function. All workloads and source variants belonging to the same project remain in one split.

Use deterministic hashing to create train 70%, validation 15%, test 15%.

For the strongest final result, keep an additional external test set containing projects never used in dataset construction.

## Acceptance criteria for the final export

The model-training export must contain no incorrect configurations; no timing timeouts; no unstable runtime records; complete program/project/workload identities; fixed compiler and target information; both before and after state features; complete pass history; runtime deltas; and a versioned checksum.

The canonical interchange format is JSONL. Convert to Parquet for model training only after validation.

## Important non-goal

Do not optimize the dataset for IR reduction. IR reduction is a diagnostic feature and ablation target. A configuration that makes IR smaller but runtime slower must be allowed to receive a negative runtime reward.
