// Research page: corpus, measurement, headroom, models, held-out test results. All numbers come from
// data/research.json, written by scripts/export_dashboard_data.py from the result files in the repo.
import { esc, h, x, pct, ms, cls, ci, icon } from "./util.js";
import { chart, C, speedAxis } from "./charts.js";

let D, root;
const SECTIONS = [
  ["overview", "Overview"], ["corpus", "Corpus generation"], ["harness", "Measurement"], ["headroom", "Headroom (Phase 3)"],
  ["wider", "Wider search (Phase 5)"], ["kb", "Pass knowledge"], ["models", "Training & validation"], ["test", "Held-out test"],
  ["ir", "IR count ≠ runtime"], ["timeline", "Timeline & decisions"],
];
const METHOD_COLOR = {
  "-O2": C.o3, "-Os": C.o3, "tune top-8 (SL)": C.lib, "tune RL + SL": C.rl, "RL only": "#f9a8d4", "no dynamic features": "#93c5fd",
  "ML-only top-1": "#818cf8", "random top-8": "#64748b", "random search@8": "#a3a3a3", "GA@8": C.ga, "predict (gated)": C.pred, "predict ungated": "#c4b5fd",
};

export async function init(el) {
  root = el;
  el.innerHTML = `<div class="empty"><span class="spin"></span> loading results…</div>`;
  D = await (await fetch("data/research.json")).json();
  el.innerHTML = `<div class="research"><nav class="toc">${SECTIONS.map(([id, t], i) => `<a href="#research" data-sec="${id}"><span class="n">${String(i + 1).padStart(2, "0")}</span>${t}</a>`).join("")}
    <div class="mini" style="padding:12px">data exported ${esc(D.generated)}<br>by <code>scripts/export_dashboard_data.py</code></div></nav><div id="sections"></div></div>`;
  const box = el.querySelector("#sections");
  [overview, corpus, harness, headroom, wider, kb, models, test, ir, timeline].forEach((f, i) => box.append(section(SECTIONS[i][0], i + 1, ...f())));
  el.querySelectorAll(".toc a").forEach((a) => (a.onclick = (e) => { e.preventDefault(); document.getElementById(`sec-${a.dataset.sec}`).scrollIntoView({ behavior: "smooth" }); }));
  const obs = new IntersectionObserver((ents) => ents.forEach((en) => { if (en.isIntersecting) el.querySelectorAll(".toc a").forEach((a) => a.classList.toggle("active", `sec-${a.dataset.sec}` === en.target.id)); }), { rootMargin: "-30% 0px -60% 0px" });
  el.querySelectorAll(".section").forEach((s) => obs.observe(s));
  drawCharts();
}

function section(id, n, title, sub, ...body) {
  return h("section", { class: "section", id: `sec-${id}` }, h("div", { class: "sec-h" }, h("span", { class: "num" }, String(n).padStart(2, "0")), h("h2", {}, title), h("p", {}, sub)), ...body);
}
const card = (title, sub, ...kids) => h("div", { class: "card" }, title ? h("div", { class: "card-h" }, h("div", {}, h("h3", {}, title), sub ? h("div", { class: "sub" }, sub) : null)) : null, ...kids);
const cv = (id, k = "") => h("div", { class: `chart ${k}` }, h("canvas", { id }));
const src = (s) => h("div", { class: "source" }, s);
const kpi = (l, v, hint, k = "") => h("div", { class: `kpi ${k}` }, h("div", { class: "label" }, l), h("div", { class: "value" }, v), h("div", { class: "hint" }, hint || ""));
const summ = (s) => `geomean ${pct(s.geomean)} (95% CI ${pct(s.ci[0])}…${pct(s.ci[1])}) · excl. largest ${pct(s.excl_largest)} · ≥5%: ${s.ge5}/${s.n}`;

// ---------------------------------------------------------------- sections
function overview() {
  const t = D.headline.tune_rlsl, p = D.headline.predict, p5 = D.headline.phase5;
  return ["Overview", "what was achieved, measured on programs never used in training",
    h("div", { class: "grid g4" },
      kpi("tune RL + SL · test", pct(t.geomean, 1), `CI ${pct(t.ci[0], 1)}…${pct(t.ci[1], 1)} · excl. largest ${pct(t.excl_largest, 1)}`, "accent"),
      kpi("regressions", `${t.slower} / ${t.n}`, "test programs measurably slower than -O3", "ok"),
      kpi("search headroom", pct(p5.geomean, 1), `wider search, ${p5.n} programs, ${p5.ge5} ≥ +5%`),
      kpi("predict (compile-only)", pct(p.geomean, 1), `CI ${pct(p.ci[0], 1)}…${pct(p.ci[1], 1)} · advisory`, "warn")),
    h("div", { class: "grid g2", style: "margin-top:18px" },
      card("Key findings", "",
        h("div", { class: "prose", html: `<ul>
          <li><b>Tune works</b>: on 33 held-out programs (11 unseen families) RL + SL tune is ${pct(t.geomean, 1)} faster than -O3 (geomean, serial re-measurement), ${t.ge5} programs ≥ +5%, none slower. Without the largest result: ${pct(t.excl_largest, 1)}.</li>
          <li><b>Headroom is real but uneven</b>: an expensive search finds ${pct(p5.geomean, 1)} on unseen programs, yet ${p5.no_gain} of ${p5.n} have no measurable gain at all.</li>
          <li><b>Timing beats prediction</b>: the supervised model ranks pipelines only weakly on unseen programs (Spearman ≈ 0.1); timing a short list of its picks is what turns that weak signal into speed.</li>
          <li><b>Predict without running is hard</b>: compile-only predict reached ${pct(p.geomean, 2)} (CI includes 0), so it ships as advisory.</li>
          <li><b>IR count is not runtime</b>: fewer IR instructions predicts nothing about speed (Spearman ${D.ir.rho.toFixed(2)}).</li></ul>` })),
      card("Gates on record", "the project's pre-registered checkpoints",
        h("div", { class: "checks" }, [
          ["Phase 1 · timing harness selftest", true, "A/A bias ≤ 0.3%, CI 0.12–0.41%"],
          ["Phase 3 · headroom gate (fresh 15)", false, `${pct(D.gate3.fresh_summary.geomean)} · 4/15 ≥ 5% (needed 30%)`],
          ["Phase 5 · data quality CLEAN", false, "10.3% noisy controls (limit 10%), mitigated"],
          ["Gate 7B · surrogate beats random", true, "narrowly, after Phase 4 data"],
          ["Phase 9 · top-k beats random & GA", true, "+7.5% vs +5.3% / +2.1%"],
          ["RL beats top-k (equal budget)", false, "RL only −4.2%; RL + SL +0.2% (n.s.)"],
          ["Predict ≥ +1.5%, ≤ 1 regression", false, "+0.64%, CI includes 0"],
        ].map(([n, ok, d]) => h("div", { class: "chk" }, h("span", { class: `dot ${ok ? "ok" : "warn"}` }), h("span", { class: "n" }, n), h("span", { class: "d" }, d)))))),
  ];
}

function corpus() {
  const c = D.corpus;
  const rej = c.rejections.reduce((a, r) => a + r[1], 0);
  return ["Corpus generation", `${c.scanned} candidate programs scanned → ${c.usable} usable in ${c.families} families`,
    h("div", { class: "grid g3" },
      card("From sources to a usable corpus", "every program must build, run deterministically and take 0.1–10 s at -O3",
        h("div", { class: "funnel" },
          h("div", { class: "fbar", style: "width:100%" }, `${c.scanned} scanned (PolyBench, LLVM test-suite SingleSource + MultiSource)`),
          h("div", { class: "fbar", style: `width:${rej / c.scanned * 100}%;opacity:.85;background:linear-gradient(135deg,#f87171,#fb923c)` }, `${rej} rejected`),
          h("div", { class: "fbar", style: `width:${c.usable / c.scanned * 100}%;opacity:.7` }, `${c.usable} usable`)),
        cv("c-rej", "short"), src(D.sources.corpus)),
      card("By suite and family", `${c.families} families; a family = programs sharing code (kept together in the split)`, cv("c-suite", "short"), cv("c-fam", "short")),
      card("Runtime at -O3 and level spread", `${c.levels_differ_3pct} programs differ ≥ 3% between -O levels; on ${c.level_beats_o3} a lower level beats -O3`, cv("c-rt"), cv("c-spread", "short"))),
    h("div", { class: "grid g2", style: "margin-top:18px" },
      card("Train / validation / test split", `frozen 2026-10-24 (seed ${c.split.seed}) before any modelling; split by family, so test programs come from families never seen in training`,
        cv("c-split", "short"),
        h("div", { class: "prose", html: `<p class="mini"><b>test families:</b> ${c.split.groups.test.map(esc).join(", ")}</p><p class="mini"><b>validation families:</b> ${c.split.groups.val.map(esc).join(", ")}</p>` })),
      card("Why programs were rejected", "", h("table", { class: "tbl", html: `<thead><tr><th>reason</th><th class="num">programs</th><th>meaning</th></tr></thead><tbody>${c.rejections.map(([r, n]) => `<tr><td><code>${r}</code></td><td class="num">${n}</td><td class="muted">${{
        too_fast: "under 0.1 s at -O3: timing noise would dominate", no_output: "prints nothing, so candidates cannot be verified", build_fail: "does not compile with clang 18 alone",
        unsupported: "needs libraries, threads or files", run_nonzero_exit: "exits with an error", too_slow: "over 10 s at -O3", output_mismatch: "output differs between -O0 and -O3 (UB or nondeterminism)", run_timeout: "hangs" }[r] || ""}</td></tr>`).join("")}</tbody>` }))),
  ];
}

function harness() {
  const H = D.harness;
  const st = [...H.selftest_v8.map((s) => ({ ...s, v: "8 vCPU" })), ...H.selftest_v14.map((s) => ({ ...s, v: "14 vCPU" }))];
  return ["Measurement", "only measured numbers count: pinned cores, interleaved runs, paired bootstrap CIs, A/A control",
    h("div", { class: "grid g2" },
      card("How a speedup is measured", "",
        h("div", { class: "prose", html: `<ul>
          <li>-O3 and each candidate are run <b>interleaved</b> in random order on an isolated, pinned CPU (SMT sibling idle), so drift hits both equally.</li>
          <li>Every comparison also times a <b>byte-identical copy of -O3</b> (A/A control); if it is "faster" than -O3 by more than the limit, the run is rejected.</li>
          <li>Speedup = paired median ratio with a <b>bootstrap 95% CI</b>; a win needs the CI lower bound above 1.</li>
          <li>Screening (few rounds, 3 parallel cores) is only used to choose; every reported number is a <b>serial re-measurement</b> (20–30 rounds).</li>
          <li>Each candidate's output is compared with the -O0 build's output: a faster binary with different output is discarded.</li>
          <li>A quiet guard waits while other processes load the machine.</li></ul>` })),
      card("Timing selftests", "reference program, run before data collection on each machine configuration",
        h("table", { class: "tbl", html: `<thead><tr><th>config</th><th>verdict</th><th class="num">median</th><th class="num">CI ±</th><th class="num">drift</th><th class="num">A/A</th></tr></thead><tbody>${st.map((s) => `<tr><td>${s.v}</td><td><span class="badge ${s.verdict === "PASS" ? "ok" : "bad"}">${s.verdict}</span></td><td class="num">${ms(s.median_ms)}</td><td class="num">${s.ci_halfwidth_pct.toFixed(2)}%</td><td class="num">${s.drift_pct.toFixed(2)}%</td><td class="num">${x(s.aa)}</td></tr>`).join("")}</tbody>` }),
        h("p", { class: "mini", style: "margin-top:8px" }, "The first 14-vCPU selftest failed (other load); it was re-run on a quiet machine before any new timing."), src(H.selftest_v8[0] ? "results/selftest_*.json" : ""))),
    h("div", { class: "grid g2", style: "margin-top:18px" },
      card("Parallel timing: how many cores?", "A/A bias on each core in multi-core runs; 3 cores passed, 5 cores made noise 5–40× larger", cv("h-aa"), src("results/aatest_*.json")),
      card("Layout randomization test", "did randomizing code layout reduce bias? No → not used", h("table", { class: "tbl", html: `<thead><tr><th>program</th><th class="num">worst deviation</th><th class="num">runs with CI excluding 1</th></tr></thead><tbody>${Object.entries(H.layout).map(([k, v]) => `<tr><td>${esc(k)}</td><td class="num">${v.worst_dev_pct.toFixed(2)}%</td><td class="num">${v.ci_excl}/${v.runs.length}</td></tr>`).join("")}</tbody>` }), src("results/layout_test_20261023-102201.json"))),
  ];
}

function headroom() {
  const g = D.gate3;
  return ["Headroom (Phase 3)", "is there anything to gain over -O3? A search on 30 programs, decided on 15 fresh ones",
    h("div", { class: "grid g2" },
      card("Per-program best validated speedup", "fresh sample (decisive) and original sample", cv("g3-bars", "tall"), src(D.sources.gate3)),
      card("Gate decision", "",
        h("div", { class: "callout warn", html: `<b>Gate NOT MET</b> on the decisive fresh sample: ${summ(g.fresh_summary)} — the gate required ≥ 30% of programs at ≥ +5%; 26.7% reached it.` }),
        h("div", { class: "grid g2", style: "margin-top:12px" }, kpi("fresh 15", pct(g.fresh_summary.geomean), `median ${pct(g.fresh_summary.median)}`, "warn"), kpi("original 15", pct(g.original_summary.geomean), `excl. largest ${pct(g.original_summary.excl_largest)}`)),
        h("div", { class: "prose", style: "margin-top:12px", html: `<p>Re-scope (user decision): continue with the target lowered to the "good" tier (+2–4%), and use the next phase's wider search on never-searched programs as an out-of-sample re-measurement. Thresholds were not relaxed after the fact; the miss is reported.</p><p class="mini">The largest original result is <b>evalloop</b>: -O3's SimplifyCFG merges an interpreter's 31 dispatch jumps into one; disabling sink-common-insts restores them.</p>` }),
        h("pre", { class: "report", style: "margin-top:10px" }, g.text))),
  ];
}

function wider() {
  const p = D.phase5;
  return ["Wider search (Phase 5)", "evolutionary search (2 × 50 evaluations) on 116 programs never searched before; every winner re-validated serially",
    h("div", { class: "grid g4" },
      kpi("geomean", pct(p.summary_all.geomean, 1), `CI ${pct(p.summary_all.ci[0], 1)}…${pct(p.summary_all.ci[1], 1)}`, "accent"),
      kpi("excl. largest", pct(p.summary_all.excl_largest, 1), `median ${pct(p.summary_all.median, 1)}`),
      kpi("≥ +5%", `${p.summary_all.ge5}/${p.summary_all.n}`, `${(p.summary_all.ge5 / p.summary_all.n * 100).toFixed(0)}% of programs`, "ok"),
      kpi("per family", pct(p.summary_family.geomean, 1), `${p.summary_family.ge5}/${p.summary_family.n} families ≥ +5%`)),
    h("div", { class: "grid g2", style: "margin-top:18px" },
      card("Best validated speedup per program (sorted)", "log scale; grey = no winner (-O3 kept); one compile-time-evaluation artifact excluded", cv("p5-sorted", "tall"), src(D.sources.phase5)),
      card("Artifact check", `winners ≥ ${p.rule.min_speedup}× checked with cachegrind: is the work actually being done?`,
        h("div", { style: "overflow:auto;max-height:380px" }, h("table", { class: "tbl", html: `<thead><tr><th>program</th><th class="num">speedup</th><th class="num">instr. ratio</th><th>verdict</th></tr></thead><tbody>${p.artifact.map((a) => `<tr><td>${esc(a.program)}</td><td class="num">${x(a.speedup, 2)}</td><td class="num">${a.instr_ratio ? a.instr_ratio.toFixed(2) + "×" : "–"}</td><td>${a.suspect_compile_time_eval ? '<span class="badge bad">excluded</span>' : '<span class="badge ok">real</span>'}</td></tr>`).join("")}</tbody>` })),
        h("p", { class: "mini", style: "margin-top:8px" }, "mandel-text ran 217× fewer instructions: the compiler computed the answer at compile time. It is excluded from every summary."))),
  ];
}

function kb() {
  const k = D.kb;
  return ["Pass knowledge", `${k.edits} single edits tried on ${k.programs} programs: which edits of -O3 help, and how often?`,
    card("Most useful single edits", "per edit, out of 31 programs: confirmed faster, confirmed slower (CI excludes 1), changed but not significant, or identical binary",
      cv("kb-bars", "tall"),
      h("div", { class: "pill-row", style: "margin-top:10px" }, Object.entries(k.by_kind).map(([a, b]) => h("span", { class: "badge" }, `${a}: ${b} edits`))),
      h("p", { class: "mini", style: "margin-top:8px" }, "Knobs (vector width, unroll counts, inline threshold) help most often, but every edit also hurts some programs — no single global change beats -O3, which is why selection is per program."), src(D.sources.kb)),
  ];
}

function models() {
  const m = D.models, tv = m.predict_train_vs_heldout;
  return ["Training & validation", "supervised surrogate (LightGBM), PPO reinforcement learning, and the predict ensemble — cross-validated by family",
    h("div", { class: "grid g2" },
      card("Tune surrogate: does ranking beat random?", "gain@k on held-out families (best true speedup among the model's top-k vs k random pipelines)", cv("m-gain"), src(D.sources.models)),
      card("Features", "what the models see about a program", cv("m-feat", "short"),
        h("div", { class: "prose", html: `<ul><li><b>static</b>: IR statistics (instruction mix, loops, calls, memory ops) of the -O0/-O3 IR</li><li><b>scan</b>: runtimes at -O0…-O3, level spread, binary size</li><li><b>sim</b>: cachegrind cache/branch simulation (labelled simulated)</li><li><b>remarks</b>: -O3 optimization remarks (vectorized loops, failed inlines…) — predict only</li></ul>` }))),
    h("div", { class: "grid g2", style: "margin-top:18px" },
      card("RL agent (PPO) learning curves", `mean reward per update (log speedup predicted by the surrogate); ${m.rl_tune_actions} actions, horizon 4`, cv("m-rl")),
      card("Predict: why compile-only is hard", "Spearman correlation of predicted vs true speedup",
        cv("m-tvh", "short"),
        h("p", { class: "mini", style: "margin-top:8px" }, `On programs it trained on the ensemble ranks well (${tv.train[0].toFixed(2)}); on held-out families only ${tv.heldout[0].toFixed(2)}. The safety gate was tuned on out-of-fold predictions: ${m.predict_cv.objective}.`),
        h("div", { class: "stat-line" }, h("span", {}, "chosen gate"), h("b", {}, `margin ${m.predict_thresholds.margin}, τ ${m.predict_thresholds.tau}, agree ≥ ${m.predict_thresholds.agree}`)),
        h("div", { class: "stat-line" }, h("span", {}, "out-of-fold: shipped / regressions"), h("b", {}, `${m.predict_cv.chosen.shipped} / ${m.predict_cv.chosen.regressions} of ${m.predict_cv.chosen.programs}`)),
        h("div", { class: "stat-line" }, h("span", {}, "safe edit pool"), h("b", {}, `${m.predict_pool.singles} singles + ${m.predict_pool.pairs} pairs (${m.predict_pool.wrong_output_edits_excluded} wrong-output edits excluded)`)))),
  ];
}

function test() {
  const s = D.eval.summary;
  return ["Held-out test", "33 programs from 11 families never used for training or tuning; every method re-measured serially in the same runs",
    card("Speedup vs -O3 by method (geomean, 95% CI)", "equal budget: top-8 / random / GA each time 8 candidates", cv("t-methods", "tall"), src(D.sources.eval)),
    h("div", { class: "grid g2", style: "margin-top:18px" },
      card("Summary table", "", h("div", { style: "overflow:auto" }, h("table", { class: "tbl", html: `<thead><tr><th>method</th><th class="num">geomean</th><th class="num">95% CI</th><th class="num">excl. largest</th><th class="num">≥5%</th><th class="num">slower</th></tr></thead><tbody>${Object.entries(s).map(([k, v]) => `<tr class="${k === "tune RL + SL" ? "hl" : ""}"><td><span class="dot" style="display:inline-block;background:${METHOD_COLOR[k] || C.o3};margin-right:8px"></span>${esc(k)}</td><td class="num ${cls(v.geomean, 0.005)}">${pct(v.geomean)}</td><td class="num muted">${pct(v.ci[0], 1)}…${pct(v.ci[1], 1)}</td><td class="num">${pct(v.excl_largest)}</td><td class="num">${v.ge5}</td><td class="num ${v.slower ? "neg" : ""}">${v.slower}</td></tr>`).join("")}</tbody>` }))),
      card("Speed vs code size", "each point = one test program; tune top-8 against -O2, -Os and GA (size cap ≈ 1.10× -O3)", cv("t-size", "tall"))),
    card("Per-program results", "speedup vs -O3 for the main methods (serial)", h("div", { style: "overflow:auto;max-height:520px;margin-top:4px" }, perProgram())),
    h("div", { class: "grid g2", style: "margin-top:18px" },
      card("Paired against tune top-8 (SL)", "per-program ratio tune top-8 / method; > 1 means tune top-8 is faster", cv("t-paired", "tall")),
      card("Compile-time cost of predict", `added over a plain -O3 compile: median ${D.eval.predict_time.added_median_s} s, max ${D.eval.predict_time.added_max_s} s`, cv("t-ptime", "tall"))),
  ];
}

function perProgram() {
  const ms_ = ["tune RL + SL", "tune top-8 (SL)", "random search@8", "GA@8", "predict (gated)", "-O2"];
  const progs = [...D.eval.programs].sort((a, b) => (b["tune RL + SL"] || 0) - (a["tune RL + SL"] || 0));
  const cell = (v) => {
    if (v == null) return `<td class="num faint">–</td>`;
    const d = Math.log(v), a = Math.min(Math.abs(d) / Math.log(1.3), 1);
    const bg = d > 0.005 ? `rgba(52,211,153,${0.08 + a * 0.4})` : d < -0.005 ? `rgba(248,113,113,${0.08 + a * 0.4})` : "transparent";
    return `<td class="num" style="background:${bg}">${v.toFixed(3)}</td>`;
  };
  return h("table", { class: "tbl", html: `<thead><tr><th>program</th><th>family</th>${ms_.map((m) => `<th class="num">${m}</th>`).join("")}</tr></thead><tbody>${progs.map((p) => `<tr><td>${esc(p.id.split("/").slice(-1)[0])}</td><td class="muted">${esc(p.family)}</td>${ms_.map((m) => cell(p[m])).join("")}</tr>`).join("")}</tbody>` });
}

function ir() {
  return ["IR count ≠ runtime", "why this project optimizes measured runtime and not instruction count",
    h("div", { class: "grid g2" },
      card("IR instructions vs speedup", `${D.ir.n.toLocaleString()} measured candidates (sample of 2,500 shown); Spearman ρ = ${D.ir.rho.toFixed(3)}`, cv("ir-sc", "tall")),
      card("What this means", "", h("div", { class: "prose", html: `<p>An earlier attempt at this project reduced IR count and binary size but not runtime. Here, among candidates with ≥ 1% fewer IR instructions than -O3, only <b>${D.ir.fewer_ir_faster_pct.toFixed(0)}%</b> were actually faster — close to a coin flip.</p><p>Fewer instructions often means less unrolling or vectorization, which is slower. That is why every decision in tune is made from <b>timed</b> runs with an A/A control, and size and IR count are constraints only.</p>` }))),
  ];
}

function timeline() {
  return ["Timeline & decisions", "what happened, in order, including the misses",
    card("", "", h("div", { class: "timeline" }, D.timeline.map((t) => h("div", { class: `tl ${t.kind || ""}` }, h("div", { class: "d" }, `${t.date} · phase ${t.phase}`), h("div", { class: "t" }, t.title), h("div", { class: "x" }, t.detail))))),
    card("Reproduce", "every number on this page comes from these scripts and files", h("div", { class: "prose", html: `<ul>${Object.entries(D.sources).map(([k, v]) => `<li><b>${k}</b>: <code>${esc(v)}</code></li>`).join("")}</ul>` })),
  ];
}

// ---------------------------------------------------------------- charts
function drawCharts() {
  const c = D.corpus;
  chart("c-rej", { type: "bar", data: { labels: c.rejections.map((r) => r[0]), datasets: [{ data: c.rejections.map((r) => r[1]), backgroundColor: C.bad + "99", borderRadius: 4 }] },
    options: { indexAxis: "y", plugins: { legend: { display: false } }, scales: { x: { grid: { color: C.grid } }, y: { grid: { display: false } } } } });
  chart("c-suite", { type: "doughnut", data: { labels: Object.keys(c.by_suite), datasets: [{ data: Object.values(c.by_suite), backgroundColor: [C.acc, C.acc2, C.lib], borderColor: "#111725", borderWidth: 3 }] },
    options: { cutout: "62%", plugins: { legend: { position: "right" } } } });
  const fam = c.family_sizes.slice(0, 14);
  chart("c-fam", { type: "bar", data: { labels: fam.map((f) => f[0]), datasets: [{ data: fam.map((f) => f[1]), backgroundColor: C.acc + "aa", borderRadius: 4 }] },
    options: { plugins: { legend: { display: false } }, scales: { x: { ticks: { maxRotation: 60, minRotation: 45, font: { size: 10 } }, grid: { display: false } }, y: { grid: { color: C.grid } } } } });
  const bins = [100, 200, 400, 800, 1600, 3200, 6400, 12800];
  const cnt = bins.slice(0, -1).map((b, i) => c.programs.filter((p) => p.o3_ms >= b && p.o3_ms < bins[i + 1]).length);
  chart("c-rt", { type: "bar", data: { labels: bins.slice(0, -1).map((b, i) => `${b < 1000 ? b + " ms" : b / 1000 + " s"}–${bins[i + 1] < 1000 ? bins[i + 1] + " ms" : bins[i + 1] / 1000 + " s"}`), datasets: [{ data: cnt, backgroundColor: C.acc2 + "aa", borderRadius: 4 }] },
    options: { plugins: { legend: { display: false }, title: { display: true, text: "-O3 runtime (programs)", color: C.muted } }, scales: { x: { grid: { display: false }, ticks: { font: { size: 10 } } }, y: { grid: { color: C.grid } } } } });
  const sp = [...c.programs].map((p) => p.level_spread).sort((a, b) => a - b);
  chart("c-spread", { type: "line", data: { labels: sp.map((_, i) => i + 1), datasets: [{ data: sp, borderColor: C.acc, backgroundColor: C.acc + "22", fill: true, pointRadius: 0, tension: 0.2 }] },
    options: { plugins: { legend: { display: false }, title: { display: true, text: "slowest / fastest of -O1…-O3, -Os (sorted)", color: C.muted } }, scales: { x: { display: false }, y: { type: "logarithmic", grid: { color: C.grid }, ticks: { callback: (v) => `${v}×` } } } } });
  const sc = c.split.counts;
  chart("c-split", { type: "bar", data: { labels: [""], datasets: [["train", C.lib], ["val", C.warn], ["test", C.rl]].map(([k, col]) => ({ label: `${k} · ${sc[k]} programs, ${c.split.groups[k].length} families`, data: [sc[k]], backgroundColor: col + "cc", borderRadius: 4 })) },
    options: { indexAxis: "y", plugins: { legend: { position: "bottom" } }, scales: { x: { stacked: true, grid: { color: C.grid } }, y: { stacked: true, grid: { display: false } } } } });

  // harness: A/A bias per core count
  const aa = D.harness.aatests;
  chart("h-aa", { type: "bar", data: { labels: aa.map((a) => `${a.cores.length} cores · ${a.file.slice(-20, -5)}`), datasets: [
    { label: "worst |A/A bias| parallel (%)", data: aa.map((a) => Math.max(...a.programs.map((p) => Math.abs(p.parallel.aa_bias_pct)))), backgroundColor: aa.map((a) => (a.pass ? C.ok : C.bad) + "bb"), borderRadius: 4 },
    { label: "worst |A/A bias| serial (%)", data: aa.map((a) => Math.max(...a.programs.map((p) => Math.abs(p.serial.aa_bias_pct)))), backgroundColor: C.o3 + "66", borderRadius: 4 }] },
    options: { plugins: { legend: { position: "bottom" } }, scales: { y: { grid: { color: C.grid }, title: { display: true, text: "% bias", color: C.muted } }, x: { grid: { display: false }, ticks: { font: { size: 10 } } } } } });

  // gate 3
  const g = D.gate3, all = [...g.fresh.map((p) => ({ ...p, s: "fresh" })), ...g.original.map((p) => ({ ...p, s: "original" }))].sort((a, b) => b.speedup - a.speedup);
  chart("g3-bars", { type: "bar", data: { labels: all.map((p) => p.id.split("/").slice(-1)[0]), datasets: [{ data: all.map((p) => p.speedup), backgroundColor: all.map((p) => (p.s === "fresh" ? C.acc2 : C.acc) + (p.speedup >= 1.05 ? "ee" : "77")), borderRadius: 3 }] },
    options: { plugins: { legend: { display: false }, refLine: { value: 1.05, label: "+5%", color: "rgba(251,191,36,.8)" }, tooltip: { callbacks: { label: (c) => `${all[c.dataIndex].s}: ${x(c.raw)}` } } },
      scales: { y: { type: "logarithmic", ...speedAxis(""), min: 0.95 }, x: { ticks: { maxRotation: 70, minRotation: 60, font: { size: 9.5 } }, grid: { display: false } } } } });

  // phase 5 sorted
  const v = D.phase5.values.filter((p) => !p.suspect).sort((a, b) => b.speedup - a.speedup);
  chart("p5-sorted", { type: "bar", data: { labels: v.map((p) => p.id), datasets: [{ data: v.map((p) => p.speedup), backgroundColor: v.map((p) => (p.source === "no winner" ? "#475569" : p.speedup >= 1.05 ? C.ok : C.acc2) + "cc"), barPercentage: 1, categoryPercentage: 0.9 }] },
    options: { plugins: { legend: { display: false }, refLine: { value: 1.05, label: "+5%", color: "rgba(251,191,36,.8)" }, tooltip: { callbacks: { title: (c) => v[c[0].dataIndex].id, label: (c) => x(c.raw) } } },
      scales: { y: { type: "logarithmic", ...speedAxis(""), min: 0.97 }, x: { display: false } } } });

  // kb
  const top = D.kb.top.slice(0, 16);
  chart("kb-bars", { type: "bar", data: { labels: top.map((t) => t.label.length > 34 ? t.label.slice(0, 33) + "…" : t.label), datasets: [
    { label: "confirmed faster", data: top.map((t) => t.faster), backgroundColor: C.ok + "dd" }, { label: "confirmed slower", data: top.map((t) => t.slower), backgroundColor: C.bad + "bb" },
    { label: "changed, not significant", data: top.map((t) => t.programs - t.faster - t.slower - t.noop), backgroundColor: C.o3 + "77" },
    { label: "identical binary", data: top.map((t) => t.noop), backgroundColor: "#334155" }] },
    options: { indexAxis: "y", plugins: { legend: { position: "bottom" } }, scales: { x: { stacked: true, grid: { color: C.grid }, title: { display: true, text: "programs", color: C.muted } }, y: { stacked: true, grid: { display: false }, ticks: { font: { family: "JBMono", size: 10.5 } } } } } });

  // models
  const tc = D.models.tune_cv.summary, ks = [1, 3, 5, 10];
  chart("m-gain", { type: "line", data: { labels: ks.map((k) => `top-${k}`), datasets: [
    { label: "regressor (used by tune)", data: ks.map((k) => tc.gbr[`gain@${k}`]), borderColor: C.lib, backgroundColor: C.lib, tension: 0.25 },
    { label: "ranker", data: ks.map((k) => tc.rank[`gain@${k}`]), borderColor: C.acc, backgroundColor: C.acc, tension: 0.25 },
    { label: "random pipelines", data: ks.map((k) => tc.gbr[`rand_gain@${k}`]), borderColor: C.o3, backgroundColor: C.o3, borderDash: [5, 4], tension: 0.25 },
    { label: "oracle (best in library)", data: ks.map(() => tc.gbr.oracle), borderColor: C.ok, borderDash: [2, 3], pointRadius: 0 }] },
    options: { plugins: { legend: { position: "bottom" } }, scales: { y: speedAxis("best true speedup in top-k"), x: { grid: { display: false } } } } });
  const fs = D.models.feature_sets;
  chart("m-feat", { type: "bar", data: { labels: Object.keys(fs), datasets: [{ data: Object.values(fs), backgroundColor: [C.acc, C.acc2, C.lib, C.lib, C.pred], borderRadius: 4 }] },
    options: { indexAxis: "y", plugins: { legend: { display: false } }, scales: { x: { grid: { color: C.grid }, title: { display: true, text: "features", color: C.muted } }, y: { grid: { display: false } } } } });
  const smooth = (a, w = 10) => a.map((_, i) => { const s = a.slice(Math.max(0, i - w + 1), i + 1); return s.reduce((p, q) => p + q, 0) / s.length; });
  const rt = D.models.rl_tune_history, rp = D.models.rl_predict_history;
  chart("m-rl", { type: "line", data: { labels: rt.map((_, i) => i + 1), datasets: [
    { label: "tune RL (raw)", data: rt, borderColor: C.rl + "44", pointRadius: 0, borderWidth: 1 }, { label: "tune RL (moving avg)", data: smooth(rt), borderColor: C.rl, pointRadius: 0, borderWidth: 2 },
    { label: "predict RL (moving avg)", data: smooth(rp), borderColor: C.pred, pointRadius: 0, borderWidth: 2 }] },
    options: { plugins: { legend: { position: "bottom" } }, scales: { x: { title: { display: true, text: "PPO update", color: C.muted }, grid: { display: false }, ticks: { maxTicksLimit: 10 } }, y: { grid: { color: C.grid }, title: { display: true, text: "mean reward (log speedup)", color: C.muted } } } } });
  const tv = D.models.predict_train_vs_heldout;
  chart("m-tvh", { type: "bar", data: { labels: ["programs seen in training", "held-out families"], datasets: [{ data: [tv.train[0], tv.heldout[0]], backgroundColor: [C.ok + "bb", C.warn + "bb"], borderRadius: 6 }] },
    options: { indexAxis: "y", plugins: { legend: { display: false } }, scales: { x: { min: 0, max: 0.5, grid: { color: C.grid }, title: { display: true, text: "Spearman ρ", color: C.muted } }, y: { grid: { display: false } } } } });

  // test
  const s = Object.entries(D.eval.summary).sort((a, b) => b[1].geomean - a[1].geomean);
  chart("t-methods", { type: "bar", data: { labels: s.map((e) => e[0]), datasets: [{ data: s.map((e) => e[1].geomean), ci: s.map((e) => e[1].ci), backgroundColor: s.map((e) => (METHOD_COLOR[e[0]] || C.o3) + "cc"), borderRadius: 6 }] },
    options: { indexAxis: "y", plugins: { legend: { display: false }, refLine: { value: 1, label: "-O3" } }, scales: { x: speedAxis("geomean speedup vs -O3 (33 programs)"), y: { grid: { display: false } } } } });
  const ssc = D.eval.size_scatter, mcol = { topk: C.lib, O2: C.o3, Os: "#64748b", "ga@8": C.ga }, mname = { topk: "tune top-8", O2: "-O2", Os: "-Os", "ga@8": "GA@8" };
  chart("t-size", { type: "scatter", data: { datasets: Object.keys(mcol).map((m) => ({ label: mname[m], data: ssc.filter((p) => p.method === m && p.size).map((p) => ({ x: p.size, y: p.speedup, id: p.id })), backgroundColor: mcol[m] + "cc", pointRadius: 4 })) },
    options: { plugins: { legend: { position: "bottom" }, refLine: { value: 1 }, tooltip: { callbacks: { label: (c) => `${c.raw.id}: ${x(c.raw.y)}, size ${c.raw.x.toFixed(2)}×` } } },
      scales: { x: { title: { display: true, text: ".text size vs -O3", color: C.muted }, grid: { color: C.grid }, ticks: { callback: (v) => `${v}×` } }, y: { type: "logarithmic", ...speedAxis() } } } });
  const pv = Object.entries(D.eval.paired_vs_tune_top8).sort((a, b) => b[1].mean - a[1].mean);
  chart("t-paired", { type: "bar", data: { labels: pv.map((e) => e[0]), datasets: [{ data: pv.map((e) => e[1].mean), ci: pv.map((e) => e[1].ci), backgroundColor: pv.map((e) => (METHOD_COLOR[e[0]] || C.o3) + "aa"), borderRadius: 5 }] },
    options: { indexAxis: "y", plugins: { legend: { display: false }, refLine: { value: 1, label: "= tune top-8" }, tooltip: { callbacks: { afterLabel: (c) => `tune better on ${pv[c.dataIndex][1].better}, worse on ${pv[c.dataIndex][1].worse}` } } }, scales: { x: speedAxis("tune top-8 / method"), y: { grid: { display: false } } } } });
  const pt = [...D.eval.predict_time.rows].sort((a, b) => b.o3_build_s - a.o3_build_s);
  chart("t-ptime", { type: "bar", data: { labels: pt.map((r) => r.program.split("/").slice(-1)[0]), datasets: [
    { label: "-O3 compile (s)", data: pt.map((r) => r.o3_build_s), backgroundColor: C.o3 + "aa" }, { label: "added by predict (s)", data: pt.map((r) => r.added_over_o3_s), backgroundColor: C.pred + "cc" }] },
    options: { plugins: { legend: { position: "bottom" } }, scales: { x: { stacked: true, ticks: { maxRotation: 70, minRotation: 60, font: { size: 9.5 } }, grid: { display: false } }, y: { stacked: true, type: "logarithmic", grid: { color: C.grid }, title: { display: true, text: "seconds", color: C.muted } } } } });

  // IR
  chart("ir-sc", { type: "scatter", data: { datasets: [{ data: D.ir.sample.map(([a, b]) => ({ x: a, y: b })), backgroundColor: C.acc2 + "55", pointRadius: 2.2 }] },
    options: { plugins: { legend: { display: false }, refLine: { value: 1 } }, scales: { x: { type: "logarithmic", min: 0.5, max: 2, title: { display: true, text: "IR instructions vs -O3", color: C.muted }, grid: { color: C.grid }, ticks: { callback: (v) => `${v}×` } }, y: { type: "logarithmic", min: 0.5, max: 2.5, ...speedAxis("measured speedup vs -O3") } } } });
}
