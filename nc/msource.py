"""LLVM test-suite MultiSource adapter: a tiny interpreter for the suite's CMakeLists.txt.

Only the subset the benchmarks use is understood: set / list(APPEND) / if-elseif-else-endif with
SMALL_PROBLEM_SIZE / LARGE_PROBLEM_SIZE and a few platform tests, llvm_multisource(name [files]),
llvm_test_data(name [SOURCE_DIR d] files), ${VAR} expansion. Anything else that changes the
build (custom commands that generate inputs, unknown libraries) makes the program unsupported,
which the scan records as a rejection instead of guessing.

Each program yields up to three input-size variants (SMALL, default, LARGE problem size), ordered
small -> large, so the scan can pick the first one whose -O3 runtime reaches the floor.
"""
from __future__ import annotations

import re
import shlex
from dataclasses import dataclass, field
from pathlib import Path

SRC_EXT = (".c", ".cpp", ".cc", ".cxx")
OK_LIBS = {"-lm", "-lstdc++"}
PLATFORM = {"ARCH": "x86_64", "TARGET_OS": "Linux", "ENDIAN": "little", "CMAKE_SYSTEM_NAME": "Linux",
            "TEST_SUITE_BENCHMARKING_ONLY": "ON"}


@dataclass
class MSVariant:
    size: str                       # SMALL | DEFAULT | LARGE
    sources: list[str]
    cflags: list[str]
    args: list[str]
    stdin: str | None
    data: list[list[str]]           # [path relative to the run dir, absolute source path] of input files
    ldflags: list[str] = field(default_factory=list)


@dataclass
class MSProgram:
    name: str
    dir: Path
    variants: list[MSVariant]
    unsupported: str = ""           # non-empty => reason it cannot be built faithfully


def _tokens(text: str) -> list[tuple[str, list[str]]]:
    """CMake commands as (name, args). Strips comments; keeps quoted args intact."""
    text = re.sub(r"(?m)#.*$", "", text)
    out = []
    i = 0
    pat = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)\s*\(")
    while True:
        m = pat.search(text, i)
        if not m:
            break
        depth, j = 1, m.end()
        while j < len(text) and depth:
            if text[j] == "(":
                depth += 1
            elif text[j] == ")":
                depth -= 1
            j += 1
        body = text[m.end():j - 1]
        try:
            args = shlex.split(body.replace("\n", " "), posix=True)
        except ValueError:
            args = body.split()
        out.append((m.group(1).lower(), args))
        i = j
    return out


def _expand(s: str, env: dict[str, list[str]]) -> str:
    for _ in range(5):
        n = re.sub(r"\$\{([A-Za-z0-9_]+)\}", lambda m: " ".join(env.get(m.group(1), [])), s)
        if n == s:
            break
        s = n
    return s


def _cond(args: list[str], env: dict[str, list[str]]) -> bool:
    """Evaluate the handful of conditions the suite uses. Unknown => False."""
    a = [x for x in args]
    neg = False
    if a and a[0] == "NOT":
        neg, a = True, a[1:]
    val = False
    if len(a) == 1:
        v = env.get(a[0], [a[0]])
        val = bool(v) and v[0].upper() not in ("", "0", "OFF", "FALSE", "NO", "N", "IGNORE", "NOTFOUND")
        if a[0] not in env and a[0] not in PLATFORM:
            val = False
    elif len(a) == 3 and a[1] in ("STREQUAL", "MATCHES"):
        lhs = " ".join(env.get(a[0], [a[0]]))
        val = (lhs == a[2]) if a[1] == "STREQUAL" else bool(re.search(a[2], lhs))
    elif "AND" in a or "OR" in a:
        return False
    return (not val) if neg else val


def _interpret(cmds, d: Path, size: str):
    env: dict[str, list[str]] = {k: [v] for k, v in PLATFORM.items()}
    env["CMAKE_CURRENT_SOURCE_DIR"] = [str(d)]
    env["CMAKE_CURRENT_BINARY_DIR"] = [str(d)]
    if size == "SMALL":
        env["SMALL_PROBLEM_SIZE"] = ["ON"]
    if size == "LARGE":
        env["LARGE_PROBLEM_SIZE"] = ["ON"]
    stack: list[list[bool]] = []           # each frame: [this branch active, any branch taken]
    progs, data, unsupported = [], [], ""

    def active() -> bool:
        return all(f[0] for f in stack)

    for name, raw in cmds:
        if name == "if":
            c = active() and _cond([_expand(x, env) for x in raw], env)
            stack.append([c, c])
            continue
        if name == "elseif":
            f = stack[-1]
            outer = all(x[0] for x in stack[:-1])
            c = outer and not f[1] and _cond([_expand(x, env) for x in raw], env)
            f[0] = c
            f[1] = f[1] or c
            continue
        if name == "else":
            f = stack[-1]
            f[0] = not f[1]
            f[1] = True
            continue
        if name == "endif":
            stack.pop()
            continue
        if not active():
            continue
        args = [y for x in raw for y in (_expand(x, env).split() if "${" in x else [x])]
        if name == "set" and args:
            env[args[0]] = args[1:]
        elif name == "list" and len(args) >= 2 and args[0] == "APPEND":
            env.setdefault(args[1], []).extend(args[2:])
        elif name == "llvm_multisource" and args:
            progs.append((args[0], args[1:]))
        elif name == "llvm_test_data" and args:
            rest, src_dir = args[1:], d
            if rest and rest[0] == "SOURCE_DIR":
                src_dir, rest = Path(rest[1]), rest[2:]
            data += [[x, str((src_dir / x).resolve())] for x in rest if x not in ("MUST_COPY",)]
        elif name in ("add_custom_command", "add_custom_target", "add_subdirectory", "llvm_singlesource",
                      "llvm_test_run", "llvm_test_executable", "llvm_test_verify", "include_directories",
                      "add_executable", "target_link_libraries", "file", "configure_file", "execute_process"):
            unsupported = unsupported or f"cmake:{name}"
        elif name == "add_definitions":
            env.setdefault("CPPFLAGS", []).extend(args)
    return env, progs, data, unsupported


def parse_program(d: Path) -> MSProgram | None:
    d = d.resolve()
    cm = d / "CMakeLists.txt"
    if not cm.exists():
        return None
    text = cm.read_text(errors="ignore")
    if "llvm_multisource" not in text:
        return None
    cmds = _tokens(text)
    variants: list[MSVariant] = []
    name, unsupported = d.name, ""
    sizes = ["SMALL", "DEFAULT", "LARGE"] if re.search(r"(SMALL|LARGE)_PROBLEM_SIZE", text) else ["DEFAULT"]
    for size in sizes:
        env, progs, data, uns = _interpret(cmds, d, size)
        if uns:
            unsupported = uns
        if len(progs) != 1:
            unsupported = unsupported or ("no target" if not progs else "several targets in one dir")
            break
        name, files = progs[0]
        srcs = [str((d / f).resolve()) for f in files if f.endswith(SRC_EXT)] if files else \
            sorted(str(p.resolve()) for p in d.iterdir() if p.suffix in SRC_EXT)
        if not srcs:
            unsupported = unsupported or "no sources"
            break
        ld = env.get("LDFLAGS", [])
        bad = [x for x in ld if x not in OK_LIBS]
        if bad:
            unsupported = unsupported or f"ldflags {' '.join(bad)[:60]}"
        cflags = env.get("CPPFLAGS", []) + env.get("CFLAGS", []) + [f"-I{d}"]
        if any(s.endswith((".cpp", ".cc", ".cxx")) for s in srcs):
            cflags += env.get("CXXFLAGS", [])
        run = env.get("RUN_OPTIONS", [])
        args, stdin, i = [], None, 0
        while i < len(run):
            t = run[i]
            if t == "<" and i + 1 < len(run):
                stdin, i = run[i + 1], i + 2
                continue
            if t.startswith("<") and len(t) > 1:
                stdin, i = t[1:], i + 1
                continue
            if t in (">", "2>", ">>"):
                unsupported = unsupported or "output redirection"
                i += 2
                continue
            args.append(t)
            i += 1
        variants.append(MSVariant(size, srcs, cflags, args, stdin, data, ld))
    # identical consecutive variants (CMake without size branches for this program) collapse
    uniq: list[MSVariant] = []
    for v in variants:
        if not uniq or (v.cflags, v.args, v.stdin, v.sources) != (uniq[-1].cflags, uniq[-1].args, uniq[-1].stdin, uniq[-1].sources):
            uniq.append(v)
    return MSProgram(name, d, uniq, unsupported)


def find_programs(base: Path) -> list[MSProgram]:
    out = []
    for cm in sorted(base.rglob("CMakeLists.txt")):
        p = parse_program(cm.parent)
        if p is not None:
            out.append(p)
    return out
