"""Compile a C source with an arbitrary LLVM pass pipeline.

Pipeline:  clang -O3 -Xclang -disable-llvm-passes  ->  start IR (keeps TBAA, lifetime
markers and attributes that real -O3 builds see, but runs no optimization)
           opt -passes=<pipeline>                    ->  optimized IR
           llc -O<backend>                           ->  object file
           clang                                     ->  binary

Binaries are cached by the hash of the optimized IR, so two pipelines that produce the
same IR share one binary and are benchmarked only once.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path

from .config import Config


class CompileError(RuntimeError):
    pass


CXX_EXT = {".cpp", ".cc", ".cxx", ".C"}
# `opt -print-pipeline-passes` does not round-trip everything default<O3> sets up. The O3 inliner
# parameters are restored explicitly for every explicit (edited) pipeline unless a genome sets them;
# with these, the printed -O3 pipeline reproduces default<O3> bit-for-bit on 126 of 146 corpus
# programs (checked per program in ProgramSearch; mismatches are flagged, not hidden).
EXPLICIT_O3_FLAGS = (("-inline-threshold", "250"), ("-locally-hot-callsite-threshold", "525"))


def sources(src) -> list[Path]:
    """A program is one source file or a list of them (multi-file programs are llvm-linked)."""
    return [Path(x) for x in src] if isinstance(src, (list, tuple)) else [Path(src)]


def is_cxx(src) -> bool:
    return any(p.suffix in CXX_EXT for p in sources(src))


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _run(cmd: list[str], timeout: float) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def normalize_ir(text: str) -> str:
    """Drop lines that depend on file paths so identical IR hashes identically."""
    keep = [
        ln for ln in text.splitlines()
        if not ln.startswith("; ModuleID") and not ln.startswith("source_filename")
    ]
    return "\n".join(keep) + "\n"


def count_ir_instructions(text: str) -> int:
    """Approximate instruction count: indented lines inside function bodies.

    Excludes debug and lifetime intrinsics. Good for relative comparison only.
    """
    n = 0
    in_fn = False
    for ln in text.splitlines():
        if ln.startswith("define "):
            in_fn = True
            continue
        if ln.startswith("}"):
            in_fn = False
            continue
        if not in_fn or not ln.startswith("  "):
            continue
        s = ln.strip()
        if not s or s.startswith(";"):
            continue
        if "@llvm.dbg." in s or "@llvm.lifetime." in s:
            continue
        n += 1
    return n


@dataclass
class Build:
    ok: bool
    status: str                 # ok | frontend_fail | opt_fail | backend_fail | timeout
    pipeline: str
    backend_opt: int
    ir_hash: str = ""
    bin_hash: str = ""
    bin_path: str = ""
    ir_inst_count: int = 0
    text_size: int = 0
    bin_size: int = 0
    opt_ms: float = 0.0
    backend_ms: float = 0.0
    dedup: bool = False         # binary reused because the optimized IR was identical
    error: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class Toolchain:
    def __init__(self, cfg: Config, work_dir: str | Path | None = None):
        self.cfg = cfg
        self.bin = Path(cfg.llvm_bin_dir)
        self.work = Path(work_dir or cfg.work_dir).resolve()   # absolute: programs may run in another cwd
        for sub in ("ir", "bins", "tmp"):
            (self.work / sub).mkdir(parents=True, exist_ok=True)
        self._version: str | None = None

    # ---- tools -------------------------------------------------------------
    def tool(self, name: str) -> str:
        p = self.bin / name
        if not p.exists():
            raise FileNotFoundError(f"{p} not found. Check llvm_bin_dir in config.toml")
        return str(p)

    def version(self) -> str:
        if self._version is None:
            out = _run([self.tool("opt"), "--version"], 30).stdout
            m = re.search(r"LLVM version (\S+)", out)
            self._version = m.group(1) if m else "unknown"
        return self._version

    # ---- front end ---------------------------------------------------------
    def _frontend_flags(self, extra: tuple[str, ...]) -> list[str]:
        return ["-O3", f"-march={self.cfg.march}", "-Xclang", "-disable-llvm-passes", *extra]

    def start_ir(self, src, extra_cflags: tuple[str, ...] = ()) -> Path:
        """Unoptimized IR of the whole program. Several files are compiled one by one and
        llvm-linked into one module, so -O3 (and every candidate) sees the whole program."""
        srcs = sources(src)
        flags = self._frontend_flags(tuple(extra_cflags))
        blob = b"".join(p.read_bytes() for p in srcs)
        if len(srcs) > 1:
            blob += "|".join(map(str, srcs)).encode()
        key = sha256_bytes(blob + " ".join(flags).encode() + self.version().encode())[:16]
        out = self.work / "ir" / f"{srcs[0].stem}-{key}.ll"
        if not out.exists():
            tmp = out.with_suffix(f".{uuid.uuid4().hex}.tmp")
            if len(srcs) == 1:
                r = _run([self.tool("clang"), *flags, "-w", "-S", "-emit-llvm", str(srcs[0]), "-o", str(tmp)], 120)
                if r.returncode != 0:
                    raise CompileError(r.stderr[-2000:])
            else:
                parts = []
                for i, p in enumerate(srcs):
                    bc = tmp.with_suffix(f".{i}.bc")
                    r = _run([self.tool("clang"), *flags, "-w", "-c", "-emit-llvm", str(p), "-o", str(bc)], 300)
                    if r.returncode != 0:
                        for q in parts:
                            q.unlink(missing_ok=True)
                        raise CompileError(f"{p.name}: " + r.stderr[-2000:])
                    parts.append(bc)
                r = _run([self.tool("llvm-link"), "-S", *map(str, parts), "-o", str(tmp)], 300)
                for q in parts:
                    q.unlink(missing_ok=True)
                if r.returncode != 0:
                    raise CompileError("llvm-link: " + r.stderr[-2000:])
            os.replace(tmp, out)
        return out

    # ---- build with a pass pipeline ---------------------------------------
    def build(self, src, pipeline: str, backend_opt: int = 3,
              extra_cflags: tuple[str, ...] = (), opt_flags: tuple[str, ...] = ()) -> Build:
        pipeline = pipeline.strip() or "verify"
        b = Build(ok=False, status="opt_fail", pipeline=pipeline, backend_opt=backend_opt)
        try:
            ir0 = self.start_ir(src, extra_cflags)
        except CompileError as e:
            b.status, b.error = "frontend_fail", str(e)
            return b
        except subprocess.TimeoutExpired:
            b.status, b.error = "timeout", "frontend timeout"
            return b

        llc_flags = [f[4:] for f in opt_flags if f.startswith("llc:")]
        opt_flags = tuple(f for f in opt_flags if not f.startswith("llc:"))
        if not pipeline.startswith("default<"):
            opt_flags += tuple(f"{k}={v}" for k, v in EXPLICIT_O3_FLAGS
                               if not any(f.startswith(k + "=") for f in opt_flags))
        tmp_ll = self.work / "tmp" / f"{uuid.uuid4().hex}.ll"
        t0 = time.perf_counter()
        try:
            r = _run([self.tool("opt"), *opt_flags, f"-passes={pipeline}", "-S", str(ir0), "-o", str(tmp_ll)], 300)
        except subprocess.TimeoutExpired:
            b.status, b.error = "timeout", "opt timeout"
            return b
        b.opt_ms = (time.perf_counter() - t0) * 1000
        if r.returncode != 0:
            b.error = r.stderr[-2000:]
            tmp_ll.unlink(missing_ok=True)
            return b

        text = normalize_ir(tmp_ll.read_text())
        tmp_ll.unlink(missing_ok=True)
        b.ir_hash = sha256_bytes(text.encode())
        b.ir_inst_count = count_ir_instructions(text)

        lsuf = f"-L{sha256_bytes(' '.join(llc_flags).encode())[:8]}" if llc_flags else ""
        bdir = self.work / "bins" / f"{b.ir_hash[:24]}-O{backend_opt}{lsuf}"
        meta = bdir / "meta.json"
        if meta.exists() and (bdir / "prog").exists():
            m = json.loads(meta.read_text())
            b.bin_hash, b.text_size, b.bin_size = m["bin_hash"], m["text_size"], m["bin_size"]
            b.backend_ms, b.dedup = m["backend_ms"], True
        else:
            staging = bdir.with_name(bdir.name + f".tmp-{uuid.uuid4().hex}")
            staging.mkdir(parents=True)
            (staging / "opt.ll").write_text(text)
            t1 = time.perf_counter()
            try:
                r1 = _run([self.tool("llc"), f"-O{backend_opt}", *llc_flags, "-relocation-model=pic",
                           "-filetype=obj", str(staging / "opt.ll"), "-o", str(staging / "prog.o")], 300)
                if r1.returncode != 0:
                    b.status, b.error = "backend_fail", r1.stderr[-2000:]
                    shutil.rmtree(staging, ignore_errors=True)
                    return b
                link = [self.tool("clang++"), "-lstdc++"] if is_cxx(src) else [self.tool("clang")]
                r2 = _run([link[0], str(staging / "prog.o"), "-o", str(staging / "prog"), "-lm", *link[1:]], 120)
                if r2.returncode != 0:
                    b.status, b.error = "backend_fail", r2.stderr[-2000:]
                    shutil.rmtree(staging, ignore_errors=True)
                    return b
            except subprocess.TimeoutExpired:
                b.status, b.error = "timeout", "backend timeout"
                shutil.rmtree(staging, ignore_errors=True)
                return b
            b.backend_ms = (time.perf_counter() - t1) * 1000
            b.bin_hash = sha256_file(staging / "prog")
            b.text_size = self._text_size(staging / "prog")
            b.bin_size = (staging / "prog").stat().st_size
            (staging / "meta.json").write_text(json.dumps({
                "bin_hash": b.bin_hash, "text_size": b.text_size,
                "bin_size": b.bin_size, "backend_ms": b.backend_ms}))
            try:
                os.replace(staging, bdir)
            except OSError:           # another worker won the race; reuse theirs
                shutil.rmtree(staging, ignore_errors=True)
        b.bin_path = str(bdir / "prog")
        b.ok, b.status = True, "ok"
        return b

    # ---- reference: plain clang -O<level> ---------------------------------
    def build_clang_direct(self, src, level: str = "-O3",
                           extra_cflags: tuple[str, ...] = ()) -> Build:
        srcs = sources(src)
        b = Build(ok=False, status="frontend_fail", pipeline=f"clang{level}", backend_opt=-1)
        key = sha256_bytes(b"".join(p.read_bytes() for p in srcs) + level.encode() + self.cfg.march.encode()
                           + " ".join(extra_cflags).encode() + self.version().encode())[:16]
        bdir = self.work / "bins" / f"clang{level}-{srcs[0].stem}-{key}"
        out = bdir / "prog"
        t0 = time.perf_counter()
        if not out.exists():
            bdir.mkdir(parents=True, exist_ok=True)
            cc = self.tool("clang++") if is_cxx(src) else self.tool("clang")
            r = _run([cc, level, f"-march={self.cfg.march}", "-w", *extra_cflags,
                      *map(str, srcs), "-o", str(out), "-lm"], 300)
            if r.returncode != 0:
                b.error = r.stderr[-2000:]
                return b
        b.backend_ms = (time.perf_counter() - t0) * 1000
        b.bin_hash, b.bin_size, b.text_size = sha256_file(out), out.stat().st_size, self._text_size(out)
        b.bin_path, b.ok, b.status = str(out), True, "ok"
        return b

    # ---- helpers -----------------------------------------------------------
    def _text_size(self, binp: Path) -> int:
        try:
            r = _run([self.tool("llvm-size"), str(binp)], 30)
            return int(r.stdout.splitlines()[1].split()[0])
        except Exception:
            return 0

    def pipeline_string(self, level: str = "O3") -> str:
        """Expanded pass list of a standard level (input for per-pass experiments)."""
        tmp = self.work / "tmp" / "empty.ll"
        tmp.write_text("define void @f() {\n  ret void\n}\n")
        r = _run([self.tool("opt"), f"-passes=default<{level}>", "-print-pipeline-passes",
                  "-disable-output", str(tmp)], 60)
        if r.returncode != 0:
            raise CompileError(r.stderr)
        return r.stdout.strip()
