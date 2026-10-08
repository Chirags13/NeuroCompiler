# Phase-1 generation

Install one internally consistent LLVM toolchain. clang, opt, llvm-dis, llvm-size, and llvm-link must come from the same LLVM release. Linux perf is optional but strongly recommended.

Run:

    python3 tools/requirements-check.py
    python3 tools/validate_pass_catalog.py

Then:

    bash scripts/generate_phase1.sh

The default config is intentionally conservative. Increase workload count and sequence sampling only after the smoke run is correct and reproducible.

External suites belong in external/, pinned to immutable commit IDs. Add concrete runnable entries to data/manifests/phase1.json. Do not commit external benchmark source unless its license permits redistribution.
