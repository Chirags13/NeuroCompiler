#!/usr/bin/env bash
# Phases 4 -> 9 after Phase 5. Every step is resumable / idempotent; started (and re-started after a WSL
# restart) by scripts/phase5_autoresume.sh from cron. Marks results/.rest_done at the end.
set -u
cd "$(dirname "$0")/.."
source .venv/bin/activate
CPUS=2,6,10
M=results/models
step() { echo; echo "######## $(date '+%F %T') $*"; }
step "phase 4: knowledge base on family-stratified training winners (parallel)"
python -u -m nc.cli passkb run --programs "$(cat results/passkb_programs.txt)" --no-add --timing-cpus $CPUS
python -u -m nc.cli passkb report
step "phase 7: surrogates (test families excluded automatically)"
[ -e $M/surrogate_nodyn.json ] || { python -u -m nc.cli model train --fsets static,scan && cp $M/surrogate_latest.json $M/surrogate_nodyn.json; }
[ -e $M/surrogate_full.json ]  || { python -u -m nc.cli model train --fsets static,sim,sim_l2,scan && cp $M/surrogate_latest.json $M/surrogate_full.json; }
step "phase 9: evaluation on the frozen test set (selection in parallel)"
python -u -m nc.cli evaluate run --tag final --k 8 --model $M/surrogate_full.json --nodyn-model $M/surrogate_nodyn.json --timing-cpus $CPUS
step "phase 9: serial re-measurement of every shipped binary (reported numbers)"
python -u -m nc.cli evaluate repro --tag final
step "phase 9: report"
python -u -m nc.cli evaluate report --tag final_serial
python -u -m nc.cli evaluate report --tag final
step "all done"
touch results/.rest_done
