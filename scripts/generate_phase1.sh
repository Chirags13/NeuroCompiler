#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"; cd "$ROOT"
python3 tools/requirements-check.py
python3 tools/validate_pass_catalog.py
python3 tools/generate_dataset.py --manifest data/manifests/phase1.json --config data/config/dataset_config.json --passes data/pass_catalog.json --mode random --output data/processed/runtime_v2 --workdir data/work
echo 'Phase-1 dataset generated at data/processed/runtime_v2'
