"""Pass pipelines as editable trees, plus the mutation operators used by the search.

The expanded -O3 pipeline (opt -print-pipeline-passes) is parsed into a tree:
    function<eager-inv>( simplifycfg<...>, sroa<...>, loop-mssa( licm<...>, ... ), ... )
Every leaf gets a stable id. A Genome is a list of EDITS that reference those ids, so removing
one edit later (pass-minimization) leaves the others meaningful.

Edit ops:  del(id) | dup(id) | swap(id) | ins(after, pass, ctx) | knob(name, value) | backend(value)
Inserted passes come only from the pool of the same context (function/loop/cgscc/module...),
so pipelines stay structurally valid.

Action space v2 (methods random2 / evo2) adds, without changing v1's behaviour:
  param(id, tok, new)        flip one option of one pass instance, e.g. sink-common-insts -> no-...
  param_all(pass, tok, new)  flip it on every instance of that pass
  del_all(pass)              delete every instance of a pass
  llc knobs ("llc:-flag")    backend options passed to llc, plus more opt knobs and insertable passes
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path


# ---------------------------------------------------------------- tree
@dataclass
class Node:
    id: int
    text: str                                   # leaf: pass text; adaptor: head, e.g. "function<eager-inv>"
    children: list["Node"] | None = None        # None => leaf

    @property
    def is_leaf(self) -> bool:
        return self.children is None

    @property
    def ctx(self) -> str:
        return re.split(r"[<(]", self.text, maxsplit=1)[0]

    def render(self) -> str:
        if self.children is None:
            return self.text
        return f"{self.text}(" + ",".join(c.render() for c in self.children) + ")"


def split_top(s: str) -> list[str]:
    out, cur, depth, angle = [], [], 0, 0
    for ch in s:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif ch == "<":
            angle += 1
        elif ch == ">":
            angle -= 1
        if ch == "," and depth == 0 and angle == 0:
            out.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    if cur:
        out.append("".join(cur))
    return out


def _parse_elem(s: str, counter: list[int]) -> Node:
    angle = 0
    for i, ch in enumerate(s):
        if ch == "<":
            angle += 1
        elif ch == ">":
            angle -= 1
        elif ch == "(" and angle == 0 and s.endswith(")"):
            counter[0] += 1
            node = Node(counter[0], s[:i], [])
            node.children = [_parse_elem(x, counter) for x in split_top(s[i + 1:-1]) if x]
            return node
    counter[0] += 1
    return Node(counter[0], s)


def parse_pipeline(s: str) -> Node:
    counter = [0]
    root = Node(0, "module", [])
    root.children = [_parse_elem(x, counter) for x in split_top(s.strip()) if x]
    return root


def render(root: Node) -> str:
    return ",".join(c.render() for c in root.children)


def _walk(root: Node):
    """Yield (parent, index, node) for every node below root."""
    stack = [root]
    while stack:
        p = stack.pop()
        for i, ch in enumerate(p.children or []):
            yield p, i, ch
            if ch.children is not None:
                stack.append(ch)


def _ctx_of(parent: Node, root: Node) -> str:
    return "module" if parent is root else parent.ctx


def _find(root: Node, nid: int):
    for p, i, n in _walk(root):
        if n.id == nid:
            return p, i, n
    return None


def _prune_empty(root: Node) -> None:
    changed = True
    while changed:
        changed = False
        for p, i, n in list(_walk(root)):
            if n.children is not None and len(n.children) == 0:
                p.children.pop(i)
                changed = True
                break


# ---------------------------------------------------------------- genome
@dataclass
class Genome:
    edits: list[dict] = field(default_factory=list)
    raw: str | None = None                      # level seeds: a literal pipeline string

    def to_json(self) -> str:
        return json.dumps({"edits": self.edits, "raw": self.raw}, sort_keys=True)

    @staticmethod
    def from_json(s: str) -> "Genome":
        d = json.loads(s)
        return Genome(d["edits"], d["raw"])


def materialize(base: Node, g: Genome) -> tuple[str, tuple[str, ...], int]:
    """Apply edits to a copy of the base tree. Returns (pipeline string, opt flags, llc level)."""
    knobs: dict[str, object] = {}
    backend = 3
    root = copy.deepcopy(base) if g.raw is None else None
    for e in g.edits:
        op = e["op"]
        if op == "knob":
            knobs[e["name"]] = e["value"]
        elif op == "backend":
            backend = int(e["value"])
        elif root is None:
            continue
        else:
            _apply_struct(root, e)
    pipeline = g.raw if g.raw is not None else render(root)
    flags = tuple(f"{k}={v}" for k, v in sorted(knobs.items()))
    return pipeline, flags, backend


def cand_id(program_id: str, pipeline: str, flags: tuple[str, ...], backend: int) -> str:
    return hashlib.sha256(f"{program_id}|{pipeline}|{flags}|{backend}".encode()).hexdigest()[:16]


# ---------------------------------------------------------------- pools and knobs
EXTRA_PASSES = {
    "module": ["globaldce", "constmerge", "mergefunc", "strip-dead-prototypes", "elim-avail-extern",
               "ipsccp", "globalopt", "deadargelim", "argpromotion", "inline", "function-attrs"],
    "function": ["mldst-motion", "gvn-hoist", "sink", "nary-reassociate", "reassociate", "dse", "dce",
                 "adce", "bdce", "early-cse", "gvn", "instcombine", "simplifycfg", "jump-threading",
                 "correlated-propagation", "sccp", "aggressive-instcombine", "slp-vectorizer",
                 "loop-vectorize", "load-store-vectorizer", "loop-distribute", "loop-fusion",
                 "loop-load-elim", "loop-unroll-and-jam", "div-rem-pairs", "tailcallelim",
                 "speculative-execution", "flatten-cfg", "memcpyopt", "float2int", "vector-combine",
                 "instsimplify", "sroa", "loop-sink", "lcssa", "loop-simplify", "constraint-elimination"],
    "loop": ["loop-idiom", "indvars", "loop-deletion", "loop-unroll-full", "loop-flatten",
             "loop-interchange", "loop-predication", "loop-reduce", "loop-simplifycfg", "loop-instsimplify"],
    "loop-mssa": ["licm", "loop-rotate", "simple-loop-unswitch", "loop-simplifycfg"],
}
WRAP = {"module": "{x}", "function": "function({x})", "loop": "function(loop({x}))",
        "loop-mssa": "function(loop-mssa({x}))", "cgscc": "cgscc({x})"}
# v2 only (kept separate so v1 pools, knobs and RNG streams stay exactly as in earlier runs)
EXTRA_PASSES_V2 = {
    "module": ["partial-inliner", "hotcoldsplit", "called-value-propagation"],
    "function": ["dfa-jump-threading", "gvn-sink", "callsite-splitting", "loop-data-prefetch",
                 "separate-const-offset-from-gep", "libcalls-shrinkwrap"],
    "loop": ["loop-versioning-licm"],
}
KNOBS_V2 = {
    "-jump-threading-threshold": [3, 12],
    "-vectorizer-min-trip-count": [4, 32],
    "-unroll-runtime": ["false"],
    "-unroll-max-count": [2, 4],
    "-phi-node-folding-threshold": [1, 4],
    "-simplifycfg-sink-common": ["false"],
    "-simplifycfg-hoist-common": ["false"],
    "llc:-tail-dup-size": [1, 4, 6],
    "llc:-tail-dup-indirect-size": [3, 50],
    "llc:-enable-tail-merge": ["false"],
    "llc:-align-loops": [1, 32, 64],
    "llc:-x86-cmov-converter": ["false"],
    "llc:-enable-misched": ["false"],
    "llc:-min-jump-table-entries": [2, 16],
}
KNOBS = {
    "-inline-threshold": [0, 50, 100, 200, 250, 325, 400, 500, 1000],
    "-unroll-threshold": [0, 100, 200, 300, 450, 600, 1000],
    "-unroll-count": [1, 2, 4, 8],
    "-force-vector-width": [1, 2, 4, 8],
    "-force-vector-interleave": [1, 2, 4],
    "-slp-threshold": [-8, -4, 0, 4],
}


def _opt_accepts(opt: str, ir: Path, extra: list[str]) -> bool:
    r = subprocess.run([opt, *extra, "-disable-output", str(ir)], capture_output=True, text=True, timeout=60)
    return r.returncode == 0


def validate_extras(opt: str, workdir: Path, version: str) -> tuple[dict[str, list[str]], dict[str, list]]:
    """Keep only extras/knobs that this LLVM version actually accepts (cached on disk)."""
    cache = workdir / f"pools_llvm{version}.json"
    if cache.exists():
        d = json.loads(cache.read_text())
        return d["extras"], d["knobs"]
    ir = workdir / "tmp" / "pool_probe.ll"
    ir.parent.mkdir(parents=True, exist_ok=True)
    ir.write_text("define i32 @f(i32 %a) {\n  %b = add i32 %a, 1\n  ret i32 %b\n}\n")
    extras = {c: [p for p in ps if _opt_accepts(opt, ir, [f"-passes={WRAP[c].format(x=p)}"])]
              for c, ps in EXTRA_PASSES.items()}
    knobs = {k: vs for k, vs in KNOBS.items()
             if _opt_accepts(opt, ir, ["-passes=verify", f"{k}={vs[0]}"])}
    cache.write_text(json.dumps({"extras": extras, "knobs": knobs}, indent=1))
    return extras, knobs


def _llc_accepts(llc: str, ir: Path, flag: str) -> bool:
    r = subprocess.run([llc, flag, "-filetype=null", str(ir)], capture_output=True, text=True, timeout=60)
    return r.returncode == 0


def pass_name(text: str) -> str:
    return re.split(r"[<(]", text, maxsplit=1)[0]


def _opts(text: str) -> list[str]:
    m = re.match(r"^[^<]+<(.*)>$", text)
    return [t for t in m.group(1).split(";")] if m else []


def _with_opt(text: str, tok: str, new: str) -> str:
    opts = _opts(text)
    if tok not in opts:
        return text
    return f"{pass_name(text)}<" + ";".join(new if t == tok else t for t in opts) + ">"


_PAIRS = {"modify-cfg": "preserve-cfg", "preserve-cfg": "modify-cfg"}


def _flips(tok: str) -> list[str]:
    if not tok:
        return []
    if tok in _PAIRS:
        return [_PAIRS[tok]]
    if "=" in tok:
        k, _, v = tok.partition("=")
        if k == "bonus-inst-threshold":
            return [f"{k}={x}" for x in (0, 2, 4) if str(x) != v]
        if k == "max-iterations":
            return [f"{k}={x}" for x in (1, 2) if str(x) != v]
        return []
    if tok.startswith("O") and tok[1:].isdigit():       # loop-unroll<O3>: optimization level
        return [f"O{x}" for x in (1, 2, 3) if f"O{x}" != tok]
    return [tok[3:]] if tok.startswith("no-") else [f"no-{tok}"]


@dataclass
class Space:
    """v2 action space: v1 pools/knobs plus validated pass-option flips and extra knobs/passes."""
    pools: dict[str, list[str]]
    knobs: dict[str, list]
    params: list[dict]           # {"pass", "ctx", "tok", "new"}: flips opt accepted, per pass name
    multi: list[str]             # pass names with >= 2 instances (targets of del_all)


def build_space(base: Node, opt: str, llc: str, workdir: Path, version: str,
                pools: dict[str, list[str]], knobs: dict[str, list]) -> Space:
    cache = workdir / f"space_v2_llvm{version}.json"
    if cache.exists():
        d = json.loads(cache.read_text())
    else:
        ir = workdir / "tmp" / "pool_probe.ll"
        ir.parent.mkdir(parents=True, exist_ok=True)
        ir.write_text("define i32 @f(i32 %a) {\n  %b = add i32 %a, 1\n  ret i32 %b\n}\n")
        extras = {c: [p for p in ps if _opt_accepts(opt, ir, [f"-passes={WRAP[c].format(x=p)}"])]
                  for c, ps in EXTRA_PASSES_V2.items()}
        kn = {}
        for k, vs in KNOBS_V2.items():
            ok = _llc_accepts(llc, ir, f"{k[4:]}={vs[0]}") if k.startswith("llc:") else \
                _opt_accepts(opt, ir, ["-passes=verify", f"{k}={vs[0]}"])
            if ok:
                kn[k] = vs
        params, seen = [], set()
        for p, _i, n in _walk(base):
            if not n.is_leaf:
                continue
            ctx = _ctx_of(p, base)
            for tok in _opts(n.text):
                for new in _flips(tok):
                    key = (pass_name(n.text), ctx, tok, new)
                    if key in seen or ctx not in WRAP:
                        continue
                    seen.add(key)
                    if _opt_accepts(opt, ir, [f"-passes={WRAP[ctx].format(x=_with_opt(n.text, tok, new))}"]):
                        params.append({"pass": key[0], "ctx": ctx, "tok": tok, "new": new})
        d = {"extras": extras, "knobs": kn, "params": params}
        cache.write_text(json.dumps(d, indent=1))
    pl = {k: sorted(set(v) | set(d["extras"].get(k, []))) for k, v in pools.items()}
    for k, v in d["extras"].items():
        pl.setdefault(k, sorted(v))
    counts: dict[str, int] = {}
    for _p, _i, n in _walk(base):
        if n.is_leaf:
            counts[pass_name(n.text)] = counts.get(pass_name(n.text), 0) + 1
    skip = {"require", "invalidate", "verify", "annotation2metadata", "annotation-remarks"}
    return Space(pl, {**knobs, **d["knobs"]}, d["params"],
                 sorted(k for k, c in counts.items() if c >= 2 and k not in skip))


def build_pools(base: Node, extras: dict[str, list[str]]) -> dict[str, list[str]]:
    pools: dict[str, set[str]] = {}
    for p, _i, n in _walk(base):
        if n.is_leaf:
            pools.setdefault(_ctx_of(p, base), set()).add(n.text)
    for ctx, ps in extras.items():
        pools.setdefault(ctx, set()).update(ps)
    return {k: sorted(v) for k, v in pools.items()}


# ---------------------------------------------------------------- mutation
def _leaves(root: Node):
    return [(p, i, n) for p, i, n in _walk(root) if n.is_leaf]


def random_edit(base: Node, g: Genome, pools: dict[str, list[str]], knobs: dict[str, list], rng) -> dict:
    """One random edit that is meaningful for the genome's current materialized tree."""
    root = copy.deepcopy(base)
    # replay structural edits so we can reference inserted nodes
    for e in g.edits:
        if e["op"] in ("del", "dup", "swap", "ins"):
            _apply_struct(root, e)
    leaves = _leaves(root)
    r = rng.random()
    nid = rng.randrange(10**6, 10**9)
    if r < 0.30 and leaves:
        return {"op": "del", "id": rng.choice(leaves)[2].id}
    if r < 0.45 and leaves:
        return {"op": "dup", "id": rng.choice(leaves)[2].id, "nid": nid}
    if r < 0.60:
        cand = [n for p, i, n in leaves if i + 1 < len(p.children) and p.children[i + 1].is_leaf]
        if cand:
            return {"op": "swap", "id": rng.choice(cand).id}
    if r < 0.85 and leaves:
        p, i, n = rng.choice(leaves)
        ctx = _ctx_of(p, root)
        pool = pools.get(ctx) or []
        if pool:
            return {"op": "ins", "after": n.id, "pass": rng.choice(pool), "ctx": ctx, "nid": nid}
    if r < 0.96 and knobs:
        k = rng.choice(sorted(knobs))
        return {"op": "knob", "name": k, "value": rng.choice(knobs[k])}
    return {"op": "backend", "value": rng.choice([0, 1, 2, 3])}


def random_edit_v2(base: Node, g: Genome, sp: Space, rng) -> dict:
    """v2 mutation: v1 ops plus pass-option flips, family-wide edits and backend knobs."""
    root = copy.deepcopy(base)
    for e in g.edits:
        if e["op"] not in ("knob", "backend"):
            _apply_struct(root, e)
    leaves = _leaves(root)
    r = rng.random()
    if r < 0.15 and sp.params:
        # pick a flip whose token is present on some current leaf of that pass
        for _ in range(8):
            f = rng.choice(sp.params)
            hits = [n for _p, _i, n in leaves if pass_name(n.text) == f["pass"] and f["tok"] in _opts(n.text)]
            if hits:
                return {"op": "param", "id": rng.choice(hits).id, "tok": f["tok"], "new": f["new"]}
    if r < 0.27 and sp.params:
        f = rng.choice(sp.params)
        return {"op": "param_all", "pass": f["pass"], "tok": f["tok"], "new": f["new"]}
    if r < 0.32 and sp.multi:
        return {"op": "del_all", "pass": rng.choice(sp.multi)}
    if r < 0.45 and sp.knobs:
        k = rng.choice(sorted(sp.knobs))
        return {"op": "knob", "name": k, "value": rng.choice(sp.knobs[k])}
    return random_edit(base, g, sp.pools, sp.knobs, rng)


def _apply_struct(root: Node, e: dict) -> None:
    op = e["op"]
    if op == "param":
        hit = _find(root, e["id"])
        if hit and hit[2].is_leaf:
            hit[2].text = _with_opt(hit[2].text, e["tok"], e["new"])
        return
    if op == "param_all":
        for _p, _i, n in _walk(root):
            if n.is_leaf and pass_name(n.text) == e["pass"]:
                n.text = _with_opt(n.text, e["tok"], e["new"])
        return
    if op == "del_all":
        for p, i, n in reversed(list(_walk(root))):
            if n.is_leaf and pass_name(n.text) == e["pass"]:
                p.children.remove(n)
        _prune_empty(root)
        return
    if op == "del":
        hit = _find(root, e["id"])
        if hit and hit[2].is_leaf:
            hit[0].children.pop(hit[1])
            _prune_empty(root)
    elif op == "dup":
        hit = _find(root, e["id"])
        if hit and hit[2].is_leaf:
            hit[0].children.insert(hit[1] + 1, Node(e["nid"], hit[2].text))
    elif op == "swap":
        hit = _find(root, e["id"])
        if hit and hit[2].is_leaf and hit[1] + 1 < len(hit[0].children) and hit[0].children[hit[1] + 1].is_leaf:
            ch = hit[0].children
            ch[hit[1]], ch[hit[1] + 1] = ch[hit[1] + 1], ch[hit[1]]
    elif op == "ins":
        hit = _find(root, e["after"])
        if hit and _ctx_of(hit[0], root) == e["ctx"]:
            hit[0].children.insert(hit[1] + 1, Node(e["nid"], e["pass"]))


def random_genome(base, pools, knobs, rng, max_edits: int = 6, space: Space | None = None) -> Genome:
    g = Genome([])
    k = 1
    while k < max_edits and rng.random() < 0.7:
        k += 1
    for _ in range(k):
        g.edits.append(random_edit_v2(base, g, space, rng) if space else random_edit(base, g, pools, knobs, rng))
    return g
