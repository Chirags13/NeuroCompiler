# OPEN DAY PPT GENERATION PROMPT

Paste this file into a Claude Code session opened at the NeuroCompiler repository root.

## Task

Create a visually spectacular, technically credible, story-driven PowerPoint for our College Project Open Day, following
the project understanding, narrative, 22-slide blueprint and design specification below. Build everything from the
repository's real data. You do not need to rediscover the repository.

## Required tools

Check each one is present, install if missing, and verify it works before you start:

| Tool | Use | Setup |
|---|---|---|
| python-pptx 1.0+ and Pillow | Build native, editable PPTX | Isolated venv `open_day/.pptxenv`. Do not change the project `.venv` |
| Microsoft PowerPoint through COM | Real rendering for review | `powershell.exe` from WSL. Copy the PPTX to a Windows temp folder, export PNG and PDF |
| `dashboard/static/data/research.json` | Single source of chart data | Read at build time; never retype numbers |
| LLVM 18.1.8 at `/usr/lib/llvm-18/bin` | Real pass pipeline | `opt -passes='default<O3>' -print-pipeline-passes`. Never use OS default LLVM 21 |
| Skills: `dataviz`, `impeccable` | Chart and visual judgement | Load if available |

Not needed: Canva, Remotion, Mermaid, Graphviz, Manim or AI images. Native shapes stay editable and real data is the imagery.
The Canva plugin exists in the catalog but needs an account connection, so it is optional.

## Rules

- Use only verified information from the repository and the listed external sources.
- Never invent functionality, metrics or improvements. Never present planned features as complete.
- Distinguish measured, calculated, simulated and external numbers.
- Report geomean with and without the largest result.
- State that RL's measured effect is +0.2% (not significant) and that an RL proposal shipped on 1 of 33 test programs.
- Label 3.83x as a best-case demo on a validation program, not part of the test set, and one the RL trained on.
- Label applications Demonstrated, Adaptable or Future potential. Never claim deployment.
- Diagrams must match the code in `nc/`.
- Do not write to `results/dataset.sqlite` or `corpus/manifest.jsonl`. Do not run CPU-heavy work while a timing job runs.
- Do not use the fabricated or simulated as if it were a real screenshot. Real assets only.

## Deliverables in `open_day/`

- `NeuroCompiler_Open_Day.pptx`: 16:9, editable text, native charts and diagrams, speaker notes on every slide
- `NeuroCompiler_Open_Day.pdf`: for a machine without the fonts
- `SPEAKING_SCRIPT.md`: full talk, 3-minute stall tour, 60-second pitch, likely questions
- `build_deck.py`, `assets/`, `review/`: reproducible build, assets and rendered slides

## Quality control

Do not finish when the PPTX is generated. Instead:

1. Render with PowerPoint to PNG and PDF.
2. Look at every slide individually.
3. Check layout, clipping, alignment, fonts, diagram legibility and chart accuracy.
4. Check that the story flows, the explanations are understandable and the applications are credible.
5. Redesign weak or ordinary slides.
6. Fix, render again, and repeat until clean.
7. Recompute the numbers on the slides against `research.json` with an automated check.

---

# PART 1: PROJECT UNDERSTANDING


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

---

# PART 2: APPLICATIONS, NARRATIVE, SLIDES, DESIGN

> **Final deck: simple 10-slide version in the explainer video's order (about 5 minutes).** Numbers are rounded as in the video. Earlier cuts are in `open_day/full_version/` (22 slides) and `open_day/version_15_slides/`.
> Order: 1 title, 2 one recipe, 3 one rule, 4 how it works, 5 result, 6 best demo, 7 dashboard, 8 what we learned, 9 where it could help, 10 close.


Companion to `PROJECT_ANALYSIS.md`. Every number here is traced there.

## Real-world applications

Maturity labels: **Demonstrated** = supported by the current implementation and measured here. **Adaptable** = applicable with some modification. **Future potential** = needs substantial development and validation. Nothing here has been deployed in production.

### 1. Numerical kernels run thousands of times (Demonstrated)

- **Scenario.** A research group runs the same linear-algebra kernel in a parameter sweep, thousands of times on one known CPU.
- **Problem.** -O3's vector and unroll heuristics do not know this kernel's data size or this CPU.
- **How we help.** Tune once on a representative input, then reuse the binary. PolyBench test results: durbin 2.81x, 3mm 1.43x, gramschmidt 1.16x.
- **Enabling component.** Knowledge-base edits (`-force-vector-width`, `-unroll-max-count`) plus the timing loop.
- **Benefit.** Less CPU time per job with no source change. Calculated payback: at +8.09%, a 1 s job repays a 139 s tune after about 1,860 runs.
- **Still needed.** Check that the tuned binary holds across the input sizes actually used; multi-thread support for parallel kernels.

### 2. Finding where the compiler hurts a program (Demonstrated)

- **Scenario.** A compiler engineer or a performance team wants to know why a program got slower.
- **Problem.** Passes interact, so a performance bug can hide inside one of 109 steps.
- **How we help.** The search plus pass minimization narrows a huge gain to a small edit list. evalloop: merged dispatch, 63 indirect jumps down to 2, with a knob restoring them.
- **Enabling component.** `nc/search.py` minimization, `nc/passkb.py`, the dashboard's pipeline diff.
- **Benefit.** A concrete, reproducible lead for a compiler bug report.
- **Still needed.** Automated regression bisection across compiler versions.

### 3. Interpreters and language runtimes (Adaptable)

- **Scenario.** A language runtime's dispatch loop runs for every bytecode instruction.
- **Problem.** Compiler changes can quietly merge dispatch. External evidence: a Clang 19 change left CPython with 3 indirect jumps instead of 332 and made builds about 9-12% slower (Elhage, 2025).
- **How we help.** Timing a build's real workload exposes this class of problem, as in evalloop.
- **Enabling component.** Timing loop, llc backend flags, output verification.
- **Benefit.** Catch dispatch regressions before release.
- **Still needed.** Large multi-file builds, long-running workloads, realistic benchmark suites, coexisting with PGO.

### 4. Release builds for CPU-heavy tools (Adaptable)

- **Scenario.** A team ships a compressor, encoder or query engine with a nightly benchmark.
- **Problem.** PGO needs profile collection; many teams stop at -O3.
- **How we help.** A release job runs tune on the benchmark, keeps the proof JSON and falls back to -O3 automatically.
- **Enabling component.** CLI, JSON report, -O3 fallback, frozen manifest.
- **Benefit.** Extra speed from a build step alone, with an audit trail.
- **Still needed.** Multi-input verification, cost control, combination with PGO/LTO/BOLT. External context: AutoFDO 10.5%, BOLT up to 8% on top of PGO and LTO. Those are different techniques, not our numbers.

### 5. Data-centre fleets (Future potential)

- **Scenario.** A service runs on thousands of machines, so small gains save real cost.
- **Problem.** Google's MLGO work shows that even 0.3-1.5% QPS was worth deploying.
- **How we help.** The tune-and-prove loop could screen per-service build recipes.
- **Enabling component.** Concept only.
- **Benefit.** Potentially lower CPU cost per request.
- **Still needed.** Multi-threaded and I/O-bound services, live traffic, safety beyond one-input hash checks, hardware counters. A long way from current scope.

## Presentation narrative

**Central message:** *Models shortlist. The stopwatch decides.* A compiler's default recipe can be beaten for an individual program, and it should only count when a clock proves it.

**Opening hook:** Two bars. Same code. 848 ms vs 222 ms. No explanation for ten seconds. Then "What changed? Not one line of the program."

**Progression:** Curiosity (a mystery speedup) -> Problem (one recipe for all) -> Challenge (too many options, misleading metrics) -> Idea (shortlist then prove) -> What we built -> Under the hood -> Demonstration (root cause, live tool, results, honest failures) -> Real world -> Impact.

**Honesty as a feature:** The deck's strongest credibility move is slide 18, which turns the misses into lessons. An audience of engineers trusts results more after seeing them.

**Ending:** "-O3 is a great default. Now it has to prove it." Then an invitation to bring a C program to the stall.

**Timing:** full talk about 14 minutes. Stall walk-through (slides 1, 7, 14, 16, 19) about 3 minutes. Sixty-second pitch in the speaking script.

## Slide-by-slide blueprint

Each entry gives: purpose / story position / takeaway / content / concepts / visual / assets / layout / transition.

### 1. Same code. 3.83x faster.
- **Purpose:** stop a passer-by. **Position:** Act 1, Curiosity. **Takeaway:** something surprising happened.
- **Content:** bars -O3 848.4 ms, NeuroCompiler 221.9 ms. Line "Same C source. Not one line changed." Footnote: confirmed 3.83x, 95% CI 3.82-3.84, 20 rounds; best-case demo, validation-set program; fair average on slide 16.
- **Concepts:** none. **Visual:** two proportional race bars on black. **Assets:** native shapes; numbers from the saved run.
- **Layout:** giant headline left and top, bars lower third. **Transition:** "So what actually changed?"

### 2. NeuroCompiler (title)
- **Purpose:** name it. **Position:** Act 1. **Takeaway:** it finds a faster compiler recipe per program.
- **Content:** wordmark; subtitle; team, guide, department, college; VTU and JSSATE logos.
- **Visual:** real 109-tick pipeline strip behind the wordmark. **Layout:** centred left, team strip at the bottom. **Transition:** "Let's start with what a compiler recipe is."

### 3. Every program gets the same 109-step recipe
- **Purpose:** explain passes without jargon. **Position:** Act 2, Problem. **Takeaway:** -O3 is one fixed order for everyone.
- **Content:** source -> 109 steps -> program. 76 distinct passes; simplifycfg and instcombine run 8 times each. Analogy: same recipe for every dish.
- **Concepts:** pass, pipeline, -O3. **Visual:** full-width strip, one tick per real pass, coloured by group. **Assets:** real pipeline from `opt`.
- **Layout:** strip through the middle, source and binary at the ends. **Transition:** "Does one recipe suit everyone?"

### 4. The same edit helps one program, hurts another
- **Purpose:** show no universal best. **Position:** Act 2. **Takeaway:** the best recipe depends on the program.
- **Content:** six real edits with min-max range across 31 programs, plus confirmed faster/slower counts.
- **Concepts:** vectorization width, unrolling. **Visual:** log-scale range bars around 1.0x. **Assets:** `research.json kb.top`.
- **Layout:** chart full width, single-line conclusion. **Transition:** "So why not try everything?"

### 5. Why not just try everything?
- **Purpose:** show the scale. **Position:** Act 2, Challenge. **Takeaway:** brute force is hopeless.
- **Content:** 346 -> 59,685 -> 6,843,880 -> 586,862,710; 18.6 years at 1 s each (calculated). "Open problem for decades" (Ashouri 2018).
- **Visual:** four rising steps, last one amber. **Layout:** big number right, steps left. **Transition:** "Can a shortcut metric help?"

### 6. The easy scoreboard lies
- **Purpose:** kill the fake metric. **Position:** Act 2. **Takeaway:** only runtime counts.
- **Content:** scatter of IR change vs speedup; rho -0.08; 18,637 candidates; 57% coin flip; earlier attempt.
- **Visual:** native XY scatter. **Assets:** sample of `ir.sample`. **Layout:** chart left two-thirds, numbers right. **Transition:** "So what can we trust? The clock."

### 7. Models shortlist. The stopwatch decides.
- **Purpose:** reveal the idea. **Position:** Act 3, Idea. **Takeaway:** ML narrows, measurement decides.
- **Content:** funnel 935 -> 48 -> 8 -> 1 or -O3, from the real evalloop run. "-O3 is always in the race."
- **Visual:** narrowing horizontal funnel, stopwatch at the end. **Layout:** full-width. **Transition:** "Here is the machine that does it."

### 8. The whole system
- **Purpose:** accurate architecture. **Position:** Act 4. **Takeaway:** an offline lab feeds an online tool.
- **Content:** two lanes with real module names. Offline: corpus -> search -> timing -> dataset -> features -> LightGBM -> PPO. Online: source -> features -> propose -> rank -> compile and verify -> time -> confirm -> binary + JSON. Trained models feed the online lane.
- **Visual:** native boxes and connectors. **Layout:** offline on top, online below, highlighted. **Transition:** "It starts with data."

### 9. 70,409 recipes, measured the hard way
- **Purpose:** show the data work. **Position:** Act 4. **Takeaway:** the test set is truly unseen.
- **Content:** 347 -> 146; PolyBench 30, SingleSource 41, MultiSource 75; 35 families; split 91/22/33; 19,534 measurements.
- **Visual:** funnel bar and native stacked split bar. **Transition:** "How do you describe a recipe to a machine?"

### 10. A recipe becomes a list of edits
- **Purpose:** explain the genome. **Position:** Act 5. **Takeaway:** edits are small, portable, removable.
- **Content:** real strip with the 16 removed passes marked; the 4 real edits from the evalloop win; list of edit operators.
- **Visual:** strip with amber marks and four edit cards. **Transition:** "Every edit needs a judge."

### 11. A stopwatch you can trust
- **Purpose:** show the core engineering. **Position:** Act 5. **Takeaway:** timing noise is under 1% by design.
- **Content:** shuffled interleaved rounds diagram; pinned core; ASLR off; A/A control; 0.12% CI, 0.01% A/A bias; 5-core rejected; Mytkowicz citation.
- **Visual:** colour-block rounds. **Transition:** "Who picks what to time?"

### 12. Two models, two jobs
- **Purpose:** show PPO and LightGBM. **Position:** Act 5. **Takeaway:** one proposes, one ranks; neither decides.
- **Content:** PPO facts; LightGBM facts; +0.11 Spearman; RL curve labelled predicted, not measured.
- **Visual:** two cards with a native line chart. **Transition:** "Then the part that keeps us honest."

### 13. Nothing ships without proof
- **Purpose:** show safety. **Position:** Act 5. **Takeaway:** default outcome is -O3.
- **Content:** three gates; lencod story; 2 wrong-output picks caught; 21/33 kept -O3.
- **Visual:** gate pipeline with an exit to -O3. **Transition:** "Back to our mystery."

### 14. The mystery solved: one jump for everything
- **Purpose:** pay off the hook. **Position:** Act 6, Demonstration. **Takeaway:** real root cause, real hardware effect.
- **Content:** merged jump vs separate jumps; 2 vs 63; branch prediction; CPython 3 vs 332 external link; note on what the RL pipeline actually did.
- **Visual:** side-by-side native control-flow diagrams. **Transition:** "See it run."

### 15. It runs. Ask us to show you.
- **Purpose:** prove it exists. **Position:** Act 6. **Takeaway:** a real tool anyone can use.
- **Content:** dashboard screenshot; fresh terminal runs from 2026-10-30 (matmul confirmed 1.485x; branchy not confirmed, -O3 shipped); `bin/neurocompiler` command.
- **Visual:** screenshot in a thin frame with a terminal card. **Transition:** "One program is a story. Here are 33."

### 16. 33 programs it had never seen: +8.09% over -O3
- **Purpose:** headline. **Position:** Act 6. **Takeaway:** +8.09%, zero slower.
- **Content:** native bar chart with CI whiskers; KPIs +8.09, +4.92 excl. largest, 9/33, 0/33. Paired vs random search not significant.
- **Transition:** "An average hides things."

### 17. Inside the average: a few big wins, most stay safe
- **Purpose:** open the average. **Position:** Act 6. **Takeaway:** a few big wins; most stay safe.
- **Content:** sorted log chart of 33 programs; 21 unchanged; median 1.00x; durbin alone moves +4.92 to +8.09.
- **Transition:** "So we put it to the test."

### 18. We put it to the test. Here is what we learned.
- **Purpose:** credibility, framed as lessons. **Position:** Act 6. **Takeaway:** testing showed the stopwatch is what makes ML safe.
- **Content:** hero 16/33 slower with ML alone vs 0/33 with the stopwatch; three questions: headroom (first sample missed, +15.6% after searching wider), RL vs LightGBM (+0.2%, n.s., 1/33), skipping the run (+0.64%, advisory); scope line.
- **Visual:** hero panel left, three question cards right. **Transition:** "So where is this useful?"

### 19. Where this could matter
- **Purpose:** relevance. **Position:** Act 7. **Takeaway:** concrete uses, honestly graded.
- **Content:** five use cases in three maturity columns.
- **Visual:** three columns with colour-coded labels. **Transition:** "When does it pay off?"

### 20. It pays off where a program runs again and again
- **Purpose:** practical economics and roadmap. **Position:** Act 7. **Takeaway:** it pays where programs run often.
- **Content:** payback calculation; what production needs; roadmap items labelled not built.
- **Transition:** "Let's bring it home."

### 21. -O3 is a great default. Now it has to prove it.
- **Purpose:** memorable end. **Position:** Act 8. **Takeaway:** the slogan.
- **Content:** three numbers, team, guide, invitation.
- **Transition:** questions.

### 22. References (appendix)
- Citations only.

## Visual design specification

**Philosophy: "instrument panel".** The deck should feel like a precision lab instrument: dark, exact, calm, with one bright signal colour reserved for the proven result. Decoration has to be data.

**Identity.** The signature is the *pipeline strip*: 109 ticks, one per real -O3 pass. It appears on the title, explains the recipe, then shows the edits. An 8-segment act tracker sits at the bottom of each slide.

**Palette.**

| Role | Hex |
|---|---|
| Ink background | `#0A0C10` |
| Panel | `#12161D` |
| Raised panel | `#1A2029` |
| Line | `#2B333F` |
| Text | `#F4F6F8` |
| Muted text | `#A3ADBB` |
| Signal amber (NeuroCompiler, proven result) | `#FFB224` |
| Cyan (LightGBM, supervised) | `#3CCFE6` |
| Rose (PPO, RL) | `#FF5D8F` |
| Green (verified) | `#39D98A` |
| Red (slower, failed) | `#FF5A52` |
| Slate (-O3 baseline) | `#8A94A3` |

**Typography.** Installed on every Windows 10/11 PC, so the deck survives a borrowed laptop: Bahnschrift (display), Segoe UI (body), Consolas (code). Titles 36-44 pt, hero numbers 80-170 pt, body at least 18 pt, labels at least 14 pt, source lines 11-12 pt.

**Layout.** 16:9. 0.6 in margins. Kicker top-left, title below it. One idea per slide. Layouts vary between hero, diagram, chart and cards.

**Diagrams.** Native rounded rectangles and connectors, thin 1.25 pt lines, colour by role, no shadows or 3D.

**Charts.** Native PowerPoint charts where possible, one highlight colour, direct labels, no chart junk.

**Images.** Real screenshots and logos only. No stock photos and no AI images: real project data is more interesting here.

**Motion.** A fade between slides only.
