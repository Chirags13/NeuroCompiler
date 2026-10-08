# Benchmark manifests

Every runnable benchmark needs stable program/project identity, source identity, workload identity, compiler flags, link flags, runtime arguments, and a correctness contract.

The split boundary is project_id. All workload variants and optimization configurations of a project stay in one split.

## Current corpus construction

The Phase-1 builder materializes PolyBench/C 4.2.1 first. PolyBench contains 30 numerical kernels and supports compile-time dataset sizes, making it a particularly clean first runtime corpus. The manifest builder creates 30 programs x 3 workload sizes = 90 workload instances.

The final corpus expansion should add the validated CPU portions of MiBench, cBench, Rodinia, and LLVM Test Suite after their adapters are validated. They must not be inserted as fake generic single-file records because many have multi-file builds, external data, or suite-specific correctness/run harnesses.

The generated runtime dataset, not this manifest alone, is the model-training corpus.
