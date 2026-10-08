#!/usr/bin/env python3
"""Check host tools required to generate runtime data."""
from __future__ import annotations
import json, shutil, subprocess
REQUIRED=['clang','opt','llvm-dis','llvm-size','llvm-link']; OPTIONAL=['perf']
def version(tool):
    p=subprocess.run([tool,'--version'],text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    return p.stdout.splitlines()[0] if p.returncode==0 and p.stdout else 'unknown'
result={'required':{x:shutil.which(x) is not None for x in REQUIRED},'optional':{x:shutil.which(x) is not None for x in OPTIONAL},'versions':{x:version(x) for x in REQUIRED+OPTIONAL if shutil.which(x)}}
print(json.dumps(result,indent=2)); raise SystemExit(0 if all(result['required'].values()) else 1)
