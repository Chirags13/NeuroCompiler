# Running NeuroCompiler (tune mode, RL + SL)

NeuroCompiler compiles a C/C++ program with an LLVM pass pipeline chosen for **that program** and returns a
binary that is at least as fast as `clang -O3` on this machine, often faster:

1. The **RL agent** (PPO) proposes pipelines for the program.
2. The **supervised model** (LightGBM) ranks them together with a library of ~900 known-good pipelines.
3. The **top 8** are compiled, their output is checked against the `-O0` build, and they are timed
   interleaved against `-O3` on a pinned CPU core.
4. The fastest ships only if a fresh confirmation run (20 rounds, with an A/A control) shows it beats `-O3`
   by more than 1%. Otherwise the `-O3` binary ships.

Measured result on 33 held-out programs: +7.9% geomean vs `-O3` (+4.7% excluding the largest gain), no
program slower. Details and limits: [results/FINAL_REPORT.md](results/FINAL_REPORT.md).

---

## 1. Requirements

| | |
|---|---|
| OS | Linux x86-64, or WSL2 on Windows. Keep the project on the Linux filesystem (`~/...`), **not** under `/mnt/c` |
| LLVM | **18.1.8 exactly** (`clang-18`, `opt`, `llc`, `llvm-link`, `llvm-size`) in `/usr/lib/llvm-18/bin` |
| Python | 3.11 or newer (tested on 3.14) |
| Git LFS | to download `results/dataset.sqlite` (340 MB) |
| valgrind | optional, only for `--dynamic` |

**Why exactly 18.1.8:** pipeline edits refer to positions in LLVM's printed `-O3` pass list; another LLVM
version can shift them. Ubuntu 24.04's own `llvm-18` package is 18.1.3, so install 18.1.8 from apt.llvm.org:

```bash
wget https://apt.llvm.org/llvm.sh && sudo bash llvm.sh 18
```

Check: `/usr/lib/llvm-18/bin/opt --version` must print `LLVM version 18.1.8`.

## 2. Get the code and data

```bash
sudo apt install -y git-lfs && git lfs install
git clone https://github.com/Chirags13/NeuroCompiler.git ~/neurocompiler
cd ~/neurocompiler
git lfs pull
```

`results/dataset.sqlite` must be about 340 MB afterwards. If it is a tiny text file, `git lfs pull` did not run.

## 3. Install

```bash
sudo apt install -y build-essential valgrind python3-venv python3-pip
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

(`setup_wsl.sh` does the apt and venv steps too, but installs Ubuntu's `llvm-18`; check the version afterwards.)

## 4. Configure for this machine (once)

Timing results are only meaningful after this step.

1. Edit `config.toml`:
   - `machine_id`: a new name for this machine (results from different machines must never be mixed)
   - `llvm_bin_dir`: `/usr/lib/llvm-18/bin` unless installed elsewhere
2. Find the quietest CPU core and set it as `timing_cpu` in `config.toml` (avoid core 0):
   ```bash
   .venv/bin/python -m nc.cli cpusweep bench/matmul.c --args 800
   ```
3. Check that the machine is quiet enough to measure 1-2% differences. It must print `PASS`:
   ```bash
   .venv/bin/python -m nc.cli selftest bench/matmul.c --args 800
   ```
   If it fails: close heavy programs, plug in the laptop, set Windows power mode to *Best performance*,
   and run it again.

## 5. Use it

```bash
bin/neurocompiler myprog.c --out myprog
```

The command works from any directory; paths are resolved relative to where you run it.

| Option | Meaning |
|---|---|
| `--out PATH` | where to write the optimized binary (required) |
| `--args "..."` | command-line arguments the program needs for a representative run |
| `--stdin FILE` | file fed to the program's standard input |
| `--cwd DIR` | working directory for the run (programs that open input files) |
| `--cflags "..."` | compiler flags, e.g. `"-I include -DSIZE=4000"` |
| `--k 8` | number of candidate pipelines that are timed (default 8) |
| `--reps 10` | timing rounds in the selection run (default 10) |
| `--dynamic` | also compute the simulated cache/branch features the model was trained with (needs valgrind; adds ~1-3 min) |
| `--no-rl` | SL only: the supervised model ranks the library, no RL proposals |

Several source files can be given at once (`bin/neurocompiler a.c b.c c.c --out prog`); they are linked into
one module. C++ files (`.cpp`, `.cc`) work too.

**Requirements on the program:** it must finish normally (exit code 0), print the same output on every run
(the output is the correctness check against `-O0`), and ideally run for at least ~0.35 s at `-O3`.
Shorter runs are too noisy to measure 1-2% differences.

### Example

```bash
bin/neurocompiler bench/matmul.c --args 800 --out /tmp/matmul_nc --dynamic
```

Output, last lines (real run on the development machine, 2026-10-25):

```
== neurocompiler (RL + SL) ==
candidates: 24 RL proposals + 913 library pipelines, ranked by the supervised model; 0 RL proposals in its top 20; 8 timed
top of the ranking: #1 library (pred 1.27x), #2 library (pred 1.27x), #3 library (pred 1.26x), ...
shipped: pipeline from the library, selection 1.663x vs -O3, confirmed 1.662x [1.658,1.671]
   edit: {"name": "-force-vector-width", "op": "knob", "value": 4}
   edit: {"name": "-unroll-max-count", "op": "knob", "value": 2}
   ... (13 edits in total)
binary: /tmp/matmul_nc   total 99.7 s
```

Here the shipped pipeline came from the library. RL proposals take part in the ranking, and on some programs
one wins (on the held-out test set: 1 of 33 programs, `fibo`, 1.231x).

- `shipped:` says whether the binary uses a changed pipeline (and whether it came from the RL agent or the
  library) or `-O3`; `confirmed` is the speedup measured in the fresh confirmation run, with its 95% CI.
- A JSON report is written next to the binary (`/tmp/matmul_nc.json`): the chosen pipeline, all timings
  and the ranking.

**Time per program:** ~80 compiles plus a few minutes of timing; longer for programs that run longer.

## 6. Tips and troubleshooting

- **Keep the machine idle while it times.** Before each timing block a quiet guard waits (up to 30 min) while
  other processes use more than 0.6 CPU cores; it prints `[quiet-guard] ... waiting`. Settings:
  `quiet_max_busy`, `quiet_max_wait_s` in `config.toml`.
- **`opt` errors about unknown passes or options:** wrong LLVM version, see section 1.
- **`-O0 reference run failed`:** the program crashed or returned a non-zero exit code with the given
  arguments/input. Fix `--args`, `--stdin` or `--cwd`.
- **Speedups on another CPU:** the models were trained with measurements from an AMD Ryzen 9 270 (Zen 4).
  On other CPUs their suggestions may fit less well, but timing always happens on your machine, so a
  changed pipeline only ships if it beats `-O3` there.
- **Correctness:** candidates must reproduce the `-O0` output for the given input. That is evidence, not
  proof; test the result on your other inputs too.

## 7. What is in the repo

| Path | Content |
|---|---|
| `bin/neurocompiler` | the command |
| `nc/` | the implementation (`deploy.py` = this mode, `rl.py` = RL agent, `model.py` = supervised model) |
| `config.toml` | machine settings and thresholds |
| `results/models/surrogate_latest.json` + `surrogate_gbr_20261024-171249.txt` | the supervised model |
| `results/models/rl_policy_latest.npz` + `.json` | the RL agent |
| `results/passkb_actions.json` | knowledge-base edits used in the candidate library |
| `results/dataset.sqlite` | measurement database; needed at runtime (library, RL feature scaling) |
| `work/*.json` | cached edit menus for LLVM 18.1.8 |
| `results/FINAL_REPORT.md` and other `results/` files | evaluation results and reports |
| `scripts/` | research scripts (searches, evaluations, reports) |

Re-running the research pipeline (corpus scan, searches, training, evaluation) additionally needs the
benchmark sources (`python -m nc.cli corpus fetch`), many hours of machine time, and the commands in
`README.md` sections 7-9.
