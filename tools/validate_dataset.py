#!/usr/bin/env python3
"""Validate runtime_v2 JSONL before model training."""

from __future__ import annotations
import argparse, json, math
from pathlib import Path

REQUIRED = [
    "record_id","program_id","project_id","benchmark_family","split","source_hash",
    "input_id","input_hash","target_arch","llvm_version","optimization_origin",
    "pass_sequence","candidate_pass","step_index","correctness",
    "runtime_before_ns","runtime_after_ns","runtime_speedup","runtime_delta_log",
    "compile_time_ns","binary_text_size_before","binary_text_size_after",
    "ir_instruction_count_before","ir_instruction_count_after","feature_vector","hardware"
]

def main() -> int:
    ap=argparse.ArgumentParser(); ap.add_argument("jsonl",type=Path); a=ap.parse_args()
    seen=set(); counts={}; errors=[]
    with a.jsonl.open(encoding="utf-8") as f:
        for lineno,line in enumerate(f,1):
            if not line.strip(): continue
            try: row=json.loads(line)
            except json.JSONDecodeError as e:
                errors.append(f"line {lineno}: invalid JSON: {e}"); continue
            missing=[x for x in REQUIRED if x not in row]
            if missing: errors.append(f"line {lineno}: missing {missing}"); continue
            if not row["correctness"]: errors.append(f"line {lineno}: incorrect record is training-ineligible")
            for x in ("runtime_before_ns","runtime_after_ns","runtime_speedup","runtime_delta_log"):
                if row[x] is None or (isinstance(row[x],float) and not math.isfinite(row[x])): errors.append(f"line {lineno}: bad {x}")
            rid=row["record_id"]
            if rid in seen: errors.append(f"line {lineno}: duplicate record_id {rid}")
            seen.add(rid); counts[row["split"]]=counts.get(row["split"],0)+1
    result={"valid":not errors,"records":len(seen),"split_counts":counts,"errors":errors[:200]}
    print(json.dumps(result,indent=2))
    return 1 if errors else 0

if __name__=="__main__": raise SystemExit(main())
