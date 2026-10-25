"""Environment report: what is (and is not) controllable on this machine."""
from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess
from pathlib import Path

from .config import Config
from .toolchain import Toolchain


def _read(path: str, default: str = "") -> str:
    try:
        return Path(path).read_text().strip()
    except OSError:
        return default


def _first_line(cmd: list[str]) -> str:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        return (r.stdout or r.stderr).strip().splitlines()[0]
    except Exception:
        return "unavailable"


def collect_env(cfg: Config, tc: Toolchain) -> dict:
    proc_version = _read("/proc/version")
    cpuinfo = _read("/proc/cpuinfo")
    model = re.search(r"model name\s*:\s*(.+)", cpuinfo)
    mhz = re.findall(r"cpu MHz\s*:\s*([\d.]+)", cpuinfo)
    mem = re.search(r"MemTotal:\s*(\d+) kB", _read("/proc/meminfo"))
    allowed = sorted(os.sched_getaffinity(0))
    env = {
        "machine_id": cfg.machine_id,
        "kernel": platform.release(),
        "is_wsl": "microsoft" in proc_version.lower(),
        "is_wsl2": "wsl2" in platform.release().lower(),
        "cpu_model": model.group(1) if model else "unknown",
        "logical_cpus": os.cpu_count(),
        "allowed_cpus": allowed,
        "timing_cpu": cfg.timing_cpu,
        "cpu_mhz_now": [round(float(x)) for x in mhz[:4]],
        "governor_controllable": os.path.exists("/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor"),
        "clocksource": _read("/sys/devices/system/clocksource/clocksource0/current_clocksource", "unknown"),
        "mem_gb": round(int(mem.group(1)) / 1024 / 1024, 1) if mem else None,
        "loadavg_1m": round(os.getloadavg()[0], 2),
        "perf_available": shutil.which("perf") is not None,
        "valgrind_available": shutil.which("valgrind") is not None,
        "python": platform.python_version(),
        "cwd": str(Path.cwd()),
    }
    try:
        env["clang"] = _first_line([tc.tool("clang"), "--version"])
        env["llvm_version"] = tc.version()
    except FileNotFoundError as e:
        env["clang"], env["llvm_version"] = str(e), "missing"
    return env


def warnings_for(env: dict) -> list[str]:
    w = []
    if not env["is_wsl"]:
        w.append("Not running under WSL (fine, just noting).")
    if env["cwd"].startswith("/mnt/"):
        w.append("Repo is on a Windows drive (/mnt/...). Move it to the Linux filesystem (~/neurocompiler): slower I/O and extra noise.")
    if env["loadavg_1m"] > 0.5:
        w.append(f"1-min load average is {env['loadavg_1m']}. Close other work and re-run for clean timing.")
    if not env["governor_controllable"]:
        w.append("CPU frequency governor is not controllable here (expected in WSL2). Use Windows 'Best performance' power mode, stay plugged in, and rely on interleaved runs.")
    if not env["perf_available"]:
        w.append("`perf` not found. Hardware counters are generally unavailable in WSL2; use valgrind/cachegrind for simulated dynamic features instead.")
    if env["timing_cpu"] not in env["allowed_cpus"]:
        w.append(f"timing_cpu={env['timing_cpu']} is not an available CPU {env['allowed_cpus']}. Edit config.toml.")
    if len(env["allowed_cpus"]) < 4:
        w.append("Fewer than 4 CPUs visible: raise `processors` in C:\\Users\\<you>\\.wslconfig.")
    if env["llvm_version"] == "missing":
        w.append("LLVM tools not found. Run setup_wsl.sh or fix llvm_bin_dir in config.toml.")
    return w


def format_env(env: dict) -> str:
    lines = [f"  {k:22s} {v}" for k, v in env.items()]
    warn = warnings_for(env)
    if warn:
        lines.append("")
        lines += [f"  [!] {w}" for w in warn]
    return "\n".join(lines)
