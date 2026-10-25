# NeuroCompiler: final report (2026-10-25)

Hybrid ML-guided LLVM pass selection, judged only by **runtime vs `clang -O3`** on programs not used in
training. One machine: AMD Ryzen 9 270 (Zen 4) under WSL2, LLVM 18.1.8 pinned, timing pinned to vCPU 6
(parallel phases: vCPUs 2, 6, 10 after a multi-core A/A test). Every number below is reproducible from the
scripts and result files named next to it; measured values are labelled as such, estimates are not used.

## Headline

On **33 test programs from 11 program families the model never saw**, the deployed loop (supervised
surrogate proposes 8 pipelines, they are compiled, verified against the -O0 output and timed against
-O3, the fastest ships only if it beats -O3, otherwise -O3 ships) measured, serially re-measured:

| method | geomean vs -O3 (95% CI) | excl. largest | programs >= +5% | regressions |
|---|---|---|---|---|
| **model top-8 + timing** | **+7.51%** (+2.25..+15.77) | **+4.30%** | 8/33 (24%) | 1 |
| same, no simulated dynamic features | +6.13% (+1.53..+13.67) | +2.93% | 8/33 | 2 |
| random search, 8 timed binaries | +5.28% (+0.79..+12.77) | +2.23% | 7/33 | 6 |
| GA (6+18), 8 timed binaries | +2.08% (-0.09..+5.27) | +0.90% | 4/33 | 6 |
| model top-1, no timing (ML only) | +2.36% (-3.72..+10.85) | -0.85% | 6/33 | 16 |
| random top-8 from the same library | +1.61% (+0.21..+3.35) | +1.10% | 4/33 | 0 |
| -O2 / -Os | -1.01% / -3.01% | | 0/33 | 6 / 17 |

Source: `results/eval_final_serial.md`, `results/eval_final_serial.json` (`python -m nc.cli evaluate report --tag final_serial`).

Paired, program by program (`scripts/phase9_paired.py` -> `results/phase9_paired.txt`): top-8 beats random
top-8 by **+5.8%** (95% CI +1.0..+13.9) and the GA at equal timed budget by **+5.3%** (+0.3..+13.4); vs random
search with 8 timed binaries +2.1% (-0.6..+5.8, not significant); dynamic features +1.3% (-0.5..+4.1, not
significant); timing is essential (top-8 vs ML-only top-1: +5.0%, +2.3..+8.3).

Against the project's tiers: **good** tier met (+4.3% excluding the largest, CI excludes 0, 24% of programs
>= +5%); **strong** (>= +5% geomean) only with the largest result (polybench/durbin 2.84x) included;
**minimum** (no regressions) missed by one program: ms/Applications/JM/lencod shipped at 0.979x. Its pick
won a 10-round selection run under 3-core parallel load and did not hold up serially. A fresh confirmation
step (20 rounds, A/A control, ship only if the CI lower bound > 1.01) is now the default in `nc/deploy.py`;
re-running lencod serially with it ships -O3 (post-hoc illustration, not a re-scored test result).

## Final version: RL + SL (user decision, 2026-10-25)

`bin/neurocompiler` runs **RL + SL** by default: the PPO agent proposes 24 pipelines for the new program, the
supervised LightGBM model ranks them together with the ~900-pipeline library, the top 8 are compiled, verified
against the -O0 output and timed against -O3, and the pick ships only if a fresh 20-round confirmation run
(with an A/A control) shows it beats -O3 by more than 1%; otherwise -O3 ships. `--no-rl` gives SL only. The
output reports where the shipped pipeline came from (RL agent or library) and the top of the ranking.
Measured on the 33 test programs (serial): RL + SL +8.09% vs SL +7.92% in the same session (paired +0.2%,
95% CI -0.2..+0.7, not significant); an RL proposal was the shipped pipeline on 1 of 33 programs
(ss/Shootout-C++/fibo, 1.231x); 11 shipped a library pipeline, 21 kept -O3. RL is included at the user's
request for demonstration; the measured gain from it is nil, which the presentation should state.
Demo runs (held-out programs): polybench/3mm shipped a library pipeline confirmed at 1.194x; fibo shipped a
library pipeline at 1.147x with RL proposals ranked #7-8 of the pool (in the evaluation run RL's won at 1.231x).

## What the earlier attempt got wrong

Across 18,637 measured candidates, the change in IR instruction count vs -O3 and the runtime change are
essentially uncorrelated (Spearman -0.08); candidates with > 1% fewer IR instructions were faster only 57%
of the time (median 1.005x). Optimizing IR count or size does not optimize runtime.

## Phase by phase

**1. Harness.** Pinned, interleaved, paired bootstrap CIs, output-hash check against -O0, ASLR off, A/A
control in every confirmation (repeated once if off by > 1%). Selftest after moving to 14 vCPUs: CI
half-width 0.12%, A/A bias 0.01% (`results/selftest_*`). Layout randomization tested: no benefit
(`results/layout_test_20261023-102201.json`).

**2. Corpus.** 146 usable programs in 35 families from PolyBench, LLVM test-suite SingleSource (C, C++,
argv-scaled) and MultiSource (multi-file programs llvm-linked into one module); -O3 runtime 0.35-2.9 s
(`python -m nc.cli corpus report`). Frozen family split (`corpus/split.json`): 91 train, 22 val, 33 test.

**3. Headroom gate: NOT MET** on the decisive fresh sample: 15 never-searched programs, budget 25 per
method, validated: geomean +4.00% (+1.54..+7.14), excluding largest +2.94%, 4/15 >= +5%
(`scripts/gate_by_sample.py` -> `results/gate_by_sample_20261023.txt`). Decision on record: re-scope to the
good tier and continue, using a wider search in Phase 5 as an out-of-sample re-measurement.

**4. Knowledge base.** 346 single edits around -O3 on 31 training winners (19 families). Strongest levers
are loop cost-model overrides, in both directions: `-force-vector-width=8` confirmed faster on 5 programs,
slower on 0 (screening 0.83..6.6x); `-force-vector-width=2` +5/-2; `-unroll-max-count=2` +5/-1;
`-unroll-count=2` +4/-6. Most single edits are no-ops on a given program (250-320 of 346 give an identical
binary). (`results/passkb_attribution_20261024-192004.csv`, `results/passkb_actions.json`.)

**5. Data collection (wider search, out-of-sample headroom).** evo + evo2 (action space with pass-option
flips, family-wide edits, llc flags), budget 50 each, on the 116 programs never searched before; every
winner re-validated serially. Excluding one compile-time-evaluation artifact: **geomean +15.6%**
(+10.2..+22.1), excluding largest +14.1%, median +3.6%, **54/115 programs >= +5%**; one value per family:
+8.5%, 10/26 families >= +5% (`scripts/phase5_report.py` -> `results/phase5_report.txt`). The wider search
finds far more headroom than the Phase 3 gate sample. Artifact: ss/Misc-C++/mandel-text (no input; winner
executes 217x fewer instructions with identical output, i.e. work evaluated at compile time;
`scripts/artifact_check.py` -> `results/artifact_check.json`). Parallel (3-core) vs serial validation:
median difference -0.15%. Data quality: 15/146 programs (10.3%) with a noisy accepted A/A control, marginally
over the 10% limit (`python -m nc.cli collect quality`, `results/dataset_version.json`, version 692d2418a83f).

**6. Features.** ~130 per program: static IR counts (canonicalized and -O3), simulated cachegrind rates
(default caches and a 1 MB private L2), scan facts; ~98 per candidate (edits by pass family, knobs, llc level).

**7. Surrogate: Gate 7B NOT MET.** LightGBM regressor and lambdarank ranker, leave-one-family-out on the
24 development families: regressor Spearman +0.124 (+0.05..+0.20) but gain@5 1.097x vs random 1.109x;
ranker gain@5 1.122x with Spearman +0.075. Offline the model ranks only slightly better than chance; at
deployment (Phase 9) it nevertheless beats random top-8 on the test set (+5.8%, CI excludes 0).

**8. RL (exploratory, added 2026-10-25).** Gate 7B was re-run after the Phase 4 knowledge-base data was in
(the plan's order; the deployed surrogate already used that data) and passed narrowly: regressor Spearman
+0.111 (+0.06..+0.15), gain@5 1.107x vs random 1.091x (`results/models/cv_latest.json`); the earlier NOT MET
was computed before Phase 4 finished. Because the pass is narrow and came after seeing the first result, the
RL run is labelled exploratory. PPO over 120 macro-edits (`nc/rl.py`; one-hidden-layer actor and critic,
horizon 4) trained on the 113 train+val programs with the surrogate as reward (200 iterations x 64 episodes);
its predicted return reached +0.22 log speedup (the surrogate's view, far above measured headroom). It favours
-inline-threshold=1000, -unroll-max-count=2/4, llc tail-dup-size 4/6, deleting every simplifycfg/instcombine.
Evaluated on the same 33 test programs with the same selection procedure, serially re-measured
(`scripts/rl_eval.sh`; `results/eval_rl_serial.md`; paired: `results/rl_paired.txt`):

| method | geomean vs -O3 (95% CI) | excl. largest | >= +5% | regressions | timed/program |
|---|---|---|---|---|---|
| model top-8 (re-run, same session) | +7.92% (+2.57..+16.23) | +4.74% | 9/33 | 0 | 8 |
| RL proposals only | +3.35% (+1.12..+6.19) | +2.51% | 6/33 | 0 | 5 |
| RL proposals + library, surrogate ranks | +8.09% (+2.60..+16.35) | +4.92% | 9/33 | 0 | 8 |

Paired: RL only vs top-8 **-4.2%** (-11.0..+0.6); RL + library vs top-8 **+0.2%** (-0.2..+0.7); RL only vs
GA@8 +1.2% (-2.4..+4.8). RL does not beat the top-k loop, so by the plan's rule it is **not adopted**; its
proposals also collapse to few distinct pipelines (about 5 distinct binaries per program). Reproducibility:
model top-8 re-run on a different day vs the reported run +0.4% (-0.1..+1.0), and 0 regressions this time.

**9. Evaluation.** See the headline. Selection ran on 3 timing cores; every shipped binary was then
re-measured serially (`python -m nc.cli evaluate repro --tag final`), parallel vs serial agreement as above.

## Limits (state these in any writeup)

- One machine and microarchitecture (Zen 4, AVX-512) under WSL2; gains may differ elsewhere.
- 33 test programs in 11 families: wide confidence intervals; the largest result (durbin) moves the
  geomean from +4.3% to +7.5%.
- The Phase 3 gate was missed; the project continued under a documented re-scope.
- Data quality marginally over the noisy-control limit (mitigated by down-weighting those labels).
- Gate 7B: NOT MET before the Phase 4 data, narrowly met after it; RL (exploratory) did not beat top-k.
- Output correctness is checked on one input per program (hash equality vs -O0), which is evidence, not proof.
- Deployment cost per program: ~78 extra compiles and a few minutes of timing to choose a pipeline.
- 20 programs are flagged o3_mismatch (the printed -O3 pass list does not reproduce default<O3> bit for bit
  even with the O3 inliner settings restored); their speedups are still measured against real -O3.
- Fixed-input benchmarks allow compile-time evaluation (mandel-text); screened by instruction counts.

## Reproduce

`README.md` sections 7-9 list the commands; `CLAUDE.md` records every decision with its result file.
Long runs: `scripts/phase5.sh`, `scripts/pipeline_rest.sh` (both resumable; auto-restarted by cron via
`scripts/phase5_autoresume.sh`).
