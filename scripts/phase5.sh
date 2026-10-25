#!/usr/bin/env bash
# Phase 5 (re-scoped, wider search): evo + evo2 at budget 50 each on every usable program never
# searched before (out-of-sample re-measurement of headroom), parallel timing on the cores that
# passed the multi-core A/A test, at most one memory-bound program at a time. Resumable.
# Usage: scripts/phase5.sh <timing-cpus>     e.g. scripts/phase5.sh 2,4,6,8,10
set -u
cd "$(dirname "$0")/.."
source .venv/bin/activate
CPUS="${1:-6}"
PROGS=$(python - <<'PY'
import json, sqlite3
done = {r[0] for r in sqlite3.connect("results/dataset.sqlite").execute("SELECT DISTINCT program_id FROM runs WHERE seed IN (0,1)")}
ok = [json.loads(l) for l in open("corpus/manifest.jsonl")]
print(",".join(sorted(r["program_id"] for r in ok if r["status"] == "ok" and r["program_id"] not in done)))
PY
)
echo "######## $(date '+%F %T') phase 5: $(echo "$PROGS" | tr ',' '\n' | wc -l) programs on cores $CPUS"
python -u -m nc.cli collect run --programs "$PROGS" --methods evo,evo2 --budget 50 --seed 2 --no-passkb --timing-cpus "$CPUS"
echo "######## $(date '+%F %T') phase 5 search done"
python -u -m nc.cli search report
echo "######## $(date '+%F %T') done"
# serial re-validation of every Phase 5 winner (one core, nothing else timing): the reported numbers
echo "######## $(date '+%F %T') serial re-validation"
python -u -m nc.cli search revalidate --seed 2
echo "######## $(date '+%F %T') all done"
touch results/.phase5_done
