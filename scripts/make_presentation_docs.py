#!/usr/bin/env python3
"""Presentation material for the 4-person dashboard demo:
  docs/Presentation_Script.pdf   who says what, what to click, numbers to remember, likely questions
  docs/Glossary_and_QA.pdf       every abbreviation / uncommon term, plus hard cross-questions with answers

Numbers come from dashboard/static/data/research.json and the saved dashboard runs (same sources as the
dashboard itself). Rendering reuses scripts/make_report_pdf.py (CSS-free helpers + headless Chrome).
Usage: .venv/bin/python scripts/make_presentation_docs.py
"""
from __future__ import annotations

import html
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import make_report_pdf as R  # noqa: E402

REPO = R.REPO
D = R.D
E = html.escape
pct, xx = R.pct, R.xx

CSS = """
@page { size: A4; margin: 15mm 15mm 16mm 15mm; }
* { box-sizing: border-box; }
body { font-family: Inter, "Segoe UI", Arial, sans-serif; color: #1f2937; font-size: 10.2pt; line-height: 1.5; margin: 0; }
h1 { font-size: 26pt; margin: 0 0 6px; letter-spacing: -.02em; color: #1e1b4b; }
h2 { font-size: 15pt; color: #312e81; border-bottom: 2px solid #c7d2fe; padding-bottom: 4px; margin: 20px 0 10px; break-after: avoid; }
h3 { font-size: 11.5pt; color: #3730a3; margin: 14px 0 6px; break-after: avoid; }
h4 { font-size: 10.5pt; margin: 10px 0 4px; color: #111827; break-after: avoid; }
.pb { break-before: page; }
.cover { padding: 26px 28px; border-radius: 14px; background: linear-gradient(160deg, #eef2ff 0%, #ecfeff 100%); margin-bottom: 14px; }
.cover p { color: #4b5563; }
p { margin: 0 0 7px; } ul, ol { margin: 4px 0 8px 18px; padding: 0; } li { margin: 2px 0; }
code { font-family: "JetBrains Mono", Consolas, monospace; font-size: 8.6pt; background: #f3f4f6; padding: 0 3px; border-radius: 3px; }
table { width: 100%; border-collapse: collapse; margin: 8px 0 12px; font-size: 9pt; }
th { text-align: left; background: #eef2ff; color: #3730a3; font-weight: 600; padding: 5px 6px; border-bottom: 1px solid #c7d2fe; }
td { padding: 4px 6px; border-bottom: 1px solid #e5e7eb; vertical-align: top; }
tr { break-inside: avoid; }
.speaker { border-radius: 12px; padding: 12px 16px; margin: 6px 0 12px; color: white; break-after: avoid; }
.speaker b { font-size: 15pt; } .speaker span { display: block; opacity: .9; font-size: 9.5pt; }
.s1 { background: linear-gradient(135deg, #7c3aed, #6366f1); } .s2 { background: linear-gradient(135deg, #0891b2, #0ea5e9); }
.s3 { background: linear-gradient(135deg, #059669, #10b981); } .s4 { background: linear-gradient(135deg, #db2777, #f43f5e); }
.beat { border: 1px solid #e5e7eb; border-radius: 10px; padding: 10px 12px; margin: 8px 0; break-inside: avoid; }
.beat .do { font-size: 9pt; color: #0369a1; background: #f0f9ff; border-radius: 6px; padding: 5px 8px; margin-bottom: 6px; }
.beat .do::before { content: "ON SCREEN  "; font-weight: 700; letter-spacing: .05em; font-size: 8pt; }
.beat .say { font-size: 10.2pt; }
.beat .say::before { content: "SAY  "; font-weight: 700; color: #6d28d9; letter-spacing: .05em; font-size: 8pt; }
.nums { background: #fefce8; border: 1px solid #fde68a; border-radius: 8px; padding: 8px 12px; margin: 8px 0; font-size: 9.4pt; break-inside: avoid; }
.nums::before { content: "NUMBERS TO REMEMBER"; display: block; font-weight: 700; color: #a16207; font-size: 8pt; letter-spacing: .05em; margin-bottom: 3px; }
.hand { font-style: italic; color: #4b5563; border-left: 3px solid #a5b4fc; padding-left: 10px; margin: 8px 0; }
.qa { border-left: 3px solid #f59e0b; background: #fffbeb; padding: 6px 10px; margin: 6px 0; border-radius: 0 8px 8px 0; break-inside: avoid; font-size: 9.6pt; }
.qa b { display: block; color: #92400e; }
.warn { border-left: 4px solid #dc2626; background: #fef2f2; padding: 8px 12px; border-radius: 6px; margin: 8px 0; break-inside: avoid; }
.tip { border-left: 4px solid #6366f1; background: #f5f3ff; padding: 8px 12px; border-radius: 6px; margin: 8px 0; break-inside: avoid; }
dl { margin: 0; } dt { font-weight: 700; color: #1e1b4b; margin-top: 7px; break-after: avoid; } dd { margin: 1px 0 0 14px; }
.cat { columns: 1; }
.term { break-inside: avoid; }
.small { font-size: 9pt; }
"""


def doc(title, body):
    return f'<!doctype html><html lang="en"><head><meta charset="utf-8"><title>{E(title)}</title><style>{CSS}</style></head><body>{body}</body></html>'


def beat(do, say):
    return f'<div class="beat"><div class="do">{do}</div><div class="say">{say}</div></div>'


def qa(q, a):
    return f'<div class="qa"><b>Q: {q}</b>{a}</div>'


def nums(items):
    return '<div class="nums">' + " · ".join(items) + "</div>"


def saved(slug):
    p = REPO / "dashboard/saved" / f"{slug}.json"
    return json.loads(p.read_text()) if p.exists() else {}


# ====================================================================== script
def script_html():
    hl, t, S = D["headline"], D["headline"]["tune_rlsl"], D["eval"]["summary"]
    c, H5, G3, md = D["corpus"], D["phase5"], D["gate3"], D["models"]
    evl = saved("tune-interpreter-loop-3-83x-rl-pick").get("result", {})
    mm = saved("tune-matrix-multiply-1-66x").get("result", {})
    pf = saved("predict-fibonacci-measured-1-23x").get("result", {}).get("measured", {})
    pm = saved("predict-matrix-multiply-gate-keeps--o3").get("result", {}).get("measured", {})
    br = saved("tune-branchy-code--o3-fallback").get("result", {})
    cm = saved("compare-matrix-multiply-all-methods").get("result", {})
    ev_cf = evl.get("confirm", {})
    mm_cf = mm.get("confirm", {})
    cmp_rows = {r["method"]: r for r in cm.get("rows", [])}

    B = []
    A = B.append
    A(f"""<div class="cover"><h1>NeuroCompiler — presentation script</h1>
    <p><b>Team:</b> Chirag (opening + Run page) · Dhanush Singh (Research page, sections 01–05) · Nithin (Research page, sections 06–10) · Gagan (Architecture page + closing)</p>
    <p>Each part lists <b>what is on screen</b> (what to click in the dashboard), <b>what to say</b> (read it or say it in your own words),
    the <b>numbers to remember</b>, the <b>hand-over line</b> to the next speaker, and the questions you are most likely to get.
    Every number here is measured and comes from the dashboard's own data. If you are asked something not covered here,
    the companion file <i>Glossary_and_QA.pdf</i> explains every term and the hard questions.</p>
    <p class="small">Generated {time.strftime('%Y-%m-%d')} by <code>scripts/make_presentation_docs.py</code>.</p></div>""")

    # ---- run of show
    A("<h2>Running order (about 20–25 minutes + questions)</h2>" + R.table(["#", "speaker", "part", "dashboard", "time"], [
        ["1", "Chirag", "Opening: the problem and the idea", "Run page (mode cards at the top)", "2 min"],
        ["2", "Chirag", "Live demo + saved runs: tune, predict, compare", "Run page", "6–7 min"],
        ["3", "Dhanush Singh", "Overview, corpus, measurement, headroom gate, wider search", "Research & results · 01–05", "5–6 min"],
        ["4", "Nithin", "Pass knowledge, models, held-out test, IR ≠ runtime, timeline", "Research & results · 06–10", "5–6 min"],
        ["5", "Gagan", "Architecture, flows, limitations, conclusion", "Architecture page", "4–5 min"],
        ["6", "everyone", "Questions (each person answers for their own part)", "any page", "5–10 min"]]))

    A("""<div class="warn"><b>Golden rule for everyone:</b> say what is <b>measured</b> and what is <b>predicted</b>. Measured = we ran the program and timed it against -O3. Predicted = a model's guess.
    If unsure, say "that is measured on 33 test programs the models never saw" or "that is the model's prediction, which we then measure".</div>""")
    A("""<h2>Before the presentation (checklist)</h2><ol>
      <li>Start the system: double-click <code>dashboard\\windows\\Start-NeuroCompiler.bat</code> (or <code>./dashboard/run.sh</code> in WSL). The browser opens <b>http://localhost:8000</b>.</li>
      <li>On the Run page, click <b>Check</b> in the Environment card. All checks should be green. "Machine quiet for timing" may be amber if other programs are busy: close heavy apps (games, video calls, extra browser tabs).</li>
      <li>Optional, 1 minute: click <b>Run timing selftest</b>, so you can say "timing is verified right now".</li>
      <li>Zoom the browser to about 90% so cards fit on the projector. Use full screen (F11).</li>
      <li>Check that the saved runs appear in <b>Background tasks → Saved runs</b>: tune (matrix multiply, Fibonacci, interpreter loop, branchy), predict (4), compare (1).</li>
      <li>During any live timing job, nobody runs heavy software on the laptop (it would disturb the measurement; the "quiet guard" would pause the job).</li>
    </ol>
""")

    # ================= CHIRAG
    A('<div class="pb"></div><div class="speaker s1"><b>Part 1–2 · Chirag</b><span>Opening and the Run page (live demo)</span></div>')
    A("<h3>Opening (≈ 2 min)</h3>")
    A(beat("Run page, top of the page (mode cards). Optionally switch to <b>Research &amp; results</b> → 01 Overview for the KPI cards, then come back.",
           "Every C or C++ program is compiled with a fixed list of optimizations called <b>-O3</b>. It is a good compromise for typical code, but it is the same for every program. "
           "Our question was: <b>can machine learning pick a better list of optimizations for one specific program, and make it actually run faster?</b> "
           "Not smaller, not fewer instructions — faster, measured with a stopwatch, on programs the models have never seen."))
    A(beat("Say the headline numbers (they are also the KPI cards in Research &amp; results → 01 Overview).",
           f"On 33 test programs from 11 program families that were never used in training, our final system is <b>{pct(t['geomean'], 1)}</b> faster than -O3 on average (geometric mean), "
           f"<b>{t['ge5']} of {t['n']}</b> programs are at least 5% faster, and <b>{t['slower']}</b> programs became slower. Because when we can't prove a speed-up, we simply keep -O3."))
    A(beat("Point at the three mode cards.",
           "The system has three modes. <b>Tune</b> is the main one: machine learning proposes candidates, and we measure them. "
           "<b>Predict</b> guesses without running the program, then we time its guess once to show how good it was. "
           "<b>Compare</b> runs every method side by side in one fair timing run."))

    A("<h3>Live demo: start a tune job first (it takes ~80 s)</h3>")
    A(beat("Mode = <b>Tune</b>. Tab <b>Examples</b> → click <b>Matrix multiply (C)</b>. The code appears in the editor and args become <code>800</code>. Click <b>Run tune</b>.",
           "I'll start a real job now, because it takes about a minute and a half. I chose a matrix-multiplication program. "
           "You can also paste your own code or upload files — the box here lists what programs are accepted: C or C++ with a main function, deterministic, printing its result, running roughly 0.1 to 10 seconds."))
    A(beat("Point at the <b>Accepted programs</b> box, then at the <b>terminal</b> panel on the right as lines appear.",
           "The program must print its result because we compare the output of every optimized version with the unoptimized version — if anything changes, that version is thrown away. "
           "On the right is the live terminal: it's the actual output of the tool running inside Linux (WSL2). You can see the steps: "
           "<b>[reference]</b> runs the unoptimized build to get the correct output, <b>[rl]</b> the reinforcement-learning agent proposes pipelines, "
           "<b>[rank]</b> the supervised model scores about 940 candidates, <b>[compile]</b> the best ones are compiled and checked, <b>[timing]</b> 8 candidates are timed against -O3, "
           "and <b>[confirm]</b> the winner is re-measured in a fresh run before we trust it."))
    A(beat("While it runs: point at the <b>Environment</b> card and the <b>Background tasks</b> list.",
           "The environment card checks that we are in WSL2, that the compiler is exactly LLVM 18.1.8, that the trained model files are unchanged (we check their hashes), "
           "and that the machine is quiet enough for timing. Jobs run one at a time, so two timings never disturb each other."))

    A("<h3>Explain a finished result (use the saved interpreter run while the live job runs)</h3>")
    A(beat("Background tasks → Saved runs → <b>Tune · interpreter loop (3.83x, RL pick)</b>. Scroll to the results.",
           f"Here is a finished run on an interpreter program. -O3 takes <b>{ev_cf.get('base_median_ms', 848):.0f} ms</b>; the pipeline we chose takes <b>{ev_cf.get('pick_median_ms', 221):.0f} ms</b> — "
           f"<b>{ev_cf.get('speedup', 3.83):.2f}× faster</b>, with a 95% confidence interval of {ev_cf.get('ci', [0, 0])[0]:.3f} to {ev_cf.get('ci', [0, 0])[1]:.3f}. "
           "It was confirmed in a fresh 20-round run, and the A/A control — an identical copy of -O3 timed alongside — came out at 1.000, so the measurement is clean. This pipeline came from the RL agent."))
    A(beat("Card <b>What changed vs -O3</b>.",
           "These are the changes to -O3, in plain words: tail duplication size 6 in the code generator, a cap on loop unrolling, and removing every SimplifyCFG pass. "
           "The reason it works: in an interpreter, -O3's SimplifyCFG merges the 31 separate jump points of the dispatch loop into one, so the CPU's branch predictor can't learn the pattern. Keeping them separate makes it almost 4× faster."))
    A(beat("Card <b>Every timed candidate vs -O3</b> (bar chart), then scroll to <b>Selected sequence vs -O3 sequence</b>.",
           "Pink bars are RL proposals, blue are pipelines from our library; whiskers are confidence intervals. "
           "Below, the full pass list of -O3 on the left and our sequence on the right — red rows are passes we removed, green ones we added, yellow ones whose options changed. "
           "The table under it gives each candidate's median runtime in milliseconds."))

    A("<h3>Back to the live job</h3>")
    A(beat("Click the live job in Background tasks (status <b>done</b>). Show the verdict banner and the KPIs.",
           f"The live job finished. -O3 runs in about <b>{mm_cf.get('base_median_ms', 423):.0f} ms</b>, our pipeline in about <b>{mm_cf.get('pick_median_ms', 254):.0f} ms</b> — roughly <b>1.66×</b> faster "
           "(today's exact numbers are on screen). The binary can be downloaded with the Binary button."))
    A(beat("Saved run <b>Tune · branchy code (-O3 fallback)</b>.",
           "And this is just as important: on this branchy program nothing beat -O3 convincingly, so the system shipped -O3. In one run the best candidate looked 4% faster in the first measurement "
           "but only 1.5% in the fresh confirmation, which was not enough. That confirmation step is what keeps us from ever shipping something slower."))

    A("<h3>Predict and Compare (≈ 2 min)</h3>")
    A(beat("Saved run <b>Predict · Fibonacci (measured 1.23x)</b>. Show the verdict, the safety gate, then the <b>Measured: the pick vs -O3</b> card.",
           f"Predict never runs the program to choose — it guesses from the code alone, in about a second. Three safety checks must pass: the pessimistic estimate, agreement of 7 models, and a low harm probability. "
           f"Then we compile its pick and time it once, just to show the truth: predicted 1.17×, measured <b>{pf.get('speedup', 1.23):.2f}×</b> ({pf.get('pick_median_ms', 778):.0f} ms vs {pf.get('o3_median_ms', 956):.0f} ms)."))
    A(beat("Saved run <b>Predict · matrix multiply (gate keeps -O3)</b>.",
           f"Here the gate said 'not confident, keep -O3'. We timed its best guess anyway: <b>{pm.get('speedup', 0.99):.3f}×</b> — slightly slower. So the gate was right. "
           "Over the 33 test programs predict averaged only +0.6%, so it's offered as advisory; tune is the real product."))
    A(beat("Saved run <b>Compare · matrix multiply (all methods)</b>.",
           f"Compare times every method in one run: -O2 and -Os are about equal to -O3, tune is <b>{cmp_rows.get('tune', {}).get('speedup', 1.657):.2f}×</b>, random search found a similar pipeline this time, "
           f"the genetic algorithm found nothing, and the A/A control is {cmp_rows.get('A/A control', {}).get('speedup', 1.0):.3f} — that's the noise floor of this run."))
    A(nums([f"tune test result <b>{pct(t['geomean'], 1)}</b> geomean, CI {pct(t['ci'][0], 1)}…{pct(t['ci'][1], 1)}", f"excl. largest {pct(t['excl_largest'], 1)}",
            f"{t['ge5']}/33 ≥ +5%, {t['slower']} slower", "interpreter 3.83× (848 → 221 ms)", "matmul ≈ 1.66× (≈ 423 → 254 ms)", "Fibonacci tune 1.14×, predict 1.23×",
            "predict test average +0.64% (advisory)", "~940 candidates ranked → 8 timed → 1 confirmed (20 rounds)"]))
    A("""<p class="hand">Hand-over: "That's what the system does for one program. Dhanush will now show how we built the data and proved that this headroom exists at all."</p>""")
    A("<h4>Questions Chirag should be ready for</h4>" + qa("Why not just always use -O3?", "For many programs -O3 is already best — the system then keeps -O3. But for some programs a different pipeline is much faster (here 1.2× to 3.8×), and -O3 can't know that because it applies the same steps to everyone.")
      + qa("How long does tune take?", "About 1–3 minutes for these demo programs: around 24–80 compilations plus a few minutes of timing at most. Predict takes about a second (plus an optional ~20–60 s measurement).")
      + qa("What if my program's input changes?", "The speed-up is measured for the input you give (args/stdin). A very different input can favour a different pipeline; the output check also uses that input. That's a stated limitation.")
      + qa("How do you know the faster binary is correct?", "Every candidate's output is compared (by hash) with the -O0 build's output; any difference and it is discarded. That's strong evidence for this input, not a mathematical proof.")
      + qa("Is the speed-up just noise?", "No: we time interleaved runs on a pinned CPU core, compute a 95% bootstrap confidence interval, require its lower bound above 1.01 in a fresh 20-round run, and check an A/A control (identical binary) that must be within 1%."))

    # ================= DHANUSH
    p5 = hl["phase5"]
    g = G3["fresh_summary"]
    A('<div class="pb"></div><div class="speaker s2"><b>Part 3 · Dhanush Singh</b><span>Research & results page, sections 01–05: overview, corpus, measurement, headroom gate, wider search</span></div>')
    A(beat("Click <b>Research &amp; results</b> in the top bar. Section <b>01 Overview</b>: the four KPI cards and Key findings.",
           f"This page shows how the project was built and tested. The headline: tune is <b>{pct(t['geomean'], 1)}</b> on unseen programs with no regressions; "
           f"a big search found <b>{pct(p5['geomean'], 1)}</b> of possible speed-up; and predict, which doesn't run the program, reached only <b>{pct(hl['predict']['geomean'], 1)}</b>. "
           "On the right are our pre-registered gates — checkpoints we defined before doing the work. Green passed, amber did not, and we report both."))
    A(beat("Section <b>02 Corpus generation</b>: the funnel, rejection chart, suites and families, runtime histogram, split bar.",
           f"We started from {c['scanned']} open-source benchmark programs — PolyBench and the LLVM test-suite. A program is kept only if it compiles at every optimization level, "
           f"gives the same output at every level, is deterministic, and runs between 0.35 and 3 seconds. {sum(r[1] for r in c['rejections'])} were rejected — most because they were too fast to time reliably. "
           f"That left <b>{c['usable']} programs in {c['families']} families</b>. A family is a group of programs that share code. "
           f"We split by family — {c['split']['counts']['train']} training, {c['split']['counts']['val']} validation, {c['split']['counts']['test']} test — so the test programs come from families the models never saw, "
           "and we froze the split before any model was trained."))
    A(beat("Section <b>03 Measurement</b>: 'How a speedup is measured', selftest table, parallel-timing chart.",
           "Everything depends on timing being trustworthy. We pin the program to one CPU core, run -O3 and the candidate interleaved in random order, and compute a paired speed-up with a bootstrap confidence interval. "
           "An A/A control — a byte-identical copy of -O3 — tells us the bias of each run. Our selftest showed bias of 0.3% or less and a confidence interval of ±0.12%. "
           "This chart shows we tested timing several programs at once: 5 cores made the noise too large, 3 cores with at most one memory-heavy program passed — so screening used 3 cores, "
           "and every number we report is re-measured on a single core."))
    A(beat("Section <b>04 Headroom (Phase 3)</b>: bar chart, gate decision callout.",
           f"Before building models we asked: is there anything to gain at all? On 15 fresh programs a search found <b>{pct(g['geomean'])}</b> on average, but only <b>4 of 15</b> reached +5% — our gate required 30%, we got 26.7%. "
           "So the gate was <b>not met</b>, and we say so. The team decided to continue with a lower target — the 'good' tier of +2 to 4% — and to re-check headroom with a wider search on new programs. We did not change the threshold to pass."))
    A(beat("Section <b>05 Wider search (Phase 5)</b>: KPIs, sorted bar chart, artifact table.",
           f"That wider search, on 115 programs never searched before, found <b>{pct(p5['geomean'], 1)}</b> on average (CI {pct(p5['ci'][0], 1)} to {pct(p5['ci'][1], 1)}), and <b>{p5['ge5']} of {p5['n']}</b> programs gained at least 5%. "
           f"Grey bars are programs where nothing beat -O3 — {p5['no_gain']} of them. We also checked suspicious winners: one program became 130× faster, but it executed 217× fewer instructions — "
           "the compiler had calculated the answer at compile time. We excluded it. This search data is what the models learn from."))
    A(nums([f"{c['scanned']} scanned → {c['usable']} usable, {c['families']} families", "split 91 / 22 / 33 (11 test families)", "A/A bias ≤ 0.3%, CI ±0.12%",
            "3 timing cores passed, 5 rejected", f"Phase 3 gate: {pct(g['geomean'])}, 4/15 ≥ 5% → NOT MET (needed 30%)",
            f"wider search {pct(p5['geomean'], 1)}, {p5['ge5']}/{p5['n']} ≥ 5%", "mandel-text excluded (217× fewer instructions)", "data quality 10.3% noisy controls (limit 10%) → labels down-weighted"]))
    A("""<p class="hand">Hand-over: "So the headroom is real but uneven. Nithin will show how the models learn to find it, and how the final system did on the test set."</p>""")
    A("<h4>Questions Dhanush should be ready for</h4>"
      + qa("You missed the gate and continued anyway — isn't that cheating?", "We report the miss with its numbers, didn't change the threshold, and wrote the decision down before continuing. The next phase re-measured headroom on 115 new programs, and all later gates stayed strict.")
      + qa("Why split by family and not randomly?", "Programs in a family share code. A random split would put near-copies in training and test, and the models would look better than they really are on new code.")
      + qa("Why at least 0.35 seconds runtime?", "Shorter runs are dominated by timing noise; the selftest showed 220 ms was too noisy and 400 ms passed.")
      + qa("What is a geometric mean, why not the normal average?", "Speed-ups are ratios; the geometric mean treats 2× faster and 2× slower symmetrically. The arithmetic mean would overstate gains.")
      + qa("Why report 'excluding the largest'?", "One huge win (e.g. 2.8×) can lift the average a lot. Showing the result without it proves the gain isn't from one program."))

    # ================= NITHIN
    tc = md["tune_cv"]["summary"]["gbr"]
    A('<div class="pb"></div><div class="speaker s3"><b>Part 4 · Nithin</b><span>Research & results page, sections 06–10: pass knowledge, training & validation, held-out test, IR ≠ runtime, timeline</span></div>')
    A(beat("Section <b>06 Pass knowledge</b>: stacked bar chart of edits.",
           "First we learned which single changes matter. We tried 346 single edits of -O3 on 31 programs. Each bar shows, out of 31 programs, where the edit was confirmed faster (green), confirmed slower (red), changed something insignificant, or produced an identical binary. "
           "The strongest levers are loop settings — vector width and unrolling — but every edit hurts some program. That's why there's no single better -O3: the choice must be per program."))
    A(beat("Section <b>07 Training &amp; validation</b>: 'does ranking beat random?' chart, features, RL curve, predict panel.",
           f"The supervised model is LightGBM, a gradient-boosted decision-tree model. It predicts how much faster a pipeline will be for a program, using about 130 program features. "
           f"We tested it the honest way: train on some families, test on a family it never saw, and repeat for every family. Its ranking correlation on unseen families is only about <b>{tc['spearman']:.2f}</b> — weak, but better than random: "
           f"the best of its top-5 picks averaged {xx(tc['gain@5'])} versus {xx(tc['rand_gain@5'])} for 5 random picks. "
           "The pink curve is the reinforcement-learning agent learning — but its reward is the model's prediction, not real time. And predict's models rank well on programs they trained on (0.42) but poorly on new ones (0.11) — that's why predict is weak."))
    A(beat("Section <b>08 Held-out test</b>: the method bar chart, then the summary table.",
           f"This is the final exam: 33 programs, 11 unseen families, every method re-measured on one core. Tune with RL + SL: <b>{pct(S['tune RL + SL']['geomean'])}</b>, CI {pct(S['tune RL + SL']['ci'][0], 1)} to {pct(S['tune RL + SL']['ci'][1], 1)}, zero programs slower. "
           f"SL alone: {pct(S['tune top-8 (SL)']['geomean'])}. Random search with the same budget of 8: {pct(S['random search@8']['geomean'])} with 6 slower; the genetic algorithm {pct(S['GA@8']['geomean'])}. "
           f"Very important: trusting the model's single guess without timing ('ML-only top-1') gives {pct(S['ML-only top-1']['geomean'])} but makes <b>16 of 33 slower</b>. "
           "So the models alone aren't reliable — the combination of model shortlist plus measurement is what works."))
    A(beat("Scroll to the per-program table and the 'paired against tune top-8' chart.",
           "Green cells are faster than -O3, red slower. Most programs stay at 1.000 because nothing convincing was found and -O3 was kept. The paired chart compares methods program by program; "
           "RL plus SL versus SL alone is +0.2%, which is not significant — we are honest that RL adds very little."))
    A(beat("Section <b>09 IR count ≠ runtime</b>: scatter plot.",
           f"Each dot is a measured candidate — {D['ir']['n']:,} of them. Horizontal: how many IR instructions it has compared to -O3; vertical: how much faster it actually ran. There's no relationship — correlation {D['ir']['rho']:.2f}. "
           "An earlier version of this project optimized instruction count and binary size and didn't get faster programs. That's why we only trust measured time."))
    A(beat("Section <b>10 Timeline &amp; decisions</b>.",
           "And here's the timeline, including the misses: the headroom gate not met, the surrogate gate first not met and then narrowly met, RL not beating the plain shortlist, predict advisory. Every number on this page is generated from result files by a script."))
    A(nums(["346 single edits on 31 programs", f"surrogate Spearman ≈ {tc['spearman']:.2f} on unseen families", f"gain@5 {xx(tc['gain@5'])} vs random {xx(tc['rand_gain@5'])}",
            f"test: RL + SL {pct(S['tune RL + SL']['geomean'])} (0 slower), SL {pct(S['tune top-8 (SL)']['geomean'])}", f"random@8 {pct(S['random search@8']['geomean'])}, GA@8 {pct(S['GA@8']['geomean'])}",
            f"ML-only top-1 {pct(S['ML-only top-1']['geomean'])}, 16 slower", "RL vs SL +0.2% (n.s.)", f"predict {pct(S['predict (gated)']['geomean'])}", f"IR vs runtime ρ = {D['ir']['rho']:.2f}"]))
    A("""<p class="hand">Hand-over: "Gagan will now put all these pieces together in the architecture."</p>""")
    A("<h4>Questions Nithin should be ready for</h4>"
      + qa("A correlation of 0.11 is tiny — why use the model at all?", "Because we only need it to put good candidates somewhere in the top 8 out of ~940. Measured on the test set, the model's top-8 beat 8 random candidates from the same library by +5.8% (CI excludes 0).")
      + qa("Why LightGBM and not deep learning?", "Small tabular data (~130 features, tens of thousands of measurements) — gradient-boosted trees are strong there, fast, and need no GPU. A deep model would overfit with this little data.")
      + qa("Why keep RL if it adds +0.2%?", "It was the team's choice to show the full RL + SL design. We state clearly that its measured effect is not significant; it never hurts because timing still decides.")
      + qa("Isn't 33 programs too few?", "It's what the corpus allows while keeping whole families unseen. That's why we always show confidence intervals, which are wide (+2.4% to +16.8%).")
      + qa("Is the +8% driven by one program?", "Without the largest result (durbin, 2.8×) it is still +4.9%, CI above zero, and 9 programs gain ≥ 5%."))

    # ================= GAGAN
    A('<div class="pb"></div><div class="speaker s4"><b>Part 5 · Gagan</b><span>Architecture page, limitations and conclusion</span></div>')
    A(beat("Click <b>Architecture</b>. Point at the four coloured lanes of the diagram.",
           "This is the whole system. It has an offline part and an online part. Lane 1, cyan, is data and measurement: benchmark sources, the corpus builder, the timing harness, the pipeline search, and the dataset. "
           "Lane 2, pink, is learning: program features, the supervised surrogate, the RL agent, the pipeline library, and the separate models for predict. "
           "Lane 3, blue, is what happens for a new program. Lane 4 is how you use it: WSL2, the command line, this dashboard, and the frozen model files."))
    A(beat("Click the box <b>Tune (RL + SL)</b>, then <b>Time + confirm</b>; read the side panel.",
           "Clicking any box shows its details and where it is in the code. The dashed pink lines are frozen models used at deployment: the surrogate, the RL agent and the library all feed into tune. "
           "Tune pools 24 RL proposals with about 913 library pipelines, the surrogate ranks them, the top 8 are compiled and checked, and then measurement decides."))
    A(beat("Scroll to <b>Tune flow</b> (8 steps) and <b>Predict flow</b>.",
           "Tune flow in eight steps: reference run, features, RL proposes, SL ranks, compile and verify, time 8 candidates against -O3, confirm the best in a fresh 20-round run, ship it or keep -O3. "
           "Predict flow: build -O3 and collect the compiler's optimization remarks, extract features, score a safe pool of 940 edits with 7 models and a harm model, apply the safety gate, and then measure the top pick once."))
    A(beat("Card <b>What an edit can do</b>.",
           "A candidate is always -O3 plus a few edits: remove a pass, repeat it, reorder, add a pass, change a pass option, change a global knob like vector width, or change code-generator flags. We call this list a genome."))
    A(beat("Box <b>Frozen models</b> in the diagram, then card <b>Technology</b>.",
           "The trained models are frozen: their files are listed with SHA-256 hashes, and tune refuses to run if anything changed. After every code change we run a regression check that tune's top-8 choice is identical. "
           "Technology: LLVM 18.1.8 pinned, Python with LightGBM, our own PPO in numpy, SQLite for all measurements, valgrind's cachegrind for simulated cache features, all inside WSL2; the dashboard is FastAPI with plain JavaScript and works offline."))
    A(beat("Card <b>Limits, stated honestly</b>.",
           "Limits: results are for one laptop CPU (AMD Zen 4) under WSL2; 33 test programs give wide confidence intervals; gains are for the input you give; tune needs minutes, not seconds; "
           "the Phase 3 gate was missed; RL adds very little; and predicting without running stays advisory."))
    A(beat("Conclusion (any page, e.g. Research &amp; results → 01 Overview).",
           f"To conclude: machine learning alone cannot reliably pick faster compiler settings — its correlation on unseen programs is about 0.1. But using it to shortlist 8 of ~940 candidates and letting careful measurement decide "
           f"gives <b>{pct(t['geomean'], 1)}</b> on programs the system never saw, with <b>no program slower</b> than -O3. Thank you — we're happy to take questions."))
    A(nums(["4 lanes: data · learning · deployment · interfaces", "24 RL + ~913 library → rank → 8 timed → confirm 20 rounds, CI > 1.01", "predict: 164 single + 776 pair safe pool, 7 models + harm model",
            "gate: pessimistic > 1.03×, ≥ 80% agree, harm < 0.5", "models frozen by SHA-256 MANIFEST; top-8 regression check IDENTICAL", "LLVM 18.1.8, LightGBM, PPO (numpy), SQLite, cachegrind, WSL2, FastAPI"]))
    A("<h4>Questions Gagan should be ready for</h4>"
      + qa("Why run on WSL2 and not native Linux?", "It's the machine we had. WSL2 has no hardware performance counters and can't control CPU frequency, so we compensate with interleaving, pinning, A/A controls and confidence intervals; the selftest proves timing is good enough.")
      + qa("Would it work on another computer?", "The method would, but the models and pipelines were trained and measured on this CPU. On another CPU you'd re-run the selftest and ideally retrain; tune still measures on the target machine, so it never ships something slower.")
      + qa("What is the RL agent's state, action and reward?", "State: program features plus edits chosen so far. Action: one of 120 macro-edits from the knowledge base. Reward: the surrogate's predicted log speed-up after 4 edits. Algorithm: PPO.")
      + qa("What does 'frozen' mean and why?", "The exact model files are fixed and hash-checked, so results can be reproduced and nothing changes silently while we added predict mode and the dashboard.")
      + qa("How is this different from existing work?", "Many tools tune compiler flags or learn phase ordering, often optimizing code size or instruction count. We optimize measured runtime only, with strict statistical confirmation and a guaranteed -O3 fallback, and we evaluate on unseen program families."))

    A("""<h2 class="pb">If something goes wrong during the demo</h2>""" + R.table(["problem", "what to do / say"], [
        ["Live job is slow or waits with <code>[quiet-guard] … waiting</code>", "Something else is using the CPU. Close heavy apps. Meanwhile show the saved runs — they're real results from earlier today."],
        ["Live job fails", "Show the terminal error (often a compile error or wrong args). Then use the saved run of the same example."],
        ["Environment pill says 'server unreachable'", "Restart with the .bat launcher (or <code>./dashboard/run.sh</code> in WSL), refresh the page."],
        ["Numbers differ slightly from this script", "Expected: every run is a new measurement (e.g. 1.656× vs 1.663×). Say 'the exact value varies by about 0.5%, within the confidence interval'."],
        ["A result says -O3 kept", "That's the safety mechanism working — explain the confirmation step."]]))
    return doc("NeuroCompiler — presentation script", "".join(B))


# ====================================================================== glossary + Q&A
GLOSSARY = {
    "Statistics and measurement": [
        ("-O3 baseline", "The standard 'optimize for speed' level of clang/LLVM. Every speed-up in the project is relative to it: 1.10× means 10% faster than -O3."),
        ("Speed-up (e.g. 1.23×)", "-O3 runtime ÷ our runtime. Above 1 = faster, below 1 = slower. 1.23× = 23% faster; it takes 1/1.23 = 81% of the time."),
        ("+8.09% / geomean", "Geometric mean of speed-ups over programs, written as a percentage: (geomean − 1) × 100. The geometric mean is the correct average for ratios (2× faster and 2× slower cancel out)."),
        ("Median", "The middle value. 'Median +0.0%' on the test set means more than half the programs kept -O3 (speed-up exactly 1.0)."),
        ("Excl. largest", "The geomean recomputed without the single biggest result, to show the average isn't carried by one program (e.g. +8.09% → +4.92%)."),
        ("CI (95% confidence interval)", "The range that would contain the true value in 95% of repeated experiments. '+2.4% … +16.8%' means we are confident the true average gain is in that range. 'CI excludes 0' (or 'excludes 1×') = the effect is statistically real."),
        ("Bootstrap", "A way to compute a CI by resampling the measured data thousands of times (4,000 here) and looking at the spread of the results. No assumption of a normal distribution is needed."),
        ("Paired comparison", "Comparing two methods program by program (or round by round), then averaging the ratios. Removes differences between programs and between rounds, so it's more sensitive."),
        ("Interleaved runs", "Running -O3 and the candidates alternately in random order (A, C, B, A, B, C …) instead of all A then all B, so slow changes (heat, background load) affect all equally."),
        ("Round / rep", "One run of every binary in the comparison. Confirmation uses 20–30 rounds; screening 1–3."),
        ("Warm-up", "Initial rounds that are discarded (caches, CPU frequency not settled)."),
        ("A/A control / A/A test", "Timing a byte-identical copy of the -O3 binary as if it were a candidate. It should measure 1.000×; any deviation is the measurement's bias/noise. Runs whose A/A deviates by more than 1% are repeated and flagged."),
        ("Noise floor", "The smallest difference the measurement can reliably detect; here about 0.1–0.5% (A/A results)."),
        ("Selftest", "The harness's own pass/fail test: repeatability (CI < 1%), drift (< 2%), A/A bias (< 1%) and a sanity check that -O0 is clearly slower than -O3."),
        ("Drift", "How much the median changes between the first and second half of a measurement; large drift = unstable machine."),
        ("Screening", "A cheap, noisy timing (1 round, 2 more only for promising candidates) used to choose what to measure properly. Never reported as a result."),
        ("Confirmation", "A long measurement (20–30 interleaved rounds + A/A control) of shortlisted candidates."),
        ("Validation", "A fresh, independent re-measurement of the winner. Used by the gates, because picking the best confirmed value is itself biased."),
        ("Winner's curse", "If you measure 8 candidates and pick the best, its number is too optimistic (you partly picked lucky noise). Fixed by re-measuring the winner in a fresh run."),
        ("Serial vs parallel timing", "Serial = one program timed at a time on one core (most accurate, used for all reported numbers). Parallel = 3 programs on 3 cores at once (used only to speed up screening/search, validated by multi-core A/A tests)."),
        ("Measurably slower / regression", "A program whose speed-up's 95% CI upper bound is below 1.0 — slower beyond doubt."),
        ("n.s.", "Not significant: the CI includes zero (or 1×), so we can't claim a difference."),
        ("Spearman correlation (ρ)", "How well two rankings agree: 1 = same order, 0 = unrelated, −1 = reversed. Used to judge how well a model orders candidates."),
        ("gain@k", "Best true speed-up among a model's top-k candidates, averaged (geomean) over programs. Compared with rand_gain@k (k random candidates) and the oracle."),
        ("recall@k", "How often the truly best candidate is inside the model's top-k."),
        ("Oracle", "The best possible choice from the library if you knew all true speed-ups (an upper bound, 1.22× here)."),
        ("Tier (minimum / good / strong)", "Success levels fixed in advance: minimum = no regressions or miscompiles; good = +2–4% with CI excluding 0 and ≥ 20–30% of programs ≥ +5%; strong = ≥ +5%."),
        ("Gate", "A pre-registered pass/fail checkpoint between phases (headroom gate, data-quality gate, Gate 7B, RL gate, predict criteria)."),
        ("Headroom", "How much faster than -O3 programs can get at all (found by expensive search)."),
        ("MPKI", "Misses per 1,000 instructions (cache misses); ≥ 20 L2 MPKI = 'memory-heavy' program in our scheduler."),
        ("Quiet guard", "Before timing, waits until other processes use less than 0.6 CPU cores (up to 30 min), because the laptop is shared."),
        ("Pinning / taskset", "Forcing a process to run on one chosen CPU core (here vCPU 6) so the OS doesn't move it around."),
        ("ASLR (disabled)", "Address Space Layout Randomization: the OS places memory at random addresses each run; we turn it off for benchmarks to reduce timing variation."),
        ("Layout randomization test", "Checked whether randomizing code placement changes results; it gave no benefit, so it isn't used."),
    ],
    "Compiler terms": [
        ("LLVM", "Open-source compiler infrastructure; clang is its C/C++ front end. We pin version 18.1.8 so every result uses the same compiler."),
        ("clang / opt / llc", "clang turns C/C++ into LLVM IR (and links); opt runs optimization passes on IR; llc turns IR into machine code (the 'backend' / code generator)."),
        ("IR (intermediate representation)", "LLVM's internal, assembly-like language between source code and machine code. Optimizations transform IR."),
        ("IR instruction count", "Number of IR instructions. Not related to runtime (ρ = −0.08); used only as a feature, never as a goal."),
        ("Pass", "One optimization step (e.g. 'inline functions', 'unroll loops')."),
        ("Pipeline / pass sequence", "The ordered, nested list of passes the optimizer runs. -O3's pipeline in LLVM 18 has 109 leaf passes."),
        ("New pass manager", "LLVM's current system for describing pipelines as text, e.g. function(sroa,early-cse,simplifycfg)."),
        ("Module / CGSCC / function / loop pass", "Levels a pass works at: whole program file; call-graph strongly-connected components (groups of functions that call each other, used for inlining); one function; one loop."),
        ("-O0 / -O1 / -O2 / -O3 / -Os", "Standard optimization levels: none, light, standard, aggressive for speed, optimize for size. -O0's output is our correctness reference ('oracle')."),
        ("Backend / code generator / llc -O level", "The stage turning IR into machine instructions; it has its own optimization level and flags."),
        ("Knob", "A global optimizer setting, e.g. -force-vector-width=4, -unroll-max-count=2, -inline-threshold=1000."),
        ("Inlining / inline threshold", "Copying a called function's body into the caller to avoid call overhead; the threshold controls how big a function may be inlined (-O3 uses 250)."),
        ("Loop unrolling", "Repeating a loop's body several times per iteration to cut loop overhead; too much makes code bigger and slower."),
        ("Vectorization / vector width", "Using SIMD instructions to process several values at once (e.g. 4 doubles). Vector width = how many."),
        ("SLP vectorizer", "Superword-Level Parallelism: packs independent straight-line operations into vector instructions."),
        ("SIMD / AVX-512", "Single Instruction Multiple Data: CPU instructions working on several values. AVX-512 is the 512-bit version on our Zen 4 CPU."),
        ("SimplifyCFG", "Pass that simplifies the control-flow graph (merges blocks, removes dead branches)."),
        ("sink-common-insts", "SimplifyCFG option that merges identical code at the end of branches. In the interpreter (evalloop) it merged 31 dispatch jumps into one, wrecking branch prediction; turning it off gave up to 3.7×."),
        ("CFG (control-flow graph)", "Graph of a function's basic blocks and the jumps between them."),
        ("Dispatch loop / computed goto", "An interpreter's main loop that jumps to the code for the next instruction; separate indirect jumps per opcode predict much better."),
        ("Branch prediction", "The CPU guesses which way a branch goes; wrong guesses cost ~15–20 cycles each."),
        ("Tail duplication / tail-dup-size", "Backend optimization copying small block endings into their predecessors to remove jumps; the size limit is 2 by default, our picks often use 6."),
        ("Loop alignment (align-loops)", "Placing loop starts at addresses that are multiples of 16/32/64 bytes, which can help instruction fetch."),
        ("cmov", "Conditional move instruction: replaces a branch with a select."),
        ("Jump table", "A switch statement implemented as a table of addresses."),
        ("LICM", "Loop-Invariant Code Motion: moves calculations that don't change out of loops."),
        ("GVN", "Global Value Numbering: removes redundant computations."),
        ("SROA", "Scalar Replacement of Aggregates: splits structs/arrays into separate variables kept in registers."),
        ("instcombine", "Peephole pass that combines and simplifies instructions."),
        ("Jump threading / DFA jump threading", "Redirect jumps through branches whose outcome is known; the DFA variant is for state machines (switch in a loop)."),
        ("TBAA", "Type-Based Alias Analysis metadata: tells the optimizer that pointers of different types don't overlap. We start from clang IR with passes disabled (not -O0) so TBAA is kept and the baseline is real -O3."),
        ("-march=native", "Compile for exactly this CPU (here Zen 4 with AVX-512). Same for -O3 and candidates so the comparison is fair."),
        (".text size", "Size of the machine code in the binary. Constraint only: soft cap 1.10× -O3."),
        ("llvm-link", "Tool that merges several IR files into one module, so multi-file programs are optimized as a whole."),
        ("o3_mismatch", "A program where our printed -O3 pass list doesn't reproduce clang's built-in -O3 bit for bit (20 programs); speed-ups are still measured against real -O3."),
        ("Compile-time evaluation", "When the compiler computes a fixed-input program's answer during compilation; the 'speed-up' is then fake. Detected by instruction counts (mandel-text, 217× fewer instructions) and excluded."),
        ("Optimization remarks", "Messages LLVM can emit about what it did or failed to do (e.g. 'loop not vectorized: …'). Counted as features for predict."),
        ("Miscompile / wrong output", "An optimized binary that produces different output than -O0. Such candidates are always discarded."),
        ("Oracle output / output hash", "The -O0 build's output, stored as a SHA-256 hash; every candidate's output hash must match it."),
    ],
    "Machine learning and RL": [
        ("ML / SL", "Machine learning / supervised learning: learning from examples with known answers (here: measured speed-ups)."),
        ("Surrogate model", "A model that predicts the result of an expensive experiment (timing) so fewer experiments are needed. Ours predicts a pipeline's speed-up for a program."),
        ("LightGBM", "A fast library for gradient-boosted decision trees (Microsoft). Strong on tabular data."),
        ("Gradient boosting", "Builds many small decision trees one after another, each correcting the previous ones' errors (here 300 trees, 15 leaves each)."),
        ("Regressor vs ranker (lambdarank)", "A regressor predicts a number (the speed-up); a ranker learns only the order of candidates. LambdaRank is a ranking objective. Tune uses the regressor."),
        ("Features", "Numbers describing a program/candidate: static IR statistics (111), scan runtimes (9), simulated cache behaviour (11 + 2), compiler remarks (36), and the candidate's edits (~98)."),
        ("Static vs dynamic features", "Static = from the code without running it. Dynamic = from running it (runtimes, cachegrind simulation)."),
        ("cachegrind (simulated)", "Valgrind tool that simulates caches and branch prediction while running a program. Labelled 'simulated' because WSL2 has no hardware counters; uses -march=x86-64-v3 builds because valgrind can't run AVX-512."),
        ("Label / label cap / weight", "Label = the true answer (measured log speed-up). Capped at |log 3| so extreme values don't dominate; programs with noisy A/A controls get weight 0.3."),
        ("Log speed-up", "ln(speed-up); symmetric for faster/slower, used for training and averaging."),
        ("Train / validation / test split", "Train = learn; validation = choose settings; test = final exam, used once. Split by family, frozen before modelling."),
        ("Family", "Programs sharing code (e.g. all PolyBench linear-algebra kernels). Kept together so test families are truly unseen."),
        ("Leave-one-family-out cross-validation (LOFO CV)", "Train on all development families except one, test on that one, repeat for each family. Honest estimate for unseen code."),
        ("Out-of-fold (OOF) predictions", "Predictions for each program made by a model that did not train on it (from cross-validation); used to choose predict's thresholds."),
        ("Overfitting", "A model memorizing its training programs: predict's models rank training programs at 0.42 but unseen ones at 0.11."),
        ("Ensemble (7 members)", "Several models trained on resampled data; their spread shows uncertainty."),
        ("Pessimistic estimate", "Mean minus 1.28 × standard deviation across ensemble members (≈ the 10th percentile). Predict ships only if this is above 1.03×."),
        ("Agreement", "Share of ensemble members predicting a gain; predict needs ≥ 80%."),
        ("Harm classifier / p_harm / τ (tau)", "A model estimating the probability that a candidate makes the program slower. Predict needs p_harm ≤ τ = 0.5."),
        ("Margin", "Minimum predicted gain (0.03 = 3% for predict; 0.01 = 1% for tune's confirmation)."),
        ("Safe pool", "Predict's candidates: 164 single edits that never produced wrong output and are harmful on ≤ 10% of programs, plus 776 pairs."),
        ("Pipeline library", "~913 pipelines that won on training programs plus random pipelines: tune's candidate pool."),
        ("Gate 7B", "Checkpoint: does the surrogate rank unseen families better than random? First NOT MET, then narrowly met after more data (Spearman +0.111, gain@5 1.107× vs 1.091×)."),
        ("RL (reinforcement learning)", "Learning by trial and reward instead of labelled answers."),
        ("PPO", "Proximal Policy Optimization: a stable RL algorithm that limits how much the policy changes per update (clip 0.2)."),
        ("Policy / value function (actor-critic)", "Policy (actor) chooses actions; value function (critic) estimates expected reward to reduce variance. Both are small neural networks (one hidden layer) written in numpy."),
        ("Episode / horizon", "One attempt at building a pipeline; horizon = number of edits per episode (4)."),
        ("Action / macro-action", "One edit chosen by the agent, out of 120 macro-edits from the knowledge base (knobs, llc flags, family-wide deletes, option flips)."),
        ("Reward", "The surrogate's predicted log speed-up of the finished pipeline (not a real measurement, which would be far too slow)."),
        ("GAE (λ = 0.95)", "Generalized Advantage Estimation: a way to estimate how much better an action was than expected."),
        ("Entropy bonus", "Small reward for keeping the policy random enough to keep exploring (0.01)."),
        ("Adam", "A standard optimizer for neural-network training (learning rate 3e-3)."),
        ("RL + SL", "Final design: RL proposes 24 pipelines, pooled with the library, SL ranks all, timing decides. Measured gain from RL over SL: +0.2% (not significant)."),
        ("ML-only top-1", "Shipping the model's single best guess without timing: +2.36% but 16 of 33 programs slower — shows timing is essential."),
        ("Random search@8 / random top-8 / GA@8", "Baselines with the same budget of 8 timed binaries: 8 random genomes; 8 random pipelines from the library; a genetic algorithm (6 + 18 evaluations)."),
        ("GA / evolutionary search (evo, evo2)", "Search that mutates and recombines the best pipelines over generations. evo uses action space v1, evo2 v2."),
    ],
    "Project-specific terms": [
        ("NeuroCompiler", "This project: ML + RL guided selection of LLVM pass pipelines, judged only by measured runtime vs -O3."),
        ("Tune", "Main mode: propose (RL + SL) → compile + verify → time 8 vs -O3 → confirm → ship pick or -O3. Minutes per program."),
        ("Predict", "Mode that chooses without running the program (≈ 1 s), then times its top pick once for reporting. Advisory: writes -O3 unless --apply."),
        ("Compare", "Mode that times -O3, -O2, -Os, predict, tune, random@8 and GA@8 in one interleaved run with an A/A control."),
        ("Advisory", "Predict missed its pre-registered gain criterion, so by default it writes the -O3 binary and only reports its recommendation."),
        ("--apply / --no-measure / --no-rl / --dynamic", "Predict: write the recommended binary / skip the timing of the pick. Tune: SL only / add cachegrind features."),
        ("Genome", "A candidate described as -O3 plus a list of edits (del, dup, swap, ins, param, param_all, del_all, knob, llc flag, backend level, or a whole 'raw' standard pipeline)."),
        ("Level seed / raw pipeline", "A whole standard pipeline (e.g. default<O2> or default<O0>) used instead of -O3's, possibly with llc -O3."),
        ("Action space v1 / v2", "Edit sets for search: v1 = delete/duplicate/swap/insert + 6 knobs + llc level; v2 adds pass-option flips, delete-all, more knobs, llc flags and more passes."),
        ("Knowledge base (passkb)", "Phase 4 table of 346 single edits tried on 31 programs: confirmed faster/slower, no-op counts."),
        ("Minimization", "Removing edits from a winner that don't contribute, so the final pipeline is as small as possible."),
        ("Phase 1–9", "1 harness, 2 corpus, 3 search + headroom gate, 4 knowledge base, 5 data collection, 6 features, 7 surrogate, 8 deployment + RL, 9 frozen-test evaluation."),
        ("Corpus / prescan / scan", "The set of benchmark programs; prescan = fast parallel filter (build, run, output); scan = pinned timing at every level."),
        ("PolyBench / LLVM test-suite / SingleSource / MultiSource", "Benchmark collections: PolyBench (numerical kernels), test-suite SingleSource (one-file programs, C and C++) and MultiSource (multi-file programs and applications)."),
        ("TSVC", "A family of 33 vectorization test programs; too large for the test budget, so it went to training."),
        ("evalloop", "A small interpreter benchmark where -O3's SimplifyCFG hurts; pathological case, always report results with and without it."),
        ("durbin", "polybench/durbin, the largest test result (2.8×); the reason we report 'excluding largest'."),
        ("lencod", "ms/Applications/JM/lencod (video encoder): the one regression in the first SL test run (0.979×), which led to the confirmation step."),
        ("mandel-text", "Program excluded as a compile-time-evaluation artifact."),
        ("MANIFEST / frozen models", "File listing each model file's SHA-256 hash; tune and predict refuse to load changed files."),
        ("Tune regression check", "Script confirming tune's top-8 choice is IDENTICAL before and after code changes."),
        ("machine_id", "Label stored with every measurement (wsl2-ryzen9-270 for 8 vCPUs, -v14 for 14 vCPUs); results from different machines are never mixed."),
        ("timing_cpu / vCPU / SMT sibling", "vCPU = virtual CPU seen by WSL2. timing_cpu = 6. SMT sibling = the other hardware thread on the same physical core (vCPU 7), kept idle when timing in parallel."),
        ("helper CPUs", "Cores used for compiling and output checks while timing cores stay quiet."),
        ("k", "Number of candidates timed per program (8)."),
        ("WSL2", "Windows Subsystem for Linux 2: a real Linux kernel in a lightweight VM on Windows. No CPU frequency control or hardware counters."),
        ("FastAPI / uvicorn / SSE", "Python web framework / web server running the dashboard / Server-Sent Events: how the live terminal output is streamed to the browser."),
        ("SQLite (dataset.sqlite)", "File database holding every candidate, build and measurement."),
        ("Re-scope", "The recorded user decision after the missed Phase 3 gate: continue with the 'good' tier target; later gates stay strict."),
    ],
}

QA = [
    ("What exactly is new in this project?", "Optimizing measured runtime only (not size or IR count), with a strict statistical protocol (interleaving, A/A controls, bootstrap CIs, fresh confirmation), a guaranteed -O3 fallback, and evaluation on unseen program families; plus an honest comparison of ML-only, ML + timing, RL, random search and GA at equal budget."),
    ("Is +8% meaningful? -O3 is already highly tuned.", "Yes, it is measured on unseen programs with CI +2.4% to +16.8%, and +4.9% even without the largest result. Most programs keep -O3 (median 0%); the gains come from the programs where -O3's one-size-fits-all choice is wrong."),
    ("Why does the median show 0%?", "On 21 of 33 test programs nothing convincing beat -O3, so -O3 was kept (speed-up exactly 1.0). That's by design: we only change what we can prove is faster."),
    ("How can a compiler setting give 3.8×?", "In the interpreter, -O3 merges 31 indirect jumps into one, so the CPU's branch predictor can't learn the pattern; keeping them separate removes most mispredictions. It's a known kind of problem (dispatch loops) and the extreme case."),
    ("Couldn't the gains be noise or luck in code placement?", "Each comparison includes an A/A control (identical binary) that measures ~1.000; a code-layout randomization test showed no effect; and winners are re-measured in a fresh run. Reproduced results differ by < 0.5% (e.g. 1.663× vs 1.656×)."),
    ("Why not optimize for code size or instruction count — it's faster to evaluate?", "We measured 18,637 candidates: IR count and runtime are uncorrelated (ρ = −0.08). An earlier attempt that optimized them didn't speed programs up."),
    ("Your Phase 3 gate failed. Why should we trust the rest?", "We report the miss, didn't relax the threshold, documented the decision before continuing, and the later out-of-sample search on 115 new programs found +15.6%. The final test was run once on frozen data."),
    ("Isn't changing the plan after a failed gate 'p-hacking'?", "We lowered the success target (to the more modest 'good' tier) rather than redefining the test, wrote it down before continuing, and kept all later gates strict. The test set was frozen before modelling and evaluated once."),
    ("Is the model overfitting?", "The tune surrogate is evaluated on unseen families (Spearman 0.11) — weak but not overfit to the point of failure, and the final test is on unseen families. Predict's models do overfit (0.42 train vs 0.11 unseen), which is why predict is advisory."),
    ("Why only 33 test programs?", "We need whole families unseen and enough programs for training; 33 programs / 11 families was the budget. We show CIs to make the uncertainty visible."),
    ("Why is RL in the final version if it doesn't help?", "Team decision to present the full RL + SL design. Its measured effect is +0.2% (not significant), and RL alone is 4.2% worse than the SL shortlist. It never hurts, because timing still decides."),
    ("Why did RL not help?", "Its reward is the surrogate's prediction, which is weak on unseen programs; the agent learned to please the model, and its proposals collapse to about 5 distinct binaries per program."),
    ("Why not train RL with real timing as reward?", "Each reward would need compiling and timing a program for seconds; PPO needs hundreds of thousands of episodes. That would take months on one laptop."),
    ("Why not use a GNN or a large language model on the code?", "With ~146 programs, a deep model would overfit badly. LightGBM on hand-built features is the right size for this data. A GNN was an option for later, not needed for the result."),
    ("Why WSL2 — isn't timing unreliable there?", "WSL2 has more noise and no frequency control. We measured that noise (selftest, A/A tests) and designed around it; every claimed gain is well above the noise floor."),
    ("Does it work on other CPUs?", "Not tested. Pipelines and models were learned on AMD Zen 4. Because tune measures on the target machine and falls back to -O3, it won't ship a slowdown, but gains may differ."),
    ("What if the input changes?", "The pipeline is chosen for the input given. A different input can change which pipeline is best; the correctness check also uses that input."),
    ("How do you guarantee correctness?", "Output hash equality with the -O0 build on the given input, for every candidate. Strong evidence, not proof; undefined behaviour in a program could still differ on other inputs."),
    ("How long does it take and is that practical?", "Tune: about 1–3 minutes for the demo programs (tens of compiles plus timing). Worth it for programs run many times (benchmarks, scientific codes, production services); predict is ~1 s but advisory."),
    ("Why is predict so much worse than tune?", "Without running, the model can't see trip counts, data sizes, cache and branch behaviour, which decide whether an edit helps. Its ranking drops from 0.42 on training programs to 0.11 on new ones."),
    ("What does the safety gate do in predict, concretely?", "Ships only if the pessimistic estimate (mean − 1.28 std of 7 models) > 1.03×, ≥ 80% of models agree, and harm probability ≤ 0.5. Without the gate, predict was −0.69% with 8 slower programs and 2 wrong-output picks."),
    ("Why geometric mean and not arithmetic?", "For ratios the geometric mean is symmetric (2× and 0.5× cancel); the arithmetic mean overweights big wins."),
    ("What does 'CI excludes 0' mean?", "The 95% confidence interval of the average gain is entirely above zero, so the gain is statistically real."),
    ("Why 20 rounds for confirmation and 30 for research data?", "Research confirmations use the full 30 rounds. Tune's 20-round confirmation keeps deployment fast while giving CIs well under ±1% on the demo programs. Be open about the history: the confirmation step was added AFTER the first test run showed the lencod regression (0.979×); the test result was not re-scored with it. The later RL + SL test runs used it and had 0 regressions."),
    ("Why the 1.01 margin?", "To ship only gains clearly above the noise floor (A/A within ~0.5%). In a demo it rejected a branchy-code candidate that confirmed at 1.015×; re-running lencod with it ships -O3 (a post-hoc illustration, not a re-scored test result)."),
    ("What is the A/A control for, in one line?", "It times an identical copy of -O3; if the measurement says that copy is faster or slower, the measurement is biased and is repeated."),
    ("Who decided what, and is it documented?", "Every decision and result is recorded with its result file in CLAUDE.md and the final report; all numbers are reproducible with scripts in the repository."),
    ("What was the hardest problem?", "Making timing trustworthy on a shared laptop in WSL2 (pinning, interleaving, A/A, quiet guard, multi-core tests), and resisting the temptation to trust model predictions without measuring."),
    ("What would you do next?", "Test on other CPUs, more programs/families, input-robust selection (several inputs), and features that capture runtime behaviour without full runs (e.g. short profiling)."),
    ("How is this related to existing tools (autotuners, MLGO, CompilerGym)?", "Autotuners search flags by running programs; ML approaches like MLGO learn individual heuristics (e.g. inlining) mainly for size; CompilerGym provides RL environments often rewarding IR count. Our system combines a learned shortlist with strict runtime measurement and an -O3 guarantee, evaluated on unseen families."),
]


def glossary_html():
    B = ['''<div class="cover"><h1>Glossary and cross-questions</h1>
    <p>Every abbreviation and uncommon term used in the NeuroCompiler presentation, dashboard and report, in plain words, followed by the hard questions you may be asked, with honest answers.
    Numbers are the measured results (33 held-out test programs, serial re-measurement) unless marked as predicted.</p></div>''']
    for cat, items in GLOSSARY.items():
        B.append(f"<h2>{E(cat)}</h2><dl>")
        for term, mean in items:
            B.append(f'<div class="term"><dt>{E(term)}</dt><dd>{E(mean)}</dd></div>')
        B.append("</dl>")
    t, S = D["headline"]["tune_rlsl"], D["eval"]["summary"]
    B.append('<h2 class="pb">Key numbers (one page)</h2>' + R.table(["what", "number", "measured or predicted"], [
        ["tune RL + SL on 33 unseen test programs", f"{pct(t['geomean'])} geomean (CI {R.ci(t['ci'])}), excl. largest {pct(t['excl_largest'])}, {t['ge5']}/33 ≥ +5%, {t['slower']} slower", "measured"],
        ["tune SL only (top-8)", f"{pct(S['tune top-8 (SL)']['geomean'])}, 1 slower", "measured"],
        ["RL only / RL vs SL", f"{pct(S['RL only']['geomean'])} / +0.2% (n.s.)", "measured"],
        ["random search@8 / GA@8 / random top-8", f"{pct(S['random search@8']['geomean'])} / {pct(S['GA@8']['geomean'])} / {pct(S['random top-8']['geomean'])}", "measured"],
        ["ML-only top-1 (no timing)", f"{pct(S['ML-only top-1']['geomean'])}, 16 of 33 slower", "measured"],
        ["-O2 / -Os vs -O3", f"{pct(S['-O2']['geomean'])} / {pct(S['-Os']['geomean'])}", "measured"],
        ["predict gated / ungated", f"{pct(S['predict (gated)']['geomean'])} (1 slower) / {pct(S['predict ungated']['geomean'])} (8 slower, 2 wrong output)", "measured (choice made without running)"],
        ["search headroom (115 unseen programs)", f"{pct(D['headline']['phase5']['geomean'])}, {D['headline']['phase5']['ge5']}/115 ≥ +5%", "measured"],
        ["Phase 3 gate (15 fresh programs)", f"{pct(D['gate3']['fresh_summary']['geomean'])}, 4/15 ≥ +5% (needed 30%) → NOT MET", "measured"],
        ["surrogate ranking on unseen families", "Spearman +0.11; gain@5 1.107× vs random 1.091×", "cross-validation"],
        ["predict model ranking", "Spearman 0.42 (training programs) vs 0.11 (unseen)", "cross-validation"],
        ["RL predicted return", "+0.22 log speed-up", "predicted by the surrogate, NOT measured"],
        ["IR count vs runtime", f"ρ = {D['ir']['rho']:.2f} over {D['ir']['n']:,} candidates", "measured"],
        ["timing quality", "A/A bias ≤ 0.3%, CI ±0.12–0.41%", "measured"],
        ["corpus", "347 scanned → 146 usable, 35 families; split 91 / 22 / 33", "—"],
        ["demo: interpreter / matmul / Fibonacci (tune)", "3.83× (848 → 221 ms) / ≈1.66× (≈423 → 254 ms) / 1.14×", "measured today"],
        ["demo: predict Fibonacci / matmul pick", "predicted 1.17× → measured 1.23× / predicted 1.01× → measured 0.99× (gate kept -O3)", "predicted vs measured"]], "small"))
    B.append('<h2 class="pb">Cross-questions and answers</h2>')
    for q, a in QA:
        B.append(qa(E(q), E(a)))
    B.append('<div class="tip"><b>If you don\'t know:</b> say "I don\'t know that exact number; the result files are in the repository and the report lists them" — never guess a number. '
             'Always separate measured (we timed it) from predicted (a model\'s guess).</div>')
    return doc("NeuroCompiler — glossary and cross-questions", "".join(B))


def render(htmlp: Path, pdfp: Path):
    exe = R.chrome()
    if not exe:
        print("no Chrome found; open the HTML and print to PDF")
        return
    if exe[0].startswith("/mnt/"):
        tmp = Path("/mnt/c/Users/Public/nc_report_tmp")
        tmp.mkdir(exist_ok=True)
        shutil.copy2(htmlp, tmp / htmlp.name)
        src, dst, out = f"file:///C:/Users/Public/nc_report_tmp/{htmlp.name}", f"C:\\Users\\Public\\nc_report_tmp\\{pdfp.name}", tmp / pdfp.name
    else:
        src, dst, out = htmlp.as_uri(), str(pdfp), pdfp
    subprocess.run(exe + ["--headless=new", "--disable-gpu", "--no-pdf-header-footer", f"--print-to-pdf={dst}", src], capture_output=True, timeout=180)
    if out != pdfp:
        shutil.copy2(out, pdfp)
        shutil.rmtree(out.parent, ignore_errors=True)
    print(f"wrote {pdfp} ({pdfp.stat().st_size / 1024:.0f} KB)")


def main():
    R.OUT.mkdir(exist_ok=True)
    for name, fn in (("Presentation_Script", script_html), ("Glossary_and_QA", glossary_html)):
        h = R.OUT / f"{name}.html"
        h.write_text(fn())
        render(h, R.OUT / f"{name}.pdf")


if __name__ == "__main__":
    main()
