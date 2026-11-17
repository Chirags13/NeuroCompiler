#!/usr/bin/env bash
# Predict mode, validation timing check: train-only models on the 22 validation programs (selection needs no
# timing; measurement on 3 cores), then a serial re-measurement. Resumable. Marks results/.predict_val_done.
set -u
cd "$(dirname "$0")/.."
source .venv/bin/activate
echo "######## $(date '+%F %T') predict validation check"
python -u -m nc.cli predict-eval --on val --which trainonly --timing-cpus 2,6,10 --serial
echo "######## $(date '+%F %T') all done"
touch results/.predict_val_done
