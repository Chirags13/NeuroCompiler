# NeuroCompiler Open Day: speaking script

Full talk: about 5 minutes, plus any live demo. The script for each slide is also in that slide's speaker notes.

## 60-second pitch

-O3 gives every program the same recipe. NeuroCompiler finds a faster one for each program, without changing your code. AI suggests recipes, and a stopwatch decides. If nothing proves itself, you keep -O3. On 33 programs it had never seen, it ran 8% faster on average, about 5% without its biggest win, and none got measurably slower. Want to race your own code?

## Full talk

### Slide 1: NeuroCompiler (15 s)

This is NeuroCompiler. It finds a faster way to compile each program, and it only believes what a stopwatch can prove.

*If asked: Each tick on the strip is one real step in the compiler's -O3 recipe.*

### Slide 2: One recipe for every program (30 s)

When you compile with -O3, the highest standard setting, the compiler runs 109 steps called passes, in the same order, for every program. That recipe is a compromise. One change can speed some programs up and slow others down. So we look for a faster recipe for each program.

*If asked: 109 is the -O3 list printed by LLVM 18 itself.*

### Slide 3: One rule: only measured runtime counts (35 s)

We have one rule: only measured runtime counts. Every candidate races -O3 in shuffled rounds. An identical copy of -O3 races too, and if it doesn't tie with -O3, we know the measurement is noisy. And if a candidate changes the program's output, it is rejected.

*If asked: Earlier work showed that shortcuts such as smaller code do not predict speed, which is why we time everything.*

### Slide 4: Models shortlist. The stopwatch decides. (40 s)

Here's how it works. First, PPO, a reinforcement-learning agent, proposes new recipes. LightGBM, a prediction model, ranks them together with a library of recipes that worked before. The top 8 are compiled, checked and timed. The fastest must win again on a fresh run. If it can't, we simply keep -O3. Think of scouts and a race: the models are scouts, and only the race picks the winner.

*If asked: Both models learned from 146 real programs. Tuning one program takes a few minutes.*

### Slide 5: Tested on 33 programs it had never seen (35 s)

To test it fairly, we kept 33 programs away from training. On those, it ran 8 percent faster than -O3 on average. Without its single biggest win, that is about 5 percent. And none got measurably slower. Most programs simply stayed at -O3. A few got much faster.

*If asked: The range around 8% is wide, because 33 programs is a small sample and one big win lifts the average. Exact values: +8.09%, and +4.92% without the largest win.*

### Slide 6: Best demo: 850 ms down to 220 ms (35 s)

Here's our best demo, an interpreter loop. Same code, not one line changed, and the runtime falls from 850 milliseconds to 220. Why? -O3 merges the interpreter's jumps into one shared jump. Our recipe keeps them separate, which lets the processor predict them. This is the best case, not the average, and it isn't one of the 33 test programs.

*If asked: We counted the jumps in both programs. We did not measure branch prediction directly, because this machine has no hardware counters. The RL agent trained on this program, so it is a demo and not a test result.*

### Slide 7: It's real. Try it live. (30-90 s)

It's a real tool. It's built on LLVM 18, and it runs from the command line or this dashboard, which shows every candidate and every changed pass. If there's time, run an example live now.

*If asked: Start it with dashboard/run.sh. A tuning run takes about 3 minutes, so keep a saved run ready.*

### Slide 8: What we learned (35 s)

The main lesson is this. On their own, the models are weak: without timing, many programs got slower. With the stopwatch, none did. Reinforcement learning added very little: 0.2 percent, which is not significant, and an RL recipe was picked on only 1 of the 33 programs. We kept it in by choice, and we say so. We also tested on one machine, with one input per program.

*If asked: The model picking alone made 16 of 33 programs slower. Output checks are strong evidence, not proof, because only one input is checked.*

### Slide 9: Where this could help (25 s)

Where could this help? Today, it suits programs that run again and again, and it helps find where a compiler hurts a program. With more work, it could help interpreters and release builds. Data centres are a long way off. Nothing here is deployed in production.

*If asked: It needs multi-threaded support and testing on many inputs before wider use.*

### Slide 10: Faster code, measured, not guessed. (15 s)

NeuroCompiler. Faster code, measured, not guessed. If you have a C program, bring it over and let's race it.

*If asked: Thank the audience and invite questions.*

## Every number, explained

- **109:** The steps in -O3. LLVM 18 prints this list itself.
- **146:** Real benchmark programs we used, after checking that each one builds, runs and can be timed well.
- **33:** Programs kept out of training, from families the models never saw.
- **Top 8:** Our choice: few enough to time in a few minutes.
- **8%:** The average gain on the 33 programs, using a geometric mean. Exact value: +8.09%.
- **About 5%:** The same average without the biggest win. Exact value: +4.92%.
- **0 slower:** No program's 95% confidence range was fully below -O3.
- **850 to 220 ms:** Median runtime of the interpreter demo. Exact values: 848.4 ms and 221.9 ms. It won again on a fresh 20-round run.
- **0.2%:** RL + LightGBM compared with LightGBM alone. The range includes zero, so it is not significant.

## Likely questions

**Is the interpreter result typical?**

No. It's our best demo. The fair result is 8% on 33 unseen programs, about 5% without the biggest win.

**Why does the average drop from 8% to 5%?**

One program, durbin, got much faster and lifts the average. So we report both numbers.

**Did every program get faster?**

No. Most stayed at -O3. A few got much faster, and none got measurably slower.

**Does the AI matter, or is it all the stopwatch?**

The stopwatch is essential. LightGBM helps choose what to time. RL added very little.

**Why keep RL if it adds so little?**

It's in the final version by team decision, and we state its measured effect openly.

**How do you know the output is still correct?**

Each candidate must match the unoptimized build's output on the given input. That's strong evidence, not proof.

**Why not just change -O3 for everyone?**

Because a change that helps one program can hurt another. That's why we tune per program.

**Will it work on my machine?**

We tested on one CPU. Tuning runs on your own hardware, but results may differ.
