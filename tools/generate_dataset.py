#!/usr/bin/env python3
"""Generate the runtime-grounded transition dataset for NeuroCompiler 2.0."""
from __future__ import annotations
import argparse, hashlib, json, math, random
from pathlib import Path
from typing import Any
from tools.extract_features import read_and_extract
from tools.llvm_measure import (
    compile_baseline, compile_to_bitcode, compiler_version, correctness_run,
    emit_ir, executable_text_size, host_metadata, link_binary, measure_runtime,
    perf_measure, require_tools, run, run_opt, sha256_file, sha256_text, tool_version,
)

def load(p: Path): return json.loads(p.read_text(encoding="utf-8"))
def split_for_project(pid: str) -> str:
    x=int(hashlib.sha256(pid.encode()).hexdigest()[:8],16)/0xFFFFFFFF
    return "train" if x<.70 else ("validation" if x<.85 else "test")

def measure(exe: Path, args: list[str], cfg: dict[str,Any], expected_stdout_sha256: str | None = None) -> dict[str,Any]:
    c=correctness_run(exe,args,cfg["measurement"]["timeout_seconds"])
    if c["ok"] and expected_stdout_sha256 is not None and c["stdout_sha256"] != expected_stdout_sha256:
        c["ok"] = False
        c["correctness_reason"] = "stdout_hash_mismatch_against_O3_baseline"
    if not c["ok"]: return {"correctness":False,"correctness_result":c}
    rt=measure_runtime(exe,args,cfg["measurement"]["warmups"],cfg["measurement"]["repetitions"],cfg["measurement"]["timeout_seconds"])
    perf=perf_measure(exe,args,cfg["measurement"]["timeout_seconds"]) if cfg["measurement"]["capture_perf"] else {}
    return {"correctness":True,"correctness_result":{k:v for k,v in c.items() if k not in ("stdout","stderr")},"runtime":rt,"perf":perf}

def baseline_ir(sources:list[Path], level:str, flags:list[str], out:Path)->dict[str,int]:
    out.parent.mkdir(parents=True,exist_ok=True)
    p=run(["clang",f"-{level}","-S","-emit-llvm",*map(str,sources),*flags,"-o",str(out)],120)
    if p.returncode: raise RuntimeError(p.stderr)
    return read_and_extract(out)

def build_custom_state(
    source_bc:Path, seq:list[str], pipeline_map:dict[str,str], work:Path,
    link_flags:list[str], cfg:dict[str,Any], run_args:list[str]
)->dict[str,Any]:
    work.mkdir(parents=True,exist_ok=True)
    out_bc=work/"state.bc"
    pipe=[pipeline_map[x] for x in seq]
    opt_time=run_opt(source_bc,out_bc,pipe) if seq else 0
    current=out_bc if seq else source_bc
    ir_path=work/"state.ll"
    emit_ir(current,ir_path)
    exe=work/"program"
    backend=link_binary(current,exe,link_flags)
    m=measure(exe,run_args,cfg)
    return {"exe":exe,"ir_path":str(ir_path),"ir_features":read_and_extract(ir_path),
            "compile_time_ns":backend+opt_time,"binary_text_size":executable_text_size(exe),**m}

def record(program, inp, split, source_hash, before, after, seq, candidate,
           step, compiler, hardware, o3_runtime_ns):
    tb=before["runtime"]["median_seconds"]; ta=after["runtime"]["median_seconds"]
    return {
      "record_id":sha256_text(json.dumps([program["program_id"],inp["input_id"],seq,candidate,compiler],sort_keys=True)),
      "program_id":program["program_id"],"project_id":program["project_id"],
      "benchmark_family":program["benchmark_family"],"split":split,"source_hash":source_hash,
      "input_id":inp["input_id"],"input_hash":sha256_text(json.dumps(inp,sort_keys=True)),
      "target_arch":hardware["machine"],"llvm_version":compiler,
      "optimization_origin":program.get("optimization_origin","runtime_campaign"),
      "pass_sequence":seq,"candidate_pass":candidate,"step_index":step,"correctness":True,
      "runtime_before_ns":round(tb*1e9),"runtime_after_ns":round(ta*1e9),
      "runtime_speedup":tb/ta,"runtime_delta_log":math.log(tb/ta),
      "compile_time_ns":after["compile_time_ns"],
      "binary_text_size_before":before["binary_text_size"],
      "binary_text_size_after":after["binary_text_size"],
      "ir_instruction_count_before":before["ir_features"]["estimated_ir_instruction_count"],
      "ir_instruction_count_after":after["ir_features"]["estimated_ir_instruction_count"],
      "feature_vector":before["ir_features"],"feature_vector_after":after["ir_features"],
      "hardware":hardware,"perf_before":before.get("perf",{}),"perf_after":after.get("perf",{}),
      "runtime_samples_before":before["runtime"]["samples_seconds"],
      "runtime_samples_after":after["runtime"]["samples_seconds"],
      "runtime_cv_before":before["runtime"]["coefficient_of_variation"],
      "runtime_cv_after":after["runtime"]["coefficient_of_variation"],
      "stdout_sha256":after["correctness_result"]["stdout_sha256"],
      "stderr_sha256":after["correctness_result"]["stderr_sha256"],
      "ir_before_path":before["ir_path"],"ir_after_path":after["ir_path"],
      "reference_o3_runtime_ns":o3_runtime_ns,
      "speedup_vs_o3":o3_runtime_ns/(ta*1e9)
    }

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--manifest",required=True,type=Path)
    ap.add_argument("--config",required=True,type=Path)
    ap.add_argument("--passes",default="data/pass_catalog.json",type=Path)
    ap.add_argument("--output",required=True,type=Path)
    ap.add_argument("--workdir",default=Path("data/work"),type=Path)
    ap.add_argument("--mode",choices=["single","random"],default="single")
    ap.add_argument("--max-programs",type=int,default=0)
    a=ap.parse_args()
    cfg=load(a.config); manifest=load(a.manifest); catalog=load(a.passes)
    require_tools(cfg["llvm"]["required_tools"])
    compiler=compiler_version(); hardware=host_metadata()
    pmap={p["id"]:p["pipeline"] for p in catalog["passes"]}; pids=list(pmap)
    rng=random.Random(cfg["sampling"]["seed"]); rows=[]; baselines=[]

    programs=manifest["programs"][:a.max_programs or None]
    for program in programs:
      sources=[Path(x) for x in program.get("sources",[program["source"]])]
      split=split_for_project(program["project_id"])
      source_hash=sha256_text("|".join(sha256_file(s) for s in sources))
      for inp in program.get("inputs",[{"input_id":"default","run_args":[]}]):
        args_run=program.get("run_args",[])+inp.get("run_args",[])
        compile_flags=program.get("compile_flags",[])+inp.get("compile_flags",[])
        root=a.workdir/program["program_id"].replace("/","__")/inp["input_id"]
        o3=None
        try:
          for level in cfg["llvm"]["baseline_levels"]:
            exe=root/f"baseline_{level}"/"program"
            ct=compile_baseline(sources,exe,level,compile_flags)
            m=measure(exe,args_run,cfg)
            if not m["correctness"]: continue
            if level == "O3":
                expected_stdout_sha256 = m["correctness_result"]["stdout_sha256"]
            ll=root/f"baseline_{level}.ll"
            try: feat=baseline_ir(sources,level,compile_flags,ll)
            except Exception: feat={}
            item={"program_id":program["program_id"],"project_id":program["project_id"],"benchmark_family":program["benchmark_family"],
                  "split":split,"input_id":inp["input_id"],"optimization_level":level,"runtime":m["runtime"],
                  "runtime_speedup_vs_o3":None,"compile_time_ns":ct,"binary_text_size":executable_text_size(exe),
                  "ir_features":feat,"correctness":True,"llvm_version":compiler,"hardware":hardware}
            if level=="O3": o3=item
            baselines.append(item)
          if o3 is None: continue
          custom_base_dir=root/"state_cache"/"root"
          source_bc,front_time=compile_to_bitcode(sources,custom_base_dir/"frontend",cfg["llvm"]["compile_frontend_flags"]+compile_flags)
          cache={():None}
          base=build_custom_state(source_bc,[],pmap,custom_base_dir,program.get("link_flags",[]),cfg,args_run)
          cache[()]=base
          if base["correctness"] and base["runtime"]["coefficient_of_variation"]<=cfg["training_policy"]["max_cv_runtime"]:
            sequences=[[x] for x in pids]
            if a.mode=="random":
              for _ in range(cfg["sampling"]["random_sequences_per_program"]):
                n=rng.randint(2,cfg["sampling"]["max_sequence_length"])
                sequences.append(rng.sample(pids,min(n,len(pids))))
            for seq in sequences:
              prev=base; prev_seq=[]
              for step,candidate in enumerate(seq):
                prefix=tuple(seq[:step+1])
                if prefix not in cache:
                  try:
                    state=build_custom_state(source_bc,list(prefix),pmap,root/"state_cache"/("__".join(prefix)),program.get("link_flags",[]),cfg,args_run)
                  except Exception:
                    break
                  cache[prefix]=state
                after=cache[prefix]
                if after["correctness"] and expected_stdout_sha256 is not None and after["correctness_result"]["stdout_sha256"] != expected_stdout_sha256:
                  after["correctness"] = False
                  after["correctness_result"]["correctness_reason"] = "stdout_hash_mismatch_against_O3_baseline"
                if not after["correctness"] or after["runtime"]["coefficient_of_variation"]>cfg["training_policy"]["max_cv_runtime"]:
                  break
                rows.append(record(program,inp,split,source_hash,prev,after,prev_seq,candidate,step,compiler,hardware,round(o3["runtime"]["median_seconds"]*1e9)))
                prev=after; prev_seq=list(prefix)
        except Exception:
          continue

    a.output.mkdir(parents=True,exist_ok=True)
    with (a.output/"transitions.jsonl").open("w",encoding="utf-8") as f:
      for r in rows: f.write(json.dumps(r,sort_keys=True)+"\n")
    # Add O3-relative speedups once the O3 baseline is known.
    o3_by={(r["program_id"],r["input_id"]):r["runtime"]["median_seconds"] for r in baselines if r["optimization_level"]=="O3"}
    for r in baselines:
      key=(r["program_id"],r["input_id"])
      if key in o3_by: r["runtime_speedup_vs_o3"]=o3_by[key]/r["runtime"]["median_seconds"]
    with (a.output/"baselines.jsonl").open("w",encoding="utf-8") as f:
      for r in baselines: f.write(json.dumps(r,sort_keys=True)+"\n")
    manifest_out={"dataset_version":cfg["dataset_version"],"records":len(rows),"baseline_records":len(baselines),
      "primary_target":"runtime","compiler":compiler,"hardware":hardware,
      "split_strategy":cfg["split"],"pass_count":len(pids),
      "llvm_tool_versions":{x:tool_version(x) for x in cfg["llvm"]["required_tools"]}}
    (a.output/"manifest.json").write_text(json.dumps(manifest_out,indent=2),encoding="utf-8")
    print(json.dumps(manifest_out,indent=2))

if __name__=="__main__": main()
