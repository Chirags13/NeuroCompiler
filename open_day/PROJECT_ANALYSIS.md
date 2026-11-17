# NeuroCompiler: project analysis for the Open Day deck

Analysed from the source code, result files and dashboard data on 2026-10-30. Where a document and the code or
data disagree, the code/data wins and the disagreement is listed in section 12.
"Measured" = a number from a result file or a run on this machine. "Calculated" = arithmetic on measured numbers.
"Simulated" = cachegrind. "External" = a cited source.

## 1. What we built

NeuroCompiler is a per-program compiler tuner for C and C++. It wraps LLVM 18.1.8 and looks for a compiler pass
pipeline that makes one specific program run faster than `clang -O3`, without touching the source code. A
reinforcement-learning agent and a supervised model suggest pipelines, and real timing decides. The product is a
command-line tool (`bin/neurocompiler`) and a web dashboard (`dashboard/`, FastAPI on port 8000). It has three
sub-commands: `tune`, `predict` and `compare`.

## 2. The problem and why it matters

- `-O3` applies one fixed sequence of 109 pass steps (76 distinct passes in LLVM 18) to every program. Measured with
  `opt -passes='default<O3>' -print-pipeline-passes`.
- The same edit helps some programs and hurts others. `-unroll-count=2`: confirmed faster on 4 programs and slower on
  6 of 31. `-force-vector-width=8`: screening range 0.83x to 6.6x.
- Compute is expensive, and the cost is paid on every run. Small gains matter at scale. External: Google's AutoFDO paper
  reports 10.5% and says over half of Google's cycles ran in FDO-optimized binaries; Google deployed MLGO
  regalloc for 0.3-1.5% QPS; Kanev et al. profiled 20,000+ production machines.

## 3. What makes it hard

- **Search space.** 346 single edits were catalogued. Four-edit combinations: C(346,4) = 586,862,710 (calculated). At one
  second each that is 18.6 years. Phase ordering has been an open problem for decades (Ashouri et al., 2018).
- **Easy metrics mislead.** Across 18,637 measured candidates, IR-instruction change vs runtime change has Spearman
  rho = -0.08. Candidates with >1% fewer IR instructions were faster only 57% of the time. An earlier attempt
  improved IR and size but not runtime, which is why this project judges runtime only.
- **Timing lies.** Layout, environment size and scheduling all bias results (Mytkowicz et al., ASPLOS 2009). WSL2 has no
  hardware counters and no governor control.
- **Winner's curse.** Picking the best of k noisy measurements overstates it.
- **Weak models.** On unseen families the surrogate's rank correlation is only about +0.11.

## 4. The central idea

**Models shortlist. The stopwatch decides.** No model is trusted to pick the answer. Models reduce about 935 candidates to 8.
Those 8 are compiled, checked and timed against -O3 on the actual program. A winner ships only after a fresh
confirmation run. If nothing proves itself, -O3 ships.

## 5. System architecture (from the code)

### Offline: building the knowledge (hours to days)

| Stage | Module | Output |
|---|---|---|
| Corpus | `nc/corpus.py`, `nc/msource.py` | 347 scanned, 146 usable, 35 families. `corpus/manifest.jsonl`, frozen `corpus/split.json` |
| Build | `nc/toolchain.py` | clang (no passes) -> opt -> llc -> link. Binaries cached by IR hash |
| Timing | `nc/timing.py` | pinned, randomized interleaved rounds, paired bootstrap CI, quiet guard |
| Representation | `nc/pipeline.py` | -O3 parsed to a tree; a genome is a list of edits over it |
| Search | `nc/search.py` | levels, random, evo (v1), random2, evo2 (v2); confirmation, minimization, validation |
| Knowledge base | `nc/passkb.py` | 346 single edits on 31 winners; pruned action set `results/passkb_actions.json` |
| Dataset | `nc/db.py`, `nc/collect.py` | `results/dataset.sqlite`: 70,409 candidates, 19,534 measurements, 858 eval rows |
| Features | `nc/features.py`, `nc/remarks.py` | 111 static IR, 11+2 simulated cache, 9 scan; ~98 per candidate; 36 remark features (predict) |
| Surrogate | `nc/model.py` | LightGBM regressor and lambdarank, leave-one-family-out CV |
| RL | `nc/rl.py` | PPO in pure numpy; 120 macro-edits + STOP; horizon 4 |
| Predict | `nc/predict.py` | 7-member ensemble, harm classifier, own PPO, gate |

### Online: `bin/neurocompiler prog.c --out prog` (`nc/deploy.py`)

1. Build at -O0 and run it. Its output hash is the reference every candidate must match.
2. Extract program features: static IR plus a quick scan of -O0, -O1, -O2, -O3, -Os.
3. Load the surrogate through the frozen manifest (`nc/tunelock.py`; refuses to run if a hash changed).
4. Build the library (913 pipelines: pruned knowledge-base edits, training winners, level seeds, 300 random genomes).
5. PPO proposes up to 24 pipelines (3k, k = 8). They are pooled with the library.
6. LightGBM scores the whole pool (about 935).
7. In ranked order, compile batches of 24 until 8 distinct binaries with verified output exist.
8. Time the 8 with -O3 in 10 interleaved rounds on a pinned core.
9. The fastest with CI lower bound > 1.0 goes to a fresh 20-round run with -O3 and a byte-identical copy (A/A control).
10. Ship only if CI lower bound > 1.01 and the control is within 1%. Otherwise copy -O3.
11. Write the binary and a JSON report with provenance (RL agent or library).

### Interfaces

- CLI: `bin/neurocompiler [tune|predict|compare] source --out prog [--args ...] [--no-rl] [--k 8] [--dynamic]`
- Dashboard: `dashboard/server.py` with job queue, streaming logs, run history, pipeline diff, research page. Static front end in `dashboard/static/`.

## 6. Core algorithms

- **Genome.** `Genome` is a list of edits over stable node ids: `del`, `dup`, `swap`, `ins`, `knob`, `backend`; v2 adds
  `param`, `param_all`, `del_all` and llc flags. An empty genome is -O3. Edits transfer between programs and pass
  minimization can remove one edit and keep the others meaningful.
- **Interleaved timing.** Each round runs every binary in a shuffled order on one pinned core. Speedup is a paired statistic, so
  slow machine drift affects both sides. Config: 30 rounds, 5 warmup, 3 s settle, ASLR off.
- **A/A control.** A byte-identical copy of -O3 is timed as a candidate. It must read 1.00x within 1%.
- **Successive halving.** Search screens 1 round, then 2 more if speedup >= 0.98; runs over 1.3x slower are killed.
- **LightGBM surrogate.** Input: program features plus genome encoding. Labels: log speedup, capped at |log 3|; programs with noisy controls weighted 0.3. Spearman +0.111 [+0.06, +0.15] on held-out families, gain@5 1.107x vs random 1.091x.
- **PPO.** One-hidden-layer actor and critic (64 units), Adam, GAE, masked softmax, written in numpy.
  Reward = surrogate(g_t+1) - surrogate(g_t). 200 iterations x 64 episodes. Mean predicted return rose from +0.01
  to +0.22 log speedup. That is the surrogate's view, not a measurement.

## 7. Technologies

LLVM/Clang 18.1.8, Python 3.14, NumPy, SciPy, LightGBM, scikit-learn, SQLite, FastAPI + uvicorn, Valgrind
cachegrind, Windows 11 + WSL2 on an AMD Ryzen 9 270 (Zen 4). Benchmarks: PolyBench/C 4.2.1, LLVM test-suite
SingleSource and MultiSource.

## 8. Engineering decisions worth showing

| Decision | Why |
|---|---|
| Judge only runtime | Earlier attempt optimized IR and size, and runtime did not move |
| Split by family | Sibling programs share code, so a random split would leak |
| -O0 output as oracle | -O0 is the least transformed build; each candidate must match its hash |
| Fresh confirmation | Added after lencod shipped at 0.979x; defeats winner's curse |
| Frozen manifest | predict work cannot silently alter tune |
| 3 timing cores, not 5 | 5 cores raised noise 5-40x in the A/A test, so it was rejected |
| PPO written in numpy | No torch dependency; policy loads anywhere |
| Criteria recorded before building predict | Prevents moving the goalposts; predict then failed them and shipped advisory |

## 9. Results

All measured, serial re-measurement, 33 test programs in 11 families never used in training.

| Method | Geomean vs -O3 | 95% CI | Excl. largest | >= +5% | Slower |
|---|---|---|---|---|---|
| **Tune RL + SL (final)** | **+8.09%** | +2.44..+16.84 | **+4.92%** | **9/33** | **0** |
| Tune top-8 (SL) | +7.51% | +2.13..+16.09 | +4.30% | 8/33 | 1 |
| Random search @8 | +5.28% | +0.80..+12.85 | +2.23% | 7/33 | 6 |
| RL only | +3.35% | +1.15..+6.13 | +2.51% | 6/33 | 0 |
| ML top-1, no timing | +2.36% | -3.79..+11.16 | -0.85% | 6/33 | 16 |
| GA @8 | +2.08% | -0.17..+5.16 | +0.90% | 4/33 | 6 |
| Random top-8 | +1.61% | +0.26..+3.37 | +1.10% | 4/33 | 0 |
| Predict (advisory) | +0.64% | -0.18..+1.96 | +0.02% | 1/33 | 1 |
| -O2 | -1.01% | -2.26..-0.13 | | 0/33 | 6 |
| -Os | -3.01% | -5.74..-0.92 | | 0/33 | 17 |

Other results:

- Median program: 1.00x. 21 of 33 keep -O3. The largest win is polybench/durbin at 2.81x.
- Paired: top-8 vs random top-8 +5.8% (CI +1.0..+13.9); vs GA@8 +5.3% (+0.3..+13.4); vs random search@8 +2.1% (-0.6..+5.8, **not significant**); vs ML-only top-1 +5.0% (+2.3..+8.3).
- RL vs SL: +0.2% (-0.2..+0.7, **not significant**). An RL proposal shipped on 1 of 33 programs (fibo, 1.231x).
- Headroom (wider search): +15.6% (+10.2..+22.1), +14.1% excl. largest, median +3.6%, 54/115 >= +5%, per family +8.5%.
- Harness: CI half-width 0.12%, A/A bias 0.01%, 3-core A/A bias <= 0.46%.
- Project tier: **good** met. **Strong** only with the largest result included. **Minimum** met in the final configuration; the earlier SL run had one regression (lencod 0.979x), which led to the confirmation rule.
- Best demo: evalloop 848.4 ms -> 221.9 ms, confirmed 3.83x [3.820, 3.838], A/A 1.001x, 22 RL + 913 library, 48 compiled, 8 timed, 90 s. **Validation-split program, not in the 33, and the RL trained on it.**
- evalloop indirect jumps, re-measured on 2026-10-30: -O3 2; `-simplifycfg-sink-common=false` 63; shipped RL pipeline 63. Cachegrind's simple predictor reports 100% vs 96.7% indirect mispredicts, which cannot model history-based prediction, so no simulated figure is quoted.
- Fresh tune runs on 2026-10-30 (`open_day/assets/runs/`): matmul shipped a library pipeline, confirmed 1.485x [1.384, 1.534], A/A 1.009x, 175.5 s (an earlier saved run read 1.66x). branchy: fresh run 1.014x, CI lower bound 1.008, -O3 shipped.

## 10. Limitations

- One machine and microarchitecture (Zen 4, AVX-512) under WSL2.
- 33 test programs, wide CI. Durbin alone moves the geomean from +4.92% to +8.09%.
- Output correctness is checked on one input per program. Evidence, not proof.
- Tuned for one input; a different workload may behave differently.
- Single-threaded, CPU-bound, deterministic programs with visible output, 0.35-2.9 s at -O3.
- Median about 139 s per program to tune.
- Phase 3 headroom gate missed (+4.00%, 4/15 = 26.7%, needed 30%). Project re-scoped to the good tier, on record.
- Gate 7B not met first, narrowly met after Phase 4 data. RL run labelled exploratory.
- Data quality 10.3% noisy controls, marginally over the 10% limit; mitigated.
- RL adds no measured value. It is included by team decision and this must be stated.
- Predict missed its gain criterion and ships advisory, -O3 by default.

## 11. Future work (none implemented)

Bare-metal hardware counters, more machines and microarchitectures, graph neural program features, RL trained on real
timing rather than the surrogate, per-function tuning, multi-input verification, combination with PGO/BOLT.

Partially implemented: `--dynamic` cachegrind features exist but add +1.3% (not significant); `layout_copies` exists, tested, no benefit.

## 12. Discrepancies found

| Item | Finding | Used in the deck |
|---|---|---|
| CI of +8.09% | research.json +2.44..+16.84; modes_paired +2.47..+16.40; FINAL_REPORT +2.60..+16.35. Same data, different bootstrap runs | +2.4..+16.8 (matches the dashboard shown live) |
| README headline | Still says +7.5% from before RL + SL | +8.09% final, +7.51% SL |
| README WSL config | Shows 8 vCPUs, 16 GB; machine has 14 vCPUs, 10 GB | Machine as configured |
| "None slower" | True of RL + SL run. SL-only first run had lencod at 0.979x | "0 of 33" with the lencod story told |
| RL status | FINAL_REPORT says not adopted on merit; deployed by team decision | Say both |
| Dashboard timeline dates | research.json timeline shows Aug-Oct; CLAUDE.md records many of the same events on 23-26 Oct | No dates in the deck |
| CI of predict and others | research.json predict -0.18..+1.96, CLAUDE.md -0.16..+2.05; same cause. All CIs above come from research.json | research.json, so the deck matches the dashboard |
| Dashboard rejection text | Says too_fast means under 0.1 s and usable means 0.1-10 s; config floor is 0.35 s, ceiling 3.0 s, report 0.35-2.9 s | Report and config values |
| Pass count | "pass #125 of 297" in an older note counts executed instances; printed pipeline has 109 | 109 |
| evalloop root cause | Dashboard says -O3 merges "31 dispatch jumps"; the shipped RL pipeline deletes every simplifycfg rather than flipping one knob | Both stated exactly |

## 13. Real-world applications

See `PRESENTATION_BLUEPRINT.md`, section "Real-world applications".

## 14. External sources

1. Chen et al., "AutoFDO: Automatic Feedback-Directed Optimization for Warehouse-Scale Applications", CGO 2016. https://research.google/pubs/autofdo-automatic-feedback-directed-optimization-for-warehouse-scale-applications/
2. Panchenko et al., "BOLT: A Practical Binary Optimizer for Data Centers and Beyond", CGO 2019. https://arxiv.org/abs/1807.06735
3. Trofin et al., "MLGO: a Machine Learning Guided Compiler Optimizations Framework", 2021. https://arxiv.org/abs/2101.04808 and https://research.google/blog/mlgo-a-machine-learning-framework-for-compiler-optimization/
4. Ashouri et al., "A Survey on Compiler Autotuning using Machine Learning", ACM CSUR 2018. https://arxiv.org/abs/1801.04405
5. Mytkowicz et al., "Producing Wrong Data Without Doing Anything Obviously Wrong!", ASPLOS 2009. https://research.ibm.com/publications/producing-wrong-data-without-doing-anything-obviously-wrong
6. Kanev et al., "Profiling a Warehouse-Scale Computer", ISCA 2015. https://research.google/pubs/retrospective-profiling-a-warehouse-scale-computer/
7. Elhage, "Performance of the Python 3.14 tail-call interpreter", 2025. https://blog.nelhage.com/post/cpython-tail-call/
