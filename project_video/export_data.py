#!/usr/bin/env python3
"""Export the real project numbers used by the animations to src/data.json (run from project_video/)."""
import json, random, re, urllib.request
from pathlib import Path
R = Path(__file__).resolve().parent.parent
D = json.loads((R / "dashboard/static/data/research.json").read_text())
ev = D["eval"]["summary"]
order = ["tune RL + SL", "tune top-8 (SL)", "random search@8", "RL only", "GA@8", "random top-8", "-O2", "-Os"]
bars = [{"name": k, "v": ev[k]["geomean"], "lo": ev[k]["ci"][0], "hi": ev[k]["ci"][1], "slower": ev[k]["slower"]} for k in order]
random.seed(1)
pts = [p for p in D["ir"]["sample"] if 0.5 <= p[0] <= 2.0 and 0.5 <= p[1] <= 2.0]
pts = random.sample(pts, 1100)
kb = next(r for r in D["kb"]["top"] if r["label"] == "-unroll-count=2")
# the real -O3 pass names, in order, from the pipeline printed by opt (saved in a tune report)
saved = json.loads((R / "dashboard/saved/tune-interpreter-loop-3-83x-rl-pick.json").read_text())["result"]
names = re.sub(r"<[^<>]*>", "", saved["o3_pipeline"])
names = [n for n in re.split(r"[(),]+", names) if n and not n.startswith(("function", "cgscc", "loop", "devirt")) or n.startswith("loop-")]
out = {"bars": bars, "ir": {"n": D["ir"]["n"], "rho": D["ir"]["rho"], "pts": pts},
       "kb": {"label": kb["label"], "programs": kb["programs"], "faster": kb["faster"], "slower": kb["slower"]},
       "passes": names, "headline": D["headline"]["tune_rlsl"],
       "demo": {"o3": saved["confirm"].get("base_median_ms"), "pick": saved["confirm"]["pick_median_ms"], "speedup": saved["confirm"]["speedup"],
                "edits": saved["shipped_edits"], "from": saved["shipped_from"]}}
(Path(__file__).parent / "src/data.json").write_text(json.dumps(out))
print(len(names), names[:12]); print(out["kb"], out["demo"]); print(len(pts))
