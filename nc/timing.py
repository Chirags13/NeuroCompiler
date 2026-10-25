"""Pinned, interleaved benchmark runner with bootstrap statistics.

Design choices (each addresses a noise source):
  * Children are pinned to one vCPU; the harness itself is kept off that vCPU.
  * Candidates are interleaved in randomized order each round, so frequency/thermal
    drift hits all of them equally.
  * Comparisons use PAIRED per-round ratios, which cancel drift further.
  * Every run's stdout is hashed, so wrong output / nondeterminism is caught.
  * Wall time is measured from just before spawn to wait4() return; CPU time comes
    from the kernel's rusage.
"""
from __future__ import annotations

import ctypes
import hashlib
import math
import os
import random
import subprocess
import tempfile
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np


@dataclass
class Sample:
    status: str          # ok | crash | timeout | nonzero_exit
    wall_ms: float
    cpu_ms: float
    maxrss_kb: int
    out_hash: str


def _hash_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _tmp_out() -> str:
    d = "/dev/shm" if os.path.isdir("/dev/shm") else None
    fd, path = tempfile.mkstemp(prefix="nc_out_", dir=d)
    os.close(fd)
    return path


def smt_siblings(cpu: int) -> set[int]:
    """Logical CPUs sharing a physical core with `cpu` (including itself)."""
    try:
        txt = Path(f"/sys/devices/system/cpu/cpu{cpu}/topology/thread_siblings_list").read_text().strip()
    except OSError:
        return {cpu}
    out: set[int] = set()
    for part in txt.split(","):
        a, _, b = part.partition("-")
        out.update(range(int(a), int(b or a) + 1))
    return out


def isolate_parent(cpu: int | None) -> set[int]:
    """Keep the harness off the benchmark vCPU (and, if configured, off its SMT sibling).
    Returns the parent's affinity set."""
    allowed = set(os.sched_getaffinity(0))
    if cpu is None:
        return allowed
    if cpu not in allowed:
        raise ValueError(f"timing_cpu={cpu} not in allowed CPUs {sorted(allowed)}; edit config.toml")
    avoid = smt_siblings(cpu) if _SETTINGS["isolate_sibling"] else {cpu}
    aff = (allowed - avoid) or (allowed - {cpu})
    if aff:
        os.sched_setaffinity(0, aff)
        return aff
    return allowed


def helper_cpus(cpu: int | None) -> list[int]:
    """CPUs that untimed work (compiles, verification runs) may use: never the timing core."""
    allowed = set(os.sched_getaffinity(0))
    if cpu is None:
        return sorted(allowed)
    return sorted(allowed - smt_siblings(cpu)) or sorted(allowed - {cpu}) or sorted(allowed)


# ------------------------------------------------------------ environment control
_SETTINGS = {"no_aslr": False, "settle_s": 0.0, "isolate_sibling": False,
             "quiet_max_busy": 0.0, "quiet_max_wait_s": 0.0, "layout_copies": 1}
ADDR_NO_RANDOMIZE = 0x0040000
_libc = ctypes.CDLL(None, use_errno=True)


def configure(no_aslr: bool = False, settle_s: float = 0.0, isolate_sibling: bool = False,
              quiet_max_busy: float = 0.0, quiet_max_wait_s: float = 0.0, layout_copies: int = 1) -> None:
    _SETTINGS["no_aslr"] = no_aslr
    _SETTINGS["settle_s"] = settle_s
    _SETTINGS["isolate_sibling"] = isolate_sibling
    _SETTINGS["quiet_max_busy"] = quiet_max_busy
    _SETTINGS["quiet_max_wait_s"] = quiet_max_wait_s
    _SETTINGS["layout_copies"] = max(1, int(layout_copies))


# ------------------------------------------------------------ quiet guard
def _cpu_ticks() -> tuple[int, int]:
    with open("/proc/stat") as f:
        v = [int(x) for x in f.readline().split()[1:]]
    idle = v[3] + (v[4] if len(v) > 4 else 0)
    return sum(v[:8]), idle


def busy_cores(window_s: float = 1.0) -> float:
    """CPU cores' worth of load on the whole (Linux side of the) machine over a short window.
    Called while the harness is idle, so this is load from OTHER processes. Windows-side load
    is invisible to WSL2."""
    t0, i0 = _cpu_ticks()
    time.sleep(window_s)
    t1, i1 = _cpu_ticks()
    dt = max(1, t1 - t0)
    return (1 - (i1 - i0) / dt) * (os.cpu_count() or 1)


_CLK = os.sysconf("SC_CLK_TCK")


def _foreign_ticks(own_sid: int) -> dict[int, int]:
    """utime+stime ticks of every process NOT in our session (and not a kernel thread)."""
    out = {}
    for d in os.listdir("/proc"):
        if not d.isdigit():
            continue
        try:
            with open(f"/proc/{d}/stat") as f:
                s = f.read()
        except OSError:
            continue
        rest = s[s.rfind(")") + 2:].split()      # fields after "(comm)": state is rest[0]
        sid = int(rest[3])
        if sid == own_sid or sid == 0:
            continue
        # utime + stime + cutime + cstime: short-lived children (e.g. benchmark runs) are
        # credited to their parent's c* counters when reaped
        out[int(d)] = sum(int(x) for x in rest[11:15])
    return out


def busy_cores_foreign(window_s: float = 1.0) -> float:
    """Cores' worth of load from processes outside our session over a short window. Parallel
    timing workers share the launcher's session, so they never block each other; other users'
    jobs (and interactive shells) do. Windows-side load is invisible to WSL2."""
    sid = os.getsid(0)
    a = _foreign_ticks(sid)
    time.sleep(window_s)
    b = _foreign_ticks(sid)
    # processes born inside the window count from zero
    return sum(t - a.get(p, 0) for p, t in b.items()) / _CLK / window_s


LAST_BUSY = {"cores": float("nan"), "waited_s": 0.0}


def wait_quiet(log=print) -> float:
    """Block until load from OTHER sessions drops below quiet_max_busy cores (or the wait limit
    passes). Returns the load seen just before measuring. Disabled when quiet_max_busy <= 0."""
    lim, max_wait = _SETTINGS["quiet_max_busy"], _SETTINGS["quiet_max_wait_s"]
    if lim <= 0:
        return float("nan")
    busy_cores = busy_cores_foreign
    t0 = time.time()
    b = busy_cores()
    warned = False
    while b > lim and time.time() - t0 < max_wait:
        if not warned:
            log(f"  [quiet-guard] {b:.2f} cores busy (limit {lim}); waiting up to {max_wait:.0f}s before timing")
            warned = True
        time.sleep(10)
        b = busy_cores()
    LAST_BUSY.update(cores=b, waited_s=time.time() - t0)
    if b > lim:
        log(f"  [quiet-guard] still {b:.2f} cores busy after {max_wait:.0f}s; measuring anyway (flagged)")
    return b


def _personality(value: int = 0xFFFFFFFF) -> int:
    return int(_libc.personality(ctypes.c_ulong(value)))


def aslr_disabled_for_children() -> bool:
    """True if processes we spawn right now would run without address randomization."""
    try:
        return bool(_personality() & ADDR_NO_RANDOMIZE)
    except Exception:
        return False


@contextmanager
def measurement_env(cpu: int | None):
    """Keep the harness off the benchmark vCPU and (optionally) disable ASLR for children.

    Layout randomization is a known source of run-to-run and path-to-path bias, so children
    inherit ADDR_NO_RANDOMIZE for the duration of the measurement.
    """
    original = set(os.sched_getaffinity(0))
    parent_aff = isolate_parent(cpu)
    prev = None
    if _SETTINGS["no_aslr"]:
        try:
            prev = _personality()
            _personality(prev | ADDR_NO_RANDOMIZE)
        except Exception:
            prev = None
    try:
        yield parent_aff
    finally:
        os.sched_setaffinity(0, original)
        if prev is not None:
            try:
                _personality(prev)
            except Exception:
                pass


def settle(binary, args, cpu, timeout_s, parent_aff, seconds: float, stdin_path=None, cwd=None) -> None:
    """Run the binary repeatedly for `seconds` so frequency/scheduling reach steady state."""
    if seconds <= 0:
        return
    out = _tmp_out()
    try:
        end = time.perf_counter() + seconds
        while time.perf_counter() < end:
            run_once(binary, args, cpu, timeout_s, out, parent_aff, stdin_path, cwd=cwd)
    finally:
        try:
            os.unlink(out)
        except OSError:
            pass


def run_once(binary: str | Path, args: list[str], cpu: int | None, timeout_s: float,
             out_file: str, parent_aff: set[int] | None = None,
             stdin_path: str | None = None, argv0: str | None = None,
             merge_stderr: bool = False, cwd: str | None = None) -> Sample:
    if argv0 == "":
        # Python >= 3.14 refuses an empty argv[0]; let bash do the exec instead.
        # Only used for (untimed) verification runs.
        cmd = ["/bin/bash", "-c", 'exec -a "" "$0" "$@"', str(Path(binary).resolve()), *map(str, args)]
        exe = None
    else:
        exe = str(Path(binary).resolve()) if cwd else str(binary)
        cmd = [argv0 if argv0 is not None else exe, *map(str, args)]
    stdin = open(stdin_path, "rb") if stdin_path else subprocess.DEVNULL
    prev = set(os.sched_getaffinity(0))
    timed_out = {"v": False}
    try:
        with open(out_file, "wb") as fout:
            os.sched_setaffinity(0, {cpu} if cpu is not None else prev)
            t0 = time.perf_counter_ns()
            p = subprocess.Popen(cmd, executable=exe, stdin=stdin, stdout=fout, cwd=cwd,
                                 stderr=subprocess.STDOUT if merge_stderr else subprocess.DEVNULL)
            os.sched_setaffinity(0, parent_aff or prev)

            def _kill():
                # os.kill, not p.kill(): Popen.kill() polls first and may REAP a child that is just
                # exiting, after which our wait4 fails with ECHILD. Until we wait4 the child stays a
                # zombie at worst, so its pid cannot be reused and the signal is safe.
                timed_out["v"] = True
                try:
                    os.kill(p.pid, 9)
                except ProcessLookupError:
                    pass

            timer = threading.Timer(timeout_s, _kill)
            timer.start()
            try:
                _, status, ru = os.wait4(p.pid, 0)
            except ChildProcessError:          # reaped elsewhere (should not happen any more): count as killed
                status, ru = None, None
                timed_out["v"] = True
            t1 = time.perf_counter_ns()
            timer.cancel()
    finally:
        os.sched_setaffinity(0, prev)
        if stdin_path:
            stdin.close()
    p.returncode = os.waitstatus_to_exitcode(status) if status is not None else (p.returncode or -9)
    wall_ms = (t1 - t0) / 1e6
    cpu_ms = (ru.ru_utime + ru.ru_stime) * 1000 if ru is not None else float("nan")
    if timed_out["v"]:
        st = "timeout"
    elif p.returncode < 0:
        st = "crash"
    elif p.returncode != 0:
        st = "nonzero_exit"
    else:
        st = "ok"
    return Sample(st, wall_ms, cpu_ms, int(ru.ru_maxrss) if ru is not None else 0, _hash_file(out_file))


def reference_hash(binary: str | Path, args: list[str], cpu: int | None, timeout_s: float) -> str:
    out = _tmp_out()
    try:
        s = run_once(binary, args, cpu, timeout_s, out)
    finally:
        os.unlink(out)
    if s.status != "ok":
        raise RuntimeError(f"reference binary failed: {s.status}")
    return s.out_hash



@dataclass
class RunSpec:
    """How to run a program: arguments, optional argv[0] override, stderr capture, stdin file."""
    args: list[str] = field(default_factory=list)
    argv0: str | None = None
    merge_stderr: bool = False
    stdin_path: str | None = None
    cwd: str | None = None              # working directory (programs that open input files)

    @staticmethod
    def from_dict(d: dict | None) -> "RunSpec":
        return RunSpec(**(d or {}))


EMPTY_OUTPUT_HASH = hashlib.sha256(b"").hexdigest()


def run_spec(binary: str | Path, spec: RunSpec, cpu: int | None, timeout_s: float) -> Sample:
    """One pinned run described by a RunSpec; returns the Sample (includes output hash)."""
    out = _tmp_out()
    try:
        with measurement_env(cpu) as parent_aff:
            return run_once(binary, spec.args, cpu, timeout_s, out, parent_aff,
                            spec.stdin_path, spec.argv0, spec.merge_stderr, spec.cwd)
    finally:
        try:
            os.unlink(out)
        except OSError:
            pass


@dataclass
class Series:
    name: str
    wall_ms: list[float] = field(default_factory=list)   # NaN for failed rounds
    cpu_ms: list[float] = field(default_factory=list)
    status: str = "ok"
    out_hash: str = ""
    busy_cores: float = float("nan")    # other load seen by the quiet guard before this block


def measure_interleaved(binaries: dict[str, str | Path], args: list[str], reps: int, warmup: int,
                        cpu: int | None, timeout_s: float, seed: int = 0,
                        expected_hash: str | None = None,
                        stdin_path: str | None = None, cwd: str | None = None,
                        timeouts: dict[str, float] | None = None, settle_s: float | None = None,
                        log=print) -> dict[str, Series]:
    """Randomized interleaved rounds. `timeouts` optionally gives a per-binary kill limit
    (screening uses it to stop clearly slow candidates early; they end with status 'timeout')."""
    names = list(binaries)
    tmo = {n: (timeouts or {}).get(n, timeout_s) for n in names}
    busy = wait_quiet(log)
    rng = random.Random(seed)
    out = _tmp_out()
    series = {n: Series(n) for n in names}

    def check(n: str, s: Sample) -> bool:
        ser = series[n]
        if s.status != "ok":
            ser.status = ser.status if ser.status != "ok" else s.status
            return False
        if expected_hash is not None and s.out_hash != expected_hash:
            ser.status = "wrong_output" if ser.status == "ok" else ser.status
            return False
        if ser.out_hash and s.out_hash != ser.out_hash:
            ser.status = "nondeterministic" if ser.status == "ok" else ser.status
            return False
        ser.out_hash = ser.out_hash or s.out_hash
        return True

    for ser in series.values():
        ser.busy_cores = busy
    st = _SETTINGS["settle_s"] if settle_s is None else settle_s
    # Layout randomization (opt-in): identical bytes loaded from different files land in different
    # physical pages, which alone can shift some programs by several percent. With K > 1 copies per
    # binary (same-length paths in one directory), round r runs copy r % K, so every comparison
    # averages over K placements instead of depending on one.
    K = _SETTINGS["layout_copies"]
    lay_dir = None
    copies = {n: [str(binaries[n])] for n in names}
    if K > 1:
        import shutil
        lay_dir = tempfile.mkdtemp(prefix="nc_layout_", dir=str(Path(binaries[names[0]]).resolve().parent.parent))
        for i, n in enumerate(names):
            copies[n] = []
            for k in range(K):
                dst = os.path.join(lay_dir, f"b{i:03d}c{k:02d}")
                shutil.copy2(binaries[n], dst)
                copies[n].append(dst)
    try:
        with measurement_env(cpu) as parent_aff:
            settle(copies[names[0]][0], args, cpu, timeout_s, parent_aff, st, stdin_path, cwd)
            for w in range(max(warmup, K if K > 1 else 0)):
                for n in rng.sample(names, len(names)):
                    if series[n].status == "ok":
                        check(n, run_once(copies[n][w % len(copies[n])], args, cpu, tmo[n], out, parent_aff, stdin_path, cwd=cwd))
            for r in range(reps):
                for n in rng.sample(names, len(names)):
                    ser = series[n]
                    if ser.status != "ok":
                        ser.wall_ms.append(math.nan)
                        ser.cpu_ms.append(math.nan)
                        continue
                    s = run_once(copies[n][r % len(copies[n])], args, cpu, tmo[n], out, parent_aff, stdin_path, cwd=cwd)
                    if check(n, s):
                        ser.wall_ms.append(s.wall_ms)
                        ser.cpu_ms.append(s.cpu_ms)
                    else:
                        ser.wall_ms.append(math.nan)
                        ser.cpu_ms.append(math.nan)
    finally:
        try:
            os.unlink(out)
        except OSError:
            pass
        if lay_dir:
            import shutil
            shutil.rmtree(lay_dir, ignore_errors=True)
    return series


def measure_sequential(binary: str | Path, args: list[str], runs: int, warmup: int,
                       cpu: int | None, timeout_s: float, stdin_path: str | None = None,
                       cwd: str | None = None) -> Series:
    """Back-to-back runs of ONE binary, in order (used to inspect noise and drift)."""
    out = _tmp_out()
    ser = Series(Path(binary).name)
    try:
        with measurement_env(cpu) as parent_aff:
            settle(binary, args, cpu, timeout_s, parent_aff, _SETTINGS["settle_s"], stdin_path, cwd)
            for i in range(warmup + runs):
                s = run_once(binary, args, cpu, timeout_s, out, parent_aff, stdin_path, cwd=cwd)
                if s.status != "ok":
                    ser.status = s.status
                    break
                ser.out_hash = ser.out_hash or s.out_hash
                if i >= warmup:
                    ser.wall_ms.append(s.wall_ms)
                    ser.cpu_ms.append(s.cpu_ms)
    finally:
        try:
            os.unlink(out)
        except OSError:
            pass
    return ser


# ---------------------------------------------------------------- statistics
def _clean(values) -> np.ndarray:
    x = np.asarray(values, dtype=float)
    return x[~np.isnan(x)]


def _boot_ci(x: np.ndarray, n_boot: int = 4000, alpha: float = 0.05, seed: int = 0) -> tuple[float, float]:
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(x), (n_boot, len(x)))
    boots = np.median(x[idx], axis=1)
    lo, hi = np.quantile(boots, [alpha / 2, 1 - alpha / 2])
    return float(lo), float(hi)


def summarize(values) -> dict:
    x = _clean(values)
    if len(x) < 3:
        return {"n": int(len(x))}
    med = float(np.median(x))
    lo, hi = _boot_ci(x)
    q25, q75 = np.percentile(x, [25, 75])
    return {
        "n": int(len(x)), "median_ms": med, "ci_lo_ms": lo, "ci_hi_ms": hi,
        "ci_halfwidth_pct": (hi - lo) / 2 / med * 100,
        "iqr_pct": float((q75 - q25) / med * 100),
        "min_ms": float(x.min()), "max_ms": float(x.max()),
    }


def drift_pct(values) -> float:
    """Median of the second half vs the first half of an ordered series (percent)."""
    x = _clean(values)
    if len(x) < 6:
        return float("nan")
    h = len(x) // 2
    m1, m2 = np.median(x[:h]), np.median(x[h:])
    return float((m2 - m1) / m1 * 100)


def paired_speedup(base_ms, new_ms, n_boot: int = 4000, seed: int = 0) -> dict:
    """Speedup of `new` over `base` (>1 means new is faster), from per-round paired ratios."""
    a, b = np.asarray(base_ms, float), np.asarray(new_ms, float)
    m = ~(np.isnan(a) | np.isnan(b))
    a, b = a[m], b[m]
    if len(a) < 3:
        return {"n": int(len(a))}
    r = np.log(a / b)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(r), (n_boot, len(r)))
    boots = np.median(r[idx], axis=1)
    lo, hi = np.quantile(boots, [0.025, 0.975])
    return {
        "n": int(len(r)), "speedup": float(np.exp(np.median(r))),
        "ci_lo": float(np.exp(lo)), "ci_hi": float(np.exp(hi)),
        "significant": bool(lo > 0 or hi < 0),
    }
