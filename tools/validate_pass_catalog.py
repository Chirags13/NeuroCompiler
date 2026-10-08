#!/usr/bin/env python3
"""Validate each declared new-pass-manager pipeline against installed opt."""
from __future__ import annotations
import argparse, json, subprocess, tempfile
from pathlib import Path
SMOKE_IR = "define i32 @main() {\nentry:\n  ret i32 0\n}\n"
def main() -> int:
    p=argparse.ArgumentParser(); p.add_argument('--catalog',type=Path,default=Path('data/pass_catalog.json')); a=p.parse_args()
    catalog=json.loads(a.catalog.read_text()); failures=[]
    with tempfile.TemporaryDirectory() as td:
        ir=Path(td)/'smoke.ll'; ir.write_text(SMOKE_IR)
        for item in catalog['passes']:
            cmd=['opt',f"-passes={item['pipeline']}",str(ir),'-disable-output']
            proc=subprocess.run(cmd,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            if proc.returncode: failures.append({'id':item['id'],'pipeline':item['pipeline'],'stderr':proc.stderr.strip()[-1000:]})
    print(json.dumps({'valid':not failures,'failures':failures} if failures else {'valid':True,'passes':len(catalog['passes'])},indent=2))
    return 1 if failures else 0
if __name__=='__main__': raise SystemExit(main())
