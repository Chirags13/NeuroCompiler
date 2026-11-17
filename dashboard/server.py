"""NeuroCompiler dashboard server (FastAPI). Local only (127.0.0.1).

Runs the normal command-line modes (`python -m nc.cli tune|predict|compare|selftest`) as background jobs,
one at a time (timing runs must not overlap), streams their terminal output to the browser, reports the
environment, and serves the static frontend plus pre-exported research data. It never changes models or
the measurement database: tune and predict load their own MANIFEST-verified files as usual.

Start:  ./dashboard/run.sh      (or the Windows launcher dashboard/windows/Start-NeuroCompiler.bat)
"""
from __future__ import annotations

import asyncio
import json
import os
import platform
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

REPO = Path(__file__).resolve().parents[1]
STATIC = REPO / "dashboard" / "static"
EXAMPLES = REPO / "dashboard" / "examples"
SAVED = REPO / "dashboard" / "saved"
JOBS = REPO / "work" / "dashboard" / "jobs"
PY = str(REPO / ".venv" / "bin" / "python")
SRC_EXT = (".c", ".cpp", ".cc", ".cxx", ".h", ".hpp")
MODES = ("tune", "predict", "compare", "selftest")

app = FastAPI(title="NeuroCompiler dashboard")
_lock = threading.Lock()
_queue: list[str] = []
_procs: dict[str, subprocess.Popen] = {}


# ---------------------------------------------------------------- jobs
def _job_path(jid: str) -> Path:
    if not re.fullmatch(r"[0-9a-f]{12}", jid):
        raise HTTPException(404, "no such job")
    return JOBS / jid


def _load(jid: str) -> dict:
    p = _job_path(jid) / "job.json"
    if not p.exists():
        raise HTTPException(404, "no such job")
    return json.loads(p.read_text())


def _save(job: dict) -> None:
    p = JOBS / job["id"] / "job.json"
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(job, indent=1))
    tmp.replace(p)


def _command(job: dict) -> list[str]:
    d = JOBS / job["id"]
    inp = job["inputs"]
    srcs = [str(d / "src" / f) for f in inp["files"] if f.endswith((".c", ".cpp", ".cc", ".cxx"))]
    m = job["mode"]
    if m == "selftest":
        return [PY, "-u", "-m", "nc.cli", "selftest", str(REPO / "bench" / "matmul.c"), "--args", "800"]
    cmd = [PY, "-u", "-m", "nc.cli", m, *srcs]
    if m in ("tune", "predict"):
        cmd += ["--out", str(d / "prog")]
    # `--opt=value`: values may start with "-" (e.g. -I..., -DSIZE=...), which argparse would read as options
    cmd.append("--cflags=" + " ".join(x for x in (inp.get("cflags", ""), f"-I{d / 'src'}") if x))
    if m in ("tune", "compare"):
        cmd += ["--args=" + inp.get("args", ""), "--k", str(inp.get("k", 8))]
        if inp.get("stdin"):
            cmd += ["--stdin", str(d / "src" / inp["stdin"])]
        cmd += ["--cwd", str(d / "src")]
    if m == "tune":
        if inp.get("no_rl"):
            cmd.append("--no-rl")
        if inp.get("dynamic"):
            cmd.append("--dynamic")
    if m == "predict":
        if inp.get("no_rl"):
            cmd.append("--no-rl")
        cmd += ["--args=" + inp.get("args", ""), "--cwd", str(d / "src")]
        if inp.get("stdin"):
            cmd += ["--stdin", str(d / "src" / inp["stdin"])]
        if inp.get("verify"):
            cmd += ["--verify", "--apply"]
        if inp.get("no_measure"):
            cmd.append("--no-measure")
    if m == "compare":
        cmd += ["--json-out", str(d / "compare.json")]
    return cmd


def _result(job: dict) -> dict | None:
    d = JOBS / job["id"]
    for f in ("prog.json", "compare.json"):
        if (d / f).exists():
            try:
                return json.loads((d / f).read_text())
            except ValueError:
                return None
    if job["mode"] == "selftest" and (d / "log.txt").exists():
        txt = (d / "log.txt").read_text(errors="replace")
        return {"verdict": "PASS" if "PASS: this environment" in txt else ("FAIL" if "FAIL:" in txt else "unknown"),
                "lines": [ln.strip() for ln in txt.splitlines() if "->" in ln or "ours / clang" in ln]}
    return None


def _worker() -> None:
    while True:
        with _lock:
            jid = _queue.pop(0) if _queue else None
        if jid is None:
            time.sleep(0.5)
            continue
        job = _load(jid)
        if job["status"] == "cancelled":
            continue
        d = JOBS / jid
        job.update(status="running", started=time.time(), command=_command(job))
        _save(job)
        with open(d / "log.txt", "w") as log:
            log.write(f"$ {' '.join(job['command'])}\n\n")
            log.flush()
            env = dict(os.environ, PYTHONUNBUFFERED="1", NC_CALLER_CWD=str(d))
            p = subprocess.Popen(job["command"], cwd=REPO, stdout=log, stderr=subprocess.STDOUT, env=env,
                                 start_new_session=True)
            _procs[jid] = p
            rc = p.wait()
        _procs.pop(jid, None)
        job = _load(jid)
        if job["status"] != "cancelled":
            job["status"] = "done" if rc == 0 else "failed"
        job.update(finished=time.time(), returncode=rc)
        _save(job)


@app.on_event("startup")
def _startup() -> None:
    JOBS.mkdir(parents=True, exist_ok=True)
    for p in JOBS.glob("*/job.json"):                  # jobs interrupted by a server restart
        j = json.loads(p.read_text())
        if j["status"] in ("running", "queued"):
            j["status"] = "interrupted"
            _save(j)
    threading.Thread(target=_worker, daemon=True).start()


@app.post("/api/jobs")
async def create_job(mode: str = Form(...), code: str = Form(""), filename: str = Form("main.c"),
                     args: str = Form(""), cflags: str = Form(""), k: int = Form(8), no_rl: bool = Form(False),
                     dynamic: bool = Form(False), verify: bool = Form(False), no_measure: bool = Form(False), example: str = Form(""),
                     files: list[UploadFile] = File(default=[]), stdin_file: UploadFile | None = File(default=None)):
    if mode not in MODES:
        raise HTTPException(400, f"mode must be one of {MODES}")
    jid = uuid.uuid4().hex[:12]
    d = JOBS / jid / "src"
    d.mkdir(parents=True)
    names = []
    if example:
        ex = _example(example)
        for f in ex["files"]:
            shutil.copy2(EXAMPLES / ex["dir"] / f, d / f)
            names.append(f)
        args = args or ex.get("args", "")
        cflags = cflags or ex.get("cflags", "")
    for up in files:
        name = Path(up.filename or "").name
        if not name.endswith(SRC_EXT):
            raise HTTPException(400, f"{name}: only C/C++ sources and headers ({', '.join(SRC_EXT)})")
        (d / name).write_bytes(await up.read())
        names.append(name)
    if code.strip():
        name = Path(filename).name or "main.c"
        if not name.endswith((".c", ".cpp", ".cc", ".cxx")):
            name += ".c"
        (d / name).write_text(code)
        names.append(name)
    stdin_name = None
    if stdin_file is not None and stdin_file.filename:
        stdin_name = "stdin_" + Path(stdin_file.filename).name
        (d / stdin_name).write_bytes(await stdin_file.read())
    if mode != "selftest" and not any(n.endswith((".c", ".cpp", ".cc", ".cxx")) for n in names):
        raise HTTPException(400, "no C/C++ source given (paste code, upload files or pick an example)")
    job = {"id": jid, "mode": mode, "status": "queued", "created": time.time(), "example": example or None,
           "inputs": {"files": names, "args": args, "cflags": cflags, "k": max(2, min(int(k), 16)), "no_rl": no_rl,
                      "dynamic": dynamic, "verify": verify, "no_measure": no_measure, "stdin": stdin_name}}
    _save(job)
    with _lock:
        _queue.append(jid)
    return job


@app.get("/api/jobs")
def list_jobs():
    jobs = []
    for p in sorted(JOBS.glob("*/job.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:30]:
        j = json.loads(p.read_text())
        with _lock:
            j["queue_position"] = _queue.index(j["id"]) + 1 if j["id"] in _queue else None
        jobs.append(j)
    return jobs


@app.get("/api/jobs/{jid}")
def get_job(jid: str):
    job = _load(jid)
    job["result"] = _result(job)
    src = JOBS / jid / "src"
    job["sources"] = {f: (src / f).read_text(errors="replace")[:200000] for f in job["inputs"]["files"]
                      if (src / f).exists()}
    return job


@app.get("/api/jobs/{jid}/stream")
async def stream(jid: str):
    """Server-Sent Events: the job's terminal output as it is written, then a final status event."""
    d = _job_path(jid)

    async def gen():
        pos = 0
        while True:
            log = d / "log.txt"
            if log.exists():
                with open(log, "rb") as f:
                    f.seek(pos)
                    chunk = f.read()
                    pos += len(chunk)
                for ln in chunk.decode(errors="replace").splitlines():
                    yield f"data: {json.dumps({'line': ln})}\n\n"
            job = _load(jid)
            if job["status"] in ("done", "failed", "cancelled", "interrupted") and log.exists() and pos >= log.stat().st_size:
                yield f"event: status\ndata: {json.dumps({'status': job['status']})}\n\n"
                break
            yield ": keep-alive\n\n"
            await asyncio.sleep(0.5)

    return StreamingResponse(gen(), media_type="text/event-stream")


@app.post("/api/jobs/{jid}/cancel")
def cancel(jid: str):
    job = _load(jid)
    with _lock:
        if jid in _queue:
            _queue.remove(jid)
    p = _procs.get(jid)
    if p is not None:
        try:
            os.killpg(p.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    job["status"] = "cancelled"
    _save(job)
    return job


@app.get("/api/jobs/{jid}/binary")
def binary(jid: str):
    b = _job_path(jid) / "prog"
    if not b.exists():
        raise HTTPException(404, "no binary for this job")
    return FileResponse(b, filename=f"neurocompiler_{jid}", media_type="application/octet-stream")


@app.post("/api/jobs/{jid}/save")
def save_run(jid: str, name: str = Form(...)):
    job = get_job(jid)
    if job["status"] != "done":
        raise HTTPException(400, "only finished jobs can be saved")
    slug = re.sub(r"[^a-z0-9_-]+", "-", name.lower()).strip("-")[:40] or jid
    job["saved_name"] = name
    job["log"] = (JOBS / jid / "log.txt").read_text(errors="replace")
    SAVED.mkdir(parents=True, exist_ok=True)
    (SAVED / f"{slug}.json").write_text(json.dumps(job, indent=1))
    return {"saved": slug}


@app.get("/api/saved")
def saved_list():
    out = []
    for p in sorted(SAVED.glob("*.json")):
        j = json.loads(p.read_text())
        out.append({"slug": p.stem, "name": j.get("saved_name", p.stem), "mode": j["mode"], "example": j.get("example"),
                    "finished": j.get("finished")})
    return out


@app.get("/api/saved/{slug}")
def saved_get(slug: str):
    p = SAVED / f"{Path(slug).name}.json"
    if not p.exists():
        raise HTTPException(404, "no such saved run")
    return json.loads(p.read_text())


# ---------------------------------------------------------------- examples
def _examples() -> list[dict]:
    return json.loads((EXAMPLES / "examples.json").read_text())


def _example(name: str) -> dict:
    for e in _examples():
        if e["id"] == name:
            return e
    raise HTTPException(404, "no such example")


@app.get("/api/examples")
def examples():
    out = []
    for e in _examples():
        e = dict(e)
        e["sources"] = {f: (EXAMPLES / e["dir"] / f).read_text(errors="replace") for f in e["files"]}
        out.append(e)
    return out


# ---------------------------------------------------------------- environment
def _run(cmd: list[str], timeout: float = 20) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=REPO).stdout.strip()
    except Exception as e:                            # noqa: BLE001
        return f"error: {e}"


@app.get("/api/env")
def env():
    sys.path.insert(0, str(REPO))
    from nc.config import load_config
    from nc.timing import busy_cores_foreign
    cfg = load_config(REPO / "config.toml")
    checks = []

    def add(name, ok, detail):
        checks.append({"name": name, "ok": bool(ok), "detail": detail})

    kern = platform.release()
    add("WSL2 Linux environment", "microsoft" in kern.lower() or "wsl" in kern.lower(), f"kernel {kern}")
    v = _run([str(Path(cfg.llvm_bin_dir) / "opt"), "--version"])
    m = re.search(r"LLVM version (\S+)", v)
    add("LLVM 18.1.8 (pinned)", m and m.group(1) == "18.1.8", m.group(1) if m else v[:80])
    add("Python environment", Path(PY).exists(), f"{sys.version.split()[0]} ({PY})")
    try:
        from nc import tunelock
        tunelock.load_verified(str(REPO / cfg.db_path))
        add("tune models (MANIFEST)", True, "all hashes verified")
    except BaseException as e:                         # noqa: BLE001
        add("tune models (MANIFEST)", False, str(e)[:160])
    try:
        cwd = os.getcwd()
        os.chdir(REPO)
        from nc import predict
        predict.load_manifest_verified()
        add("predict models (MANIFEST)", True, "all hashes verified")
    except BaseException as e:                         # noqa: BLE001
        add("predict models (MANIFEST)", False, str(e)[:160])
    finally:
        os.chdir(cwd)
    busy = busy_cores_foreign(1.0)
    add("machine quiet for timing", busy <= cfg.quiet_max_busy, f"{busy:.2f} cores busy from other processes "
                                                               f"(limit {cfg.quiet_max_busy})")
    st = sorted((REPO / cfg.results_dir).glob(f"selftest_{cfg.machine_id}_*.json"))
    if st:
        j = json.loads(st[-1].read_text())
        add("last timing selftest", j.get("verdict") == "PASS", f"{j.get('verdict')} ({st[-1].name})")
    else:
        add("last timing selftest", False, "none for this machine_id; run the selftest")
    return {"checks": checks, "machine_id": cfg.machine_id, "timing_cpu": cfg.timing_cpu,
            "cpus": os.cpu_count(), "ok": all(c["ok"] for c in checks)}


# ---------------------------------------------------------------- pipelines
_TREE = {}


def _tree():
    if not _TREE:
        sys.path.insert(0, str(REPO))
        from nc.config import load_config
        from nc.pipeline import _ctx_of, _walk, parse_pipeline
        from nc.toolchain import Toolchain
        tc = Toolchain(load_config(REPO / "config.toml"), REPO / "work")
        text = tc.pipeline_string("O3")
        root = parse_pipeline(text)
        _TREE["text"] = text
        _TREE["leaves"] = {n.id: {"name": re.split(r"[<(]", n.text, maxsplit=1)[0], "text": n.text, "ctx": _ctx_of(p, root)}
                           for p, _i, n in _walk(root) if n.is_leaf}
    return _TREE


def _flatten(pipeline: str) -> list[dict]:
    """Leaf passes in execution order with their stage (module / cgscc / function / loop)."""
    from nc.pipeline import parse_pipeline
    out = []

    def rec(node, ctx):
        for ch in node.children or []:
            if ch.is_leaf:
                out.append({"pass": re.split(r"[<(]", ch.text, maxsplit=1)[0], "text": ch.text, "ctx": ctx})
            else:
                rec(ch, ch.ctx)
    rec(parse_pipeline(pipeline), "module")
    return out


def diff_pipelines(selected: str | None, flags: list[str] | None = None, backend: int | None = None) -> dict:
    import difflib
    o3 = _tree()["text"]
    a = _flatten(o3)
    b = _flatten(selected) if selected and not selected.startswith("default<") else None
    ops = []
    if b is None:
        ops = [{"op": "equal", "a": x, "b": x} for x in a] if not selected or selected == o3 else []
    else:
        sm = difflib.SequenceMatcher(a=[x["text"] for x in a], b=[x["text"] for x in b], autojunk=False)
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag == "equal":
                ops += [{"op": "equal", "a": a[i], "b": b[j]} for i, j in zip(range(i1, i2), range(j1, j2))]
            elif tag == "replace" and (i2 - i1) == (j2 - j1):
                ops += [{"op": "changed" if a[i]["pass"] == b[j]["pass"] else "replace", "a": a[i], "b": b[j]}
                        for i, j in zip(range(i1, i2), range(j1, j2))]
            else:
                ops += [{"op": "delete", "a": a[i], "b": None} for i in range(i1, i2)]
                ops += [{"op": "insert", "a": None, "b": b[j]} for j in range(j1, j2)]
    cnt = {k: sum(1 for o in ops if o["op"] == k) for k in ("equal", "delete", "insert", "changed", "replace")}
    return {"o3_passes": len(a), "selected_passes": len(b) if b else (len(a) if not selected or selected == o3 else None),
            "standard_level": selected if selected and selected.startswith("default<") else None,
            "ops": ops, "counts": cnt, "flags": flags or [], "backend": backend, "o3_text": o3, "selected_text": selected}


def _job_diff(job: dict) -> dict:
    r = job.get("result") or {}
    if job["mode"] == "tune":
        if r.get("choice") != "candidate":
            return {"note": "-O3 shipped (no candidate confirmed)", **diff_pipelines(None)}
        return diff_pipelines(r.get("pipeline"), r.get("flags"), r.get("backend"))
    if job["mode"] == "predict":
        if not r.get("recommended"):
            return {"note": "predict recommends keeping -O3", **diff_pipelines(None)}
        return diff_pipelines(r.get("recommended_pipeline"), r.get("recommended_flags"), r.get("recommended_backend"))
    return {"note": "no single pipeline for this mode"}


@app.get("/api/o3tree")
def o3tree():
    t = _tree()
    return {"text": t["text"], "leaves": t["leaves"], "passes": len(t["leaves"])}


@app.get("/api/jobs/{jid}/diff")
def job_diff(jid: str):
    return _job_diff(get_job(jid))


@app.get("/api/saved/{slug}/diff")
def saved_diff(slug: str):
    return _job_diff(saved_get(slug))


@app.get("/api/health")
def health():
    return {"ok": True, "time": time.time()}


class _NoCacheStatic(StaticFiles):
    """Browsers must revalidate (ETag) on every load, so dashboard updates show up on a normal refresh."""
    async def get_response(self, path, scope):
        r = await super().get_response(path, scope)
        r.headers["Cache-Control"] = "no-cache"
        return r


app.mount("/", _NoCacheStatic(directory=STATIC, html=True), name="static")
