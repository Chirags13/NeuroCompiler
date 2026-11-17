# NeuroCompiler Open Day: speaking script

Full talk: about 7 minutes. The script for each slide is also in that slide's speaker notes.

## 60-second pitch

-O3 gives every program the same 109-step recipe. NeuroCompiler finds a faster one for each program, without changing your code. AI proposes and ranks recipes, then real timing decides, and if nothing proves itself you get -O3. On 33 unseen programs it ran 8.09% faster, 4.92% without the largest win, and none were slower. Want to race your own code?

## 3-minute stall tour

1. **Slide 1 (20 s):** the two bars.
2. **Slide 5 (30 s):** models shortlist, the stopwatch decides.
3. **Slide 9 (40 s):** why the demo got 3.83x.
4. **Slide 11 (40 s):** the 33-program result, with caveats.
5. **Slide 13 (20 s):** where it could be used, then offer the live demo.

## Full talk

### Slide 1: Same code. 3.83× faster. (20 s)

Two bars, same C program. 848 milliseconds, or 222. We did not change a single line. This is our best demo, not our average. The fair number comes later.

*Evidence: dashboard/saved/tune-interpreter-loop-3-83x-rl-pick.json. Confirmed 3.830x, CI 3.820-3.838, A/A control 1.001x. Validation-split program the RL trained on; not in the 33 test programs.*

### Slide 2: NeuroCompiler (15 s)

This is NeuroCompiler. It finds a faster compiler recipe for each program, and only believes what a stopwatch can prove.

*Evidence: Strip built from opt -print-pipeline-passes, LLVM 18.1.8, in execution order.*

### Slide 3: Every program gets the same 109-step recipe (30 s)

Compilers improve code in small steps called passes. -O3 runs 109 of them, in the same order for every program. But one edit, vectorizing eight lanes wide, made one program 6.6 times faster and another 17 percent slower. So no single recipe suits everyone.

*Evidence: open_day/assets/o3_pipeline_llvm18.txt: 109 steps, 76 distinct. research.json kb.top: -force-vector-width=8, screening 0.83x to 6.59x on 31 programs; confirmed faster on 5, slower on 0. Colours group passes for readability.*

### Slide 4: Why not just try everything? (30 s)

Why not try everything? Four edits out of our 346 gives 587 million recipes: over eighteen years at one second each. And shortcuts fail: each dot is a real recipe, and smaller code does not mean faster code. The correlation is minus 0.08. So we judge one thing: time.

*Evidence: C(346,4) = 586,862,710, calculated. research.json ir: n = 18,637, rho -0.0797. An earlier attempt improved code size and runtime did not move. Ashouri et al. 2018 calls phase ordering a long-open problem.*

### Slide 5: Models shortlist. The stopwatch decides. (30 s)

Here is the one sentence to remember: models shortlist, the stopwatch decides. Like scouts and a race. About 935 candidates go in, eight actually race -O3, and one must win again on a fresh run. If nothing proves itself, you get -O3.

*Evidence: Interpreter demo: 22 RL + 913 library, 48 compiled, 8 timed. nc/deploy.py select_topk.*

### Slide 6: The whole system (40 s)

The top lane is the lab: 146 real programs, timed recipes, two trained models, then frozen. The amber lane is your program: features, proposals, ranking, compile and check, time against -O3, and you get a binary with a proof report.

*Evidence: nc/deploy.py deploy_source, nc/tunelock.py. Split by family, frozen before modelling: 91 train, 22 val, 33 test. 70,409 candidates, 19,534 measurements. Median about 139 s.*

### Slide 7: Two models, two jobs (30 s)

Two models, two jobs. PPO, a reinforcement-learning agent we wrote from scratch in NumPy, proposes recipes. LightGBM ranks them. Its ranking on unseen programs is honest but weak, plus 0.11. That is exactly why neither model picks the winner.

*Evidence: PPO up to 24 proposals (3k), 120 macro-edits, reward = surrogate delta, 200 iterations x 64 episodes. LightGBM ~130 program + ~98 recipe features, Spearman +0.111 [+0.06, +0.15], gain@5 1.107x vs random 1.091x. Gate 7B narrowly met after Phase 4 data.*

### Slide 8: Nothing ships without proof (35 s)

Three gates. Same answer as the unoptimized build? Faster in the race? Faster again on a fresh run, with an identical copy of -O3 as a control? Fail and -O3 ships. 21 of 33 test programs kept -O3, and that is the system working. Our timing uncertainty is about a tenth of a percent.

*Evidence: deploy.py: margin 0.01, confirm_reps 20. Selftest CI half-width 0.12%, A/A bias 0.01%. Gate 3 was added after lencod shipped at 0.979x in an early run. Branchy 2026-10-30: fresh 1.014x, CI lower bound 1.008. Mytkowicz et al. 2009 on measurement bias.*

### Slide 9: The mystery solved: one jump for everything (40 s)

Back to the mystery. This program is an interpreter. -O3 merged all its jumps into one, so the processor has one place to guess what runs next. Undo that, and 63 jumps can each learn their own pattern. Not a toy problem: the same kind of change hit CPython with Clang 19.

*Evidence: Measured with llvm-objdump: 2 at -O3; 63 with -simplifycfg-sink-common=false and with the RL pipeline. CPython: Elhage 2025, 332 vs 3 jumps, 9-12%; fixed by LLVM PR 114990.*

### Slide 10: It runs. Ask us to show you. (30-90 s)

This is a running tool. On the left, real runs from 30 October: matrix multiply 1.49 times faster, and branchy keeping -O3. On the right, the dashboard. If time allows, run an example live.

*Evidence: open_day/assets/runs/: matmul confirmed 1.485x [1.384, 1.534], A/A 1.009x, 175.5 s. Dashboard: dashboard/run.sh, localhost:8000.*

### Slide 11: 33 programs it had never seen: +8.09% over -O3 (40 s)

The real test: 33 programs from families it had never seen. 8.09 percent faster than -O3, 4.92 without the largest win, none measurably slower. Two honest caveats: the interval is wide, and our lead over random search is not significant. The median program gains nothing; the wins come from a few.

*Evidence: research.json eval.summary. Durbin 2.81x. 9/33 >= +5%. Paired (LightGBM + timing): vs random top-8 +5.8% (+1.0..+13.9), GA +5.3% (+0.3..+13.4), random search +2.1% (-0.6..+5.8, n.s.).*

### Slide 12: We put it to the test. Here is what we learned. (40 s)

We tested this hard. An ML pick alone made 16 of 33 programs slower; with the stopwatch, none. We also asked three questions. Our first headroom sample missed its goal, so we reset the target and searched wider. RL added only 0.2 percent, not significant. And predicting without running ships only as advice.

*Evidence: ML-only top-1 16 slower; RL + SL 0. gate_by_sample: +4.00%, 4/15 = 26.7%, target 30%. Phase 5: +15.6% (CI +10.2..+22.1), +14.1% excl. largest. RL +0.2% (-0.2..+0.7), shipped on 1/33 (fibo). Predict +0.64%, target +1.5%, median +0.62 s. Output checks are evidence, not proof.*

### Slide 13: Where this could matter (30 s)

Where could it matter? Green works today. Amber needs engineering. Grey is a long way off. It suits programs that run often and rarely change. Nothing here is deployed in production.

*Evidence: PRESENTATION_BLUEPRINT.md applications section. External: Elhage 2025; MLGO 0.3-1.5% QPS. Calculated payback: 139 s / 7.49% = about 1,860 runs of a 1 s job at the average gain. Future work, not built: hardware counters, graph neural features, RL on real timings, per-function tuning.*

### Slide 14: -O3 is a great default. Now it has to prove it. (20 s)

-O3 is a fantastic default. But for individual programs we can find something faster, and prove it. If you have a C program, bring it over and let's race it.

*Evidence: Summary of slides 9 to 11.*

### Slide 15: References (reference)

Reference slide. Show it if someone asks about the sources.

*Evidence: open_day/PROJECT_ANALYSIS.md lists full URLs.*

## Likely questions

**Is 3.83x your typical result?**

No. It is the best demo, on a validation program the RL trained on. The fair result is +8.09% on 33 unseen programs, +4.92% without the largest win. The median program gains nothing.

**Why not just use PGO?**

PGO is a different and proven technique. We did not compare against it, and the two could combine. We change the pass recipe; PGO feeds runtime profiles to the same recipe. Combining them is future work.

**Does the AI matter, or is it all the stopwatch?**

Both matter, unevenly. LightGBM + timing beat random top-8 by 5.8% and the GA by 5.3%, but its lead over random search at equal budget is not significant. RL added +0.2%, not significant. Timing is the essential part: without it, 16 of 33 programs got slower.

**Why keep RL if it adds nothing?**

It is in the final version by team decision, as a demonstration, and we state the measured effect. An RL proposal shipped on 1 of 33 test programs.

**How do you know the output is still correct?**

Each candidate's output hash must match the -O0 build on the given input. That is strong evidence, not proof: other inputs are not checked.

**Will it work on my machine?**

We measured one CPU, a Zen 4 Ryzen 9 270 under WSL2. Because tuning times your program on your hardware, it can be re-run, but the models were trained here and gains may differ.

**Why not delete those passes from -O3 for everyone?**

Because that edit hurts other programs. Deleting every simplifycfg ranged from 0.86x to 3.82x. That is the point of per-program tuning.

**Isn't this overfitting to benchmarks?**

A tuned binary is tuned for the input used. That is a real limitation, and multi-input verification is on the production list. The models themselves are tested on families they never saw.

**What about multi-threaded programs?**

Not supported in this study. The corpus is deterministic and single-threaded, with visible output.
