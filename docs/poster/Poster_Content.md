# NeuroCompiler poster: content for each section

Images are in this folder at high resolution on white. `Poster_Preview.png` shows everything together in the template's layout.

## ABSTRACT
Every program compiled with **-O3** gets the same 109 LLVM passes in the same order. **NeuroCompiler** finds a faster recipe for each program. A reinforcement-learning agent (PPO) proposes pipelines, a LightGBM model ranks them, and real timing picks the winner. On 33 unseen programs it runs **8.09% faster than -O3** (+4.92% without the largest win), with **none measurably slower**.

## PROBLEM STATEMENT
One fixed compiler recipe cannot suit every program: the same edit makes some programs faster and others slower. Testing every option is impossible, and easy metrics mislead. Across 18,637 timed candidates, IR instruction count barely predicted runtime (ρ = −0.08). **Can we find a faster pipeline per program, and prove it?**

## OBJECTIVES
- Build a timing harness precise to within 1%
- Collect 146 real programs, split by family
- Train LightGBM and PPO to shortlist pipelines
- Beat -O3 on unseen programs, with identical output
- Ship a CLI and a live dashboard

## SYSTEM ARCHITECTURE / BLOCK DIAGRAM
Image: `01_architecture.png`

## METHODOLOGY
Image: `02_methodology.png`

## RESULTS AND PERFORMANCE ANALYSIS
- Performance comparison: `03_performance_chart.png`, with `04_key_numbers.png` beneath it
- Sample output, input: `05_sample_input.png`
- Sample output, output: `06_sample_output.png`

Heading for the sample: **SAMPLE OUTPUT: INTERPRETER DEMO**

## CONCLUSION AND FUTURE WORK
**-O3 can be beaten, program by program, with proof.** Models shortlist and the stopwatch decides: +8.09% over -O3 on unseen programs, none slower. RL's extra gain over LightGBM was +0.2% (not significant); measurement gives the reliability.

**Next:** hardware counters on bare metal, graph neural program features, RL trained on real timings, per-function tuning.

## APPLICATIONS
Strip: `07_applications.png`. Single icons: `08_app_*.png`. These are potential uses, not deployments.
- Scientific Computing: linear-algebra kernels
- Language Runtimes: interpreters, VMs
- Cloud Workloads: less CPU time per job
- Build Pipelines: per-program tuning
- Compiler Research: pipeline data

## Where each number comes from
| Number | Source |
|---|---|
| +8.09%, CI +2.44…+16.84%, +4.92% without the largest win, 0/33 slower, 9/33 at least 5% faster | `dashboard/static/data/research.json` (headline.tune_rlsl) |
| Comparison chart | research.json (eval.summary), serial test-set runs |
| 109 passes | LLVM 18 -O3 pipeline printed by opt |
| 18,637 candidates, ρ = −0.08 | research.json (ir) |
| 146 programs, 35 families, 70,409 candidates | corpus, `results/dataset.sqlite` |
| 3.83×, 848.4 ms vs 221.9 ms | `dashboard/saved/tune-interpreter-loop-3-83x-rl-pick.json`; validation program, not in the test set |
| RL +0.2%, not significant | `results/rl_paired.txt` |
