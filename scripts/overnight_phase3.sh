#!/usr/bin/env bash
# Overnight Phase 3 job. Every step is resumable; re-running skips finished work.
#   1. validate the 15 programs searched so far (independent re-measurement of their best candidate)
#   2. expand the corpus: prescan (parallel, untimed) + pinned scan of new candidates
#      (SingleSource C++, MultiSource) and rescan of argv-scalable programs rejected as too fast
#   3. a FRESH gate run on 15 programs never searched before, v1 + v2 action spaces
# Start detached:   setsid nohup scripts/overnight_phase3.sh > logs/overnight_$(date +%Y%m%d-%H%M).log 2>&1 &
# Watch:            tail -f logs/overnight_*.log
set -u
cd "$(dirname "$0")/.."
source .venv/bin/activate
step() { echo; echo "######## $(date '+%F %T') $*"; }
step "1/6 validate existing winners";      python -u -m nc.cli search validate
step "2/6 corpus prescan (new candidates)"; python -u -m nc.cli corpus prescan --suite all
step "3/6 corpus scan (pinned)";            python -u -m nc.cli corpus scan --suite all
for p in ss/BenchmarkGame/spectral-norm ss/Shootout/ackermann ss/Shootout/ary3 ss/Shootout/nestedloop ss/Shootout/objinst ss/Shootout/strcat; do
  python -u -m nc.cli corpus scan --suite singlesource --only "$p" --force
done
step "4/6 corpus report";                   python -u -m nc.cli corpus report
step "5/6 fresh gate run";                  python -u -m nc.cli search run --sample 15 --budget 25 --methods random,evo,evo2 --exclude-searched --seed 1
step "6/6 report";                          python -u -m nc.cli search report
step "done"
