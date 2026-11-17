"""Prepare real data for the Open Day deck. Run with the project's .venv from the repo root.
Writes open_day/assets/pipeline_order.json: the LLVM 18 default<O3> pipeline in execution order, one entry per
pass step, grouped for colouring. Reads open_day/assets/o3_pipeline_llvm18.txt (printed by opt)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, ".")
from nc.pipeline import parse_pipeline, pass_name  # noqa: E402

GROUPS = {
    "vector": {"loop-vectorize", "slp-vectorizer", "vector-combine", "infer-alignment", "inject-tli-mappings"},
    "loop": {"licm", "loop-rotate", "loop-deletion", "loop-unroll", "loop-unroll-full", "loop-idiom", "indvars",
             "loop-instsimplify", "loop-simplifycfg", "simple-loop-unswitch", "loop-distribute", "loop-load-elim",
             "loop-sink"},
    "cleanup": {"simplifycfg", "instcombine", "aggressive-instcombine", "instsimplify", "sroa", "mem2reg", "early-cse",
                "gvn", "sccp", "bdce", "adce", "dse", "memcpyopt", "reassociate", "jump-threading",
                "correlated-propagation", "tailcallelim", "constraint-elimination", "mldst-motion",
                "div-rem-pairs", "speculative-execution"},
    "inter": {"inline", "always-inline", "argpromotion", "function-attrs", "rpo-function-attrs", "globalopt", "globaldce",
              "ipsccp", "deadargelim", "called-value-propagation", "constmerge", "elim-avail-extern", "inferattrs",
              "forceattrs", "openmp-opt", "openmp-opt-cgscc", "recompute-globalsaa"},
}


def walk(n):
    if n.is_leaf:
        yield n
    else:
        for c in n.children:
            yield from walk(c)


root = parse_pipeline(Path("open_day/assets/o3_pipeline_llvm18.txt").read_text().strip())
root = root[0] if isinstance(root, tuple) else root
out = []
for leaf in walk(root):
    nm = pass_name(leaf.text)
    g = next((k for k, v in GROUPS.items() if nm in v), "other")
    out.append({"name": nm, "group": g})
Path("open_day/assets/pipeline_order.json").write_text(json.dumps(out, indent=0))
print(len(out), len({o["name"] for o in out}), [o["name"] for o in out[:12]], {g: sum(o["group"] == g for o in out) for g in ["vector", "loop", "cleanup", "inter", "other"]})
