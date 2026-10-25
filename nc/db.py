"""SQLite store for the measurement dataset (Layer 2 of the dataset design).

candidates    one row per (program, pipeline, knobs, backend): how it was built, sizes, status
measurements  one row per timing experiment (screen / confirm / control), raw times kept
runs          one row per (program, method) search run, with config and summary
"""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS candidates(
  cand_id TEXT PRIMARY KEY, program_id TEXT NOT NULL, method TEXT, generation INTEGER,
  genome_json TEXT, pipeline TEXT, opt_flags TEXT, backend INTEGER,
  ir_hash TEXT, bin_hash TEXT, status TEXT, same_as_o3 INTEGER DEFAULT 0,
  ir_insts INTEGER, text_size INTEGER, bin_size INTEGER, opt_ms REAL, backend_ms REAL,
  n_edits INTEGER, created_at TEXT, machine_id TEXT, llvm_version TEXT);
CREATE INDEX IF NOT EXISTS idx_c_prog ON candidates(program_id);
CREATE TABLE IF NOT EXISTS measurements(
  id INTEGER PRIMARY KEY AUTOINCREMENT, cand_id TEXT, program_id TEXT, stage TEXT,
  n INTEGER, median_ms REAL, base_median_ms REAL, speedup REAL, ci_lo REAL, ci_hi REAL,
  raw_ms TEXT, base_raw_ms TEXT, ts TEXT, machine_id TEXT, cpu INTEGER, note TEXT);
CREATE INDEX IF NOT EXISTS idx_m_cand ON measurements(cand_id);
CREATE INDEX IF NOT EXISTS idx_m_prog ON measurements(program_id, stage);
CREATE TABLE IF NOT EXISTS runs(
  run_id TEXT PRIMARY KEY, program_id TEXT, method TEXT, seed INTEGER, budget INTEGER,
  started TEXT, finished TEXT, config_json TEXT, summary_json TEXT);
"""


class Store:
    def __init__(self, path: str | Path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.con = sqlite3.connect(str(path), timeout=120)
        self.con.row_factory = sqlite3.Row
        self.con.execute("PRAGMA journal_mode=WAL")      # several timing workers write concurrently
        self.con.executescript(SCHEMA)

    def _put(self, table: str, row: dict, replace: bool = True) -> None:
        cols = ",".join(row)
        qs = ",".join("?" for _ in row)
        verb = "INSERT OR REPLACE" if replace else "INSERT"
        self.con.execute(f"{verb} INTO {table}({cols}) VALUES({qs})", list(row.values()))
        self.con.commit()

    def put_candidate(self, row: dict) -> None:
        row.setdefault("created_at", time.strftime("%Y-%m-%dT%H:%M:%S"))
        self._put("candidates", row)

    def put_measurement(self, row: dict) -> None:
        row.setdefault("ts", time.strftime("%Y-%m-%dT%H:%M:%S"))
        for k in ("raw_ms", "base_raw_ms"):
            if k in row and not isinstance(row[k], str):
                row[k] = json.dumps([None if x != x else round(x, 3) for x in row[k]])
        self._put("measurements", row, replace=False)

    def put_run(self, row: dict) -> None:
        self._put("runs", row)

    def get_candidate(self, cand_id: str):
        return self.con.execute("SELECT * FROM candidates WHERE cand_id=?", (cand_id,)).fetchone()

    def latest_measurement(self, cand_id: str, stage: str):
        return self.con.execute(
            "SELECT * FROM measurements WHERE cand_id=? AND stage=? ORDER BY id DESC LIMIT 1",
            (cand_id, stage)).fetchone()

    def rows(self, sql: str, args: tuple = ()):
        return self.con.execute(sql, args).fetchall()
