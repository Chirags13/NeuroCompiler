#!/usr/bin/env python3
"""Build a runnable PolyBench/C manifest from utilities/benchmark_list.

PolyBench has 30 kernels and compile-time tunable dataset sizes. We keep the
kernel source and common polybench.c as separate translation units and vary
the dataset macro per workload.
"""
from __future__ import annotations
import argparse, json
from pathlib import Path

SIZES = ["MINI_DATASET", "MEDIUM_DATASET", "LARGE_DATASET"]

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--root",type=Path,default=Path("external/PolyBenchC"))
    ap.add_argument("--output",type=Path,default=Path("data/manifests/polybench.json"))
    args=ap.parse_args()

    listing=args.root/"utilities"/"benchmark_list"
    if not listing.exists():
        raise SystemExit(f"Missing {listing}; clone PolyBench/C first")

    entries=[]
    for raw in listing.read_text(errors="replace").splitlines():
        rel=raw.strip()
        if not rel or rel.startswith("#"): continue
        kernel=args.root/rel
        if not kernel.exists() or kernel.suffix != ".c": continue
        stem=kernel.stem
        rel_id=Path(rel).with_suffix("").as_posix()
        project_id=f"polybench/{rel_id}"
        inputs=[]
        for size in SIZES:
            inputs.append({
                "input_id": size.lower(),
                "run_args": [],
                "compile_flags": [f"-D{size}"]
            })
        entries.append({
            "program_id": f"polybench/{rel_id}",
            "project_id": project_id,
            "benchmark_family": "polybench-c",
            "sources": [str(kernel), str(args.root/"utilities"/"polybench.c")],
            "compile_flags": [
                "-std=c99",
                "-O0",
                "-DPOLYBENCH_TIME",
                f"-I{args.root/'utilities'}"
            ],
            "link_flags": [],
            "run_args": [],
            "inputs": inputs,
            "optimization_origin": "polybench_c_4.2.1"
        })

    if len(entries) != 30:
        raise SystemExit(f"Expected 30 PolyBench kernels, discovered {len(entries)}")

    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps({
        "manifest_version":"2.0",
        "source":{"id":"polybench-c","root":str(args.root)},
        "programs":entries
    },indent=2))
    print(json.dumps({"programs":len(entries),"workloads":len(entries)*len(SIZES),"output":str(args.output)},indent=2))

if __name__=="__main__":
    main()
