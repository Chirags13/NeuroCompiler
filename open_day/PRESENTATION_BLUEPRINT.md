# NeuroCompiler Open Day: presentation blueprint

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
