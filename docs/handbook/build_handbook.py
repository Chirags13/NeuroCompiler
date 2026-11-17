"""Build the NeuroCompiler project handbook (Markdown, Word, PDF) from handbook_body.md plus tables generated from
dashboard/static/data/research.json, so every table number matches the measured data.

Run from the repo root:  open_day/.pptxenv/bin/python docs/handbook/build_handbook.py
Needs pypandoc_binary (Word, HTML) and Windows Chrome (PDF).
"""
import json
import shutil
import subprocess
from pathlib import Path

import pypandoc

H = Path("docs/handbook")
D = json.load(open("dashboard/static/data/research.json"))
EV, C = D["eval"], D["corpus"]
S = EV["summary"]


def pct(v):
    return f"{(v - 1) * 100:+.2f}%"


methods = [("tune RL + SL", "**NeuroCompiler final: RL + SL, top-8 + timing**"), ("tune top-8 (SL)", "LightGBM top-8 + timing (SL only)"),
           ("no dynamic features", "SL top-8, no simulated features"), ("random search@8", "Random search, 8 timed binaries"),
           ("RL only", "RL proposals only"), ("ML-only top-1", "ML top-1, no timing"), ("GA@8", "Genetic algorithm, 8 timed binaries"),
           ("random top-8", "Random top-8 from the same library"), ("predict (gated)", "Predict mode (compile-only, gated)"),
           ("predict ungated", "Predict, ungated"), ("-O2", "-O2"), ("-Os", "-Os")]
rows = ["| Method | Geomean vs -O3 | 95% CI | Excl. largest | Median | ≥ +5% | Measurably slower |", "|---|---|---|---|---|---|---|"]
for k, lab in methods:
    s = S[k]
    rows.append(f"| {lab} | {pct(s['geomean'])} | {pct(s['ci'][0])} .. {pct(s['ci'][1])} | {pct(s['excl_largest'])} | "
                f"{s['median']:.3f}× | {s['ge5']}/33 | {s['slower']}/33 |")
METHODS = "\n".join(rows)

cols = [("tune RL + SL", "Final (RL+SL)"), ("tune top-8 (SL)", "SL top-8"), ("random search@8", "Random @8"), ("GA@8", "GA @8"),
        ("ML-only top-1", "ML top-1"), ("predict (gated)", "Predict"), ("-O2", "-O2")]
P = sorted(EV["programs"], key=lambda p: -p["tune RL + SL"])
rows = ["| # | Program | Family | " + " | ".join(c for _, c in cols) + " |", "|---|---|---|" + "---|" * len(cols)]
for i, p in enumerate(P, 1):
    rows.append(f"| {i} | {p['id'].split('/')[-1]} | {p['family']} | " + " | ".join(f"{p[k]:.3f}" if p.get(k) is not None else "–" for k, _ in cols) + " |")
PROGRAMS = ("Speed-up vs -O3 for every test program, sorted by the final system's result (1.000 = kept -O3 or no "
            "difference).\n\n" + "\n".join(rows))

sp = C["split"]
CORPUS = f"""Sources: PolyBench/C 4.2.1 (dimensions scaled), LLVM test-suite SingleSource (C and C++, argv-scaled where
possible) and MultiSource (multi-file programs compiled per file and `llvm-link`ed into one module, so -O3 and every
candidate see the whole program).

A program is kept only if it builds at -O0, -O1, -O2, -O3 and -Os, gives identical output at every level (the -O0 output is the
reference), is deterministic, and its -O3 runtime lies between 0.35 s and 3.0 s on this machine.

| Funnel | Count |
|---|---|
| Programs scanned | {C['scanned']} |
| Usable | **{C['usable']}** in {C['families']} families |
| By suite | PolyBench {C['by_suite']['polybench']}, SingleSource {C['by_suite']['singlesource']}, MultiSource {C['by_suite']['multisource']} |

| Rejection reason | Programs |
|---|---|
""" + "\n".join(f"| {r} | {n} |" for r, n in C["rejections"]) + f"""

**Split by family**, frozen on 2026-10-24 (seed 0) before any modelling: train {sp['counts']['train']} programs
({len(sp['groups']['train'])} families), validation {sp['counts']['val']} ({len(sp['groups']['val'])} families), test
{sp['counts']['test']} ({len(sp['groups']['test'])} families). A family enters test or validation only if it fits the remaining budget
(TSVC, with 33 programs, goes to train).

- **Test families:** {", ".join(sp['groups']['test'])}
- **Validation families:** {", ".join(sp['groups']['val'])}
- **Train families:** {", ".join(sp['groups']['train'])}

**Dataset** (`results/dataset.sqlite`, version 692d2418a83f): 70,409 candidate pipelines, 19,534 timing measurements
(17,423 screening, 1,044 confirmation, 340 knowledge-base confirmation, 170 validation, 127 serial validation, plus
A/A controls), 858 evaluation rows. On {D['corpus']['levels_differ_3pct']} programs the standard levels differ by at least 3%, and on {D['corpus']['level_beats_o3']} a lower
level beats -O3."""

md = (H / "handbook_body.md").read_text().replace("{{METHODS}}", METHODS).replace("{{PROGRAMS}}", PROGRAMS).replace("{{CORPUS}}", CORPUS)
assert "{{" not in md
fig = H / "figures"
fig.mkdir(exist_ok=True)
for f in ("docs/poster/01_architecture.png", "docs/poster/03_performance_chart.png", "docs/assets/shots/tune_summary.jpg",
          "docs/assets/shots/tune_diff.jpg", "docs/assets/shots/tune_cands.jpg", "docs/poster/02_methodology.png",
          "docs/assets/shots/research_overview.jpg", "docs/assets/shots/research_test.jpg", "docs/poster/Poster_Preview.png"):
    shutil.copy(f, fig)
out_md = H / "NeuroCompiler_Project_Handbook.md"
out_md.write_text(md)

common = ["--toc", "--toc-depth=2", f"--resource-path={H}"]
pypandoc.convert_file(str(out_md), "docx", outputfile=str(H / "NeuroCompiler_Project_Handbook.docx"), extra_args=common)

css = """body{font:10.5pt/1.5 'Segoe UI',sans-serif;color:#15191f;max-width:none;margin:0}
h1{font:600 18pt Bahnschrift,'Segoe UI';border-bottom:2pt solid #e09a10;padding-bottom:1mm;margin-top:9mm;break-after:avoid}
h1.title{border:0;font-size:28pt;margin-top:0} p.subtitle{color:#556;font-size:13pt}
h2{font:600 13pt Bahnschrift,'Segoe UI';margin-top:6mm;break-after:avoid} h3{font-size:11pt;break-after:avoid}
table{border-collapse:collapse;width:100%;margin:2mm 0 4mm;font-size:9pt} th,td{border:.5pt solid #ccd;padding:1.2mm 2mm;vertical-align:top}
th{background:#f3f4f7;text-align:left} tr{break-inside:avoid} img{max-width:100%;break-inside:avoid;border:.5pt solid #ccd}
code{font:9pt Consolas,monospace;background:#f3f4f7;padding:0 1mm} pre{background:#f3f4f7;padding:3mm;font-size:9pt;white-space:pre-wrap;break-inside:avoid}
nav#TOC{break-after:page} nav#TOC ul{list-style:none;padding-left:5mm} figure{margin:3mm 0;break-inside:avoid} figcaption{font-size:9pt;color:#556}
@page{size:A4;margin:16mm 15mm;@bottom-right{content:counter(page);font:9pt 'Segoe UI';color:#667}@bottom-left{content:"NeuroCompiler: Project Handbook";font:9pt 'Segoe UI';color:#667}}"""
(H / "handbook.css").write_text(css)
tmp = Path("/mnt/c/Users/Public/nc_handbook_tmp")
shutil.rmtree(tmp, ignore_errors=True)
tmp.mkdir()
shutil.copytree(fig, tmp / "figures")
shutil.copy(H / "handbook.css", tmp)
pypandoc.convert_file(str(out_md), "html", outputfile=str(tmp / "handbook.html"),
                      extra_args=common + ["--standalone", "--css=handbook.css", "--metadata=lang:en"])
base = "C:\\Users\\Public\\nc_handbook_tmp\\"
subprocess.run(["/mnt/c/Program Files/Google/Chrome/Application/chrome.exe", "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                f"--print-to-pdf={base}handbook.pdf", "file:///" + (base + "handbook.html").replace("\\", "/")],
               check=True, timeout=180, capture_output=True)
shutil.copy(tmp / "handbook.pdf", H / "NeuroCompiler_Project_Handbook.pdf")
for f in ("NeuroCompiler_Project_Handbook.md", "NeuroCompiler_Project_Handbook.docx", "NeuroCompiler_Project_Handbook.pdf"):
    print(f, (H / f).stat().st_size)
