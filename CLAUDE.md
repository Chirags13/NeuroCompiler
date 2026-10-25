# NeuroCompiler

Hybrid ML + RL guided LLVM pass selection. Success = measurable, reproducible **runtime** improvement
over -O3 on programs not used in training. Binary size, IR count and compile time are constraints only
(an earlier attempt improved IR/size but not runtime; do not repeat that).

Objective: never slower than -O3 beyond noise, ideally a few percent faster, `.text` <= ~1.10x -O3
(soft penalty `size_cap`). Deployment: the model proposes top-k pipelines, they are compiled and briefly
timed, -O3 is always among them, the fastest wins. Tiers: minimum = no regressions/miscompiles;
good = geomean +2-4% with CI excluding 0 and >= 20-30% of programs >= +5%; strong = >= +5% geomean.

## Environment (fixed)
WSL2 Ubuntu, AMD Ryzen 9 270 (host 8 cores/16 threads). Since 2026-10-23 WSL2 has 14 vCPUs (SMT pairs
0-1 ... 12-13) and 10 GB (.wslconfig; backup .wslconfig.bak-20261023). All data up to then was measured with
8 vCPUs; re-run cpusweep + selftest before new timing and tag new data with a new machine_id. Python 3.14 venv `.venv`.
LLVM pinned to 18.1.8 at /usr/lib/llvm-18/bin (OS default is 21: never use it for data).
`timing_cpu = 6`, `machine_id = wsl2-ryzen9-270`. No perf counters (cachegrind features are labelled
simulated; cachegrind binaries use -march=x86-64-v3 because valgrind cannot run AVX-512).
The machine is shared with other heavy experiments: check load before timing; the quiet guard waits.

## Rules
- Never run anything CPU-heavy while a timing job runs; long jobs detached (`setsid nohup ... &`), poll the log.
- Only confirmed numbers count (30 rounds + A/A control); the gate uses VALIDATED numbers. Screening overstates.
- Report geomean with and without the largest result (evalloop is pathological: report both).
- Do not relax thresholds or gates to get a pass; do not re-split after seeing results; split only when the corpus is final.
- Never delete results/dataset.sqlite or corpus/manifest.jsonl without asking. Ask before changing measurement settings
  (e.g. `isolate_sibling`, reps, warmup, settle) and before launching multi-hour jobs.
- Say what is measured vs estimated. Everything reported must be reproducible from scripts and result files in the repo.
- Smoke tests go to a scratch config (own db_path/results_dir/corpus_dir), never the real dataset.

## Decisions on record
- 2026-10-23: **Phase 3 headroom gate NOT MET** on the decisive fresh sample (15 never-searched programs,
  validated): geomean +4.00% (95% CI +1.54..+7.14), excluding largest +2.94%, 4/15 programs >= +5% (26.7%).
  The pooled 30 programs pass at exactly 30.0% only by counting polybench/jacobi-1d (noisy A/A control).
  Reproduce: `.venv/bin/python scripts/gate_by_sample.py` (output in results/gate_by_sample_20261023.txt).
- **Re-scope (user decision):** continue to Phase 5+ with the target lowered to the "good" tier (+2-4%);
  no separate re-test. Phase 5 runs the WIDER search (evo + evo2 only, larger budget) on the programs never
  searched before, which doubles as an out-of-sample re-measurement of headroom. Later gates (5 quality,
  7B surrogate vs random, RL vs top-k) stay strict. The writeup must report the gate miss with these numbers.
- Measurement protocol unchanged: layout randomization (layout_copies) tested, no benefit
  (results/layout_test_20261023-102201.json). Parallel timing: 5 and 3 cores distort memory-bound programs
  (results/aatest_*); 2 cores with at most one memory-bound program showed <=0.5% bias.
- Phase 5 timing: **3 workers on vCPUs 2,6,10** (helpers 0,1,12,13 idle-sibling layout), at most one
  memory-heavy program at a time (simulated L2 misses >= 20 per 1000 instructions, features fset sim_l2).
  This passed the multi-core A/A (results/aatest_3cores_20261023-124343.json: bias <= 0.46%, noise ~serial,
  known speedups within 0.2%). 5 workers with the same rule kept speedups unbiased but made noise 5-40x
  larger (results/aatest_5cores_20261023-123459.json), so it is not used.

- 2026-10-24 Phase 5 (wider search, out-of-sample, serial re-validated; scripts/phase5_report.py ->
  results/phase5_report.txt): excluding the one compile-time-evaluation artifact (mandel-text, 217x fewer
  instructions, results/artifact_check.json): geomean +15.6% (CI +10.2..+22.1), excl. largest +14.1%, median
  +3.6%, 54/115 programs >= +5%; per family +8.5%, 10/26 families >= +5%.
- Phase 5 quality: 15/146 programs (10.3%) have a noisy ACCEPTED A/A control -> marginally NOT clean (limit 10%).
  Mitigation decided before modelling: those programs' labels weighted 0.3; labels capped at |log 3|.
- Split frozen 2026-10-24 (corpus/split.json, seed 0): test 33 programs / 11 families, val 22, train 91.
  Rule: a family enters test/val only if it fits the remaining budget (TSVC, 33 programs, falls to train).
- **Gate 7B NOT MET** (held-out families, model cv): regressor Spearman +0.124 [+0.05,+0.20] but gain@5 1.097x
  < random 1.109x; ranker gain@5 1.122x (barely above) with Spearman +0.075; dynamic features add ~0.01;
  compiled-candidate features made it worse. => no RL. Phase 9 still measures top-k vs random top-k vs GA.

- 2026-10-25 **Phase 9 (frozen test set, 33 programs / 11 families, serial re-measurement)**: model top-8 +
  timing +7.51% (CI +2.25..+15.77), excl. largest +4.30%, 8/33 >= +5%, 1 regression (lencod 0.979x);
  beats random top-8 (+5.8%, CI +1.0..+13.9) and GA@8 (+5.3%, CI +0.3..+13.4); vs random search@8 +2.1% (n.s.).
  Selection now requires a fresh 20-round confirmation with CI > 1.01 (nc/deploy.py); runs before this used
  confirm_reps=0. Full write-up: results/FINAL_REPORT.md. RL (PPO) not trained (Gate 7B).
- 2026-10-25 Gate 7B re-run AFTER Phase 4 data was in (the plan's order; the deployed surrogate already used
  that data): regressor Spearman +0.111 [+0.06,+0.15], gain@5 1.107x vs random 1.091x -> narrowly MET
  (results/models/cv_latest.json). The earlier NOT MET was computed before Phase 4 finished. Both are reported;
  the RL run below is labelled exploratory because the pass is narrow and came after seeing the first result.
- Backup of the supervised version: /home/chirag/neurocompiler_backups/v1-supervised-20261025.tar (+ copy in
  C:\Users\Chirag\neurocompiler_backups), sha256 f73073e1...c91f.
- RL (PPO, nc/rl.py): trained on 113 train+val programs, surrogate_full reward, 200 iters x 64 episodes;
  predicted return +0.22 log (surrogate's view, not measured). Policy favours -inline-threshold=1000,
  -unroll-max-count=2/4, llc tail-dup-size 4/6, deleting every simplifycfg / instcombine.
- 2026-10-25 **RL result (exploratory, serial, 33 test programs; results/eval_rl_serial.md, results/rl_paired.txt)**:
  RL only +3.35% (vs model top-8 -4.2%, CI -11.0..+0.6); RL + library +8.09% (vs top-8 +0.2%, CI -0.2..+0.7);
  model top-8 re-run +7.92% (reproduces +7.51%). RL does not beat top-k -> NOT adopted; top-k loop stays the result.

- 2026-10-25 **Final version = RL + SL (user decision for the presentation)**: bin/neurocompiler / nc/deploy.py
  pool RL proposals with the library, SL ranks, timing + confirmation decide, -O3 fallback; --no-rl = SL only.
  Measured effect of RL vs SL: +0.2% (n.s.); RL proposal shipped on 1/33 test programs. State this when presenting.

## Workflow
Commands and phase descriptions: README.md (sections 7-9). Overnight Phase 3 job: `scripts/overnight_phase3.sh`.
Gates: Phase 3 headroom (validated, >= 10 programs) -> Phase 5 quality CLEAN -> 7B surrogate beats random on
held-out families -> RL only if it beats top-k and GA at equal compile budget.
