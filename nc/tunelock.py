"""Freeze for tune mode: results/models/tune/MANIFEST.json pins (sha256) every file tune reads and the
database rows its candidate library is built from. Tune loads its models through this manifest and refuses
to run if anything changed, so work on other modes (predict) cannot silently alter tune's behaviour.
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

MANIFEST = Path("results/models/tune/MANIFEST.json")
WINNERS_SQL = """SELECT DISTINCT c.genome_json, c.program_id FROM measurements m JOIN candidates c ON c.cand_id = m.cand_id
                 WHERE m.stage IN ('confirm','confirm_min','validate') AND m.ci_lo > 1.0"""


def _sha(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def winners_hash(db_path: str, train_programs: list[str]) -> str:
    """Hash of the library's 'winners from training programs' (the DB-dependent part of tune's library)."""
    import sqlite3
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    tp = set(train_programs)
    rows = sorted(r[0] for r in con.execute(WINNERS_SQL) if r[1] in tp)
    return hashlib.sha256("\n".join(rows).encode()).hexdigest()


def tune_files(surrogate: Path, nodyn: Path, rl_policy: Path, results_dir: Path, work_dir: Path,
               llvm_version: str) -> dict[str, Path]:
    s = json.loads(surrogate.read_text())
    nd = json.loads(nodyn.read_text())
    files = {"surrogate": surrogate, "surrogate_model": Path(s["paths"]["gbr"]),
             "nodyn": nodyn, "nodyn_model": Path(nd["paths"]["gbr"]),
             "rl_policy": rl_policy, "rl_policy_meta": rl_policy.with_suffix(".json"),
             "passkb_actions": results_dir / "passkb_actions.json",
             "pools_cache": work_dir / f"pools_llvm{llvm_version}.json",
             "space_cache": work_dir / f"space_v2_llvm{llvm_version}.json"}
    return files


def write_manifest(files: dict[str, Path], db_path: str, llvm_version: str) -> dict:
    s = json.loads(files["surrogate"].read_text())
    man = {"created": time.strftime("%Y-%m-%dT%H:%M:%S"), "mode": "tune", "llvm": llvm_version,
           "files": {k: {"path": str(p), "sha256": _sha(p)} for k, p in files.items()},
           "db_winners_sha256": winners_hash(db_path, s["train_programs"]),
           "note": "Tune mode loads only these files and refuses to run if a hash differs."}
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(man, indent=1))
    return man


def load_verified(db_path: str) -> dict[str, Path]:
    """Return tune's file paths from the manifest after checking every hash; raise on any mismatch."""
    if not MANIFEST.exists():
        raise SystemExit(f"{MANIFEST} missing: tune mode is not frozen (python -m nc.cli tune-freeze)")
    man = json.loads(MANIFEST.read_text())
    bad = []
    for k, v in man["files"].items():
        p = Path(v["path"])
        if not p.exists() or _sha(p) != v["sha256"]:
            bad.append(k)
    s = json.loads(Path(man["files"]["surrogate"]["path"]).read_text())
    if winners_hash(db_path, s["train_programs"]) != man["db_winners_sha256"]:
        bad.append("db_winners (library rows in results/dataset.sqlite)")
    if bad:
        raise SystemExit(f"tune MANIFEST mismatch: {bad}. Tune refuses to run; restore the frozen files.")
    return {k: Path(v["path"]) for k, v in man["files"].items()}
