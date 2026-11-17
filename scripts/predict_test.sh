#!/usr/bin/env bash
# Predict mode, the ONE test-set evaluation (frozen final models and thresholds): picks measured on 3 cores,
# serial re-measurement of every shipped binary, then predict's added time over -O3 builds (fresh caches).
# Resumable. Marks results/.predict_test_done.
set -u
cd "$(dirname "$0")/.."
source .venv/bin/activate
echo "######## $(date '+%F %T') predict test evaluation"
python -u -m nc.cli predict-eval --on test --which final --timing-cpus 2,6,10 --serial
echo "######## $(date '+%F %T') predict time check (test programs)"
python -u -m nc.cli predict-time --on test
echo "######## $(date '+%F %T') all done"
touch results/.predict_test_done
