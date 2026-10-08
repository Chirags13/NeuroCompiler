# Benchmark manifest contract

Every runnable benchmark needs a stable program_id, project_id, benchmark_family, source/sources, workload identity, compiler/link flags, runtime arguments, and correctness contract.

The project_id is the leakage boundary: every input and configuration belonging to a project stays in one split.

External suites must be pinned to immutable source commits. The LLVM Test Suite should be imported through its native CMake/lit infrastructure rather than forced through a generic one-file runner. The smoke manifest is only an infrastructure test.
