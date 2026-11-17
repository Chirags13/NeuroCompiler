// Run page: choose a mode, give a program, run it live (terminal via SSE) and show the results in detail.
/* global CodeMirror */
import { api, esc, h, x, pct, ms, secs, cls, ci, ago, toast, icon } from "./util.js";
import { describe, genomeSummary, passInfo } from "./edits.js";
import { chart, C, speedAxis } from "./charts.js";

const MODES = {
  tune: {
    title: "Tune", ico: "bolt", badge: ["RL + SL", "measured"],
    desc: "RL agent + supervised model propose pipelines, the top-k are compiled, verified and timed against -O3. Ships only a confirmed win.",
    time: "≈ 1–10 min (runs the program ~250×)",
  },
  predict: {
    title: "Predict", ico: "sparkle", badge: ["predicts without running", "then measures 1"],
    desc: "Models choose a pipeline from static code features alone (no runs). Then its top pick is compiled and timed once against -O3 to show the real result.",
    time: "≈ 10–60 s (prediction ~1 s + one timing run)",
  },
  compare: {
    title: "Compare", ico: "scale", badge: ["all methods", "measured"],
    desc: "One interleaved timing run of -O3, -O2, -Os, predict, tune, random search and a genetic algorithm, with an A/A control.",
    time: "≈ 5–20 min",
  },
};

const STARTER = `// Paste a C or C++ program with a main(). It must print its result (output is verified),
// run for roughly 0.1 to 10 s at -O3, and be deterministic.
#include <stdio.h>
#include <stdlib.h>

int main(int argc, char **argv) {
    int n = argc > 1 ? atoi(argv[1]) : 3000;
    double *a = malloc(sizeof(double) * n), s = 0;
    for (int i = 0; i < n; i++) a[i] = (i % 7) * 0.5;
    for (int r = 0; r < 20000; r++)
        for (int i = 1; i < n; i++) s += a[i] * a[i - 1] + r;
    printf("%f\\n", s);
    return 0;
}
`;

const S = { mode: "tune", tab: "editor", files: [], stdin: null, example: null, examples: [], leaves: {}, current: null, es: null, jobs: [] };
let editor, root;

export function init(el) {
  root = el;
  el.innerHTML = `
  <div class="run-layout">
    <div class="stack">
      <div class="card">
        <div class="card-h"><div class="ico">${icon.bolt}</div><div><h3>1 · Choose a mode</h3><div class="sub">all three use the same frozen models</div></div></div>
        <div class="modes" id="modes"></div>
      </div>

      <div class="card">
        <div class="card-h"><div class="ico">${icon.code}</div><div><h3>2 · Give a program</h3><div class="sub">paste code, upload files, or pick a prepared example</div></div></div>
        <div class="tabs" id="src-tabs">
          <button data-tab="editor" class="active">Code editor</button>
          <button data-tab="upload">Upload files</button>
          <button data-tab="examples">Examples</button>
        </div>
        <div data-pane="editor">
          <div class="row" style="margin-bottom:10px">
            <div class="field" style="width:200px"><label>file name</label><input type="text" id="fname" value="main.c"></div>
            <div class="spacer"></div>
            <button class="btn sm ghost" id="reset-code">${icon.refresh} starter code</button>
          </div>
          <textarea id="code"></textarea>
        </div>
        <div data-pane="upload" hidden>
          <div class="drop" id="drop">${icon.up}<div style="margin-top:6px"><b>Drop source files here</b> or click to choose</div>
            <div class="faint" style="font-size:12px;margin-top:4px">.c .cpp .cc .cxx .h .hpp — several files are compiled and linked together</div></div>
          <input type="file" id="file-in" multiple accept=".c,.cpp,.cc,.cxx,.h,.hpp,.hh" hidden>
          <div class="filelist" id="filelist"></div>
        </div>
        <div data-pane="examples" hidden><div class="grid g2" id="examples"></div></div>

        <div class="callout" style="margin-top:14px">
          <b>Accepted programs</b>
          <div class="accept">
            <div>C or C++ source with a <code>main()</code></div>
            <div>one file, or several files linked together</div>
            <div>prints its result (used to verify every candidate)</div>
            <div>deterministic: same input → same output</div>
            <div>runs ~0.1–10 s at -O3 (tune/compare)</div>
            <div>command-line args and a stdin file are supported</div>
            <div class="no">no network, threads-timing or random seeds from time</div>
            <div class="no">no external libraries beyond libc / libm / libstdc++</div>
          </div>
        </div>

        <div class="grid g2" style="margin-top:14px">
          <div class="field"><label>program arguments</label><input type="text" id="args" placeholder="e.g. 800"></div>
          <div class="field"><label>extra compiler flags</label><input type="text" id="cflags" placeholder="e.g. -DN=1000"></div>
        </div>
        <details style="margin-top:12px">
          <summary>Advanced options</summary>
          <div class="grid g2" style="margin-top:12px">
            <div class="field"><label>stdin file (optional)</label><input type="file" id="stdin-in" style="color:var(--muted);font-size:12px"></div>
            <div class="field"><label>candidates to time (k)</label><input type="number" id="k" value="8" min="2" max="16"></div>
          </div>
          <div class="row" style="margin-top:12px;gap:22px">
            <label class="check"><input type="checkbox" id="no_rl"> SL only (no RL proposals)</label>
            <label class="check"><input type="checkbox" id="dynamic"> dynamic features (cachegrind, tune)</label>
            <label class="check"><input type="checkbox" id="verify"> predict: write the recommended binary (--apply)</label>
            <label class="check"><input type="checkbox" id="no_measure"> predict: compile-only (skip the timing run)</label>
          </div>
        </details>

        <div class="row" style="margin-top:18px">
          <button class="btn primary" id="run-btn">${icon.play} <span id="run-label">Run tune</span></button>
          <span class="muted" id="run-time" style="font-size:12.5px"></span>
        </div>
      </div>
    </div>

    <div class="stack">
      <div class="card" id="env-card">
        <div class="card-h"><div class="ico">${icon.cpu}</div><div><h3>Environment</h3><div class="sub">WSL2 · pinned LLVM · frozen models · quiet machine</div></div>
          <div class="spacer"></div><button class="btn sm" id="env-check">${icon.refresh} Check</button></div>
        <div class="checks" id="env-checks"><div class="muted"><span class="spin"></span> checking…</div></div>
        <div class="row" style="margin-top:12px">
          <button class="btn sm" id="selftest">${icon.term} Run timing selftest</button>
          <span class="muted" style="font-size:12px">≈ 1 min · confirms timing is trustworthy right now</span>
        </div>
        <details style="margin-top:10px"><summary>Starting the environment from Windows</summary>
          <p style="font-size:12.5px;margin-top:8px">Double-click <code>dashboard\\windows\\Start-NeuroCompiler.bat</code>: it boots WSL (Ubuntu),
          starts this server inside it and opens the browser. From a WSL terminal: <code>./dashboard/run.sh</code>.</p></details>
      </div>

      <div class="card" id="tasks-card">
        <div class="card-h"><div class="ico">${icon.list}</div><div><h3>Background tasks</h3><div class="sub">one job runs at a time so timings never overlap</div></div></div>
        <div class="jobs" id="jobs"></div>
        <div class="eyebrow" style="margin:14px 0 8px">Saved runs (replay instantly)</div>
        <div class="jobs" id="saved" style="max-height:150px"></div>
      </div>

      <div class="terminal">
        <div class="term-h"><div class="lights"><i></i><i></i><i></i></div><span id="term-title">terminal</span><div class="spacer"></div>
          <span id="term-state"></span>
          <button class="btn sm ghost danger" id="cancel" hidden>${icon.stop} Cancel</button></div>
        <div class="term-body" id="term"><span class="l-dim">Output of the running job appears here, line by line, exactly as in a WSL terminal.</span></div>
      </div>
    </div>
  </div>

  <div id="results" style="margin-top:26px"></div>`;

  renderModes();
  editor = CodeMirror.fromTextArea(el.querySelector("#code"), { mode: "text/x-csrc", lineNumbers: true, indentUnit: 4, theme: "default" });
  editor.setValue(STARTER);
  el.querySelector("#fname").addEventListener("input", (e) => editor.setOption("mode", /\.(cpp|cc|cxx)$/.test(e.target.value) ? "text/x-c++src" : "text/x-csrc"));
  el.querySelector("#reset-code").onclick = () => editor.setValue(STARTER);
  el.querySelectorAll("#src-tabs button").forEach((b) => (b.onclick = () => setTab(b.dataset.tab)));
  setupUpload();
  loadExamples();
  el.querySelector("#run-btn").onclick = submit;
  el.querySelector("#env-check").onclick = () => window.ncRefreshEnv();
  el.querySelector("#selftest").onclick = selftest;
  el.querySelector("#cancel").onclick = () => S.current && api(`/api/jobs/${S.current}/cancel`, { method: "POST" }).then(() => toast("Cancel requested"));
  window.addEventListener("env", (e) => renderEnv(e.detail));
  window.addEventListener("jobs", (e) => renderJobs(e.detail));
  loadSaved();
  api("/api/o3tree").then((t) => (S.leaves = t.leaves)).catch(() => {});
  // deep link: #run/job/<id> or #run/saved/<slug>
  const m = location.hash.match(/#run\/(job|saved)\/([\w-]+)/);
  if (m) (m[1] === "job" ? openJob : openSaved)(m[2]);
}

export function show() { editor?.refresh(); }

function renderModes() {
  const box = root.querySelector("#modes");
  box.innerHTML = "";
  for (const [k, m] of Object.entries(MODES)) {
    box.append(h("div", { class: `mode ${S.mode === k ? "active" : ""}`, onclick: () => { S.mode = k; renderModes(); } },
      h("div", { class: "mt", html: `${icon[m.ico]} ${m.title}` }),
      h("div", { class: "md" }, m.desc),
      h("div", { class: "mr" }, m.badge.map((b, i) => h("span", { class: `badge ${i ? (b === "advisory" ? "warn" : "ok") : k === "tune" ? "rl" : "acc"}` }, b)))));
  }
  root.querySelector("#run-label").textContent = `Run ${MODES[S.mode].title.toLowerCase()}`;
  root.querySelector("#run-time").textContent = MODES[S.mode].time;
}

function setTab(t) {
  S.tab = t;
  root.querySelectorAll("#src-tabs button").forEach((b) => b.classList.toggle("active", b.dataset.tab === t));
  root.querySelectorAll("[data-pane]").forEach((p) => (p.hidden = p.dataset.pane !== t));
  if (t === "editor") editor.refresh();
}

function setupUpload() {
  const drop = root.querySelector("#drop"), inp = root.querySelector("#file-in");
  drop.onclick = () => inp.click();
  inp.onchange = () => addFiles(inp.files);
  drop.ondragover = (e) => { e.preventDefault(); drop.classList.add("over"); };
  drop.ondragleave = () => drop.classList.remove("over");
  drop.ondrop = (e) => { e.preventDefault(); drop.classList.remove("over"); addFiles(e.dataTransfer.files); };
  root.querySelector("#stdin-in").onchange = (e) => (S.stdin = e.target.files[0] || null);
}

function addFiles(list) {
  for (const f of list) {
    if (!/\.(c|cpp|cc|cxx|h|hpp|hh)$/i.test(f.name)) { toast(`${f.name}: not a C/C++ source or header`); continue; }
    S.files = S.files.filter((g) => g.name !== f.name).concat(f);
  }
  const fl = root.querySelector("#filelist");
  fl.innerHTML = "";
  S.files.forEach((f) => fl.append(h("span", { class: "chip" }, `${f.name} · ${(f.size / 1024).toFixed(1)} KB `,
    h("a", { href: "#", onclick: (e) => { e.preventDefault(); S.files = S.files.filter((g) => g !== f); addFiles([]); } }, "×"))));
}

async function loadExamples() {
  S.examples = await api("/api/examples").catch(() => []);
  const box = root.querySelector("#examples");
  box.innerHTML = "";
  for (const e of S.examples) {
    const card = h("div", { class: `mode ${S.example === e.id ? "active" : ""}`, onclick: () => pickExample(e) },
      h("div", { class: "mt" }, e.name),
      h("div", { class: "mr" }, h("span", { class: "badge" }, e.kind), e.o3_ms ? h("span", { class: "badge" }, `-O3 ≈ ${ms(e.o3_ms)}`) : null,
        e.args ? h("span", { class: "chip" }, `args: ${e.args}`) : null),
      h("div", { class: "md" }, e.story));
    box.append(card);
  }
}

function pickExample(e) {
  S.example = e.id;
  const f = e.files[0];
  root.querySelector("#fname").value = f;
  editor.setOption("mode", /\.(cpp|cc|cxx)$/.test(f) ? "text/x-c++src" : "text/x-csrc");
  editor.setValue(e.sources[f]);
  root.querySelector("#args").value = e.args || "";
  root.querySelector("#cflags").value = e.cflags || "";
  loadExamples();
  toast(`Example "${e.name}" loaded into the editor`);
}

async function submit() {
  const fd = new FormData();
  fd.append("mode", S.mode);
  const v = (id) => root.querySelector(`#${id}`);
  const ex = S.examples.find((e) => e.id === S.example);
  const code = editor.getValue();
  if (S.tab === "upload") {
    if (!S.files.length) return toast("Choose at least one source file");
    S.files.forEach((f) => fd.append("files", f));
  } else if (ex && code === ex.sources[ex.files[0]]) {
    fd.append("example", ex.id);
  } else {
    if (!/\bmain\s*\(/.test(code)) return toast("The program needs a main() function");
    fd.append("code", code);
    fd.append("filename", v("fname").value || "main.c");
  }
  fd.append("args", v("args").value);
  fd.append("cflags", v("cflags").value);
  fd.append("k", v("k").value);
  if (v("no_rl").checked) fd.append("no_rl", "true");
  if (v("dynamic").checked) fd.append("dynamic", "true");
  if (v("verify").checked) fd.append("verify", "true");
  if (v("no_measure").checked) fd.append("no_measure", "true");
  if (S.stdin) fd.append("stdin_file", S.stdin);
  try {
    const job = await api("/api/jobs", { method: "POST", body: fd });
    toast(`${MODES[S.mode].title} job queued`);
    openJob(job.id);
  } catch (e) { toast(`Could not start: ${e.message}`); }
}

async function selftest() {
  const fd = new FormData();
  fd.append("mode", "selftest");
  const job = await api("/api/jobs", { method: "POST", body: fd }).catch((e) => toast(e.message));
  if (job) openJob(job.id);
}

// ---------------------------------------------------------------- environment
function renderEnv(e) {
  const box = root?.querySelector("#env-checks");
  if (!box) return;
  if (e.error) {
    box.innerHTML = `<div class="callout bad"><b>Server not reachable.</b> Start it with <code>dashboard\\windows\\Start-NeuroCompiler.bat</code> or <code>./dashboard/run.sh</code> in WSL.</div>`;
    return;
  }
  box.innerHTML = "";
  for (const c of e.checks) {
    box.append(h("div", { class: "chk" }, h("span", { class: `dot ${c.ok ? "ok" : /quiet|selftest/.test(c.name) ? "warn" : "bad"}` }),
      h("span", { class: "n" }, c.name), h("span", { class: "d", title: c.detail }, c.detail.length > 46 ? c.detail.slice(0, 44) + "…" : c.detail)));
  }
  box.append(h("div", { class: "muted", style: "font-size:12px;margin-top:4px" }, `${e.cpus} vCPUs · timing on CPU ${e.timing_cpu} · machine ${e.machine_id}`));
}

// ---------------------------------------------------------------- jobs
const ST = { queued: "", running: "live", done: "ok", failed: "bad", cancelled: "warn", interrupted: "warn" };
function renderJobs(jobs) {
  S.jobs = jobs;
  const box = root?.querySelector("#jobs");
  if (!box) return;
  box.innerHTML = jobs.length ? "" : `<div class="muted" style="font-size:13px">No jobs yet.</div>`;
  for (const j of jobs.filter((j) => j.mode !== "selftest" || j.status === "running").slice(0, 12).concat(jobs.filter((j) => j.mode === "selftest" && j.status !== "running").slice(0, 2))) {
    const name = j.example || (j.inputs.files || [])[0] || "selftest";
    const dur = j.finished ? secs(j.finished - j.started) : j.started ? secs(Date.now() / 1000 - j.started) : j.queue_position ? `#${j.queue_position} in queue` : "";
    box.append(h("div", { class: `job ${S.current === j.id ? "sel" : ""}`, onclick: () => openJob(j.id) },
      h("span", { class: `dot ${ST[j.status] || ""}` }), h("span", { class: "t" }, j.mode), h("span", {}, name),
      h("span", { class: "e" }, `${j.status} · ${dur} · ${ago(j.created)}`)));
  }
  // job just finished while open: load its results
  const cur = jobs.find((j) => j.id === S.current);
  if (cur && S.lastStatus === "running" && cur.status !== "running") openJob(cur.id, true);
  if (cur) S.lastStatus = cur.status;
}

async function loadSaved() {
  const list = await api("/api/saved").catch(() => []);
  const box = root.querySelector("#saved");
  box.innerHTML = list.length ? "" : `<div class="muted" style="font-size:13px">No saved runs yet. Finished jobs can be saved from their result panel.</div>`;
  for (const s of list) {
    box.append(h("div", { class: "job", onclick: () => openSaved(s.slug) }, h("span", { class: "dot ok" }), h("span", { class: "t" }, s.mode),
      h("span", {}, s.name), h("span", { class: "e" }, s.finished ? new Date(s.finished * 1000).toLocaleDateString() : "")));
  }
}

function termLine(ln) {
  const t = esc(ln);
  let c = "";
  if (/^\$ /.test(ln)) c = "l-cmd";
  else if (/^==|^\[|^Phase|^#|candidates:|top of the ranking/.test(ln)) c = "l-hd";
  else if (/error|Traceback|FAIL|failed|Error/.test(ln)) c = "l-err";
  else if (/warning|note:|kept -O3|not confirmed/i.test(ln)) c = "l-warn";
  else if (/PASS|shipped:|confirmed|recommended|\bok\b/.test(ln)) c = "l-ok";
  else if (/^\s*[{}\]]|^\s+"/.test(ln)) c = "l-dim";
  return `<div class="${c}">${t || "&nbsp;"}</div>`;
}

function setTerm(text, title) {
  const t = root.querySelector("#term");
  t.innerHTML = text.split("\n").map(termLine).join("");
  t.scrollTop = t.scrollHeight;
  root.querySelector("#term-title").textContent = title;
}

async function openJob(id, quiet) {
  S.current = id;
  S.es?.close();
  history.replaceState(null, "", `#run/job/${id}`);
  const job = await api(`/api/jobs/${id}`);
  S.lastStatus = job.status;
  const title = `${job.mode} · ${job.example || job.inputs.files[0] || ""} · ${id}`;
  const term = root.querySelector("#term");
  root.querySelector("#term-state").innerHTML = `<span class="badge ${job.status === "done" ? "ok" : job.status === "failed" ? "bad" : ""}">${job.status}</span>`;
  root.querySelector("#cancel").hidden = !["running", "queued"].includes(job.status);
  renderJobs(S.jobs);
  if (["running", "queued"].includes(job.status)) {
    root.querySelector("#term-title").textContent = title;
    term.innerHTML = job.status === "queued" ? `<div class="l-dim">waiting in the queue…</div>` : "";
    renderPending(job);
    S.es = new EventSource(`/api/jobs/${id}/stream`);
    let first = true;
    S.es.onmessage = (ev) => {
      if (first) { term.innerHTML = ""; first = false; }
      const stick = term.scrollTop + term.clientHeight >= term.scrollHeight - 30;
      term.insertAdjacentHTML("beforeend", termLine(JSON.parse(ev.data).line));
      if (stick) term.scrollTop = term.scrollHeight;
    };
    S.es.addEventListener("status", () => { S.es.close(); setTimeout(() => openJob(id, true), 300); });
    if (!quiet) root.querySelector(".terminal").scrollIntoView({ behavior: "smooth", block: "center" });
  } else {
    const log = await fetch(`/api/jobs/${id}/stream`).then((r) => r.text()).catch(() => "");
    const lines = log.split("\n").filter((l) => l.startsWith("data: ")).map((l) => { try { return JSON.parse(l.slice(6)).line; } catch (_) { return null; } }).filter((l) => l != null);
    setTerm(lines.join("\n"), title);
    await renderResult(job, false);
    if (!quiet) document.getElementById("results").scrollIntoView({ behavior: "smooth" });
  }
}

async function openSaved(slug) {
  S.current = null;
  S.es?.close();
  history.replaceState(null, "", `#run/saved/${slug}`);
  const job = await api(`/api/saved/${slug}`);
  setTerm(job.log || "", `saved · ${job.saved_name}`);
  root.querySelector("#term-state").innerHTML = `<span class="badge acc">saved replay</span>`;
  root.querySelector("#cancel").hidden = true;
  await renderResult(job, slug);
  document.getElementById("results").scrollIntoView({ behavior: "smooth" });
}

function renderPending(job) {
  document.getElementById("results").innerHTML = `
    <div class="card"><div class="empty"><div class="big"><span class="spin" style="width:30px;height:30px;border-width:3px"></span></div>
    <h3>${MODES[job.mode]?.title || job.mode} is ${job.status}…</h3>
    <p class="muted">${job.mode === "tune" ? "Compiling candidates, checking each one's output, then timing them interleaved with -O3 on pinned CPUs." :
      job.mode === "compare" ? "Running every method, then one long interleaved timing run with an A/A control." :
      job.mode === "predict" ? "Extracting static features and compiler remarks, then scoring the safe edit pool." : "Measuring timing quality on this machine."}
    Follow the terminal for live output.</p></div></div>`;
}

// ---------------------------------------------------------------- results
async function renderResult(job, savedSlug) {
  const box = document.getElementById("results");
  const r = job.result;
  if (job.status !== "done" || !r) {
    box.innerHTML = `<div class="callout ${job.status === "failed" ? "bad" : "warn"}"><b>Job ${job.status}.</b> ${job.status === "failed" ? "See the terminal for the error (compile error, program crashed, or output not deterministic)." : ""}</div>`;
    return;
  }
  let diff = null;
  if (job.mode === "tune" || job.mode === "predict") diff = await api(savedSlug ? `/api/saved/${savedSlug}/diff` : `/api/jobs/${job.id}/diff`).catch(() => null);
  box.innerHTML = "";
  const head = h("div", { class: "row", style: "margin-bottom:14px" },
    h("h2", {}, `Results · ${MODES[job.mode]?.title || job.mode}`),
    h("span", { class: "badge" }, job.example || job.inputs.files.join(", ")),
    job.inputs.args ? h("span", { class: "chip" }, `args: ${job.inputs.args}`) : null,
    h("div", { class: "spacer" }),
    !savedSlug && job.mode !== "selftest" ? h("button", { class: "btn sm", html: `${icon.save} Save run`, onclick: () => saveRun(job) }) : null,
    !savedSlug && job.mode !== "compare" && job.mode !== "selftest" ? h("a", { class: "btn sm", href: `/api/jobs/${job.id}/binary`, html: `${icon.dl} Binary` }) : null,
    h("button", { class: "btn sm", html: `${icon.dl} JSON`, onclick: () => download(`${job.mode}_${job.id || savedSlug}.json`, JSON.stringify(r, null, 1)) }));
  box.append(head);
  if (job.mode === "tune") renderTune(box, r, diff);
  else if (job.mode === "predict") renderPredict(box, r, diff);
  else if (job.mode === "compare") renderCompare(box, r);
  else renderSelftest(box, r);
  const srcs = job.sources || {};
  if (Object.keys(srcs).length) {
    box.append(h("details", { class: "card flat", style: "margin-top:18px" }, h("summary", {}, `Program source (${Object.keys(srcs).join(", ")})`),
      ...Object.entries(srcs).map(([f, s]) => h("pre", { class: "mono", style: "max-height:360px;overflow:auto;font-size:12px;color:var(--text-2);margin:10px 0 0" }, `// ${f}\n${s}`))));
  }
}

function download(name, text) {
  const a = h("a", { href: URL.createObjectURL(new Blob([text], { type: "application/json" })), download: name });
  a.click();
}

async function saveRun(job) {
  const name = prompt("Name for this saved run", `${job.mode} · ${job.example || job.inputs.files[0]}`);
  if (!name) return;
  const fd = new FormData();
  fd.append("name", name);
  await api(`/api/jobs/${job.id}/save`, { method: "POST", body: fd }).then(() => { toast("Saved"); loadSaved(); }).catch((e) => toast(e.message));
}

const verdict = (kind, big, title, sub, right) => h("div", { class: `verdict ${kind}` },
  h("div", { class: `big ${kind || "ok"}` }, big), h("div", {}, h("div", { class: "vt" }, title), h("div", { class: "vs", html: sub })), right || h("span"));

const kpi = (label, value, hint, k = "") => h("div", { class: `kpi ${k}` }, h("div", { class: "label" }, label), h("div", { class: "value sm" }, value), h("div", { class: "hint" }, hint || ""));

const rawItem = (raw) => ({ kind: "lvl", label: "whole pipeline", what: raw, why: "a standard LLVM pipeline used in place of -O3's (a level seed from the library); the edits below are applied on top" });
function editsList(edits, raw) {
  const items = (raw ? [rawItem(raw)] : []).concat(genomeSummary(edits, S.leaves));
  if (!items.length) return h("div", { class: "muted" }, "No edits: this is exactly -O3.");
  return h("div", { class: "edits" }, items.map((d) => h("div", { class: "edit" }, h("div", { class: `k ${d.kind}` }, d.label),
    h("div", {}, h("div", { class: "w" }, d.what), d.why ? h("div", { class: "x" }, d.why) : null))));
}

function editsShort(edits, raw) {
  const items = (raw ? [rawItem(raw)] : []).concat(genomeSummary(edits, S.leaves));
  return items.length ? items.map((d) => `<span class="edit-s"><b class="${d.kind}">${esc(d.label)}</b> ${esc(d.what)}</span>`).join("<br>") : `<span class="muted">-O3 unchanged</span>`;
}

// The selected sequence next to -O3's: the whole pass list, changed passes highlighted.
function sequenceSection(diff, title) {
  const card = h("div", { class: "card" });
  if (!diff) return card;
  const c = diff.counts || {};
  const changed = (c.delete || 0) + (c.insert || 0) + (c.changed || 0) + (c.replace || 0);
  const be = diff.backend;
  card.append(h("div", { class: "card-h" }, h("div", { class: "ico", html: icon.layers }),
    h("div", {}, h("h3", {}, title), h("div", { class: "sub" }, diff.note ? diff.note : `${diff.o3_passes} passes in -O3 · ${diff.selected_passes ?? "?"} in the selected pipeline · ${changed} pass-level change${changed === 1 ? "" : "s"}`))));
  const flags = (diff.flags || []);
  card.append(h("div", { class: "flagrow" },
    h("span", { class: "eyebrow" }, "code generator (llc)"),
    h("span", { class: "chip" }, `-O${be ?? 3}`),
    flags.length ? flags.map((f) => h("span", { class: "chip", style: "color:var(--lib)" }, f.replace("llc:", ""))) : h("span", { class: "muted", style: "font-size:12.5px" }, "same flags as -O3"),
    h("span", { class: "eyebrow", style: "margin-left:14px" }, "opt pipeline"),
    h("span", { class: "badge ok" }, `${c.insert || 0} added`), h("span", { class: "badge bad" }, `${c.delete || 0} removed`), h("span", { class: "badge warn" }, `${(c.changed || 0) + (c.replace || 0)} options changed`)));
  if (!diff.ops || !diff.ops.length) {
    if (diff.standard_level) card.append(h("div", { class: "callout" }, `Selected a standard level: `, h("code", {}, diff.standard_level)));
    return card;
  }
  let onlyChanges = changed > 0;
  const tog = h("label", { class: "check", style: "margin:4px 0 10px" }, h("input", { type: "checkbox", checked: onlyChanges, onchange: (e) => { onlyChanges = e.target.checked; draw(); } }), "show only changed passes (± 2 neighbours)");
  const grid = h("div", { class: "diff" });
  card.append(tog, grid);
  const pass = (p, i) => p ? `<span class="ix">${i}</span>${esc(p.text)}<span class="ctx">${esc(p.ctx)}</span>` : "";
  function draw() {
    const keep = new Set();
    diff.ops.forEach((o, i) => { if (o.op !== "equal") for (let j = i - 2; j <= i + 2; j++) keep.add(j); });
    let ia = 0, ib = 0, rows = "", gap = false;
    diff.ops.forEach((o, i) => {
      if (o.a) ia++;
      if (o.b) ib++;
      if (onlyChanges && !keep.has(i)) { if (!gap) rows += `<div class="c empty" style="grid-column:1/-1;text-align:center;color:var(--faint)">⋯ unchanged ⋯</div>`; gap = true; return; }
      gap = false;
      const tipA = o.a ? passInfo(o.a.pass) : "", tipB = o.b ? passInfo(o.b.pass) : "";
      rows += `<div class="c ${o.a ? (o.op === "equal" ? "" : o.op === "insert" ? "empty" : o.op) : "empty"}" title="${esc(tipA)}">${pass(o.a, ia)}</div>`;
      rows += `<div class="c ${o.b ? (o.op === "equal" ? "" : o.op === "delete" ? "empty" : o.op) : "empty"}" title="${esc(tipB)}">${pass(o.b, ib)}</div>`;
    });
    grid.innerHTML = `<div class="col-h"><span class="dot" style="background:var(--o3)"></span> -O3 sequence (LLVM 18 default&lt;O3&gt;)</div>
      <div class="col-h"><span class="dot" style="background:var(--accent-2)"></span> selected sequence</div><div class="cells">${rows}</div>`;
  }
  draw();
  card.append(h("details", { style: "margin-top:12px" }, h("summary", {}, "Full pipeline strings (copy into opt -passes=…)"),
    h("div", { class: "eyebrow", style: "margin-top:10px" }, "-O3"), h("pre", { class: "mono pipe" }, diff.o3_text || ""),
    h("div", { class: "eyebrow", style: "margin-top:10px" }, "selected"), h("pre", { class: "mono pipe" }, diff.selected_text || diff.o3_text || "")));
  return card;
}

function renderTune(box, r, diff) {
  const shipped = r.choice === "candidate";
  const cf = r.confirm || {};
  const base = cf.base_median_ms ?? r.base_median_ms;
  const pick = shipped ? (cf.pick_median_ms ?? (r.base_median_ms / r.select_speedup)) : base;
  const sp = shipped ? (cf.speedup ?? r.select_speedup) : 1;
  const spci = shipped ? (cf.ci && cf.ci[0] != null ? cf.ci : r.select_ci) : null;
  box.append(verdict(shipped ? "" : "neutral", shipped ? x(sp, 2) : "-O3",
    shipped ? `Faster pipeline shipped · from the ${r.shipped_from}` : "Kept -O3 (no confirmed win)",
    shipped ? `${pct(sp, 1)} vs -O3, 95% CI ${ci(spci)}${cf.rounds ? ` · confirmed in a fresh ${cf.rounds}-round run with an A/A control (${x(cf.control, 3)})` : ""}`
      : `${esc(r.reason || "")} — the safe default: tune never ships a pipeline it cannot show is faster.`,
    h("span", { class: `badge ${r.mode === "RL + SL" ? "rl" : "lib"}` }, r.mode)));
  const kp = h("div", { class: "grid g6", style: "margin-top:14px" },
    kpi("-O3 runtime", ms(base), "median wall time"),
    kpi("selected runtime", ms(pick), shipped ? `saves ${ms(base - pick)} per run` : "same binary as -O3", shipped ? "ok" : ""),
    kpi("speedup", x(sp, 3), shipped ? `CI ${ci(spci)}` : "", shipped ? "ok" : ""),
    kpi(".text size", r.text_size && r.o3_text_size ? `${(r.text_size / r.o3_text_size).toFixed(2)}×` : "1.00×", `${r.text_size || r.o3_text_size || "?"} B vs ${r.o3_text_size || "?"} B`),
    kpi("candidates", `${r.rl_proposals || 0} + ${r.library || 0}`, `RL + library · ${r.n_compiled} compiled · ${r.n_timed} timed`),
    kpi("total time", secs(r.total_s), `compile ${secs(r.compile_s)} · timing ${secs(r.timing_s)}`));
  box.append(kp);

  const row = h("div", { class: "grid g2", style: "margin-top:18px" });
  const ed = h("div", { class: "card" }, h("div", { class: "card-h" }, h("div", { class: "ico", html: icon.sparkle }), h("div", {}, h("h3", {}, "What changed vs -O3"), h("div", { class: "sub" }, "edits to the -O3 pipeline, explained"))),
    shipped ? editsList(r.shipped_edits, r.shipped_raw) : h("div", { class: "muted" }, "Nothing: -O3 was shipped."));
  const cc = h("div", { class: "card" }, h("div", { class: "card-h" }, h("div", { class: "ico", html: icon.chart }), h("div", {}, h("h3", {}, "Every timed candidate vs -O3"), h("div", { class: "sub" }, `${r.n_timed} candidates, interleaved with -O3 · bars = speedup, whiskers = 95% CI`))),
    h("div", { class: "chart" }, h("canvas", { id: "tune-cands" })),
    h("div", { class: "legend", style: "margin-top:8px" }, h("span", { html: `<i style="background:${C.rl}"></i>RL proposal` }), h("span", { html: `<i style="background:${C.lib}"></i>library pipeline` }), h("span", { html: `<i style="border:1px dashed ${C.o3}"></i>-O3 = 1.00×` })));
  row.append(ed, cc);
  box.append(row);
  const timed = (r.timed || []).map((t, i) => ({ ...t, i })).sort((a, b) => (b.speedup || 0) - (a.speedup || 0));
  chart("tune-cands", {
    type: "bar",
    data: { labels: timed.map((t) => `#${t.i + 1} ${t.source}`), datasets: [{ data: timed.map((t) => t.speedup), ci: timed.map((t) => t.ci), backgroundColor: timed.map((t) => (t.source === "RL" ? C.rl : C.lib) + "cc"), borderRadius: 5 }] },
    options: { indexAxis: "y", plugins: { legend: { display: false }, refLine: { value: 1, label: "-O3" }, tooltip: { callbacks: { label: (c) => `${x(c.raw)} · ${ms(timed[c.dataIndex].median_ms)}` } } },
      scales: { x: speedAxis("speedup vs -O3", { suggestedMin: 0.9 }), y: { grid: { display: false } } } },
  });

  box.append(h("div", { style: "margin-top:18px" }, sequenceSection(diff, "Selected sequence vs -O3 sequence")));

  const t = h("div", { class: "card", style: "margin-top:18px" }, h("div", { class: "card-h" }, h("div", { class: "ico", html: icon.list }), h("div", {}, h("h3", {}, "Timed candidates in detail"), h("div", { class: "sub" }, `selection run: ${r.timed?.length || 0} binaries + -O3, interleaved; -O3 median ${ms(r.base_median_ms)}`))));
  const tbl = h("table", { class: "tbl" });
  tbl.innerHTML = `<thead><tr><th>#</th><th>source</th><th>edits</th><th class="num">median runtime</th><th class="num">speedup</th><th class="num">95% CI</th><th class="num">.text</th></tr></thead>
    <tbody><tr><td>–</td><td><span class="badge">-O3</span></td><td class="muted">baseline</td><td class="num">${ms(r.base_median_ms)}</td><td class="num">1.000×</td><td></td><td class="num">${r.o3_text_size || ""}</td></tr>
    ${timed.map((c) => `<tr class="${shipped && JSON.stringify(c.edits) === JSON.stringify(r.shipped_edits) ? "hl" : ""}"><td>${c.i + 1}</td><td><span class="badge ${c.source === "RL" ? "rl" : "lib"}">${c.source}</span></td>
      <td style="font-size:12px">${editsShort(c.edits, c.raw)}</td><td class="num">${ms(c.median_ms)}</td><td class="num ${cls(c.speedup)}">${x(c.speedup)}</td><td class="num muted">${ci(c.ci)}</td><td class="num">${c.text_size || ""}</td></tr>`).join("")}</tbody>`;
  t.append(h("div", { style: "overflow:auto" }, tbl));
  if (shipped) t.append(h("div", { class: "muted", style: "font-size:12.5px;margin-top:10px" }, "Highlighted row = shipped. The selection run picks the fastest; a separate confirmation run re-measures it (the selection speedup of the best of k is biased upward)."));
  box.append(t);

  if (r.top_ranked?.length) {
    const rk = h("div", { class: "card", style: "margin-top:18px" }, h("div", { class: "card-h" }, h("div", { class: "ico", html: icon.sparkle }), h("div", {}, h("h3", {}, "Model ranking (before timing)"), h("div", { class: "sub" }, `the supervised model scored ${(r.rl_proposals || 0) + (r.library || 0)} pipelines; ${r.rl_in_top20_ranked || 0} RL proposals in its top 20`))));
    rk.append(h("div", { class: "flagrow" }, r.top_ranked.map((t) => h("span", { class: `badge ${t.source === "RL" ? "rl" : "lib"}` }, `#${t.rank} ${t.source} · pred ${x(t.predicted_speedup, 2)} · ${t.n_edits} edit${t.n_edits === 1 ? "" : "s"}`))));
    rk.append(h("div", { class: "muted", style: "font-size:12.5px" }, "Predictions are only a ranking; the model is weak on unseen programs (Spearman ≈ 0.1), which is why tune always times its picks."));
    box.append(rk);
  }
}

function renderPredict(box, r, diff) {
  const rec = r.recommended;
  box.append(verdict(rec ? "" : "neutral", rec ? x(r.predicted_speedup, 2) : "-O3",
    rec ? `Recommends a pipeline · confidence ${r.confidence}` : "Recommends keeping -O3",
    `${esc(r.reason || "")}${rec ? ` · predicted range ${ci(r.range)}` : ""}<br><span class="faint">The choice is made without running the program${r.measured ? "; the measurement below then times the top pick once" : ""}. ${r.applied ? "The recommended pipeline was applied to the binary." : "The binary written is -O3 (advisory mode)."}</span>`,
    h("span", { class: "badge rl" }, r.mode)));
  const g = r.gate || {};
  const ck = (r.top && r.top[0] && r.top[0].checks) || {};
  box.append(h("div", { class: "grid g6", style: "margin-top:14px" },
    kpi("predicted speedup", x(r.predicted_speedup, 3), `range ${ci(r.range)}`, rec ? "ok" : ""),
    kpi("model agreement", r.member_agreement != null ? `${(r.member_agreement * 100).toFixed(0)}%` : "–", `need ≥ ${((g.agree ?? 0.8) * 100).toFixed(0)}% of 7 models`),
    kpi("harm probability", r.p_harmful != null ? r.p_harmful.toFixed(2) : "–", `need < ${g.tau ?? 0.5}`),
    kpi("-O3 build", secs(r.o3_build_s), "plain -O3 compile"),
    kpi("predict total", secs(r.predict_total_s), `+${secs(r.added_over_o3_s)} over -O3`),
    kpi(".text -O3", `${r.o3_text_size || "?"} B`, "size of the -O3 binary")));

  if (r.measured) box.append(measuredCard(r.measured));
  const gate = h("div", { class: "card", style: "margin-top:18px" }, h("div", { class: "card-h" }, h("div", { class: "ico", html: icon.scale }), h("div", {}, h("h3", {}, "Safety gate"), h("div", { class: "sub" }, "all three must pass, otherwise -O3"))),
    h("div", { class: "checks" },
      [["pessimistic estimate", `mean − 1.28·std of 7 models > ${(1 + (g.margin ?? 0.03)).toFixed(2)}×`, ck.pessimistic, r.range ? `${x(r.range[0])}` : ""],
       ["models agree", `≥ ${((g.agree ?? 0.8) * 100).toFixed(0)}% predict a gain`, ck.agreement, r.member_agreement != null ? `${(r.member_agreement * 100).toFixed(0)}%` : ""],
       ["not likely harmful", `harm classifier p < ${g.tau ?? 0.5}`, ck.harm, r.p_harmful != null ? r.p_harmful.toFixed(2) : ""]].map(([n, d, ok, v]) =>
        h("div", { class: "chk" }, h("span", { class: `dot ${ok ? "ok" : "bad"}` }), h("span", { class: "n" }, n), h("span", { class: "muted", style: "font-size:12px" }, d), h("span", { class: "d" }, v)))));
  const ed = h("div", { class: "card", style: "margin-top:18px" }, h("div", { class: "card-h" }, h("div", { class: "ico", html: icon.sparkle }), h("div", {}, h("h3", {}, "Recommended edits vs -O3"), h("div", { class: "sub" }, `from the ${r.source || "safe pool"}`))),
    rec ? editsList(r.recommended_edits) : h("div", { class: "muted" }, "No candidate passed the gate."));
  box.append(h("div", { class: "grid g2" }, gate, ed));
  box.append(h("div", { style: "margin-top:18px" }, sequenceSection(diff, "Recommended sequence vs -O3 sequence")));

  if (r.top?.length) {
    const c = h("div", { class: "card", style: "margin-top:18px" }, h("div", { class: "card-h" }, h("div", { class: "ico", html: icon.chart }), h("div", {}, h("h3", {}, "Top 10 candidates (shown even if they fail the gate)"), h("div", { class: "sub" }, "bars = predicted speedup, whiskers = pessimistic … optimistic range"))),
      h("div", { class: "chart" }, h("canvas", { id: "pred-top" })));
    const tbl = h("table", { class: "tbl", style: "margin-top:14px" });
    tbl.innerHTML = `<thead><tr><th>#</th><th>source</th><th>edits</th><th class="num">predicted</th><th class="num">range</th><th class="num">agree</th><th class="num">p harm</th><th>gate</th></tr></thead><tbody>
      ${r.top.map((t, i) => `<tr class="${i === 0 && rec ? "hl" : ""}"><td>${i + 1}</td><td><span class="badge ${/RL/.test(t.source) ? "rl" : "lib"}">${esc(t.source)}</span></td><td style="font-size:12px">${editsShort(t.edits)}</td>
      <td class="num ${cls(t.predicted_speedup)}">${x(t.predicted_speedup)}</td><td class="num muted">${ci(t.range)}</td><td class="num">${(t.agreement * 100).toFixed(0)}%</td><td class="num">${t.p_harmful?.toFixed(2)}</td>
      <td>${Object.entries(t.checks).map(([k, v]) => `<span class="badge ${v ? "ok" : "bad"}" title="${k}">${v ? "✓" : "✗"} ${k.slice(0, 5)}</span>`).join(" ")}</td></tr>`).join("")}</tbody>`;
    c.append(h("div", { style: "overflow:auto" }, tbl));
    box.append(c);
    chart("pred-top", {
      type: "bar",
      data: { labels: r.top.map((t, i) => `#${i + 1}`), datasets: [{ data: r.top.map((t) => t.predicted_speedup), ci: r.top.map((t) => t.range), backgroundColor: r.top.map((t) => (Object.values(t.checks).every(Boolean) ? C.ok : C.pred) + "bb"), borderRadius: 5 }] },
      options: { plugins: { legend: { display: false }, refLine: { value: 1, label: "-O3" } }, scales: { y: speedAxis("predicted speedup", { suggestedMin: 0.95 }), x: { grid: { display: false } } } },
    });
  }
  box.append(h("div", { class: "callout warn", style: "margin-top:18px", html: "<b>How much to trust predict.</b> On 33 held-out programs predict's gated picks gave a geomean of +0.6% (CI −0.2…+1.7%), 1 regression. The model ranks well on programs it trained on (Spearman 0.42) but weakly on unseen ones (0.11): runtime effects of pass edits are hard to see without running. Use <b>Tune</b> when you can run the program." }));
}

// Predict's top pick, compiled and timed against -O3 after the prediction (reporting only).
function measuredCard(m) {
  const ok = m.status === "ok";
  const k = !ok ? "warn" : m.verdict === "faster" ? "ok" : m.verdict === "slower" ? "bad" : "";
  const card = h("div", { class: "card", style: "margin-top:18px" },
    h("div", { class: "card-h" }, h("div", { class: "ico", html: icon.chart }),
      h("div", {}, h("h3", {}, "Measured: the pick vs -O3"), h("div", { class: "sub" }, `${m.which} · compiled, output checked against -O0, timed ${m.rounds} interleaved rounds with an A/A control`)),
      h("div", { class: "spacer" }), h("span", { class: `badge ${k === "bad" ? "bad" : k === "ok" ? "ok" : "warn"}` }, ok ? m.verdict : m.status.replace("_", " "))));
  if (!ok) {
    card.append(h("div", { class: `callout ${m.status === "same_binary" ? "" : "warn"}` }, m.note || m.status,
      m.status === "same_binary" ? " — so it runs exactly like -O3 (1.000×)." : ""));
    return card;
  }
  card.append(h("div", { class: "grid g6" },
    kpi("-O3 runtime", ms(m.o3_median_ms), "median wall time"),
    kpi("pick runtime", ms(m.pick_median_ms), m.pick_median_ms < m.o3_median_ms ? `saves ${ms(m.o3_median_ms - m.pick_median_ms)} per run` : `${ms(m.pick_median_ms - m.o3_median_ms)} slower per run`, k),
    kpi("measured speedup", x(m.speedup, 3), `95% CI ${ci(m.ci)}`, k),
    kpi("predicted", x(m.predicted_speedup, 3), "what the models expected"),
    kpi("A/A control", x(m.control, 3), m.control_ok ? "clean: timing trustworthy" : "noisy: re-run on a quiet machine", m.control_ok ? "" : "warn"),
    kpi(".text size", m.text_size ? `${m.text_size} B` : "–", `measured in ${secs(m.measure_s)}`)));
  card.append(h("div", { class: "chart short", style: "margin-top:14px" }, h("canvas", { id: "pred-meas" })));
  card.append(h("div", { class: "mini", style: "margin-top:8px" }, "This measurement does not change predict's decision or the binary it writes; it shows how the guess actually performs on your program and input."));
  setTimeout(() => chart("pred-meas", {
    type: "bar",
    data: { labels: ["-O3", "predict's pick"], datasets: [{ data: [m.o3_median_ms, m.pick_median_ms], backgroundColor: [C.o3 + "aa", (k === "ok" ? C.ok : k === "bad" ? C.bad : C.pred) + "cc"], borderRadius: 6 }] },
    options: { indexAxis: "y", plugins: { legend: { display: false }, tooltip: { callbacks: { label: (c) => ms(c.raw) } } },
      scales: { x: { min: 0, grid: { color: C.grid }, title: { display: true, text: "median runtime (ms)", color: C.muted } }, y: { grid: { display: false } } } },
  }), 0);
  return card;
}

function renderCompare(box, r) {
  const rows = r.rows || [];
  const best = rows.filter((x) => x.method !== "A/A control").reduce((a, b) => ((b.speedup || 0) > (a?.speedup || 0) ? b : a), null);
  const ctl = rows.find((x) => x.method === "A/A control");
  box.append(verdict(best && best.speedup > 1.01 ? "" : "neutral", best ? x(best.speedup, 2) : "–", `Fastest: ${best?.method || "-O3"}`,
    `All binaries timed in one interleaved run against -O3 (median ${ms(r.o3_median_ms)}). A/A control (a byte-identical copy of -O3): ${ctl ? x(ctl.speedup) : "–"} — the noise floor of this run.`));
  const colors = { O2: C.o3, Os: C.o3, predict: C.pred, tune: C.rl, "A/A control": "#475569" };
  const c = h("div", { class: "card", style: "margin-top:18px" }, h("div", { class: "card-h" }, h("div", { class: "ico", html: icon.chart }), h("div", {}, h("h3", {}, "Speedup vs -O3 by method"), h("div", { class: "sub" }, "whiskers = 95% bootstrap CI; methods that kept -O3 sit at 1.00×"))),
    h("div", { class: "chart tall" }, h("canvas", { id: "cmp-chart" })));
  box.append(c);
  chart("cmp-chart", {
    type: "bar",
    data: { labels: rows.map((x) => x.method), datasets: [{ data: rows.map((x) => x.speedup), ci: rows.map((x) => x.ci), backgroundColor: rows.map((x) => (colors[x.method] || (/ga/.test(x.method) ? C.ga : C.lib)) + "cc"), borderRadius: 6 }] },
    options: { indexAxis: "y", plugins: { legend: { display: false }, refLine: { value: 1, label: "-O3" } },
      scales: { x: speedAxis("speedup vs -O3", { min: Math.floor(Math.min(0.95, ...rows.map((r) => (r.ci && r.ci[0]) || r.speedup || 1)) * 20) / 20 }), y: { grid: { display: false } } } },
  });
  const tbl = h("table", { class: "tbl" });
  tbl.innerHTML = `<thead><tr><th>method</th><th class="num">median runtime</th><th class="num">speedup</th><th class="num">95% CI</th><th>note</th></tr></thead><tbody>
    <tr><td><span class="badge">-O3</span></td><td class="num">${ms(r.o3_median_ms)}</td><td class="num">1.000×</td><td></td><td class="muted">baseline</td></tr>
    ${rows.map((x2) => `<tr><td><b>${esc(x2.method)}</b></td><td class="num">${x2.median_ms ? ms(x2.median_ms) : ms(r.o3_median_ms)}</td><td class="num ${cls(x2.speedup)}">${x(x2.speedup)}</td><td class="num muted">${ci(x2.ci)}</td><td class="muted">${esc(x2.note || "")}</td></tr>`).join("")}</tbody>`;
  box.append(h("div", { class: "card", style: "margin-top:18px;overflow:auto" }, tbl));
  const n = r.notes || {};
  const notes = h("div", { class: "grid g2", style: "margin-top:18px" });
  if (n.tune) notes.append(h("div", { class: "callout" }, h("b", {}, "tune: "), n.tune.choice === "candidate" ? `shipped a pipeline from the ${n.tune.shipped_from}, selection ${x(n.tune.select_speedup)}` + (n.tune.confirm?.speedup ? `, confirmation ${x(n.tune.confirm.speedup)}` : "") : `kept -O3 (${n.tune.reason || ""})`));
  if (n.predict) notes.append(h("div", { class: "callout" }, h("b", {}, "predict: "), `${n.predict.ship ? `predicted ${x(n.predict.predicted_speedup)}` : "kept -O3"} — ${n.predict.reason || ""}`));
  box.append(notes);
}

function renderSelftest(box, r) {
  box.append(verdict(r.verdict === "PASS" ? "" : "warn", r.verdict, r.verdict === "PASS" ? "Timing on this machine is trustworthy right now" : "Timing quality is not good enough right now",
    "A/A bias, CI width, drift and -O0 vs -O3 sanity check on a reference program. If it fails, other processes are probably loading the machine."));
  box.append(h("pre", { class: "card mono", style: "margin-top:14px;font-size:12px;white-space:pre-wrap" }, (r.lines || []).join("\n")));
}

window.ncRun = { openJob, openSaved };
