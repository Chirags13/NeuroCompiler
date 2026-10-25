# NeuroCompiler (WSL2)

**Results: see [results/FINAL_REPORT.md](results/FINAL_REPORT.md).** Model top-8 + timing: +7.5% geomean vs -O3
(+4.3% excluding the largest result) on 33 held-out programs; details, baselines and limits in the report.

**Final version = RL + SL** (`bin/neurocompiler prog.c --out prog`): the RL agent (PPO) proposes pipelines for the
program, the supervised LightGBM model ranks them together with the pipeline library, the top 8 are compiled,
verified and timed against -O3, and the fastest ships only if a fresh run confirms it beats -O3 by >1% (else -O3).
`--no-rl` = SL only. Measured on the test set, RL + SL equals SL (+0.2%, not significant); see the report.

Measurement harness for the NeuroCompiler project. It compiles a C program with any LLVM pass
pipeline, runs it pinned and interleaved, checks the output, and reports runtime with confidence
intervals, plus binary size, IR instruction count and compile time. **Nothing downstream
(search, dataset, models) should be trusted until `selftest` passes on your machine.**

## 1. WSL2 preparation (Windows side)

Create/edit `C:\Users\<you>\.wslconfig`:

```
[wsl2]
processors=8
memory=16GB
swap=0
```

Then in PowerShell: `wsl --shutdown`, and reopen Ubuntu. Before every measurement session:
plug in, set Windows power mode to **Best performance**, and close browsers, games, and heavy
background apps. (WSL2 cannot control the CPU governor or turbo, so these are your only levers.)

## 2. Install (inside WSL2)

```bash
cp -r neurocompiler ~/neurocompiler     # must live on the Linux filesystem, not /mnt/c
cd ~/neurocompiler
./setup_wsl.sh
source .venv/bin/activate
python -m nc.cli env                    # read the [!] warnings
```

Pinned toolchain: **LLVM 18** from Ubuntu 24.04 apt. Do not mix LLVM versions in one dataset.

## 3. Run the gate

```bash
python -m nc.cli selftest bench/matmul.c
python -m nc.cli selftest bench/branchy.c
python -m nc.cli cpusweep bench/matmul.c     # pick the quietest vCPU, then edit timing_cpu
python -m nc.cli baselines bench/matmul.c
python -m nc.cli o3pipeline
```

`selftest` checks, in order: (1) one binary's repeatability and drift, (2) an A/A test of an
identical binary at two paths, (3) that -O0 vs -O3 shows a clear gap and outputs match,
(4) fidelity of our `opt`+`llc` path against plain `clang -O3` (informational).
Reports are saved to `results/`.

If it fails, change one thing at a time: run `python -m nc.cli cpusweep bench/matmul.c` to find the quietest
vCPU (set it as `timing_cpu` in `config.toml`), cleaner machine state, more `--reps`, a longer-running input. If no setting passes, tell me the
numbers and we will decide whether to relax the thresholds and say so in the writeup.

## 4. How a build works

```
clang -O3 -march=native -Xclang -disable-llvm-passes  ->  start IR (TBAA, attributes, no passes)
opt -passes=<pipeline>                                 ->  optimized IR
llc -O3 -relocation-model=pic                          ->  object
clang obj -lm                                          ->  binary
```

Why not `-O0` IR: it lacks TBAA and other metadata that real `-O3` builds see, which would make
our baseline weaker than the real `-O3`. Binaries are cached by the hash of the optimized IR, so
identical IR is never benchmarked twice. All builds use the same `-march`, including the baseline.

Note: the empty-`argv[0]` PolyBench dump is launched through `bash exec -a`, because Python 3.14
refuses to spawn a process with an empty argv[0].

## 5. WSL2 limits you should know

| Item | Status |
|---|---|
| CPU governor / turbo control | Not available. Mitigated by interleaving and paired comparisons |
| `perf` hardware counters | Generally unavailable. Use `valgrind --tool=cachegrind` for *simulated* dynamic features (instructions, cache and branch misses). They are simulations, not hardware counters, and are labelled as such in the dataset |
| Timing noise | Higher than native. The self-test measures it; every claimed gain must exceed it |
| GPU (RTX 5060) | Works via the Windows NVIDIA driver (do not install a Linux driver inside WSL). Needed only for GNN work later: use a PyTorch build with CUDA 12.8+ |

## 6. Layout

```
nc/toolchain.py   compile with any pass pipeline (single or multi-file, C or C++), IR-hash dedup, llc flags
nc/timing.py      pinned, interleaved runner; bootstrap CIs; correctness check; quiet guard; SMT-sibling option
nc/envcheck.py    environment report and warnings
nc/corpus.py      fetch suites, prescan, scan with quality filters, frozen split, report
nc/msource.py     LLVM test-suite MultiSource adapter (mini CMake interpreter)
nc/pipeline.py    -O3 pass tree, edit genome, mutation operators; action space v1 and v2
nc/search.py      levels / random / evo (v1) / random2 / evo2 (v2), merged confirmation, minimization, validation, report
nc/passkb.py      Phase 4: per-pass knowledge base (leave-one-out, option flips, family edits, add-one, knobs)
nc/collect.py     Phase 5: data collection driver and data-quality report with dataset version tag
nc/features.py    Phase 6: static IR features, simulated (cachegrind) dynamic features, scan facts, genome encoding
nc/model.py       Phase 7: LightGBM surrogate (regressor + lambdarank), leave-one-family-out CV, gate 7B
nc/deploy.py      Phase 8: top-k deployment loop (-O3 always included); bin/neurocompiler wrapper
nc/rl.py          Phase 8 upgrade: PPO (numpy) over macro-actions with surrogate reward
nc/evaluate.py    Phase 9: frozen-test evaluation of all methods and baselines, report, reproduction run
nc/db.py          SQLite measurement dataset
nc/cli.py         env | o3pipeline | baselines | selftest | cpusweep | corpus | search | passkb | collect |
                  features | model | rl | deploy | evaluate
bench/            two sample programs (regular loops vs branchy integer code)
config.toml       machine id, pinned CPU, LLVM path, thresholds, speed and guard settings
```

## 7. Corpus (Phase 2)

```bash
python -m nc.cli corpus fetch                         # PolyBench/C 4.2.1 + LLVM test-suite SingleSource + MultiSource
python -m nc.cli corpus prescan --suite multisource   # parallel, untimed filter (build, oracle, rough runtime)
python -m nc.cli corpus prescan --suite singlesource
python -m nc.cli corpus scan --suite multisource      # pinned scan of prescan survivors; keep the machine idle
python -m nc.cli corpus scan --suite singlesource
python -m nc.cli corpus report                        # funnel: candidates, usable, rejection reasons
python -m nc.cli corpus split                         # ONCE, after scanning. Frozen by family
```

Suites: PolyBench (dimensions scaled continuously), SingleSource C **and C++** (programs whose size comes
from `argv[1]` are scaled through the argument), MultiSource Benchmarks + Applications (multi-file
programs are compiled per file and `llvm-link`ed into one module, so -O3 and every candidate see the whole
program; inputs are exposed in a per-program run directory under `corpus/generated/run/`;
SMALL/default/LARGE problem sizes are input variants). Programs whose CMake generates inputs or needs
other libraries are recorded as `unsupported`.

A program is kept only if it builds at -O0/-O1/-O2/-O3/-Os, runs with identical output at every
level (the -O0 output is the oracle; PolyBench arrays are dumped from the same timed binary),
is deterministic, and its -O3 runtime lies in [`floor_s`, `ceiling_s`] on THIS machine.
The prescan only rejects what load cannot fake (build/run failures, empty or mismatching output,
fast even under load); everything else goes to the pinned scan. Programs needing more than 3 GB are
rejected (`too_big`). Everything is written to `corpus/manifest.jsonl`, rejected programs included,
with the reason. The split is by family, written to `corpus/split.json`, and refuses to be
overwritten without `--force`.

## 8. Search and the headroom gate (Phase 3)

```bash
python -m nc.cli search run --sample 15 --budget 25 --methods random,evo,evo2 --exclude-searched
python -m nc.cli search validate          # independent re-measurement of programs searched before validation existed
python -m nc.cli search report
python -m nc.cli search show --program ss/Misc/evalloop
```

Per program: (1) standard-level seeds, (2) search methods: `random`/`evo` mutate the -O3 pass tree with
action space v1 (delete / duplicate / swap / insert, six opt knobs, llc level); `random2`/`evo2` use v2,
which adds pass-option flips on one or every instance of a pass (e.g. simplifycfg `sink-common-insts`),
deleting every instance of a pass, more opt knobs, llc backend flags (tail duplication/merging, loop
alignment, cmov conversion, scheduling, jump tables) and more insertable passes (dfa-jump-threading,
gvn-sink, ...). v1 is unchanged (same pipelines for the same genomes, same random streams).

Cost controls (screening only; the confirmation protocol is unchanged):
* compile in parallel; identical IR/binaries cost nothing;
* output verification on helper CPUs while nothing is timed;
* successive-halving screening: 1 interleaved round for every binary, 2 more only if the 1-round
  speedup is >= `screen_keep` (0.98; on past data this keeps 64% and retains ~95% of 3-round winners >= 3%);
* screening runs slower than `screen_abort` x -O3 (1.3) are killed (status `slow`).

Then, once per program: the shortlists of all methods are **confirmed together** in one 30-round
interleaved run with an A/A control (repeated once if the control deviates by more than
`control_max_dev_pct`); the best confirmed candidate is pass-minimized (batched; relative tolerance)
and **validated** in a fresh, independent run. Picking the best of several confirmed candidates is a
winner's curse of its own, so the gate uses the validated numbers. Logs show seconds per stage
(compile, verify, screen, confirm, minimize, validate).

Environment guards: before every timing block the **quiet guard** waits while processes from OTHER
sessions use more than `quiet_max_busy` cores (up to `quiet_max_wait_s`, then measures and flags it; the
load seen is stored with each measurement). Our own parallel workers share the launcher's session and
are not counted. `isolate_sibling` also keeps the harness off timing_cpu's SMT sibling (vCPU 7 for vCPU 6);
it is off by default because it changes the measurement conditions.

**Parallel timing** (`--timing-cpus 2,4,6,8,10` on `search run`, `passkb run`, `collect run`): one worker
process per timing core runs whole programs (longest first); each core's SMT sibling stays idle and
compiles run on the remaining helper CPUs. Every comparison is still interleaved and paired on ONE core.
Cores differ in absolute speed (~5% on this machine), so never compare absolute times across cores.
Use it only for core sets that passed the multi-core A/A test:

```bash
python -m nc.cli aatest --cpus 2,4,6,8,10 --programs a,b,c,d,e --reps 30 --rounds 2
```

It measures -O3 vs a byte-identical copy (and vs the program's validated winner) on each core, first one
core at a time, then all cores at once (cores that finish early keep running as filler load), rotating
programs across cores. Pass = every parallel A/A within 1% with CI containing 1, A/A noise at most 2x
serial, and known speedups within 1% of their serial values. Results: `results/aatest_*.json`.
The final Phase 9 measurement stays serial on one core regardless.

## 9. Phases 4-9

```bash
# 4  per-pass knowledge base on programs with a confirmed gain (add-one inserts are the largest group)
python -m nc.cli passkb run --winners [--no-add]
python -m nc.cli passkb report                       # attribution CSV + pruned action set (results/passkb_actions.json)
# 5  full data collection (resumable), then the quality report and dataset version tag
python -m nc.cli collect run --all --budget 40 --methods random,evo,evo2
python -m nc.cli collect quality
python -m nc.cli corpus split                        # freeze, AFTER the corpus is final
# 6  features (cachegrind runs in parallel on helper CPUs; never during a timing job)
python -m nc.cli features extract --all --include-test
# 7  surrogate: leave-one-family-out CV (test families excluded automatically), then train
python -m nc.cli model cv --fsets static,sim,scan
python -m nc.cli model cv --fsets static,scan        # ablation: no simulated dynamic features
python -m nc.cli model train --fsets static,sim,scan
# 8  deployment loop; RL only if gate 7B passed
bin/neurocompiler prog.c --out prog --k 8 [--dynamic] [--no-rl]   # RL + SL by default
python -m nc.cli rl train
# 9  frozen test set, run once; then report and a reproduction run
python -m nc.cli evaluate run --tag final --k 8 [--nodyn-model ...] [--rl results/models/rl_policy_latest.npz]
python -m nc.cli evaluate report --tag final
python -m nc.cli evaluate repro --tag final
```

Gates (enforced in code where possible): headroom gate on validated numbers (Phase 3); `collect quality`
must be CLEAN (Phase 5); `rl train` refuses unless `model cv` passed gate 7B (surrogate ranks unseen
families better than random); `evaluate run` refuses without a frozen split and refuses a surrogate that
saw a test family.
