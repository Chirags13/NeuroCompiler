#!/usr/bin/env bash
set -euo pipefail
python3 tools/build_polybench_manifest.py --root external/PolyBenchC --output data/manifests/polybench.json
