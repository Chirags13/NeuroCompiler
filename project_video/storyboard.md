# NeuroCompiler explainer: storyboard

Timestamps come from the real voice timings (`mix.py`). Every number is from a result file in this repo; sources are listed per scene.

## 0:00–0:11 · Introduction

**Visual:** Terminal types `clang -O3 program.c`. A conveyor of real -O3 pass names scrolls past while three program files drop onto it and a counter climbs to 109. It clears to the NeuroCompiler logo and a ticking stopwatch.

**Sound:** Pad fades in. Low thud and bell on the title.

**Source of the numbers:** 109 leaf passes: LLVM 18 -O3 pipeline as printed by opt (saved tune report). Pass names are real.

## 0:11–0:23 · Problem

**Visual:** A grid of 31 programs fills in for one edit, -unroll-count=2: 4 green up, 6 red down, the rest grey. Then 1,100 real points plot IR count against measured speedup, forming a shapeless cloud, and rho = -0.08 appears.

**Sound:** Whoosh in. Arpeggio enters quietly.

**Source of the numbers:** dashboard/static/data/research.json: kb.top (31 programs, 4 faster, 6 slower) and ir (18,637 candidates, rho -0.08; 1,100 points sampled from the stored 2,500).

## 0:23–0:37 · Measurement

**Visual:** Five shuffled rounds of -O3, A/A copy and two candidates fill like progress bars. The A/A blocks glow. Then an output check: candidate A identical, kept; candidate B differs, struck through and rejected.

**Sound:** Clock-like hat pulse begins. Ticks as rounds fill. High bell for keep, low bell for rejected.

**Source of the numbers:** nc/timing.py, nc/search.py and the protocol in CLAUDE.md. The round layout and candidates A and B are illustrations of the protocol, not a specific run.

## 0:37–0:52 · Data and models

**Visual:** Counters climb to 146 programs and 70,409 candidates, then dashed data lines flow into two cards: LightGBM grows five small trees, and PPO adds real edits to -O3 one at a time.

**Sound:** Whoosh in. Sub bass enters.

**Source of the numbers:** results/dataset.sqlite (candidates table: 70,409), corpus (146 usable programs). The PPO edits are the ones it shipped in the saved interpreter run. The tree drawing is schematic.

## 0:52–1:09 · How tune mode works

**Visual:** 937 dots appear: 24 pink PPO proposals, then about 913 blue library pipelines. They sort by predicted speedup; the top 8 fly out to timing bars; the winner reaches a Confirm panel; then the line 'The models shortlist. The stopwatch decides.'

**Sound:** Full arrangement. Ticks for the 8 timing bars. Bell on the final line.

**Source of the numbers:** nc/deploy.py: 24 RL proposals, about 913 library pipelines, top 8, 20-round confirmation, CI lower bound above 1.01. Dot order and bar lengths are schematic.

## 1:09–1:24 · Results

**Visual:** Animated bars with 95% CI whiskers for eight methods, including the strong random search@8 baseline; headline cards +8.09%, +4.92% and 0 of 33. Then a race: -O3 848 ms against the RL pick 222 ms, 3.83x, labelled as a validation-set demo.

**Sound:** Thud and bell on the headline number.

**Source of the numbers:** research.json eval.summary and headline.tune_rlsl; dashboard/saved/tune-interpreter-loop-3-83x-rl-pick.json for the demo. The interpreter (ss/Misc/evalloop) is a validation program, so it is not in the test-set number.

## 1:24–1:36 · Implementation and honest lesson

**Visual:** Technology chips, then a pan over the real dashboard screenshot comparing the selected sequence with -O3. Then three cards: LightGBM alone (Spearman about 0.11), RL on top (+0.2%, n.s.), measure and confirm (+8.09%, 0 slower).

**Sound:** Hat pulse fades out.

**Source of the numbers:** docs/assets/shots/tune_diff.jpg; CLAUDE.md decisions and results/models/cv_latest.json (Spearman +0.111); results/rl_paired.txt (+0.2%, 1 of 33 programs).

## 1:36–1:42 · Close

**Visual:** Logo, name, tagline, three result chips and the team line.

**Sound:** Final thud and bell, music resolves and fades.

**Source of the numbers:** research.json headline.tune_rlsl.
