// Plain-language explanations of pipeline edits (genome ops) and LLVM passes / knobs.
const PASS = {
  "simplifycfg": "simplifies the control-flow graph (merges blocks, removes dead branches)",
  "instcombine": "combines and simplifies instructions (peephole optimizer)",
  "instsimplify": "simplifies instructions without creating new ones",
  "licm": "hoists loop-invariant code out of loops",
  "loop-unroll": "unrolls loops (repeats the body to cut loop overhead)",
  "loop-unroll-full": "fully unrolls loops with small constant trip counts",
  "loop-vectorize": "turns loops into SIMD vector code",
  "slp-vectorizer": "packs independent scalar operations into vector instructions",
  "vector-combine": "cleans up and combines vector operations",
  "inline": "inlines function calls",
  "always-inline": "inlines functions marked always_inline",
  "gvn": "removes redundant computations (global value numbering)",
  "sroa": "breaks aggregates into scalars kept in registers",
  "early-cse": "early common-subexpression elimination",
  "jump-threading": "threads jumps through predictable branches",
  "dfa-jump-threading": "threads jumps in state machines (switch in a loop)",
  "loop-rotate": "rotates loops into do-while form for later passes",
  "loop-instsimplify": "simplifies instructions inside loops",
  "loop-simplifycfg": "simplifies control flow inside loops",
  "loop-deletion": "deletes loops with no effect",
  "loop-idiom": "recognizes loop idioms (memset, memcpy)",
  "indvars": "canonicalizes loop induction variables",
  "simple-loop-unswitch": "moves loop-invariant conditions out of loops",
  "correlated-propagation": "propagates value ranges from conditions",
  "reassociate": "reorders arithmetic to expose optimizations",
  "dse": "removes dead stores",
  "memcpyopt": "optimizes memcpy/memset calls",
  "tailcallelim": "turns tail calls into loops",
  "sccp": "sparse conditional constant propagation",
  "ipsccp": "interprocedural constant propagation",
  "globalopt": "optimizes global variables",
  "globaldce": "removes unused globals and functions",
  "function-attrs": "infers function attributes (readonly, nounwind, ...)",
  "forceattrs": "applies forced function attributes",
  "argpromotion": "passes pointer arguments by value",
  "mldst-motion": "sinks/hoists loads and stores around diamonds",
  "bdce": "bit-tracking dead code elimination",
  "adce": "aggressive dead code elimination",
  "div-rem-pairs": "combines division and remainder",
  "loop-load-elim": "removes redundant loads across loop iterations",
  "loop-distribute": "splits loops so parts can vectorize",
  "constraint-elimination": "removes conditions proven by earlier checks",
  "gvn-sink": "sinks common code out of branches",
  "callsite-splitting": "splits call sites to specialize arguments",
  "partial-inliner": "inlines the early-exit part of functions",
  "hotcoldsplit": "moves cold code into separate functions",
  "loop-versioning-licm": "versions loops to hoist more code",
  "loop-data-prefetch": "inserts software prefetches",
  "infer-alignment": "infers memory alignment",
  "aggressive-instcombine": "expensive instruction combines",
  "float2int": "turns float math into integer math when exact",
  "loop-sink": "sinks code into colder loop paths",
  "speculative-execution": "hoists cheap code speculatively",
};

const KNOB = {
  "-force-vector-width": (v) => [`loop vectorizer: force vector width ${v}`, `pack ${v} values per SIMD instruction instead of the cost model's choice`],
  "-force-vector-interleave": (v) => [`loop vectorizer: interleave ${v}×`, `run ${v} vector iterations side by side`],
  "-unroll-count": (v) => [`unroll loops ${v}× (forced)`, v == 1 ? "disables unrolling" : `repeat loop bodies ${v} times`],
  "-unroll-max-count": (v) => [`unroll at most ${v}×`, "caps the unroller's choice"],
  "-unroll-threshold": (v) => [`unroll size budget ${v}`, "how large an unrolled loop may get"],
  "-unroll-runtime": (v) => [`runtime unrolling ${v === "false" ? "off" : "on"}`, "unrolling of loops with unknown trip counts"],
  "-inline-threshold": (v) => [`inline threshold ${v}`, `-O3 uses 250; higher inlines more, lower inlines less`],
  "-slp-threshold": (v) => [`SLP vectorizer threshold ${v}`, "lower = vectorize straight-line code more eagerly"],
  "-jump-threading-threshold": (v) => [`jump threading size limit ${v}`, "how much code may be duplicated to thread jumps"],
  "-vectorizer-min-trip-count": (v) => [`vectorize loops with ≥ ${v} iterations`, "minimum trip count for vectorization"],
  "-phi-node-folding-threshold": (v) => [`phi folding threshold ${v}`, "how eagerly branches become selects"],
  "-simplifycfg-sink-common": (v) => [`SimplifyCFG: sinking common code ${v === "false" ? "off" : "on"}`, "the evalloop fix: keeps per-opcode dispatch jumps"],
  "-simplifycfg-hoist-common": (v) => [`SimplifyCFG: hoisting common code ${v === "false" ? "off" : "on"}`, ""],
  "llc:-tail-dup-size": (v) => [`backend: tail duplication size ${v}`, "duplicates small block tails to remove jumps (default 2)"],
  "llc:-tail-dup-indirect-size": (v) => [`backend: tail duplication of indirect jumps ${v}`, "duplicates blocks ending in indirect jumps"],
  "llc:-enable-tail-merge": (v) => [`backend: tail merging ${v === "false" ? "off" : "on"}`, "merging identical block tails"],
  "llc:-align-loops": (v) => [`backend: align loops to ${v} bytes`, "code alignment of loop headers (default 16)"],
  "llc:-x86-cmov-converter": (v) => [`backend: cmov→branch conversion ${v === "false" ? "off" : "on"}`, "keeps conditional moves"],
  "llc:-enable-misched": (v) => [`backend: machine scheduler ${v === "false" ? "off" : "on"}`, "instruction scheduling"],
  "llc:-min-jump-table-entries": (v) => [`backend: jump tables from ${v} cases`, "when a switch becomes a jump table"],
};

export function passInfo(name) { return PASS[name] || ""; }

// leaves: { id: {name, text, ctx} } from /api/o3tree
export function describe(e, leaves = {}) {
  const leaf = (id) => leaves[id] || leaves[String(id)] || { name: `pass #${id}`, ctx: "?" };
  switch (e.op) {
    case "knob": {
      const f = KNOB[e.name];
      const [w, why] = f ? f(e.value) : [`${e.name.replace("llc:", "backend ")} = ${e.value}`, ""];
      return { kind: e.name.startsWith("llc:") ? "llc" : "knob", label: e.name.startsWith("llc:") ? "backend" : "knob", what: w, why };
    }
    case "backend": return { kind: "lvl", label: "backend", what: `code generator at -O${e.value}`, why: "-O3 uses llc -O3" };
    case "del": { const l = leaf(e.id); return { kind: "del", label: "remove", what: `${l.name}  (${l.ctx} stage)`, why: passInfo(l.name) }; }
    case "dup": { const l = leaf(e.id); return { kind: "dup", label: "repeat", what: `run ${l.name} twice  (${l.ctx})`, why: passInfo(l.name) }; }
    case "swap": { const l = leaf(e.id); return { kind: "swap", label: "reorder", what: `swap ${l.name} with the next pass  (${l.ctx})`, why: "changes pass order" }; }
    case "ins": { const n = e.pass.split(/[<(]/)[0]; const a = leaf(e.after); return { kind: "ins", label: "add", what: `${n} after ${a.name}  (${e.ctx})`, why: passInfo(n) }; }
    case "param": { const l = leaf(e.id); return { kind: "flip", label: "option", what: `${l.name}: ${e.tok} → ${e.new}`, why: "changes one option of one pass instance" }; }
    case "param_all": return { kind: "flip", label: "option ×all", what: `every ${e.pass}: ${e.tok} → ${e.new}`, why: passInfo(e.pass) };
    case "del_all": return { kind: "del", label: "remove all", what: `every ${e.pass}`, why: passInfo(e.pass) };
    default: return { kind: "lvl", label: e.op, what: JSON.stringify(e), why: "" };
  }
}

export function genomeSummary(edits, leaves) {
  return (edits || []).filter((e) => !(e.op === "backend" && e.value === 3)).map((e) => describe(e, leaves));
}
