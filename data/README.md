# NeuroCompiler Runtime-Grounded Dataset

This directory defines the Phase-1 dataset contract for NeuroCompiler 2.0.

Execution runtime is the primary learning target. IR instruction count, object text size, memory, and compilation time are retained as observations or secondary objectives.

A training example represents a compiler transition:

program + workload + target + current optimization history + candidate pass -> measured result

Dataset layers:

1. Structural corpus: large program/IR/feature catalog, including compile-only material.
2. Optimization corpus: baseline, single-pass, pair/order, random, and search-generated trajectories.
3. Performance corpus: correctness-passing and runtime-stable configurations with repeated measurements.

External benchmark sources are not vendored. Pin source commits and record licenses in manifests.

See DATASET_SPEC.md for the complete research contract.
