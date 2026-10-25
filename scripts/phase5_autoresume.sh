#!/usr/bin/env bash
# Started by cron (@reboot and every 10 min). (Re)starts the current long job unless it is finished or
# stopped on purpose (touch results/.phase5_stop). Phase 5 first, then phases 4-9 (scripts/pipeline_rest.sh).
# Both are resumable, so a restart only repeats the programs that were in progress.
cd /home/chirag/neurocompiler || exit 1
[ -e results/.phase5_stop ] && exit 0
exec 9>/tmp/nc_phase5.lock
flock -n 9 || exit 0
pgrep -f '^(/usr/bin/|/bin/)?bash (/home/chirag/neurocompiler/)?scripts/(phase5|pipeline_rest|rl_eval)\.sh' >/dev/null && exit 0
T=$(date +%Y%m%d-%H%M)
if [ ! -e results/.phase5_done ]; then
  echo "$(date '+%F %T') autoresume: starting phase 5 -> logs/phase5_$T.log" >> logs/autoresume.log
  scripts/phase5.sh 2,6,10 > logs/phase5_$T.log 2>&1
elif [ ! -e results/.rest_done ]; then
  echo "$(date '+%F %T') autoresume: starting phases 4-9 -> logs/rest_$T.log" >> logs/autoresume.log
  scripts/pipeline_rest.sh > logs/rest_$T.log 2>&1
elif [ -e results/.rl_requested ] && [ ! -e results/.rl_done ]; then
  echo "$(date '+%F %T') autoresume: starting RL evaluation -> logs/rl_$T.log" >> logs/autoresume.log
  scripts/rl_eval.sh > logs/rl_$T.log 2>&1
fi
