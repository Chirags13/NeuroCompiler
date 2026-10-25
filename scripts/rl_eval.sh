#!/usr/bin/env bash
# Exploratory RL evaluation on the frozen test set: model top-8 (re-run in the same session), RL proposals
# only (A), RL proposals pooled with the library and ranked by the surrogate (B). Same selection procedure
# as the reported run (confirm_reps=0), then a serial re-measurement of every shipped binary. Resumable.
set -u
cd "$(dirname "$0")/.."
source .venv/bin/activate
M=results/models
echo "######## $(date '+%F %T') RL evaluation (selection on 3 cores)"
python -u -m nc.cli evaluate run --tag rl --k 8 --model $M/surrogate_full.json --rl $M/rl_policy_latest.npz \
       --methods topk,rl_topk,rl_lib_topk --confirm-reps 0 --timing-cpus 2,6,10
echo "######## $(date '+%F %T') serial re-measurement"
python -u -m nc.cli evaluate repro --tag rl
python -u -m nc.cli evaluate report --tag rl_serial
echo "######## $(date '+%F %T') all done"
touch results/.rl_done
