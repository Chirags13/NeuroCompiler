#!/usr/bin/env python3
"""Create a reproducibility manifest with hashes for dataset artifacts."""

from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path

def sha256(path: Path) -> str:
    h=hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""): h.update(chunk)
    return h.hexdigest()

def main() -> None:
    ap=argparse.ArgumentParser(); ap.add_argument("root",type=Path); ap.add_argument("--output",type=Path,default=None); a=ap.parse_args()
    rows=[]
    for p in sorted(a.root.rglob("*")):
        if p.is_file() and p.name not in {"hash_manifest.json"}:
            rows.append({"path":str(p.relative_to(a.root)),"bytes":p.stat().st_size,"sha256":sha256(p)})
    out=a.output or a.root/"hash_manifest.json"; out.write_text(json.dumps({"files":rows},indent=2),encoding="utf-8")
    print(out)

if __name__=="__main__": main()
