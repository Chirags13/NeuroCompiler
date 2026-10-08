#!/usr/bin/env python3
from __future__ import annotations
import hashlib, os, platform, shutil, statistics, subprocess, time
from pathlib import Path
from typing import Any, Iterable

def require_tools(names: Iterable[str]) -> None:
    missing=[x for x in names if shutil.which(x) is None]
    if missing: raise RuntimeError('Missing required tools: '+', '.join(missing))

def run(cmd:list[str],timeout:int=120)->subprocess.CompletedProcess[str]:
    return subprocess.run(cmd,timeout=timeout,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=False)

def sha256_text(text:str)->str: return hashlib.sha256(text.encode()).hexdigest()
def sha256_file(path:Path)->str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for c in iter(lambda:f.read(1024*1024),b''): h.update(c)
    return h.hexdigest()

def compiler_version()->str:
    p=run(['clang','--version'],15); return p.stdout.splitlines()[0] if p.returncode==0 and p.stdout else 'unknown'
def tool_version(tool:str)->str:
    p=run([tool,'--version'],15); return p.stdout.splitlines()[0] if p.returncode==0 and p.stdout else 'unknown'
def host_metadata()->dict[str,Any]:
    return {'hostname':platform.node(),'os':platform.platform(),'machine':platform.machine(),'processor':platform.processor(),'python':platform.python_version(),'logical_cpus':os.cpu_count()}

def compile_to_bitcode(sources:list[Path],out_dir:Path,cflags:list[str])->tuple[Path,int]:
    out_dir.mkdir(parents=True,exist_ok=True); t0=time.perf_counter_ns(); objects=[]
    for i,src in enumerate(sources):
        bc=out_dir/f'input_{i}.bc'; p=run(['clang',*cflags,str(src),'-o',str(bc)])
        if p.returncode: raise RuntimeError(p.stderr)
        objects.append(bc)
    if len(objects)==1: return objects[0],time.perf_counter_ns()-t0
    result=out_dir/'module.bc'; p=run(['llvm-link',*map(str,objects),'-o',str(result)])
    if p.returncode: raise RuntimeError(p.stderr)
    return result,time.perf_counter_ns()-t0

def emit_ir(bitcode:Path,ir_path:Path)->None:
    p=run(['llvm-dis',str(bitcode),'-o',str(ir_path)],60)
    if p.returncode: raise RuntimeError(p.stderr)

def run_opt(input_bc:Path,output_bc:Path,pipeline:list[str])->int:
    output_bc.parent.mkdir(parents=True,exist_ok=True); t0=time.perf_counter_ns()
    p=run(['opt',f"-passes={','.join(pipeline)}",str(input_bc),'-o',str(output_bc)])
    if p.returncode: raise RuntimeError(p.stderr)
    return time.perf_counter_ns()-t0

def link_binary(bitcode:Path,exe:Path,flags:list[str])->int:
    t0=time.perf_counter_ns(); p=run(['clang',str(bitcode),'-O0',*flags,'-o',str(exe)])
    if p.returncode: raise RuntimeError(p.stderr)
    return time.perf_counter_ns()-t0

def compile_baseline(sources:list[Path],exe:Path,level:str,flags:list[str])->int:
    t0=time.perf_counter_ns(); p=run(['clang',f'-{level}',*map(str,sources),*flags,'-o',str(exe)])
    if p.returncode: raise RuntimeError(p.stderr)
    return time.perf_counter_ns()-t0

def executable_text_size(exe:Path)->int|None:
    p=run(['llvm-size','-format=SysV',str(exe)],15)
    if p.returncode: return None
    for line in p.stdout.splitlines():
        parts=line.split()
        if parts and parts[0]=='text' and len(parts)>1:
            try: return int(parts[1])
            except ValueError: return None
    return None

def correctness_run(exe:Path,args:list[str],timeout:int)->dict[str,Any]:
    p=subprocess.run([str(exe),*args],timeout=timeout,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=False)
    return {'ok':p.returncode==0,'returncode':p.returncode,'stdout_sha256':sha256_text(p.stdout),'stderr_sha256':sha256_text(p.stderr),'stdout':p.stdout,'stderr':p.stderr}

def timed_run(exe:Path,args:list[str],timeout:int)->float:
    t0=time.perf_counter_ns(); p=subprocess.run([str(exe),*args],timeout=timeout,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=False); dt=(time.perf_counter_ns()-t0)/1e9
    if p.returncode: raise RuntimeError(f'benchmark failed: returncode={p.returncode}')
    return dt

def measure_runtime(exe:Path,args:list[str],warmups:int,repetitions:int,timeout:int)->dict[str,Any]:
    for _ in range(warmups): timed_run(exe,args,timeout)
    samples=[timed_run(exe,args,timeout) for _ in range(repetitions)]
    median=statistics.median(samples); mean=statistics.fmean(samples); stdev=statistics.stdev(samples) if len(samples)>1 else 0.0
    return {'samples_seconds':samples,'median_seconds':median,'mean_seconds':mean,'stdev_seconds':stdev,'coefficient_of_variation':stdev/mean if mean else float('inf')}

def perf_measure(exe:Path,args:list[str],timeout:int)->dict[str,int]:
    if shutil.which('perf') is None: return {}
    events=['cycles','instructions','branches','branch-misses','cache-references','cache-misses']
    p=subprocess.run(['perf','stat','-x,','-e',','.join(events),'--',str(exe),*args],timeout=timeout,text=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,check=False)
    result={}
    if p.returncode:
        return result
    for line in p.stderr.splitlines():
        parts=[x.strip() for x in line.split(',')]
        if len(parts)>=2:
            try: result[parts[1]]=int(parts[0].replace(',',''))
            except ValueError: pass
    return result
