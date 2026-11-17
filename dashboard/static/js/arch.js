// Architecture page: clickable system diagram + detail drawer, the two runtime flows, edit types, stack, limits.
import { esc, h, icon } from "./util.js";

const K = {
  data: { c: "#22d3ee", n: "data & measurement" }, learn: { c: "#f472b6", n: "learning" },
  run: { c: "#60a5fa", n: "per-program deployment" }, ui: { c: "#94a3b8", n: "interfaces & environment" },
};

const N = [
  // lane 1: data & measurement
  { id: "sources", k: "data", x: 30, y: 62, t: "Benchmark sources", s: "PolyBench · LLVM test-suite",
    what: "Open-source C/C++ benchmarks with known licences: PolyBench/C 4.2 kernels and the LLVM test-suite (SingleSource and MultiSource, including C++ programs).",
    kv: [["candidates", "347 programs"], ["suites", "polybench 30 · singlesource 41 · multisource 75 (usable)"]], files: ["corpus/manifest.jsonl", "scripts/fetch_*"] },
  { id: "corpus", k: "data", x: 245, y: 62, t: "Corpus builder", s: "build · run · filter · split",
    what: "Builds each program at -O0…-O3/-Os, runs it, checks the output is deterministic and identical across levels, and keeps programs that run 0.1–10 s at -O3. Programs are grouped into families (shared code) and split by family into train / validation / test, frozen before modelling.",
    kv: [["usable", "146 programs, 35 families"], ["split", "train 91 · val 22 · test 33 (11 families)"], ["rejected", "201 (too fast 130, no output 25, build fail 22, …)"]], files: ["nc/corpus.py", "corpus/split.json"] },
  { id: "harness", k: "data", x: 460, y: 62, t: "Timing harness", s: "pinned · interleaved · A/A",
    what: "Every speedup is measured, not estimated: binaries run interleaved on an isolated CPU with an idle SMT sibling; a byte-identical copy of -O3 (A/A control) detects bias; paired bootstrap gives 95% CIs. A quiet guard pauses while other processes load the machine. Screening uses 3 parallel cores with a memory-aware scheduler; everything reported is re-measured serially.",
    kv: [["selftest", "A/A bias ≤ 0.3%, CI ±0.12% at 420 ms"], ["parallel", "3 cores (2, 6, 10), ≤ 1 memory-heavy program"], ["rule", "win = CI lower bound > 1"]], files: ["nc/timing.py", "nc/parallel.py", "results/selftest_*.json", "results/aatest_*.json"] },
  { id: "search", k: "data", x: 675, y: 62, t: "Pipeline search", s: "GA · evolution · random",
    what: "Explores edits to the explicit -O3 pipeline (LLVM 18 new pass manager) per training program: random search, a genetic algorithm and an evolutionary search (evo/evo2), plus a single-edit knowledge base (346 edits on 31 programs). Every candidate's output is verified against -O0.",
    kv: [["headroom", "+15.6% geomean on 115 unseen programs (Phase 5)"], ["≥ +5%", "54 / 115 programs"], ["artifact check", "cachegrind: work actually done"]], files: ["nc/search.py", "nc/pipeline.py", "nc/passkb.py"] },
  { id: "db", k: "data", x: 890, y: 62, w: 200, t: "Dataset", s: "dataset.sqlite · results/",
    what: "All candidates, builds, measurements (screen / confirm / validate stages), features and evaluation results in SQLite, with machine_id tags. The labels for learning are validated log-speedups vs -O3, capped at |log 3|; noisy-control programs are down-weighted (0.3).",
    kv: [["measurements", "≈ 18,600 candidates with IR + runtime"], ["labels", "log speedup vs -O3"]], files: ["results/dataset.sqlite", "results/predict.sqlite", "nc/store.py"] },
  // lane 2: learning
  { id: "features", k: "learn", x: 30, y: 252, t: "Program features", s: "static · scan · sim · remarks",
    what: "What the models know about a program: 111 static IR statistics (instruction mix, loops, calls, memory), 9 scan features (runtime at each -O level, spread, size), 13 cachegrind simulations (labelled simulated, x86-64-v3 builds), and 36 optimization-remark counts from -O3 (predict only).",
    kv: [["static", "111"], ["scan", "9 (needs running)"], ["sim", "11 + 2 (L2)"], ["remarks", "36 (compile-only)"]], files: ["nc/features.py", "nc/remarks.py"] },
  { id: "surrogate", k: "learn", x: 245, y: 252, t: "Supervised surrogate", s: "LightGBM ranker",
    what: "Predicts log-speedup vs -O3 from program features and a pipeline's edit encoding. Trained on the training families only and cross-validated by family. Its job in tune is ranking ~940 candidate pipelines so only the top 8 need to be timed.",
    kv: [["held-out ρ", "+0.11 (weak but > random)"], ["gate 7B", "beats random top-k (narrowly)"], ["used by", "tune (rank) and RL (reward)"]], files: ["nc/model.py", "results/models/tune/MANIFEST.json"] },
  { id: "rl", k: "learn", x: 460, y: 252, t: "RL agent (PPO)", s: "builds edit sequences",
    what: "A policy network (numpy PPO) that builds a pipeline edit by edit (horizon 4, 120 actions) for a given program, rewarded by the surrogate's predicted speedup. At deployment it proposes 24 pipelines that are pooled with the library and ranked by the surrogate (RL + SL).",
    kv: [["alone", "+3.3% on test (−4.2% vs top-8)"], ["RL + SL", "+8.1% on test (+0.2% vs SL, n.s.)"], ["final version", "RL + SL (user decision)"]], files: ["nc/rl.py", "results/models/rl_policy*.npz"] },
  { id: "library", k: "learn", x: 675, y: 252, t: "Pipeline library", s: "≈ 913 proven pipelines",
    what: "Winning pipelines found by search on training programs plus random pipelines: the candidate pool that the surrogate ranks for a new program. Contains only pipelines from training families.",
    kv: [["size", "≈ 913 + 300 random"], ["source", "training programs only"]], files: ["nc/deploy.py (library)"] },
  { id: "pens", k: "learn", x: 890, y: 252, w: 200, t: "Predict models", s: "7 LightGBM + harm model",
    what: "A separate, compile-only model family: a 7-member LightGBM ensemble on static + remark features predicts speedup for each pipeline in a safe pool (164 single edits + 776 pairs that never caused wrong output and rarely harm); a classifier estimates the probability of a slowdown. Has its own PPO agent.",
    kv: [["train ρ", "0.42"], ["held-out ρ", "0.11"], ["gate", "pessimistic > 1.03, agree ≥ 80%, harm < 0.5"]], files: ["nc/predict.py", "results/models/predict/MANIFEST.json"] },
  // lane 3: deployment
  { id: "user", k: "run", x: 30, y: 470, t: "Your program", s: "C/C++ · args · stdin",
    what: "Any deterministic C/C++ program with a main() that prints its result. Several source files are linked together. Arguments and a stdin file define the workload used for both verification and timing.",
    kv: [["runtime", "≈ 0.1–10 s at -O3 for tune"], ["verified", "output must equal the -O0 build's"]], files: ["bin/neurocompiler"] },
  { id: "toolchain", k: "run", x: 245, y: 470, t: "LLVM toolchain", s: "clang -O0 IR → opt → llc",
    what: "LLVM 18.1.8 pinned. clang emits unoptimized IR; opt runs the explicit -O3 pass pipeline string (with edits applied: delete, repeat, reorder, insert passes, change pass options, knobs); llc generates code with optional backend flags; clang links. -O3's own inliner flags are restored so the explicit pipeline equals -O3 exactly.",
    kv: [["-O3 pipeline", "109 leaf passes"], ["cache", "builds cached by hash"]], files: ["nc/toolchain.py", "nc/pipeline.py"] },
  { id: "tune", k: "run", x: 460, y: 430, t: "Tune (RL + SL)", s: "propose · rank · top-8",
    what: "RL proposes 24 pipelines, pooled with the library (~940); the surrogate ranks them; candidates are compiled in ranked order until 8 distinct binaries with verified output exist.",
    kv: [["test result", "+8.1% geomean, 0 slower, 9/33 ≥ +5%"], ["time", "≈ 1–10 min per program"]], files: ["nc/deploy.py", "nc/cli.py tune"] },
  { id: "timing", k: "run", x: 690, y: 430, t: "Time + confirm", s: "8 vs -O3 · then confirm",
    what: "The 8 binaries and -O3 are timed interleaved (10 rounds). The fastest must then win a fresh confirmation run (20 rounds, with an A/A control) with CI lower bound > 1.01; this removes the winner's-curse bias of picking the best of 8.",
    kv: [["ship rule", "confirmed CI > 1.01 and clean control"], ["else", "-O3"]], files: ["nc/deploy.py select_topk"] },
  { id: "predict", k: "run", x: 460, y: 525, t: "Predict", s: "choose blind · then measure 1",
    what: "Builds -O3, collects optimization remarks and static features, scores the safe pool + RL proposals with the 7-model ensemble and harm classifier, and applies the gate (no runs). Then its top pick is compiled, output-checked and timed once against -O3 (20 rounds + A/A) so you see the real result; this measurement never changes the choice. Advisory: writes -O3 unless --apply.",
    kv: [["test result", "+0.64% (CI −0.2…+2.1%), 1 slower"], ["time", "+0.6 s median over -O3"]], files: ["nc/predict.py", "nc/cli.py predict"] },
  { id: "gate", k: "run", x: 690, y: 525, t: "Safety gate", s: "3 checks or -O3",
    what: "Ships a prediction only if the pessimistic estimate (mean − 1.28·std across members) beats 1.03×, ≥ 80% of members predict a gain, and the harm probability is below 0.5. Thresholds chosen on out-of-fold data before the test.",
    kv: [["OOF", "13 shipped, 2 regressions of 107"]], files: ["nc/predict.py decide"] },
  { id: "out", k: "run", x: 920, y: 478, w: 170, t: "Binary", s: "candidate or -O3",
    what: "The output executable plus a JSON report: chosen pipeline and edits, -O3 pipeline, speedups with CIs, runtimes in ms, every timed candidate. -O3 is always the fallback, so the result is never knowingly slower.",
    kv: [["report", "<out>.json"]], files: ["work/…/prog, prog.json"] },
  // lane 4: interfaces
  { id: "wsl", k: "ui", x: 30, y: 655, t: "WSL2 environment", s: "Ubuntu · 14 vCPU · 10 GB",
    what: "Everything runs in WSL2 on a Ryzen 9 270 laptop. Timing uses pinned vCPUs with idle siblings. The Windows launcher boots WSL and starts the dashboard.",
    kv: [["timing CPU", "6 (serial), 2/6/10 (parallel)"], ["machine_id", "wsl2-ryzen9-270(-v14)"]], files: ["dashboard/windows/Start-NeuroCompiler.bat", ".wslconfig"] },
  { id: "cli", k: "ui", x: 245, y: 655, t: "CLI", s: "tune · predict · compare",
    what: "A drop-in style command: neurocompiler tune prog.c --args … --out prog. Research commands (corpus, search, model train, rl train, evaluate) live in python -m nc.cli.",
    kv: [["modes", "tune (default), predict, compare"]], files: ["bin/neurocompiler", "nc/cli.py", "RUN.md"] },
  { id: "dash", k: "ui", x: 460, y: 655, t: "Dashboard", s: "FastAPI · SSE · this page",
    what: "A local web app: submit programs, a single-worker job queue (so timings never overlap), live terminal output over Server-Sent Events, result views, saved runs and this research/architecture documentation.",
    kv: [["server", "uvicorn on 127.0.0.1:8000"], ["front-end", "vanilla JS, Chart.js, CodeMirror — offline"]], files: ["dashboard/server.py", "dashboard/static/"] },
  { id: "freeze", k: "ui", x: 675, y: 655, t: "Frozen models", s: "MANIFEST hashes",
    what: "Tune and predict load their model files only through MANIFEST.json with SHA-256 hashes; tune refuses to run if anything changed. A regression check confirms tune's top-8 is byte-identical before and after any change.",
    kv: [["check", "scripts/tune_regression_check.py"]], files: ["nc/tunelock.py", "results/models/*/MANIFEST.json"] },
  { id: "reports", k: "ui", x: 890, y: 655, w: 200, t: "Reports", s: "reproducible from scripts",
    what: "Every reported number is produced by a script from result files in the repo: gate reports, Phase 5 report, evaluation tables, the final report and this dashboard's data export.",
    kv: [["final", "results/FINAL_REPORT.md"]], files: ["scripts/*.py", "results/*.txt|json"] },
];

const E = [
  ["sources", "corpus"], ["corpus", "harness"], ["harness", "search"], ["search", "db"],
  ["db", "library", "down"], ["db", "pens", "down"], ["db", "surrogate", "over"], ["features", "surrogate"], ["surrogate", "rl", null, "reward"],
  ["user", "toolchain"], ["toolchain", "tune"], ["toolchain", "predict"], ["tune", "timing"], ["timing", "out"], ["predict", "gate"], ["gate", "out"],
  ["surrogate", "tune", "model"], ["rl", "tune", "model"], ["library", "tune", "model"], ["pens", "predict", "model"],
  ["dash", "user", "ui"], ["cli", "user", "ui"],
];

const LANES = [[20, 20, 172, "1 · data & measurement (offline)", "data"], [20, 210, 172, "2 · learning (offline)", "learn"],
  [20, 400, 200, "3 · deployment, per program (online)", "run"], [20, 618, 128, "4 · interfaces & environment", "ui"]];

const W = 175, H = 64;
const box = (n) => ({ x: n.x, y: n.y, w: n.w || W, h: H });

function svg() {
  const byId = Object.fromEntries(N.map((n) => [n.id, n]));
  let s = `<svg class="arch-svg" viewBox="0 0 1110 760" xmlns="http://www.w3.org/2000/svg">
  <defs><marker id="ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" fill="#5c6680"/></marker>
  <marker id="ahm" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" fill="#f472b6"/></marker></defs>`;
  for (const [x, y, hh, label, k] of LANES) {
    s += `<rect x="${x}" y="${y}" width="1080" height="${hh}" rx="14" fill="${K[k].c}" fill-opacity=".035" stroke="${K[k].c}" stroke-opacity=".18"/>
      <text x="${x + 14}" y="${y + 22}" fill="${K[k].c}" font-size="11.5" font-weight="650" letter-spacing=".08em" style="text-transform:uppercase">${label.toUpperCase()}</text>`;
  }
  for (const [a, b, kind, label] of E) {
    const A = box(byId[a]), B = box(byId[b]);
    let d;
    const model = kind === "model";
    if (kind === "down") d = `M${A.x + A.w / 2 + (b === "library" ? -40 : 0)} ${A.y + A.h} C ${A.x + A.w / 2 - (b === "library" ? 60 : 0)} ${A.y + A.h + 60}, ${B.x + B.w / 2} ${B.y - 60}, ${B.x + B.w / 2} ${B.y}`;
    else if (kind === "over") d = `M${A.x + 30} ${A.y + A.h} L${A.x + 30} ${A.y + A.h + 42} L${B.x + B.w / 2} ${A.y + A.h + 42} L${B.x + B.w / 2} ${B.y}`;
    else if (model) d = `M${A.x + A.w / 2} ${A.y + A.h} C ${A.x + A.w / 2} ${A.y + A.h + 70}, ${B.x + B.w / 2} ${B.y - 70}, ${B.x + B.w / 2 + (a === "pens" ? 40 : a === "library" ? 50 : a === "rl" ? 0 : -50)} ${B.y}`;
    else if (kind === "ui") d = `M${A.x + A.w / 2} ${A.y} C ${A.x + A.w / 2} ${A.y - 60}, ${B.x + B.w / 2} ${B.y + B.h + 60}, ${B.x + B.w / 2 + (a === "dash" ? 30 : -10)} ${B.y + B.h}`;
    else if (Math.abs((A.y + A.h / 2) - (B.y + B.h / 2)) < 2) d = `M${A.x + A.w} ${A.y + A.h / 2} L${B.x} ${B.y + B.h / 2}`;
    else d = `M${A.x + A.w} ${A.y + A.h / 2} C ${A.x + A.w + 30} ${A.y + A.h / 2}, ${B.x - 30} ${B.y + B.h / 2}, ${B.x} ${B.y + B.h / 2}`;
    s += `<path d="${d}" fill="none" stroke="${model ? "#f472b6" : "#4b5675"}" stroke-opacity="${model ? 0.55 : 0.9}" stroke-width="1.4" ${model || kind === "ui" ? 'stroke-dasharray="5 4"' : ""} marker-end="url(#${model ? "ahm" : "ah"})"/>`;
    if (label) s += `<text x="${(A.x + A.w + B.x) / 2}" y="${A.y + A.h / 2 - 6}" fill="#8a94ac" font-size="10.5" text-anchor="middle">${label}</text>`;
  }
  for (const n of N) {
    const b = box(n), c = K[n.k].c;
    s += `<g class="node" data-id="${n.id}" tabindex="0">
      <rect class="box" x="${b.x}" y="${b.y}" width="${b.w}" height="${b.h}" rx="11" fill="#111725" stroke="${c}" stroke-opacity=".55"/>
      <rect x="${b.x}" y="${b.y + 10}" width="3" height="${b.h - 20}" rx="1.5" fill="${c}"/>
      <text x="${b.x + 14}" y="${b.y + 27}" fill="#e7eaf3" font-size="13.5" font-weight="650">${esc(n.t)}</text>
      <text x="${b.x + 14}" y="${b.y + 46}" fill="#8a94ac" font-size="11">${esc(n.s)}</text></g>`;
  }
  s += `<text x="1090" y="752" fill="#5c6680" font-size="10.5" text-anchor="end">click any box for details · dashed pink = frozen model used at deployment</text></svg>`;
  return s;
}

function drawer(id) {
  const n = N.find((m) => m.id === id);
  const d = document.getElementById("arch-drawer");
  d.innerHTML = "";
  d.append(h("span", { class: "badge", style: `color:${K[n.k].c};border-color:${K[n.k].c}55` }, K[n.k].n),
    h("h3", { style: "margin-top:10px" }, n.t), h("div", { class: "muted", style: "font-size:12.5px" }, n.s),
    h("p", { style: "margin-top:12px;font-size:13.5px" }, n.what),
    h("div", { class: "kv" }, n.kv.flatMap(([a, b]) => [h("div", {}, a), h("div", {}, b)])),
    h("div", { class: "eyebrow", style: "margin-top:16px" }, "where in the repo"), h("ul", {}, n.files.map((f) => h("li", {}, h("code", {}, f)))));
  document.querySelectorAll(".arch-svg .node").forEach((g) => g.classList.toggle("sel", g.dataset.id === id));
}

const steps = (arr) => h("div", { class: "flow" }, arr.map(([t, d], i) => h("div", { class: "step" }, h("div", { class: "sn" }, `step ${i + 1}`), h("div", { class: "st" }, t), h("div", { class: "sd" }, d))));

export function init(el) {
  el.innerHTML = "";
  el.append(
    h("div", { class: "hero", style: "grid-template-columns:1fr" }, h("div", {},
      h("div", { class: "eyebrow" }, "how it fits together"),
      h("h1", { style: "margin-top:6px", html: "System <span>architecture</span>" }),
      h("p", {}, "Offline, a measured corpus and a pipeline search produce labelled data; supervised models and an RL agent learn from it and are frozen. Online, for each new program, the models propose pipelines and — in tune — timing decides. -O3 is always the fallback."),
      h("div", { class: "legend", style: "margin-top:12px" }, Object.values(K).map((k) => h("span", { html: `<i style="background:${k.c}"></i>${k.n}` }))))),
    h("div", { class: "arch-wrap" },
      h("div", { class: "card", style: "padding:14px", html: svg() }),
      h("div", { class: "card drawer", id: "arch-drawer" })),
    h("div", { class: "card", style: "margin-top:18px" }, h("div", { class: "card-h" }, h("div", { class: "ico", html: icon.bolt }), h("div", {}, h("h3", {}, "Tune flow (RL + SL, measured)"), h("div", { class: "sub" }, "what happens when you press Run tune"))),
      steps([["Reference run", "build at -O0, run, hash the output: the truth every candidate must match"],
        ["Features", "static IR stats + a quick scan of -O0…-O3 runtimes"], ["RL proposes", "the PPO agent builds 24 edit sequences for this program"],
        ["SL ranks", "the surrogate scores 24 RL + ~913 library pipelines"], ["Compile + verify", "in rank order until 8 distinct binaries with correct output"],
        ["Time", "8 candidates + -O3 interleaved on a pinned core, 10 rounds"], ["Confirm", "fresh 20-round run of the best vs -O3 with an A/A control"],
        ["Ship", "candidate if CI > 1.01, otherwise -O3"]])),
    h("div", { class: "card", style: "margin-top:18px" }, h("div", { class: "card-h" }, h("div", { class: "ico", html: icon.sparkle }), h("div", {}, h("h3", {}, "Predict flow (choose without running, then measure)"), h("div", { class: "sub" }, "the choice uses no runs; one timing run then shows the real effect"))),
      steps([["Build -O3", "plus optimization remarks (what -O3 vectorized, inlined, failed to do)"], ["Features", "111 static + 36 remark features"],
        ["Candidates", "safe pool: 164 single edits + 776 pairs, + RL proposals"], ["Ensemble", "7 LightGBM models predict speedup; classifier predicts harm"],
        ["Gate", "pessimistic > 1.03×, ≥ 80% agree, harm < 0.5"], ["Output", "advisory: report + -O3 binary (or the pick with --apply)"], ["Measure", "compile the top pick, check output, time it vs -O3 (20 rounds + A/A)"]])),
    h("div", { class: "grid g3", style: "margin-top:18px" },
      h("div", { class: "card" }, h("h3", {}, "What an edit can do"), h("div", { class: "sub muted", style: "font-size:12.5px;margin:4px 0 12px" }, "a candidate = -O3 + a short list of edits (a \"genome\")"),
        h("div", { class: "edits" }, [["del", "remove", "delete one pass instance"], ["dup", "repeat", "run a pass twice"], ["swap", "reorder", "swap a pass with its neighbour"],
          ["ins", "add", "insert a pass at a valid position"], ["flip", "option", "change a pass option (e.g. vectorizer interleave)"], ["knob", "knob", "global opt flag: vector width, unroll count, inline threshold"],
          ["llc", "backend", "code generator flags: tail duplication, loop alignment"], ["lvl", "backend -O", "code generator optimization level"]].map(([k, l, d]) =>
          h("div", { class: "edit" }, h("div", { class: `k ${k}` }, l), h("div", { class: "x", style: "margin:0" }, d))))),
      h("div", { class: "card" }, h("h3", {}, "Technology"), h("div", { class: "prose", style: "margin-top:10px", html: `<ul>
        <li><b>LLVM 18.1.8</b> (pinned): clang, opt (new pass manager pipeline strings), llc</li>
        <li><b>Python 3.14</b>: numpy, scipy, LightGBM; PPO implemented in numpy</li>
        <li><b>SQLite</b> for all measurements and results</li>
        <li><b>valgrind cachegrind</b> for simulated cache/branch features</li>
        <li><b>WSL2</b> Ubuntu on an AMD Ryzen 9 270, 14 vCPUs</li>
        <li><b>Dashboard</b>: FastAPI + uvicorn, Server-Sent Events, vanilla JS, Chart.js, CodeMirror — works offline</li></ul>` })),
      h("div", { class: "card" }, h("h3", {}, "Limits, stated honestly"), h("div", { class: "prose", style: "margin-top:10px", html: `<ul>
        <li>Gains depend on the workload given (args/stdin); a different input may favour a different pipeline.</li>
        <li>Tune needs to run the program ~250 times: minutes, not seconds.</li>
        <li>The Phase 3 headroom gate was missed on the fresh sample (+4.0%, 4/15 ≥ 5%); the target was re-scoped to +2–4%.</li>
        <li>RL adds only +0.2% over SL (not significant); kept because the final version is RL + SL.</li>
        <li>Predict cannot see runtime effects well without running: +0.6%, advisory only.</li>
        <li>One machine (laptop, WSL2); results tagged by machine_id.</li></ul>` }))),
  );
  el.querySelectorAll(".arch-svg .node").forEach((g) => {
    g.addEventListener("click", () => drawer(g.dataset.id));
    g.addEventListener("keydown", (e) => e.key === "Enter" && drawer(g.dataset.id));
  });
  drawer("tune");
}
