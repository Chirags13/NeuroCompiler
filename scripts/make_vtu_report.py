#!/usr/bin/env python3
"""Build the major-project report in the VTU / JSSATE format (docs/NeuroCompiler_Major_Project_Report.pdf).

Layout follows the department's report format: double-ruled page border, cover with university and college
logos, certificate, declaration, abstract and acknowledgement (roman page numbers), contents, list of figures,
list of tables and abbreviations, then the chapters (arabic page numbers) and references.

All numbers come from the same sources as scripts/make_report_pdf.py (research.json exported from the result
files, results/FINAL_REPORT.md, CLAUDE.md, dashboard/saved/). Dashboard snapshots are in docs/assets/shots/.

Fill in the CONFIG block (USNs, guide, coordinator, academic year) and re-run:
    .venv/bin/python scripts/make_vtu_report.py
Needs Chrome/Chromium/Edge (headless printing) and pypdfium2 (page numbers for the contents, merging, border).
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import make_report_pdf as R  # noqa: E402  (charts, data, helpers)

import pypdfium2 as pdfium  # noqa: E402
import pypdfium2.raw as pdfraw  # noqa: E402

REPO, D, E, pct, xx, ci, COL = R.REPO, R.D, R.E, R.pct, R.xx, R.ci, R.COL
OUT = REPO / "docs"
ASSETS = OUT / "assets"
NAME = "NeuroCompiler_Major_Project_Report"

# ------------------------------------------------------------------ CONFIG (edit and re-run)
# Values in [square brackets] are printed highlighted as placeholders.
CONFIG = {
    "title": "NEUROCOMPILER: HYBRID MACHINE LEARNING AND REINFORCEMENT LEARNING GUIDED LLVM PASS SELECTION "
             "FOR RUNTIME OPTIMIZATION",
    "short_title": "NeuroCompiler: ML + RL Guided LLVM Pass Selection",
    "title_text": "NeuroCompiler: Hybrid Machine Learning and Reinforcement Learning Guided LLVM Pass Selection for Runtime Optimization",
    "report_kind": "MAJOR PROJECT REPORT",
    "students": [("Chirag S", "1JS23CS039"), ("Dhanush Singh", "1JS23CS048"),
                 ("Gagan S Shamnur", "1JS23CS052"), ("Nithin Choudhary A", "1JS23CS101")],
    "guide": "Dr. P.B. Mallikarjuna",
    "guide_designation": "Professor",
    "guide_pronoun": "their",
    "coordinator": "[Project co-ordinator]",
    "coordinator_designation": "[Designation]",
    "hod": "Dr. Prabhudev Jagadeesh M P",
    "hod_designation": "Professor & Head",
    "principal": "Dr. Bhimasen Soragaon",
    "year": "2026-2027",
    "year_short": "2026-27",
    "university": "VISVESVARAYA TECHNOLOGICAL UNIVERSITY",
    "university_addr": "Jnana Sangama, Belagavi - 590018, Karnataka, India",
    "college": "JSS ACADEMY OF TECHNICAL EDUCATION, BENGALURU",
    "college_short": "JSSATE",
    "college_addr": "JSS Campus, Dr. Vishnuvardhan Road, Bengaluru-560060",
    "dept": "DEPARTMENT OF COMPUTER SCIENCE & ENGINEERING",
    "dept_short": "Dept. of CSE",
    "swamiji": "His Holiness Jagadguru Sri Shivarathri Deshikendra Mahaswamiji",
}


def ph(s: str) -> str:
    """Escape, and highlight [placeholders]."""
    return re.sub(r"\[([^\]]+)\]", r'<span class="ph">[\1]</span>', E(s))


C = {k: (ph(v) if isinstance(v, str) else v) for k, v in CONFIG.items()}

# ------------------------------------------------------------------ numbering of chapters, figures, tables
TOC: list[tuple[int, str, str, str]] = []     # (level, number, title, marker)
FIGS: list[tuple[str, str, str]] = []        # (number, caption, marker)
TABS: list[tuple[str, str, str]] = []
_st = {"ch": 0, "fig": 0, "tab": 0}


def mk(m: str) -> str:
    return f'<span class="mk">@@{m}@@</span>'


def chapter(title: str) -> str:
    _st["ch"] += 1
    _st["fig"] = _st["tab"] = 0
    n = _st["ch"]
    TOC.append((0, str(n), title, f"H{n}"))
    return f'<div class="chap">{mk(f"H{n}")}<div class="chapno">CHAPTER {n}</div><h1>{E(title.upper())}</h1></div>'


def unnumbered(title: str, key: str) -> str:
    TOC.append((0, "", title, key))
    return f'<div class="chap">{mk(key)}<h1>{E(title.upper())}</h1></div>'


def sec(num: str, title: str) -> str:
    key = "H" + num
    TOC.append((1, num, title, key))
    return f'<h2>{mk(key)}{num} {E(title)}</h2>'


def sub(num: str, title: str) -> str:
    return f"<h3>{num} {E(title)}</h3>"


def fig(body: str, caption: str, cls: str = "") -> str:
    _st["fig"] += 1
    n = f"{_st['ch']}.{_st['fig']}"
    FIGS.append((n, caption, f"F{n}"))
    return f'<figure class="{cls}">{body}<figcaption>{mk(f"F{n}")}Figure {n}: {E(caption)}</figcaption></figure>'


def img(path: str, caption: str) -> str:
    return fig(f'<img src="{path}" alt="">', caption, "shot")


def tab(caption: str, head: list[str], rows: list[list], cls: str = "") -> str:
    _st["tab"] += 1
    n = f"{_st['ch']}.{_st['tab']}"
    TABS.append((n, caption, f"T{n}"))
    th = "".join(f"<th>{h}</th>" for h in head)
    tr = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    keep = " keep" if len(rows) <= 16 else ""
    return (f'<div class="tblock{keep}"><div class="tcap">{mk(f"T{n}")}Table {n}: {E(caption)}</div>'
            f'<table class="{cls}"><thead><tr>{th}</tr></thead><tbody>{tr}</tbody></table></div>')


def P(*paras: str) -> str:
    return "".join(f"<p>{p}</p>" for p in paras)


def UL(*items: str) -> str:
    return "<ul>" + "".join(f"<li>{i}</li>" for i in items) + "</ul>"


def OL(*items: str) -> str:
    return "<ol>" + "".join(f"<li>{i}</li>" for i in items) + "</ol>"


def code(s: str) -> str:
    return f'<pre class="code">{E(s.strip())}</pre>'


# ------------------------------------------------------------------ extra diagrams
def flow_svg(steps: list[tuple[str, str]], color: str, decision: tuple[int, str, str] | None = None) -> str:
    """Vertical flowchart. decision = (index, yes-label, no-label) turns that step into a diamond with a side exit."""
    w, bh, gap, x = 360, 46, 22, 150
    h = len(steps) * (bh + gap) + 10
    s = [f'<svg viewBox="0 0 660 {h}" width="88%" xmlns="http://www.w3.org/2000/svg" font-family="Times New Roman">',
         '<defs><marker id="ar" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto">'
         '<path d="M0 0L10 5L0 10z" fill="#333"/></marker></defs>']
    for i, (t, d) in enumerate(steps):
        y = 5 + i * (bh + gap)
        if decision and decision[0] == i:
            cx, cy = x + w / 2, y + bh / 2
            s.append(f'<polygon points="{cx},{y - 4} {x + w + 10},{cy} {cx},{y + bh + 4} {x - 10},{cy}" fill="#fff" stroke="{color}" stroke-width="1.6"/>')
            s.append(f'<text x="{cx}" y="{cy - 3}" font-size="14" font-weight="bold" text-anchor="middle">{E(t)}</text>')
            s.append(f'<text x="{cx}" y="{cy + 13}" font-size="11.5" text-anchor="middle" fill="#444">{E(d)}</text>')
            s.append(f'<path d="M{x + w + 10} {cy} L{x + w + 60} {cy}" stroke="#333" stroke-width="1.3" marker-end="url(#ar)"/>')
            s.append(f'<rect x="{x + w + 62}" y="{cy - 16}" width="76" height="32" rx="6" fill="#f3f4f6" stroke="#555"/>')
            s.append(f'<text x="{x + w + 100}" y="{cy + 5}" font-size="13" text-anchor="middle">{E(decision[2])}</text>')
            s.append(f'<text x="{x + w + 34}" y="{cy - 6}" font-size="11" text-anchor="middle">no</text>')
            s.append(f'<text x="{cx + 12}" y="{y + bh + 18}" font-size="11">{E(decision[1])}</text>')
        else:
            s.append(f'<rect x="{x}" y="{y}" width="{w}" height="{bh}" rx="{20 if i in (0, len(steps) - 1) else 6}" fill="#fff" stroke="{color}" stroke-width="1.6"/>')
            s.append(f'<text x="{x + w / 2}" y="{y + 19}" font-size="14" font-weight="bold" text-anchor="middle">{E(t)}</text>')
            s.append(f'<text x="{x + w / 2}" y="{y + 36}" font-size="11.5" text-anchor="middle" fill="#444">{E(d)}</text>')
        if i < len(steps) - 1:
            s.append(f'<path d="M{x + w / 2} {y + bh + (4 if decision and decision[0] == i else 0)} L{x + w / 2} {y + bh + gap}" stroke="#333" stroke-width="1.3" marker-end="url(#ar)"/>')
    s.append("</svg>")
    return "".join(s)


def er_svg() -> str:
    tables = [
        ("candidates", ["cand_id (PK)", "program_id", "method", "genome_json", "pipeline", "opt_flags, backend",
                        "ir_hash, bin_hash", "status, same_as_o3", "ir_insts, text_size", "machine_id"], 20, 20),
        ("measurements", ["id (PK)", "cand_id (FK)", "program_id", "stage", "n, median_ms", "base_median_ms",
                          "speedup, ci_lo, ci_hi", "raw_ms, base_raw_ms", "machine_id, cpu"], 250, 20),
        ("runs", ["run_id (PK)", "program_id", "method, seed", "budget", "config_json", "summary_json"], 480, 20),
        ("features", ["program_id (PK)", "fset (PK)", "version", "json"], 20, 290),
        ("pass_effects", ["program_id (PK)", "label (PK)", "kind, pass", "edit_json", "cand_id (FK)",
                          "screen_sp, conf_sp", "ci_lo, ci_hi"], 250, 290),
        ("eval_results", ["tag (PK)", "program_id (PK)", "method (PK)", "choice, genome_json",
                          "speedup, ci_lo, ci_hi", "select_speedup", "control"], 480, 290),
    ]
    s = ['<svg viewBox="0 0 700 520" width="96%" xmlns="http://www.w3.org/2000/svg" font-family="Times New Roman">']
    for name, cols, x, y in tables:
        hh = 26 + 17 * len(cols)
        s.append(f'<rect x="{x}" y="{y}" width="200" height="{hh}" fill="#fff" stroke="#1f2937" stroke-width="1.3"/>')
        s.append(f'<rect x="{x}" y="{y}" width="200" height="24" fill="#e5e7eb" stroke="#1f2937" stroke-width="1.3"/>')
        s.append(f'<text x="{x + 100}" y="{y + 17}" font-size="14" font-weight="bold" text-anchor="middle">{name}</text>')
        for i, c in enumerate(cols):
            s.append(f'<text x="{x + 8}" y="{y + 40 + 17 * i}" font-size="12">{E(c)}</text>')
    for (x1, y1, x2, y2, lab) in [(220, 60, 250, 60, "1 : N"), (120, 214, 120, 290, ""), (350, 290, 350, 196, "N : 1"), (580, 290, 580, 140, "")]:
        s.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="#6b7280" stroke-width="1.2" stroke-dasharray="4 3"/>')
        if lab:
            s.append(f'<text x="{(x1 + x2) / 2 + 4}" y="{(y1 + y2) / 2 - 4}" font-size="11" fill="#374151">{lab}</text>')
    s.append('<text x="350" y="505" font-size="12" text-anchor="middle" fill="#4b5563">All tables are keyed by program_id; every row carries machine_id so measurements of different machines are never mixed.</text></svg>')
    return "".join(s)


def interleave_svg() -> str:
    cols = {"B": ("#64748b", "-O3 (base)"), "C": ("#0891b2", "A/A copy of -O3"), "1": ("#7c3aed", "candidate 1"), "2": ("#db2777", "candidate 2")}
    rounds = [["B", "1", "C", "2"], ["2", "B", "1", "C"], ["C", "2", "B", "1"], ["1", "C", "2", "B"], ["B", "2", "1", "C"]]
    s = ['<svg viewBox="0 0 700 250" width="92%" xmlns="http://www.w3.org/2000/svg" font-family="Times New Roman">',
         '<text x="10" y="18" font-size="13" font-weight="bold">pinned vCPU 6 (sibling idle), ASLR off, 3 s busy warm-up, quiet guard checked before the block</text>']
    for r, order in enumerate(rounds):
        y = 36 + r * 32
        s.append(f'<text x="10" y="{y + 18}" font-size="12">round {r + 1}</text>')
        for i, k in enumerate(order):
            c, _ = cols[k]
            s.append(f'<rect x="{80 + i * 120}" y="{y}" width="112" height="26" rx="4" fill="{c}" fill-opacity=".18" stroke="{c}"/>')
            s.append(f'<text x="{136 + i * 120}" y="{y + 18}" font-size="12" text-anchor="middle">{E(cols[k][1])}</text>')
    s.append('<text x="580" y="70" font-size="12">per round: ratio</text><text x="580" y="86" font-size="12">base / candidate</text>'
             '<text x="580" y="116" font-size="12">speedup = median</text><text x="580" y="132" font-size="12">of the ratios</text>'
             '<text x="580" y="162" font-size="12">95% CI: bootstrap</text><text x="580" y="178" font-size="12">(4,000 resamples)</text>')
    s.append('<text x="10" y="232" font-size="12" fill="#374151">Order is shuffled every round, so slow drift (temperature, frequency, background load) affects every binary equally.</text></svg>')
    return "".join(s)


def genome_svg() -> str:
    s = ['<svg viewBox="0 0 700 210" width="94%" xmlns="http://www.w3.org/2000/svg" font-family="Times New Roman">',
         '<text x="10" y="18" font-size="13" font-weight="bold">-O3 pass tree (LLVM 18, 109 leaf passes)</text>']
    passes = ["annotation2metadata", "forceattrs", "inferattrs", "…", "sroa", "early-cse", "simplifycfg", "instcombine", "…", "licm", "loop-unroll", "slp-vectorizer"]
    for i, p in enumerate(passes):
        s.append(f'<rect x="{10 + i * 57}" y="30" width="53" height="40" rx="3" fill="#f3f4f6" stroke="#6b7280"/>'
                 f'<text x="{36 + i * 57}" y="54" font-size="8.5" text-anchor="middle">{E(p)}</text>')
    s.append('<text x="10" y="100" font-size="13" font-weight="bold">genome = list of edits applied to a copy of the tree</text>')
    eds = [("param_all", "every simplifycfg: sink-common-insts off", "#2563eb"), ("knob", "-unroll-max-count=4", "#d97706"),
           ("del_all", "every instcombine removed", "#dc2626"), ("llc flag", "-tail-dup-size=6", "#059669")]
    for i, (k, d, c) in enumerate(eds):
        s.append(f'<rect x="{10 + i * 172}" y="110" width="164" height="48" rx="6" fill="#fff" stroke="{c}" stroke-width="1.5"/>'
                 f'<text x="{92 + i * 172}" y="129" font-size="12.5" font-weight="bold" text-anchor="middle" fill="{c}">{k}</text>'
                 f'<text x="{92 + i * 172}" y="148" font-size="10.5" text-anchor="middle">{E(d)}</text>')
    s.append('<text x="10" y="190" font-size="12">materialize(tree, genome) → (opt pipeline string, opt flags, llc level and flags) → clang/opt/llc build → binary (cached by IR hash)</text></svg>')
    return "".join(s)


# ------------------------------------------------------------------ front matter
def logo(name: str, cls: str) -> str:
    p = ASSETS / name
    return f'<img class="{cls}" src="assets/{name}" alt="">' if p.exists() else f'<div class="{cls} logo-ph">[{name}]</div>'


def students_table(cls="stud") -> str:
    return f'<table class="{cls}">' + "".join(f"<tr><td>{E(n)}</td><td>{ph(u)}</td></tr>" for n, u in CONFIG["students"]) + "</table>"


def cover() -> str:
    return f"""<section class="cover">
      <div class="uni">{C['university']}</div><div class="uniaddr">{C['university_addr']}</div>
      {logo('vtu_logo.png', 'vtu')}
      <div class="kind">{C['report_kind']}</div><div class="on">ON</div>
      <div class="ptitle">“{C['title']}”</div>
      <div class="sub">Submitted in the partial fulfillment of the requirements for the award of the degree of</div>
      <div class="deg">BACHELOR OF ENGINEERING<br>IN<br>COMPUTER SCIENCE &amp; ENGINEERING</div>
      <div class="by">Submitted by</div>{students_table()}
      <div class="ug">Under the Guidance of</div><div class="gname">{C['guide']}</div>
      <div class="gdes">{C['guide_designation']}, Department of Computer Science and Engineering<br>{C['college_short']}, Bengaluru</div>
      {logo('jss_logo.png', 'jss')}
      <div class="col">{C['college']}</div><div class="col">{C['dept']}</div><div class="yr">{C['year']}</div>
    </section>"""


def certificate() -> str:
    names = ", ".join(f"{E(n)} ({ph(u)})" for n, u in CONFIG["students"])
    return f"""<section class="cert">
      <div class="col big">JSS ACADEMY OF TECHNICAL EDUCATION</div><div class="uniaddr">{C['college_addr']}</div>
      <div class="col">{C['dept']}</div>{logo('jss_logo.png', 'jss')}
      <div class="certh">CERTIFICATE</div>
      <p>This is to certify that the Project Work entitled <b>“{E(CONFIG['title_text'])}”</b> has been successfully carried out by
      {names} in partial fulfillment for the award of the degree of Bachelor of Engineering in Computer Science and Engineering of
      Visvesvaraya Technological University, Belagavi during the year {C['year']}. It is certified that all corrections / suggestions
      indicated for Internal Assessment have been incorporated in the report deposited in the departmental library. The project work
      report has been approved as it satisfies the academic requirements in respect of project work prescribed for the said degree.</p>
      <table class="sig"><tr>
        <td><div class="line"></div><b>{C['guide']}</b><br>{C['guide_designation']}<br>Dept. of CSE<br>{C['college_short']}, Bengaluru</td>
        <td><div class="line"></div><b>{C['hod']}</b><br>{C['hod_designation']}<br>Dept. of CSE<br>{C['college_short']}, Bengaluru</td>
        <td><div class="line"></div><b>{C['principal']}</b><br>Principal<br>{C['college_short']}, Bengaluru</td></tr></table>
      <div class="ext">External Examiner</div>
      <table class="exam"><tr><th>Name of the examiners</th><th>Signature with date</th></tr>
        <tr><td>1) ______________________________</td><td>______________________________</td></tr>
        <tr><td>2) ______________________________</td><td>______________________________</td></tr></table>
    </section>"""


def declaration() -> str:
    return f"""<section class="decl"><h1 class="fm">DECLARATION</h1>
      <p>We, the students of the Department of Computer Science and Engineering, {E('JSS Academy of Technical Education, Bengaluru')},
      hereby declare that the project work entitled <b>“{E(CONFIG['title_text'])}”</b> has been carried out by us under the guidance of
      {C['guide']}, {C['guide_designation']}, Department of Computer Science and Engineering, and submitted in partial fulfillment of the
      requirements for the award of the degree of Bachelor of Engineering in Computer Science and Engineering of Visvesvaraya Technological
      University, Belagavi, during the academic year {C['year']}.</p>
      <p>We further declare that the work reported in this report has not been submitted, either in part or in full, for the award of
      any other degree or diploma. All measurements reported here were produced by the scripts and result files contained in the project
      repository and can be reproduced from them.</p>
      <p style="margin-top:14mm">Place: Bengaluru<br>Date: ____________</p>{students_table('stud right')}
    </section>"""


def abstract() -> str:
    t, p5, pr = D["headline"]["tune_rlsl"], D["headline"]["phase5"], D["headline"]["predict"]
    return f"""<section class="fmsec"><h1 class="fm">ABSTRACT</h1>
    <p>Optimizing compilers apply one fixed sequence of transformation passes, such as LLVM's <i>-O3</i>, to every program, although
    the best sequence depends on the program's loops, data sizes, memory behaviour and branches. Earlier attempts to learn better
    sequences often optimized proxies such as IR instruction count or binary size, which, as this project confirms on
    {D['ir']['n']:,} measured candidates (Spearman ρ = {D['ir']['rho']:.2f}), say almost nothing about runtime.
    <b>NeuroCompiler</b> selects, for each C/C++ program, an LLVM 18 pass pipeline that is judged only by <b>measured runtime</b>
    against <i>clang -O3</i>, and that must reproduce the unoptimized program's output exactly.</p>
    <p>A statistically controlled timing harness (CPU pinning, interleaved rounds, paired bootstrap confidence intervals and an
    A/A control binary) was built first. A corpus of {D['corpus']['usable']} programs in {D['corpus']['families']} families was assembled
    from PolyBench and the LLVM test-suite and split by family into training, validation and a frozen test set. Genetic and
    evolutionary search over an edit space of pass deletions, repetitions, reorderings, insertions, pass options, global knobs and
    code-generator flags found a geomean improvement of {pct(p5['geomean'], 1)} on {p5['n']} programs it had never seen. These
    measurements train a LightGBM surrogate model and a Proximal Policy Optimization (PPO) agent. In deployment (<i>tune</i> mode)
    the agent proposes pipelines, the surrogate ranks them together with a library of about 913 pipelines, and the eight best are
    compiled, verified and timed; a pick ships only after a fresh confirmation run, otherwise -O3 is kept.</p>
    <p>On 33 test programs from 11 families never used in training, tune is {pct(t['geomean'])} faster than -O3 (geomean, 95% CI
    {ci(t['ci'])}; {pct(t['excl_largest'])} excluding the largest result), with {t['ge5']} programs at least 5% faster and none
    measurably slower. A compile-only <i>predict</i> mode reached {pct(pr['geomean'])} and missed its pre-registered target, so it is
    shipped as advisory. A web dashboard and a command-line tool make the system usable, and the report states every gate that was
    missed together with the decision taken.</p>
    <p class="kw"><b>Keywords:</b> compiler optimization, LLVM, phase ordering, autotuning, LightGBM, reinforcement learning, PPO,
    performance measurement.</p></section>"""


def acknowledgement() -> str:
    return f"""<section class="fmsec"><h1 class="fm">ACKNOWLEDGEMENT</h1>
    <p>The satisfaction and euphoria that accompany the successful completion of any task would be incomplete without the mention of
    the people who made it possible. With gratitude, we acknowledge all those whose guidance and encouragement crowned our effort with success.</p>
    <p>First and foremost, we would like to thank <b>{C['swamiji']}</b> and <b>{C['principal']}</b>, Principal, {C['college_short']},
    Bengaluru, for providing us an opportunity to present this project as a part of our curriculum in the partial fulfillment of the degree course.</p>
    <p>We express our sincere gratitude to <b>{C['hod']}</b>, {C['hod_designation']}, Department of Computer Science and Engineering,
    for the co-operation and encouragement at all the moments of our work.</p>
    <p>We are sincerely grateful to our project guide, <b>{C['guide']}</b>, {C['guide_designation']}, Department of Computer Science and
    Engineering, for {CONFIG['guide_pronoun']} guidance and advice in carrying out our project work; the valuable suggestions and constant
    supervision have been very helpful.</p>
    <p>We express our sincere thanks to the project co-ordinator, <b>{C['coordinator']}</b>, {C['coordinator_designation']}, Department of
    Computer Science and Engineering, who helped us in every aspect of our project work.</p>
    <p>We would like to thank the department for the constant encouragement, valuable help and assistance in every possible way, and
    all the staff members for their wholehearted support and co-operation.</p>
    {students_table('stud right')}</section>"""


ABBR = [
    ("A/A control", "a byte-identical copy of the -O3 binary timed as if it were a candidate; it must measure 1.00× (noise check)"),
    ("AVX-512", "512-bit SIMD instruction set of the Zen 4 CPU"), ("CFG", "control-flow graph"),
    ("CGSCC", "call-graph strongly connected component (LLVM pass level)"), ("CI", "confidence interval (95% unless stated)"),
    ("CLI", "command-line interface"), ("CV", "cross-validation"),
    ("evo / evo2", "evolutionary search over action space v1 / v2"), ("GA", "genetic algorithm"),
    ("GAE", "generalized advantage estimation"), ("gain@k", "best true speedup among a model's top-k candidates"),
    ("geomean", "geometric mean of per-program speedups"), ("GVN", "global value numbering"),
    ("IR", "intermediate representation (LLVM IR)"), ("KB", "knowledge base (Phase 4 single-edit study)"),
    ("LICM", "loop-invariant code motion"), ("llc", "LLVM static compiler (code generator)"),
    ("LL / LLd", "last-level cache / last-level data cache (simulated)"), ("LOFO", "leave-one-family-out"),
    ("MLP", "multi-layer perceptron"), ("MPKI", "misses per thousand instructions"),
    ("n.s.", "not statistically significant"), ("opt", "LLVM IR optimizer"),
    ("PPO", "proximal policy optimization"), ("RL", "reinforcement learning"),
    ("SL", "supervised learning (the LightGBM surrogate)"), ("SMT", "simultaneous multithreading (two vCPUs per core)"),
    ("SROA", "scalar replacement of aggregates"), ("SSE", "server-sent events (live terminal stream)"),
    ("TBAA", "type-based alias analysis metadata"), ("vCPU", "virtual CPU visible inside WSL2"),
    ("WSL2", "Windows Subsystem for Linux, version 2"), ("-O3", "clang/LLVM's standard highest optimization level"),
]


def toc_page(pages: dict[str, int]) -> str:
    def pg(m):
        return str(pages.get(m, "")) if pages else ""
    rows = []
    for lvl, num, title, m in TOC:
        cls = "t0" if lvl == 0 else "t1"
        label = (f"CHAPTER {num}: " if lvl == 0 and num else (num + " " if num else "")) + title
        rows.append(f'<div class="{cls}"><span class="tl">{E(label.upper() if lvl == 0 else label)}</span><span class="dots"></span><span class="pg">{pg(m)}</span></div>')
    return '<section class="fmsec toc"><h1 class="fm">TABLE OF CONTENTS</h1>' + \
        '<div class="t0 hd"><span class="tl">Contents</span><span class="dots" style="border:0"></span><span class="pg">Page</span></div>' + \
        "".join(rows) + "</section>"


def list_page(title: str, items, pages, word: str) -> str:
    rows = "".join(f'<div class="t1"><span class="tl">{word} {n}: {E(c)}</span><span class="dots"></span><span class="pg">{pages.get(m, "") if pages else ""}</span></div>' for n, c, m in items)
    return f'<section class="fmsec toc"><h1 class="fm">{title}</h1>{rows}</section>'


def abbr_page() -> str:
    return '<section class="fmsec"><h1 class="fm">LIST OF ABBREVIATIONS</h1><table class="abbr">' + \
        "".join(f"<tr><td><b>{E(a)}</b></td><td>{E(b)}</td></tr>" for a, b in ABBR) + "</table></section>"


# ------------------------------------------------------------------ chapters
def chapters() -> str:
    c, H5, G3, ev, md, kb = D["corpus"], D["phase5"], D["gate3"], D["eval"], D["models"], D["kb"]
    t, t8, p5, prd = D["headline"]["tune_rlsl"], D["headline"]["tune_top8"], D["headline"]["phase5"], D["headline"]["predict"]
    S = ev["summary"]
    fs = md["feature_sets"]
    A = []

    # ================= 1 INTRODUCTION
    A.append(chapter("Introduction"))
    A.append(sec("1.1", "Overview"))
    A.append(P(
        "A compiler translates a program written in a high-level language into machine code. Between parsing and code generation, an "
        "optimizing compiler such as LLVM transforms the program through a long sequence of <i>passes</i>: each pass performs one analysis "
        "or transformation, for example promoting memory to registers (SROA), removing redundant computations (GVN, early-CSE), simplifying "
        "the control-flow graph (SimplifyCFG), moving loop-invariant code out of loops (LICM), unrolling loops or vectorizing them. The "
        "standard optimization levels (-O1, -O2, -O3, -Os) are fixed recipes: the LLVM 18 -O3 pipeline consists of 109 leaf passes in a "
        "fixed order with fixed options, applied identically to every program.",
        "Those recipes are a compromise tuned on typical code. For an individual program, a different order, a different set of passes or "
        "different pass parameters can produce noticeably faster code, because whether a transformation helps depends on properties that the "
        "fixed recipe cannot see: loop trip counts, data-set sizes relative to the caches, branch predictability, and the micro-architecture of "
        "the machine. Selecting and ordering passes per program is known as the <i>phase-ordering</i> or <i>pass-selection</i> problem.",
        "<b>NeuroCompiler</b> is a system that solves this problem for C and C++ programs on a fixed machine. It combines a supervised "
        "machine-learning model (LightGBM), a reinforcement-learning agent (PPO) and, decisively, real measurement: for each new program it "
        "proposes a small number of edited -O3 pipelines, compiles them, verifies that each produces exactly the same output as the "
        "unoptimized program, times them against -O3 under statistical control, and ships a pipeline only if it is confirmed to be faster. "
        "-O3 is always among the candidates, so the system is designed never to be slower than the standard compiler."))
    A.append(sec("1.2", "Motivation"))
    A.append(P(
        "Runtime performance matters directly for energy use, cloud cost and user experience, and a few percent on hot code is significant. "
        "Hand-tuning compiler flags requires expert knowledge and many experiments per program. Machine-learning approaches to compiler "
        "optimization have been studied for two decades, but many published systems optimize proxy metrics that are cheap to compute, such as "
        "the number of IR instructions or the code size, because measuring runtime reliably is slow and noisy.",
        f"An earlier attempt in this project did exactly that: it reduced IR instruction count and binary size, but runtime did not improve. "
        f"Our measurements later confirmed why: across {D['ir']['n']:,} timed candidates the change in IR instruction count and the change in "
        f"runtime are essentially uncorrelated (Spearman ρ = {D['ir']['rho']:.2f}). Fewer instructions frequently means less unrolling or "
        "vectorization, which is slower. The motivation of NeuroCompiler is therefore to optimize the quantity that users actually care about, "
        "measured runtime, and to build the measurement infrastructure that makes this trustworthy."))
    A.append(sec("1.3", "Problem Statement"))
    A.append(P(
        "Given a C/C++ program, its command-line arguments and standard input, and the LLVM 18.1.8 toolchain on a fixed machine, select an "
        "optimization pipeline (a sequence of LLVM passes with their options, global optimizer knobs and code-generator settings) such that the "
        "resulting binary (i) produces exactly the same output as the program compiled without optimization, (ii) is measurably and reproducibly "
        "faster than the binary produced by <i>clang -O3</i>, and (iii) stays within a soft limit of 1.10× the -O3 code size, for programs that "
        "were not used to train the system. If no such pipeline can be confirmed, the system must return the -O3 binary."))
    A.append(sec("1.4", "Objectives"))
    A.append(OL(
        "Build a measurement harness whose timing noise and bias are quantified and below 1% (CPU pinning, interleaving, paired bootstrap "
        "confidence intervals, A/A control, self-test).",
        "Assemble a corpus of real benchmark programs that are deterministic, verifiable and long enough to time, grouped into families and "
        "split so that the test programs come from families never seen in training.",
        "Measure the headroom over -O3 with search (random, genetic, evolutionary) on a rich edit space, and stop the project at a "
        "pre-registered gate if there is none.",
        "Learn from the search data which edits matter (pass knowledge base) and train a surrogate model that ranks candidate pipelines for an "
        "unseen program, and a reinforcement-learning agent that proposes new pipelines.",
        "Deploy a per-program tuning loop (propose, rank, compile, verify, time, confirm, fall back to -O3) and evaluate it once on a frozen test "
        "set against random and genetic baselines at equal compile budget.",
        "Provide a compile-only <i>predict</i> mode, a command-line tool and a web dashboard, and document every decision reproducibly."))
    A.append(sec("1.5", "Scope of the Project"))
    A.append(P(
        "The project targets single-threaded C and C++ programs that read their input from arguments, standard input or files, and print their "
        "result deterministically. It uses one pinned compiler version (LLVM 18.1.8) and one machine (AMD Ryzen 9 270, Zen 4, under WSL2 Ubuntu), "
        "because pipeline effects are machine specific. Runtime is the only objective; binary size, IR count and compile time are constraints. "
        "Multi-threaded programs, programs with non-deterministic output, cross-compilation and other compilers (GCC) are out of scope."))
    A.append(sec("1.6", "Success Criteria"))
    A.append(tab("Success tiers defined before the work", ["Tier", "Definition"], [
        ["Minimum", "no regressions beyond noise and no miscompiled programs"],
        ["Good", "geomean speedup +2–4% with the 95% CI excluding 0, and 20–30% or more of the programs at least +5% faster"],
        ["Strong", "geomean speedup of +5% or more"]]))
    A.append(P(
        "In addition, a sequence of gates was fixed in advance: a headroom gate after the search phase (Phase 3), a data-quality gate after "
        "data collection (Phase 5), a model gate requiring the surrogate to beat random selection on held-out families (Gate 7B), and a rule "
        "that reinforcement learning is adopted only if it beats the top-k loop and the genetic algorithm at equal compile budget. Thresholds "
        "were never relaxed after seeing results; where a gate was missed, this report says so and states the decision that followed."))
    A.append(sec("1.7", "Organization of the Report"))
    A.append(P(
        "Chapter 2 surveys the literature on iterative compilation, machine-learning compilers and performance measurement. Chapter 3 states "
        "the functional and non-functional requirements and the hardware and software environment. Chapter 4 presents the system design: "
        "architecture, data flow, module decomposition, pipeline representation, database and the tune, predict and dashboard designs. "
        "Chapter 5 describes the implementation phase by phase. Chapter 6 covers testing and validation of the harness and the system. "
        "Chapter 7 presents and discusses the results, including the dashboard snapshots. Chapter 8 concludes and lists future enhancements."))

    # ================= 2 LITERATURE SURVEY
    A.append(chapter("Literature Survey"))
    A.append(sec("2.1", "The LLVM Compiler Infrastructure"))
    A.append(P(
        "LLVM [1] is a compiler framework built around a typed, SSA-based intermediate representation. Front ends such as clang translate "
        "C/C++ into LLVM IR; the <i>opt</i> tool applies optimization passes to the IR; <i>llc</i> lowers the IR to machine code. Since LLVM 13 "
        "the default <i>new pass manager</i> describes a pipeline textually as nested module, CGSCC, function and loop pass managers, and "
        "<code>opt -passes='default&lt;O3&gt;' -print-pipeline-passes</code> prints the complete expanded -O3 pipeline with every pass option. "
        "This textual form makes it possible to edit the standard pipeline programmatically, which NeuroCompiler exploits: every candidate is "
        "the real -O3 pipeline plus a short list of edits."))
    A.append(sec("2.2", "Iterative Compilation and Search"))
    A.append(P(
        "Cooper et al. [2] showed that genetic algorithms can find pass sequences that beat fixed optimization levels, initially for code size. "
        "Such <i>iterative compilation</i> compiles and runs many variants of a program and keeps the best; it is effective but expensive, often "
        "requiring hundreds of evaluations per program. OpenTuner [6] generalized this into an extensible autotuning framework with an ensemble "
        "of search techniques. These works establish that headroom exists, but they need many runs per program and give no help for new programs."))
    A.append(sec("2.3", "Machine Learning for Compiler Optimization"))
    A.append(P(
        "Agakov et al. [3] used models trained on program features to focus iterative search on promising regions, reducing the number of "
        "evaluations by an order of magnitude. MILEPOST GCC [4] extracted static program features inside GCC and learned to predict good "
        "optimization flags for unseen programs. Kulkarni and Cavazos [5] trained neural networks to choose the next optimization based on the "
        "current state of the code, addressing phase ordering directly. Wang and O'Boyle [22] survey the field and note recurring difficulties: "
        "small training sets, features that do not capture dynamic behaviour, and evaluation on proxy metrics.",
        "More recent work uses deep learning and reinforcement learning. AutoPhase [7] applied deep RL to phase ordering for high-level "
        "synthesis, using program features and pass histograms as the state. NeuroVectorizer [11] used RL to choose vectorization and "
        "interleaving factors for loops. MLGO [8] integrated learned policies for inlining (for size) and register allocation into "
        "production LLVM. CompilerGym [9] provides standardized RL environments for LLVM phase ordering, where the most common reward is IR "
        "instruction count, and ProGraML [10] proposed graph representations of programs for learning."))
    A.append(sec("2.4", "Gradient-Boosted Trees and Policy-Gradient Methods"))
    A.append(P(
        "LightGBM [12] is a gradient-boosted decision-tree library that uses histogram-based split finding and leaf-wise tree growth. "
        "Gradient-boosted trees are strong on small, tabular, heterogeneous feature sets, need little tuning, train in seconds and handle "
        "features of different scales without normalization, which suits a data set of a few thousand labelled (program, pipeline) pairs. "
        "LightGBM also implements the LambdaRank objective [21] for learning to rank.",
        "Proximal Policy Optimization [13] is a policy-gradient RL algorithm that limits the size of each policy update with a clipped "
        "probability-ratio objective, making training stable with few hyper-parameters. Combined with generalized advantage estimation [14] "
        "and the Adam optimizer [24], it is a standard choice for discrete action spaces such as choosing the next compiler edit."))
    A.append(sec("2.5", "Performance Measurement Methodology"))
    A.append(P(
        "Mytkowicz et al. [15] showed that seemingly innocuous factors, such as the size of the UNIX environment or the link order, change "
        "measured runtime by several percent and can produce wrong conclusions. STABILIZER [16] randomizes code and data layout to make "
        "performance comparisons statistically sound. These results motivate NeuroCompiler's harness: interleaved, paired measurements on a "
        "pinned core with ASLR disabled, bootstrap confidence intervals [20], and an A/A control that detects bias directly. Layout "
        "randomization was also tested in this project and gave no benefit for our measurements."))
    A.append(sec("2.6", "Summary of the Survey and Research Gap"))
    A.append(tab("Summary of the literature survey", ["Work", "Approach", "Metric", "Limitation addressed by this project"], [
        ["Cooper et al. [2]", "genetic search of pass sequences", "code size", "many evaluations per program; no transfer to new programs"],
        ["Agakov et al. [3]", "models focus iterative search", "runtime", "older GCC framework; small feature sets"],
        ["MILEPOST GCC [4]", "static features → flags", "runtime", "flag selection only, no pass-level edits"],
        ["Kulkarni & Cavazos [5]", "neural phase ordering", "runtime", "evaluated on few programs; no confirmation of wins"],
        ["OpenTuner [6]", "ensemble autotuning", "user-defined", "needs many runs per program"],
        ["AutoPhase [7]", "deep RL phase ordering", "HLS cycle count", "different target (HLS), simulated cost"],
        ["MLGO [8]", "learned inlining / regalloc", "size / runtime", "single decision type, not the whole pipeline"],
        ["CompilerGym [9]", "RL environments for LLVM", "mostly IR count", "IR count is not runtime (ρ ≈ 0 here)"],
        ["Mytkowicz et al. [15]", "measurement bias study", "–", "motivates A/A controls and interleaving"]], "small"))
    A.append(P(
        "The gap this project addresses is the combination of (a) whole-pipeline edits on the real LLVM -O3 pipeline, including pass options, "
        "global knobs and code-generator flags, (b) optimization of measured runtime only, with statistical controls that detect noise and bias, "
        "(c) strict evaluation on program families never used in training, with gates fixed in advance, and (d) a deployment loop in which "
        "models only shortlist candidates and measurement makes the final decision, so that the system cannot be slower than -O3 beyond noise."))

    # ================= 3 SRS
    A.append(chapter("System Requirements Specification"))
    A.append(sec("3.1", "Functional Requirements"))
    A.append(tab("Functional requirements", ["ID", "Requirement"], [
        ["FR1", "Accept a C/C++ program (one or more files), its arguments, standard input and extra compiler flags."],
        ["FR2", "Build the program at -O0 and record the hash of its output as the correctness oracle."],
        ["FR3", "Build the program with any edited LLVM pipeline (pass deletions, repetitions, swaps, insertions, pass options, knobs, llc flags and level)."],
        ["FR4", "Reject every candidate whose output differs from the -O0 output, and skip candidates whose binary is identical to -O3."],
        ["FR5", "Time candidates against -O3 with interleaved rounds, paired bootstrap confidence intervals and an A/A control."],
        ["FR6", "Tune mode: propose (RL), rank (SL), compile and time the top 8, confirm the fastest, and output the pick or -O3 with a JSON report."],
        ["FR7", "Predict mode: choose a pipeline without running the program, apply a safety gate, then compile and time the top pick for reporting."],
        ["FR8", "Compare mode: time -O3, -O2, -Os, predict, tune, random search and GA in one interleaved run with a control."],
        ["FR9", "Research commands: environment check, self-test, corpus building, search, knowledge base, data collection, features, model training, RL training and evaluation."],
        ["FR10", "Web dashboard: submit jobs, stream the terminal output live, show the chosen versus -O3 sequence, runtimes in ms, edits in words, save and replay runs."]], "small"))
    A.append(sec("3.2", "Non-Functional Requirements"))
    A.append(UL(
        "<b>Correctness:</b> no miscompiled program may be shipped; output equality with -O0 is checked for every candidate.",
        "<b>Measurement quality:</b> harness self-test thresholds CI half-width &lt; 1%, A/A bias &lt; 1%, drift &lt; 2%.",
        "<b>Safety:</b> -O3 is always the fallback; a pick ships only if its confirmation CI lower bound exceeds 1.01.",
        "<b>Reproducibility:</b> every reported number is produced by a script from result files in the repository; models are frozen with SHA-256 manifests.",
        "<b>Performance:</b> tune completes in minutes per program; predict adds at most 10 s (median) over a plain -O3 build.",
        "<b>Usability:</b> one command (<code>bin/neurocompiler</code>) and a local web dashboard that works offline.",
        "<b>Maintainability:</b> modular Python package (<code>nc/</code>) with one module per phase; long jobs resumable."))
    A.append(sec("3.3", "Hardware Requirements"))
    A.append(tab("Hardware used", ["Component", "Specification"], [
        ["Processor", "AMD Ryzen 9 270 (Zen 4, AVX-512), 8 cores / 16 threads"],
        ["Memory", "host RAM shared with WSL2; WSL2 configured with 10 GB"],
        ["vCPUs visible to WSL2", "14 (SMT pairs 0-1 … 12-13); earlier data measured with 8"],
        ["Timing CPU", "vCPU 6 for serial timing; vCPUs 2, 6, 10 for parallel screening"],
        ["Storage", "SSD; SQLite databases and binary cache in the repository"]]))
    A.append(sec("3.4", "Software Requirements"))
    A.append(tab("Software used", ["Software", "Version / purpose"], [
        ["Operating system", "Windows with WSL2 Ubuntu"],
        ["Compiler", "LLVM / clang 18.1.8 (pinned at /usr/lib/llvm-18/bin; the OS default LLVM 21 is never used for data)"],
        ["Language", "Python 3.14 (virtual environment .venv)"],
        ["Libraries", "NumPy, SciPy, LightGBM, scikit-learn; PPO implemented in NumPy"],
        ["Profiling", "valgrind cachegrind (simulated cache and branch statistics)"],
        ["Database", "SQLite (dataset.sqlite, predict.sqlite, deploy.sqlite)"],
        ["Dashboard", "FastAPI + uvicorn, vanilla JavaScript modules, Chart.js 4.4.4, CodeMirror 5.65"],
        ["Benchmarks", "PolyBench/C 4.2.1, LLVM test-suite SingleSource and MultiSource"]]))
    A.append(sec("3.5", "Constraints and Assumptions"))
    A.append(UL(
        "The machine is shared with other heavy experiments; a quiet guard waits for foreign load to drop before any timing block.",
        "No hardware performance counters are available inside WSL2; cache and branch statistics are simulated with cachegrind and labelled as such. "
        "Cachegrind builds use -march=x86-64-v3 because valgrind cannot execute AVX-512.",
        "Programs must be deterministic and run 0.35–3 s at -O3 so that timing is precise and the corpus can be processed in reasonable time.",
        "Gains are specific to the workload supplied (arguments and input) and to this machine."))

    # ================= 4 SYSTEM DESIGN
    A.append(chapter("System Design"))
    A.append(sec("4.1", "System Architecture"))
    A.append(P(
        "The system has an offline part, which produces measurements and trained models, and an online part, which serves one program at a "
        "time. Figure 4.1 shows the four layers. In lane 1, benchmark sources become a filtered, family-split corpus; the timing harness and "
        "the pipeline search produce labelled measurements stored in <code>dataset.sqlite</code>. In lane 2, program features are extracted "
        "and the supervised surrogate, the RL agent, the pipeline library and the predict models are trained and frozen with hashed manifests. "
        "In lane 3, for a new program, the toolchain builds the reference and the features, tune pools RL proposals with the library, the "
        "surrogate ranks them and the top eight are compiled, verified and timed. Lane 4 contains the interfaces (CLI, dashboard) and the environment."))
    A.append(fig(R.arch_svg(), "System architecture of NeuroCompiler (dashed arrows: frozen models used at deployment)"))
    A.append(sec("4.2", "Data Flow"))
    A.append(P(
        "Data flows in one direction from measurement to models, and the models never write measurements. A <i>candidate</i> (program, genome) "
        "is materialized into an opt pipeline string, opt flags and llc settings, compiled, and stored with its IR hash and binary hash. "
        "Measurements reference candidates and record the stage (screen, confirm, validate), the number of rounds, the medians of base and "
        "candidate, the speedup and its CI, and the raw per-round times. Features are stored per program and feature set. Training reads "
        "validated, confirmed and screened measurements with stage-dependent weights. Deployment reads only frozen model files."))
    A.append(sec("4.3", "Module Decomposition"))
    A.append(tab("Modules of the nc package and the user interfaces", ["Module", "Responsibility"], [
        ["nc/toolchain.py", "build with any pass pipeline (single or multi-file, C or C++), knobs and llc flags; IR-hash cache; -O3 pipeline printing"],
        ["nc/timing.py", "pinned interleaved runner, bootstrap CIs, paired speedup, output hashing, quiet guard, SMT-sibling handling, A/A control"],
        ["nc/corpus.py, nc/msource.py", "fetch suites, prescan, quality filters, frozen family split; MultiSource adapter (mini CMake interpreter)"],
        ["nc/pipeline.py", "-O3 pass-tree parsing and rendering, genome, edit operators, action spaces v1 and v2, materialize()"],
        ["nc/search.py", "levels / random / evo / evo2 search, screening, merged confirmation, minimization, validation"],
        ["nc/passkb.py", "Phase 4 knowledge base of single edits; attribution and pruned action set"],
        ["nc/collect.py, nc/parallel.py", "Phase 5 data collection; multi-core timing with the memory-aware scheduler; data-quality report"],
        ["nc/features.py, nc/remarks.py", "static IR, scan and cachegrind features; genome encoding; optimization-remark features"],
        ["nc/model.py", "LightGBM regressor and ranker, leave-one-family-out CV, Gate 7B"],
        ["nc/rl.py", "PPO in NumPy: macro-actions, environment with surrogate reward, training, proposals"],
        ["nc/deploy.py, nc/tunelock.py", "tune mode (RL + SL), confirmation and JSON report; frozen MANIFEST with SHA-256 hashes"],
        ["nc/predict.py", "predict mode: safe pool, ensemble, harm classifier, gate, measurement of the pick"],
        ["nc/evaluate.py", "Phase 9 frozen-test evaluation of all methods"],
        ["nc/cli.py, bin/neurocompiler", "command-line interface for research commands and the tune / predict / compare modes"],
        ["dashboard/", "FastAPI server, static web front end, examples, saved runs, Windows launcher"]], "small"))
    A.append(sec("4.4", "Representation of a Pipeline (Genome)"))
    A.append(P(
        "The -O3 pipeline printed by opt is parsed into a tree of pass managers and leaf passes, each with its options. A candidate is not an "
        "arbitrary pass list but a <b>genome</b>: a short list of edits applied to a copy of that tree (Figure 4.2). This keeps every candidate "
        "close to a known-good pipeline, makes candidates human-readable, and lets search and learning work with a small action vocabulary. "
        "Table 4.2 lists the edit types; action space v1 contains the first four plus six knobs and the llc level, and v2 adds the rest."))
    A.append(fig(genome_svg(), "A genome is a list of edits applied to the -O3 pass tree"))
    A.append(tab("Edit types of the genome", ["Edit", "Meaning", "Example"], [
        ["del", "delete one pass instance", "remove one licm"],
        ["dup", "run a pass instance twice", "repeat instcombine"],
        ["swap", "swap a pass with its neighbour", "reorder two function passes"],
        ["ins", "insert a pass at a valid position", "add dfa-jump-threading after jump-threading"],
        ["param", "change one option of one pass instance", "simplifycfg switch-range-to-icmp"],
        ["param_all", "change an option on every instance of a pass", "every simplifycfg: sink-common-insts off"],
        ["del_all", "delete every instance of a pass", "remove every simplifycfg"],
        ["knob", "global optimizer flag", "-force-vector-width=4, -unroll-max-count=2, -inline-threshold=1000"],
        ["llc flag", "code-generator flag", "-tail-dup-size=6, -align-loops=32"],
        ["backend", "code-generator optimization level", "llc -O2 instead of -O3"],
        ["raw seed", "a whole standard pipeline in place of -O3's", "default&lt;O2&gt;, default&lt;O0&gt; + llc -O3"]], "small"))
    A.append(sec("4.5", "Database Design"))
    A.append(P(
        "All results are stored in SQLite so that every table and figure in this report can be regenerated by a script. Figure 4.3 shows the "
        "main tables of <code>results/dataset.sqlite</code>. At the end of the project it held "
        "70,409 candidates, 19,534 measurements, 615 search runs, 584 feature records, 10,726 knowledge-base pass effects and 858 evaluation results."))
    A.append(fig(er_svg(), "Main tables of results/dataset.sqlite"))
    A.append(sec("4.6", "Design of the Tune Mode"))
    A.append(P(
        "Tune is the final deployed mode (Figure 4.4). The models only shortlist candidates; measurement decides. The confirmation step is a "
        "separate, fresh measurement of the selected candidate. Picking the fastest of eight noisy measurements systematically overstates "
        "its speedup (the winner's curse), so the selection run is never used to decide on shipping."))
    A.append(fig(flow_svg([
        ("Input program", "C/C++ source, arguments, stdin"),
        ("Reference build at -O0", "run once, hash the output (oracle)"),
        ("Features", "static IR features + quick scan of -O0…-O3/-Os"),
        ("RL proposes", "PPO policy generates 24 pipelines"),
        ("SL ranks", "LightGBM scores 24 + ~913 library pipelines"),
        ("Compile and verify", "in ranked order until 8 distinct correct binaries"),
        ("Selection timing", "8 candidates + -O3, 10 interleaved rounds"),
        ("Confirmed faster?", "fresh 20 rounds + A/A, CI lower bound > 1.01"),
        ("Ship the candidate", "binary + JSON report")], COL["lib"], (7, "yes", "ship -O3")),
        "Flowchart of the tune mode (RL + SL)"))
    A.append(sec("4.7", "Design of the Predict Mode"))
    A.append(P(
        "Predict must choose without running the program, so it uses only compile-time information: the static IR features and the counts "
        "of LLVM optimization remarks emitted by -O3 (which loops were vectorized, unrolled or not, and why; inlining decisions). It scores a "
        "<i>safe pool</i> of candidates with an ensemble and a harm classifier and recommends a pipeline only if a conservative safety gate "
        "passes (Figure 4.5). After the choice, it compiles and times its top pick for reporting."))
    A.append(fig(flow_svg([
        ("Input program", "source, arguments, stdin"),
        ("Build -O3 and collect remarks", "static (111) + remark (36) features"),
        ("Score the safe pool", "164 single edits + 776 pairs + own PPO proposals"),
        ("Ensemble + harm classifier", "7 LightGBM regressors, P(harmful)"),
        ("Gate passes?", "mean − 1.28·std > 1.03, ≥ 80% agree, P(harm) ≤ 0.5"),
        ("Recommend pipeline", "advisory: -O3 binary unless --apply"),
        ("Measure the top pick", "check output, 20 rounds + A/A vs -O3")], COL["pred"], (4, "yes", "keep -O3")),
        "Flowchart of the predict mode"))
    A.append(sec("4.8", "Design of the Timing Harness"))
    A.append(P(
        "Figure 4.6 shows how one comparison is measured. All binaries of a comparison, including -O3 and its byte-identical A/A copy, run in "
        "a freshly shuffled order in every round, on one pinned vCPU whose SMT sibling is kept idle. The speedup is the median of the per-round "
        "ratios base/candidate, and its 95% confidence interval comes from a bootstrap over rounds."))
    A.append(fig(interleave_svg(), "Interleaved, paired timing with an A/A control"))
    A.append(sec("4.9", "Design of the Dashboard"))
    A.append(P(
        "The dashboard is a local web application served by FastAPI on 127.0.0.1:8000. A single-worker job queue guarantees that two timing "
        "jobs never overlap. Each job runs the same CLI as a subprocess; its output is streamed to the browser with server-sent events. The "
        "front end has three pages: <b>Run</b> (choose a mode, give a program, watch the terminal, read the result), <b>Research &amp; "
        "results</b> (all phases and test results, generated from one JSON file exported from the result files) and <b>Architecture</b> "
        "(clickable system diagram and the tune and predict flows). Fonts and libraries are vendored so the dashboard runs offline, and "
        "a Windows launcher starts WSL, the server and the browser with one double-click."))

    # ================= 5 IMPLEMENTATION
    A.append(chapter("Implementation"))
    A.append(P(
        "The project was implemented in nine phases, each with a defined deliverable and, where applicable, a gate. This chapter describes "
        "each phase in the order in which it was built."))
    A.append(sec("5.1", "Toolchain and Build Process"))
    A.append(P(
        "Every candidate is built in four steps (below). The starting IR is produced by clang with LLVM passes disabled rather than at -O0, "
        "so that it keeps the metadata (TBAA, function attributes) that a real -O3 build sees; otherwise every candidate would start from "
        "weaker IR than -O3. Multi-file programs are compiled per file and linked into one module with <code>llvm-link</code>. Binaries are "
        "cached by the hash of the optimized IR, so identical IR is never compiled or timed twice. The -O3 inliner settings are passed "
        "explicitly so that the printed -O3 pipeline reproduces <code>default&lt;O3&gt;</code>; all speedups are measured against the real "
        "<code>default&lt;O3&gt;</code> binary."))
    A.append(code("""
clang -O3 -march=native -Xclang -disable-llvm-passes -emit-llvm  ->  start IR (TBAA and attributes, no passes)
opt -passes=<edited pipeline> [knobs]                             ->  optimized IR
llc -O3 [backend flags] -relocation-model=pic                     ->  object file
clang object -lm                                                  ->  binary"""))
    A.append(P("The genome is applied by <code>materialize()</code> in <code>nc/pipeline.py</code>:"))
    A.append(code('''
@dataclass
class Genome:
    edits: list[dict] = field(default_factory=list)
    raw: str | None = None                      # level seeds: a literal pipeline string

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
        ...'''))
    A.append(sec("5.2", "Phase 1: Measurement Harness"))
    A.append(P(
        "Nothing downstream can be trusted unless timing is trustworthy, so the harness was built first and given its own pass/fail self-test. "
        "Its components are:"))
    A.append(UL(
        "<b>Pinning and isolation:</b> benchmark processes run on one vCPU; the harness and compilations run elsewhere. ASLR is disabled for "
        "benchmark children and a 3 s busy warm-up lets the clock frequency settle.",
        "<b>Interleaving:</b> -O3 and the candidates run in randomized round-robin order (30 rounds plus 5 warm-up rounds for confirmation).",
        "<b>Paired statistics:</b> speedup = median of per-round ratios; 95% CI by bootstrap with 4,000 resamples; a win requires the lower bound above 1.",
        "<b>A/A control:</b> a byte-identical copy of the -O3 binary at a different path is timed in the same run; if it deviates from 1.0 by "
        "more than 1% the measurement is repeated once and flagged.",
        "<b>Correctness oracle:</b> every candidate's output hash must equal the -O0 output hash.",
        "<b>Quiet guard:</b> before each timing block the harness waits (up to 30 min) while processes of other sessions use more than 0.6 cores.",
        "<b>Screening versus confirmation:</b> search uses cheap screening (1 round, 2 more only if ≥ 0.98×, runs slower than 1.3× -O3 are "
        "killed); shortlists are confirmed together in one 30-round run; the winner is minimized (useless edits removed) and validated in a "
        "fresh, independent run."))
    A.append(P("The paired speedup and its confidence interval are computed as follows (<code>nc/timing.py</code>):"))
    A.append(code('''
def paired_speedup(base_ms, new_ms, n_boot: int = 4000, seed: int = 0) -> dict:
    """Speedup of `new` over `base` (>1 means new is faster), from per-round paired ratios."""
    a, b = np.asarray(base_ms, float), np.asarray(new_ms, float)
    m = ~(np.isnan(a) | np.isnan(b))
    a, b = a[m], b[m]
    if len(a) < 3:
        return {"n": int(len(a))}
    r = np.log(a / b)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(r), (n_boot, len(r)))
    boots = np.median(r[idx], axis=1)
    lo, hi = np.quantile(boots, [0.025, 0.975])
    return {"n": int(len(r)), "speedup": float(np.exp(np.median(r))),
            "ci_lo": float(np.exp(lo)), "ci_hi": float(np.exp(hi)),
            "significant": bool(lo > 0 or hi < 0)}'''))
    A.append(P(
        "Timing several programs in parallel was evaluated with multi-core A/A tests. Three workers on vCPUs 2, 6 and 10 (siblings idle), with "
        "at most one memory-heavy program at a time (simulated L2 misses ≥ 20 per 1,000 instructions), kept bias ≤ 0.46% with noise close to "
        "serial; five workers multiplied the noise by 5–40×, so they were not used. Every number reported in Chapter 7 is in any case a serial "
        "re-measurement on one core."))
    A.append(sec("5.3", "Phase 2: Corpus Construction"))
    rej = sum(r[1] for r in c["rejections"])
    A.append(P(
        f"Programs were taken from PolyBench/C 4.2.1 [17] (kernels with continuously scalable problem sizes) and the LLVM test-suite [18] "
        f"SingleSource (C and C++ programs scaled through argv[1]) and MultiSource (multi-file benchmarks and applications, built through a "
        f"small CMake interpreter written for this project, with inputs in per-program run directories). {c['scanned']} candidate programs "
        f"were scanned and {rej} rejected, leaving <b>{c['usable']} usable programs in {c['families']} families</b>.",
        "A program is kept only if it builds at -O0, -O1, -O2, -O3 and -Os, produces identical output at every level, is deterministic, needs "
        "under 3 GB of memory and runs 0.35–3 s at -O3. A <i>family</i> groups programs that share code, for example all PolyBench linear-algebra "
        "kernels; families are kept together when splitting, so test programs come from families never seen in training."))
    A.append(fig(R.hbar([{"label": r[0], "value": r[1], "color": COL["bad"]} for r in c["rejections"]], title="rejection reasons (programs)",
                        fmt=lambda v: f"{v:.0f}", vmin=0), "Reasons for rejecting candidate programs"))
    A.append(tab("Frozen family split (seed 0, before any modelling)", ["Split", "Programs", "Families"],
                 [[k, c["split"]["counts"][k], f"{len(c['split']['groups'][k])}: " + E(", ".join(c["split"]["groups"][k]))] for k in ("train", "val", "test")], "small"))
    A.append(P("Rule: a family enters the test or validation split only if it fits the remaining budget (TSVC, with 33 programs, therefore falls to "
               "training). The split file refuses to be overwritten."))
    A.append(sec("5.4", "Phase 3: Search and the Headroom Gate"))
    A.append(P(
        "Each program was searched with standard-level seeds, random search, and genetic/evolutionary search on action space v1 (<code>evo</code>) "
        "and v2 (<code>evo2</code>), with a budget of 25 unique timed binaries per method, followed by merged confirmation, minimization and "
        "independent validation. The evolutionary search keeps a population of genomes, creates children by mutation (adding, removing or "
        "changing an edit) and crossover of edit lists, screens them cheaply and keeps the fastest. The gate required, on validated numbers, "
        "at least 30% of a fresh sample of programs to reach +5%. Its outcome is reported in Section 7.1."))
    A.append(sec("5.5", "Phase 4: Pass Knowledge Base"))
    A.append(P(
        f"To learn which edits matter, {kb['edits']} single edits around -O3 were tried on {kb['programs']} training programs with a confirmed "
        f"gain: leave-one-out deletion of every pass, option flips, family-wide edits, add-one insertions and knob settings "
        f"({', '.join(f'{k}: {v}' for k, v in kb['by_kind'].items())}). Each edit's effect was screened and, where promising, confirmed. The "
        "knowledge base produced the pruned macro-action set of the RL agent and the safe edit pool of predict."))
    A.append(sec("5.6", "Phase 5: Data Collection with the Wider Search"))
    A.append(P(
        "The training data for the models came from evo and evo2 with the full v2 action space and a budget of 50 each, on the 116 programs never "
        "searched before; every winner was re-validated serially. This also served as an out-of-sample re-measurement of headroom. Winners "
        "≥ 1.5× were re-checked with cachegrind instruction counts to detect compile-time evaluation artifacts. The data-quality check counts "
        "programs with a noisy accepted A/A control: 15 of 146 (10.3%), marginally above the 10% limit; as decided before modelling, those "
        "programs' labels are weighted 0.3 and all labels are capped at |log 3|."))
    A.append(sec("5.7", "Phase 6: Feature Extraction"))
    A.append(tab("Feature sets", ["Set", "Count", "Contents", "Needs running?"], [
        ["static", fs["static"], "55 IR statistics (30 instruction-type counts, 19 ratios, size and shape, loop counts and depth) of the canonicalized and of the -O3 IR, plus the -O3/canonical size ratio", "no"],
        ["scan", fs["scan"], "runtime at -O0/-O1/-O2/-O3/-Os, level spread, -O0/-O3 ratio, binary size, distinct level binaries", "yes (quick scan)"],
        ["sim", fs["sim"], "cachegrind: instructions, data references per instruction, L1/LL miss rates and MPKI, I-cache MPKI, branch and indirect-branch mispredict rates", "yes (simulated)"],
        ["sim_l2", fs["sim_l2"], "simulated 1 MB 8-way private L2: miss rate and MPKI (also used by the parallel scheduler)", "yes"],
        ["remarks", fs["remarks"], "counts of -O3 optimization remarks: vectorized / not vectorized and why, inlining, unrolling, LICM, GVN", "no (predict only)"],
        ["genome encoding", "≈ 98", "edits by pass family and stage, knob values, llc flags and level, raw level seeds", "no"]], "small"))
    A.append(P(
        "The canonical form is the IR after <code>sroa, early-cse, simplifycfg, instcombine</code>, which removes front-end noise; features of "
        "both canonical and -O3 IR describe what the program is and what -O3 does to it. Tune's surrogate uses static, scan and sim features; "
        "predict, which must not run the program, uses static and remark features only."))
    A.append(sec("5.8", "Phase 7: Supervised Surrogate (LightGBM)"))
    A.append(P(
        "The surrogate predicts the log-speedup over -O3 of a (program, pipeline) pair from the program features concatenated with the genome "
        "encoding. Two forms were trained: a LightGBM regressor and a LightGBM LambdaRank ranker, each with 300 trees, learning rate 0.05, 15 "
        "leaves and 0.8 subsampling. Training uses every validated, confirmed and screened measurement of the training families, weighted by "
        "stage reliability. Evaluation is leave-one-family-out cross-validation on the 24 development families: all programs of one family are "
        "held out, the model is trained on the rest, and it ranks the held-out programs' candidates.",
        "<b>Metrics:</b> <i>Spearman</i> is the rank correlation between predicted and true speedups of a held-out program's candidates (1 = "
        "perfect, 0 = random). <i>gain@k</i> is the best true speedup among the model's top-k candidates, averaged geometrically over programs, "
        "and is compared with k random candidates and with the best candidate in the library (oracle). LightGBM was chosen because the data "
        "set is small and tabular, with mixed counts, ratios and categorical edit encodings; boosted trees handle this without normalization, "
        "train in seconds (which makes leave-one-family-out CV affordable) and are robust with little tuning."))
    A.append(sec("5.9", "Phase 8: Reinforcement-Learning Agent (PPO)"))
    A.append(P(
        f"An episode builds a pipeline for one program, choosing one edit per step for a horizon of 4 steps, from {md['rl_tune_actions']} "
        "macro-actions taken from the knowledge base (knobs, llc flags, family-wide deletes and option flips). The state is the program's "
        "features plus the edits chosen so far; the reward at the end of the episode is the surrogate's predicted log-speedup of the finished "
        "pipeline. The policy and the value function are one-hidden-layer MLPs implemented in NumPy and trained with PPO (clip ε = 0.2, entropy "
        "bonus 0.01, 4 epochs per update, Adam with learning rate 3·10⁻³, GAE λ = 0.95) on the 113 training and validation programs, for 200 "
        "iterations of 64 episodes. The clipped PPO objective is",
        "<span class=\"eq\">L(θ) = E[min(r<sub>t</sub>(θ)·Â<sub>t</sub>, clip(r<sub>t</sub>(θ), 1−ε, 1+ε)·Â<sub>t</sub>)],&nbsp;&nbsp; "
        "r<sub>t</sub>(θ) = π<sub>θ</sub>(a<sub>t</sub>|s<sub>t</sub>) / π<sub>θ,old</sub>(a<sub>t</sub>|s<sub>t</sub>)</span>",
        "PPO was chosen because the action space is discrete and small, the clipped update is stable without delicate tuning, and a NumPy "
        "implementation of a few hundred lines avoids a deep-learning dependency. Because the reward is the surrogate's prediction, the agent can "
        "only be as good as the surrogate; this is why its measured contribution (Section 7.5) is small."))
    A.append(fig(R.lines([("mean reward (moving average of 10)", [sum(md["rl_tune_history"][max(0, i - 9):i + 1]) / len(md["rl_tune_history"][max(0, i - 9):i + 1]) for i in range(len(md["rl_tune_history"]))], COL["rl"])],
                         list(range(1, len(md["rl_tune_history"]) + 1)), title="PPO learning curve (reward = surrogate's predicted log speedup)", yfmt=lambda v: f"{v:+.3f}"),
                 "PPO training curve"))
    A.append(sec("5.10", "Deployment: Tune Mode (RL + SL)"))
    A.append(P(
        "Tune is invoked as <code>bin/neurocompiler tune prog.c --args … --out prog</code>. It implements Figure 4.4: reference run, features, "
        "24 RL proposals pooled with about 913 library pipelines (winners from training programs plus random pipelines), ranking by the "
        "surrogate, compilation in ranked order in parallel until 8 distinct binaries with correct output exist, selection timing of 10 "
        "interleaved rounds, and a fresh 20-round confirmation with an A/A control. The pick ships only if the CI lower bound exceeds 1.01 and the "
        "control is clean. The output is the binary and a JSON report with the shipped pipeline and edits, its origin (RL agent or library), the "
        "-O3 pipeline, every timed candidate with runtime in ms, speedup and CI, code size, and the model's top-10 ranking.",
        "Tune loads its models only through <code>results/models/tune/MANIFEST.json</code>, which stores SHA-256 hashes, and refuses to run if a "
        "file changed. <code>scripts/tune_regression_check.py</code> verifies that tune's top-8 order is identical before and after every code "
        "change. <code>--no-rl</code> gives the SL-only variant."))
    A.append(sec("5.11", "Predict Mode"))
    pc = md["predict_cv"]
    A.append(P(
        f"Predict has its own models in <code>results/models/predict/</code> and never reads tune's. Its candidate pool contains "
        f"{md['predict_pool']['singles']} knowledge-base single edits that never appeared in a wrong-output candidate and are harmful on at most 10% "
        f"of the programs they change, plus {md['predict_pool']['pairs']} pairs of the top 40 ({md['predict_pool']['wrong_output_edits_excluded']} "
        "edits excluded for wrong output), plus proposals of its own PPO policy. Seven bootstrap LightGBM regressors predict the speedup and a "
        "LightGBM classifier predicts the probability that a candidate is harmful. The gate ships only if the pessimistic estimate (mean − 1.28 × "
        f"standard deviation across members) exceeds 1 + margin, at least 80% of members agree, and the harm probability is at most τ. The thresholds "
        f"(margin {md['predict_thresholds']['margin']}, τ {md['predict_thresholds']['tau']}) were chosen only on leave-one-family-out out-of-fold "
        f"predictions of training and validation families. The criteria for success were recorded before building and not changed afterwards.",
        "On request, predict now also compiles its top-ranked sequence, checks its output against -O0 and times it against -O3 (20 rounds with "
        "an A/A control), reporting both runtimes in ms and the measured versus predicted speedup. This is reporting only: the choice, the gate "
        "and the advisory rule are unchanged."))
    A.append(sec("5.12", "Command-Line Interface and Dashboard"))
    A.append(code('''
bin/neurocompiler tune    prog.c --args "..." --out prog   # default mode (RL + SL); --no-rl, --dynamic
bin/neurocompiler predict prog.c --args "..." --out prog   # choose without running, then time the top pick
bin/neurocompiler compare prog.c --args "..."              # -O3, -O2, -Os, predict, tune, random@8, GA@8 + A/A'''))
    A.append(P(
        "Research commands are available through <code>python -m nc.cli</code> (env, o3pipeline, baselines, selftest, cpusweep, aatest, corpus, "
        "search, passkb, collect, features, model, rl, evaluate, predict-train/eval/time, tune-freeze). The dashboard server "
        "(<code>dashboard/server.py</code>) exposes REST endpoints for jobs, saved runs, examples, the environment check and the -O3 pass tree, "
        "plus an SSE stream per job; job files are kept in <code>work/dashboard/jobs/&lt;id&gt;/</code>. The front end is written in vanilla "
        "JavaScript modules with Chart.js for charts and CodeMirror for the code editor."))

    # ================= 6 TESTING
    A.append(chapter("Testing"))
    A.append(sec("6.1", "Testing Strategy"))
    A.append(P(
        "Testing in this project has two goals: that the software works, and, more importantly, that the measurements it produces are correct "
        "and unbiased. Accordingly, testing covers (i) harness self-tests with numeric pass criteria, (ii) A/A tests in which a program is "
        "compared with an identical copy of itself, (iii) correctness checks of every candidate against the -O0 output, (iv) artifact checks of "
        "suspiciously large wins, (v) regression checks of the frozen tune models, and (vi) end-to-end runs of each mode through the CLI and "
        "the dashboard."))
    A.append(sec("6.2", "Harness Self-Tests"))
    st = D["harness"]["selftest_v8"] + D["harness"]["selftest_v14"]
    A.append(tab("Harness self-test results", ["Run", "Verdict", "Median", "CI half-width", "Drift", "A/A", "-O0/-O3"],
                 [[E(s["file"].replace("selftest_", "").replace(".json", "")), s["verdict"], f"{s['median_ms']:.0f} ms", f"{s['ci_halfwidth_pct']:.2f}%",
                   f"{s['drift_pct']:.2f}%", xx(s["aa"]), f"{s['o0_vs_o3']:.2f}×"] for s in st], "small"))
    A.append(P(
        "Thresholds: CI half-width &lt; 1%, A/A bias &lt; 1%, drift &lt; 2%, -O0/-O3 gap ≥ 1.2×. The first self-test after the change to 14 vCPUs "
        "failed while other experiments were loading the machine and passed when re-run on a quiet machine; this failure led to the quiet guard. "
        "The minimum program runtime of 0.35 s was set from the self-test: a 220 ms program was too noisy, a 400 ms program passed."))
    A.append(sec("6.3", "A/A and Parallel-Timing Tests"))
    aa = D["harness"]["aatests"]
    A.append(fig(R.hbar([{"label": f"{len(a['cores'])} cores · {a['file'][7:22]}", "value": max(abs(p['parallel']['aa_bias_pct']) for p in a['programs']),
                          "color": COL["ok"] if a["pass"] else COL["bad"]} for a in aa], title="worst |A/A bias| (%) when timing on several cores at once (green = passed)",
                         fmt=lambda v: f"{v:.2f}%", vmin=0), "Multi-core A/A tests"))
    A.append(sec("6.4", "Test Cases"))
    A.append(tab("Selected test cases and results", ["ID", "Test", "Expected", "Observed", "Status"], [
        ["TC1", "Harness self-test on a quiet machine (bench/matmul.c)", "CI &lt; 1%, A/A &lt; 1%, drift &lt; 2%", "CI ±0.12%, A/A within 1%", "Pass"],
        ["TC2", "Self-test under foreign load", "detected as unreliable", "verdict FAIL (CI 1.58%, drift −6.0%)", "Pass (detected)"],
        ["TC3", "3-core parallel A/A test", "bias ≤ 0.5%", "bias ≤ 0.46%", "Pass"],
        ["TC4", "5-core parallel A/A test", "noise close to serial", "noise 5–40× larger", "Fail → not used"],
        ["TC5", "Candidate with different output (predict ungated picks on deriche, doitgen)", "rejected by the oracle", "detected as wrong output", "Pass"],
        ["TC6", "Win of 1.5× or more with suspicious instruction count (mandel-text)", "flagged as artifact", "217× fewer instructions; excluded", "Pass"],
        ["TC7", "Candidate identical to -O3", "skipped, not timed", "skipped by binary hash", "Pass"],
        ["TC8", "Selection winner that does not hold up (branchy demo: 1.044× in selection)", "-O3 shipped", "confirmation 1.015×, -O3 shipped", "Pass"],
        ["TC9", "Tune top-8 order after code changes", "IDENTICAL", "IDENTICAL", "Pass"],
        ["TC10", "Tune end-to-end on the interpreter example", "confirmed speedup or -O3", "3.830× confirmed, RL pick", "Pass"],
        ["TC11", "Predict end-to-end on matrix multiply", "gate decision + measured pick", "gate kept -O3; pick measured 0.990×", "Pass"],
        ["TC12", "Compare end-to-end on matrix multiply", "all methods + A/A in one run", "A/A 1.000×, tune 1.657×", "Pass"],
        ["TC13", "Reproducibility of the test evaluation (re-run on another day)", "same result within CI", "+7.92% vs +7.51%", "Pass"],
        ["TC14", "Dashboard: two jobs submitted together", "run one after another", "queued, single worker", "Pass"]], "small"))
    A.append(sec("6.5", "Validation of Results"))
    A.append(P(
        "Screening results overstate gains, so only confirmed numbers (30 rounds with an A/A control) count, and gates use validated numbers, "
        "that is, a fresh independent measurement of the winner. All final test-set results are serial re-measurements in which the shipped "
        "binary of every method is timed in the same runs as -O3 with an A/A control. The parallel and serial validations of Phase 5 differed "
        "by a median of −0.15%."))

    # ================= 7 RESULTS
    A.append(chapter("Results and Discussion"))
    A.append(sec("7.1", "Headroom over -O3 (Phase 3 Gate)"))
    g = G3["fresh_summary"]
    allg = sorted([dict(p, s="fresh") for p in G3["fresh"]] + [dict(p, s="original") for p in G3["original"]], key=lambda p: -p["speedup"])
    A.append(fig(R.vbars([p["speedup"] for p in allg], [COL["acc2"] if p["s"] == "fresh" else COL["acc"] for p in allg],
                         title="best validated speedup per program (cyan = fresh sample, purple = original; dashed = +5%)",
                         log=True, ref=1.05, vmin=0.98, labels=[p["id"].split("/")[-1] for p in allg]), "Best validated speedup per program in the headroom study"))
    A.append(tab("Headroom gate results", ["Sample", "n", "Geomean (95% CI)", "Excl. largest", "Median", "≥ +5%"], [
        ["fresh (decisive)", g["n"], f"{pct(g['geomean'])} ({ci(g['ci'], 2)})", pct(g["excl_largest"]), pct(g["median"]), f"{g['ge5']}/{g['n']}"],
        ["original", G3["original_summary"]["n"], f"{pct(G3['original_summary']['geomean'])} ({ci(G3['original_summary']['ci'], 2)})",
         pct(G3["original_summary"]["excl_largest"]), pct(G3["original_summary"]["median"]), f"{G3['original_summary']['ge5']}/{G3['original_summary']['n']}"]]))
    A.append(P(
        "<b>The gate was not met</b> on the decisive fresh sample: 4 of 15 programs (26.7%) reached +5%, below the required 30%. The pooled 30 "
        "programs pass at exactly 30.0% only by counting polybench/jacobi-1d, whose A/A control was noisy, so the pooled pass was not used. "
        "The decision taken was to continue with the target lowered to the <i>good</i> tier (+2–4%) and to use the Phase 5 wider search on "
        "never-searched programs as an out-of-sample re-measurement of headroom; later gates stayed strict."))
    A.append(sec("7.2", "Wider Search (Phase 5)"))
    vals = sorted([v for v in H5["values"] if not v["suspect"]], key=lambda v: -v["speedup"])
    sa, sf = H5["summary_all"], H5["summary_family"]
    A.append(fig(R.vbars([v["speedup"] for v in vals], [("#94a3b8" if v["source"] == "no winner" else COL["ok"] if v["speedup"] >= 1.05 else COL["acc2"]) for v in vals],
                         title="best validated speedup per program, sorted (grey = no winner, -O3 kept; dashed = +5%)", log=True, ref=1.05, vmin=0.98, height=200),
                 "Headroom found by the wider search on programs never searched before"))
    A.append(tab("Phase 5 summary (excluding the compile-time evaluation artifact)", ["View", "n", "Geomean (95% CI)", "Excl. largest", "Median", "≥ +5%", "No gain"], [
        ["all programs", sa["n"], f"{pct(sa['geomean'], 1)} ({ci(sa['ci'])})", pct(sa["excl_largest"], 1), pct(sa["median"], 1), f"{sa['ge5']}/{sa['n']}", sa["no_gain"]],
        ["one value per family", sf["n"], f"{pct(sf['geomean'], 1)} ({ci(sf['ci'])})", pct(sf["excl_largest"], 1), pct(sf["median"], 1), f"{sf['ge5']}/{sf['n']}", sf["no_gain"]]], "small"))
    A.append(P(
        f"With a larger budget and the full v2 edit space, search finds substantial headroom out of sample: {pct(sa['geomean'], 1)} geomean, and "
        f"{sa['ge5']} of {sa['n']} programs at least 5% faster. The gain is uneven: {sa['no_gain']} programs have no measurable gain at all, "
        "which is why the deployed system must be able to keep -O3. One program (ss/Misc-C++/mandel-text) was excluded because the compiler had "
        "computed its answer at compile time (217× fewer instructions with identical output)."))
    A.append(sec("7.3", "Pass Knowledge Base Findings"))
    A.append(tab("Most informative single edits (knowledge base)", ["Edit", "Kind", "Programs", "Confirmed faster", "Confirmed slower", "Identical binary", "Screening range"],
                 [[f"<code>{E(r['label'])}</code>", r["kind"], r["programs"], r["faster"], r["slower"], r["noop"], f"{r['min']:.2f}–{r['max']:.2f}×"] for r in kb["top"][:12]], "small"))
    A.append(P(
        "The strongest levers are the loop cost-model overrides, in both directions: <code>-force-vector-width=8</code> was confirmed faster on 5 "
        "programs and slower on none, while <code>-unroll-count=2</code> was faster on 4 and slower on 6. Most single edits do nothing on a given "
        "program, and every edit hurts some program, so no single global change beats -O3: selection has to be per program. The project also "
        "found the cause of the largest win, on the <i>evalloop</i> interpreter: -O3's SimplifyCFG option <i>sink-common-insts</i> merges the "
        "interpreter's 31 indirect dispatch jumps into one, which destroys branch prediction; turning the option off restores them and makes the "
        "program up to 3.7× faster."))
    A.append(sec("7.4", "Accuracy of the Surrogate Model"))
    tc = md["tune_cv"]["summary"]
    ks = [1, 3, 5, 10]
    A.append(fig(R.lines([("regressor (used by tune)", [tc["gbr"][f"gain@{k}"] for k in ks], COL["lib"]),
                          ("ranker", [tc["rank"][f"gain@{k}"] for k in ks], COL["acc"]),
                          ("random", [tc["gbr"][f"rand_gain@{k}"] for k in ks], COL["o3"]),
                          ("oracle", [tc["gbr"]["oracle"]] * 4, COL["ok"])], [f"top-{k}" for k in ks],
                         title="gain@k on held-out families", yfmt=lambda v: f"{v:.2f}×"), "Best true speedup among the model's top-k on held-out families"))
    A.append(tab("Leave-one-family-out cross-validation of the surrogate", ["Model", "Spearman (95% CI)", "gain@1", "gain@5", "Random gain@5", "Recall@5"],
                 [[m, f"{tc[m]['spearman']:+.3f} ({tc[m]['spearman_ci'][0]:+.2f}…{tc[m]['spearman_ci'][1]:+.2f})", xx(tc[m]["gain@1"]), xx(tc[m]["gain@5"]),
                   xx(tc[m]["rand_gain@5"]), f"{tc[m]['recall@5'] * 100:.1f}%"] for m in ("gbr", "rank", "transfer", "random")], "small"))
    A.append(P(
        "Gate 7B asked whether the surrogate ranks unseen families better than random. The first run, before the knowledge-base data was "
        "complete, did <b>not</b> meet it (regressor gain@5 1.097× below random 1.109×). The re-run after that data, in the plan's order, met it "
        "narrowly: Spearman +0.111 (+0.06…+0.15), gain@5 1.107× against 1.091× for random. Both results are reported; because the pass is narrow "
        "and came after the first result, the RL work that followed is labelled exploratory. Offline the model ranks only slightly better than "
        "chance, yet in deployment it beats a random shortlist from the same library by +5.8%: a shortlist of eight only needs the good "
        "pipelines to be somewhere near the top."))
    A.append(sec("7.5", "Evaluation on the Frozen Test Set"))
    order = sorted(S.items(), key=lambda kv: -kv[1]["geomean"])
    colmap = {"tune RL + SL": COL["rl"], "tune top-8 (SL)": COL["lib"], "predict (gated)": COL["pred"], "predict ungated": "#a78bfa", "GA@8": COL["ga"],
              "RL only": "#f472b6", "random search@8": "#9ca3af", "random top-8": "#94a3b8", "ML-only top-1": "#818cf8", "no dynamic features": "#93c5fd"}
    A.append(P(
        "The 33 test programs from 11 families were never used for training, model selection or threshold tuning, and were evaluated once. "
        "Every method's shipped binary was re-measured serially in the same runs as -O3 with an A/A control. Top-8, random search@8 and GA@8 "
        "each time eight binaries (equal budget)."))
    A.append(fig(R.hbar([{"label": k, "value": v["geomean"], "ci": v["ci"], "color": colmap.get(k, COL["o3"])} for k, v in order],
                        title="geomean speedup vs -O3 with 95% CI (33 test programs)", ref=1.0, fmt=lambda v: xx(v)), "Geomean speedup of every method on the test set"))
    A.append(tab("Test-set results of all methods", ["Method", "Geomean", "95% CI", "Excl. largest", "≥ +5%", "Measurably slower"],
                 [[E(k), pct(v["geomean"]), ci(v["ci"]), pct(v["excl_largest"]), v["ge5"], v["slower"]] for k, v in order], "small"))
    A.append(P(
        f"The final system, <b>tune (RL + SL)</b>, is {pct(t['geomean'])} faster than -O3 (CI {ci(t['ci'])}), {pct(t['excl_largest'])} excluding the "
        f"largest result (polybench/durbin, 2.84×), with {t['ge5']} of 33 programs at least 5% faster and none measurably slower. SL alone (top-8) "
        f"reached {pct(t8['geomean'])} with one regression (lencod 0.979×), which motivated the confirmation step. Top-8 beats a random top-8 from the "
        "same library by +5.8% (CI +1.0…+13.9) and the GA at equal budget by +5.3% (+0.3…+13.4); against random search@8 the difference (+2.1%) is "
        "not significant. Timing is essential: trusting the model's single best guess without timing (ML-only top-1) gives +2.4% but makes 16 of "
        "33 programs slower.",
        "RL on its own reaches +3.35%; pooled with the library it adds +0.2% over SL (CI −0.2…+0.7), which is not significant, and an RL proposal "
        "was the shipped pipeline on 1 of 33 test programs. By the plan's rule RL was not adopted as a result; it is included in the final version "
        "by decision of the team for the presentation, and its measured effect is stated here."))
    A.append(tab("Result against the success tiers", ["Tier", "Outcome"], [
        ["Minimum (no regressions)", "met by tune RL + SL (0 measurably slower); missed by one program in the first SL-only run"],
        ["Good (+2–4%, CI excludes 0, ≥ 20–30% at +5%)", f"met: {pct(t['excl_largest'])} excluding the largest result, CI excludes 0, {t['ge5']}/33 = {t['ge5'] / 33 * 100:.0f}% at +5%"],
        ["Strong (≥ +5%)", "only with the largest result included"]]))
    A.append(sec("7.6", "Predict Mode Results"))
    A.append(tab("Predict on the test set (evaluated once)", ["Variant", "Geomean (95% CI)", "Excl. largest", "Measurably slower", "Programs changed"], [
        ["predict (RL + SL, gated)", "+0.64% (−0.16…+2.05)", "+0.02%", "1 (lencod 0.971×)", "5"],
        ["predict_sl (SL only, gated)", "+0.64% (−0.14…+1.97)", "+0.03%", "1", "5"],
        ["predict ungated", "−0.69% (−3.02…+1.44)", "−1.34%", "8 (+2 wrong-output picks)", "24"]], "small"))
    A.append(P(
        "Predict's added time over a plain -O3 build was a median of +0.62 s (maximum +17.8 s). Against its pre-registered criteria the gain was "
        "<b>not met</b>, regressions and time were met; predict therefore ships as <b>advisory</b> and writes the -O3 binary unless "
        f"<code>--apply</code> is given. The ensemble ranks candidates with Spearman {md['predict_train_vs_heldout']['train'][0]:.2f} on its training "
        f"programs but only {md['predict_train_vs_heldout']['heldout'][0]:.2f} on held-out families: the effect of a pass edit depends on trip counts, "
        "data sizes and cache behaviour, which a compile-time view does not contain. Without the gate predict is slower than -O3 on average and "
        "chose two pipelines with wrong output, which shows why the gate and the output check matter."))
    A.append(sec("7.7", "IR Instruction Count Is Not Runtime"))
    A.append(fig(R.scatter(D["ir"]["sample"], title=f"IR instructions vs measured speedup ({len(D['ir']['sample']):,} of {D['ir']['n']:,} candidates, ρ = {D['ir']['rho']:.3f})",
                           xlab="IR instruction count relative to -O3", ylab="measured speedup vs -O3"), "IR instruction count versus measured speedup"))
    A.append(P(
        f"Candidates with more than 1% fewer IR instructions than -O3 were faster only {D['ir']['fewer_ir_faster_pct']:.0f}% of the time. This result "
        "justifies the central design choice of the project: decisions are made from timed runs, never from IR count."))
    A.append(sec("7.8", "Demonstration Runs"))
    A.append(tab("Runs through the dashboard (measured on the project machine)", ["Program", "Mode", "-O3 runtime", "Pick runtime", "Measured speedup", "Note"], [
        ["interpreter loop (evalloop)", "tune", "848.4 ms", "221.9 ms", "3.830×", "RL proposal shipped"],
        ["matrix multiply", "tune", "423 ms", "254 ms", "1.656×", "library pipeline"],
        ["recursive Fibonacci", "tune", "–", "–", "1.141×", "confirmed"],
        ["branchy code", "tune", "–", "–", "-O3 kept", "selection 1.044×, confirmation 1.015×"],
        ["Fibonacci", "predict", "956.1 ms", "777.6 ms", "1.230× (predicted 1.168×)", "recommended"],
        ["interpreter loop", "predict", "–", "–", "3.818× (predicted 1.583×)", "recommended"],
        ["matrix multiply", "predict", "–", "–", "0.990×", "gate kept -O3 (correctly)"],
        ["matrix multiply", "compare", "–", "–", "tune 1.657×, random@8 1.653×, GA -O3, A/A 1.000×", "one interleaved run"]], "small"))
    A.append(sec("7.9", "Snapshots of the Dashboard"))
    A.append(img("assets/shots/run.jpg", "Run page: mode selection, program editor, environment check and job queue"))
    A.append(img("assets/shots/tune_summary.jpg", "Tune result for the interpreter loop: verdict, runtimes in ms, edits explained, candidate chart"))
    A.append(img("assets/shots/tune_diff.jpg", "Selected sequence compared with the -O3 sequence, pass by pass"))
    A.append(img("assets/shots/tune_cands.jpg", "Every timed candidate with median runtime, speedup and 95% CI, and the model ranking"))
    A.append(img("assets/shots/predict_measured.jpg", "Predict result with the measured top pick, safety gate and recommended edits"))
    A.append(img("assets/shots/compare.jpg", "Compare mode: all methods timed in one interleaved run with an A/A control"))
    A.append(img("assets/shots/research_overview.jpg", "Research & results page: overview, gates and corpus"))
    A.append(img("assets/shots/research_test.jpg", "Research & results page: held-out test results"))
    A.append(img("assets/shots/arch.jpg", "Architecture page: clickable system diagram and the tune and predict flows"))
    A.append(sec("7.10", "Discussion"))
    A.append(P(
        "Three observations summarize the results. First, there is real headroom over -O3, but it is concentrated: a few programs gain a lot "
        "(interpreters, some linear-algebra kernels), many gain nothing. Second, models trained on a few thousand measurements predict the effect "
        "of compiler edits on unseen program families only weakly (Spearman ≈ 0.1), whether supervised or reinforcement-learned; but a weak "
        "ranking is enough to shortlist eight candidates, and measurement turns that weak signal into a reliable +8% without regressions. Third, "
        "methodological safeguards were decisive: the A/A control, the output oracle, the artifact check and the confirmation step each caught "
        "real errors that would otherwise have been reported as gains."))
    A.append(tab("Limitations", ["Limitation", "Effect"], [
        ["One machine (Zen 4, AVX-512) under WSL2", "gains may differ on other hardware"],
        ["33 test programs in 11 families", "wide confidence intervals; one program moves the geomean from +4.9% to +8.1%"],
        ["Phase 3 headroom gate missed", "project continued under a documented re-scope to the good tier"],
        ["Data quality marginally over the noisy-control limit", "mitigated by down-weighting those labels"],
        ["Gate 7B narrow; RL exploratory", "RL adds +0.2% (n.s.)"],
        ["Predict missed its gain criterion", "shipped as advisory"],
        ["Correctness checked on one input", "evidence, not proof; gains are specific to the given workload"],
        ["Tune cost", "tens of compiles and minutes of timing per program"]], "small"))

    # ================= 8 CONCLUSION
    A.append(chapter("Conclusion and Future Enhancements"))
    A.append(sec("8.1", "Conclusion"))
    A.append(P(
        "NeuroCompiler set out to improve measured runtime over clang -O3 on programs not used in training, and to report the result honestly. "
        "A statistically controlled harness, a family-split corpus of 146 programs and an extensive search established that headroom exists "
        f"({pct(p5['geomean'], 1)} out of sample with search). A LightGBM surrogate and a PPO agent trained on these measurements shortlist "
        f"candidate pipelines for a new program, and real timing with confirmation makes the decision. On 33 unseen test programs the final "
        f"system is {pct(t['geomean'])} faster than -O3 ({pct(t['excl_largest'])} excluding the largest result) with no program measurably slower, "
        "meeting the project's <i>good</i> tier and beating random and genetic baselines at equal budget.",
        "The project also produced negative results that are equally important: IR instruction count does not predict runtime; compile-only "
        "prediction is not yet reliable enough to replace measurement; reinforcement learning on a weak surrogate adds little. The deliverables "
        "are a command-line tool with tune, predict and compare modes, a web dashboard, frozen and hash-verified models, and a repository in "
        "which every number in this report can be reproduced from scripts and result files."))
    A.append(sec("8.2", "Future Enhancements"))
    A.append(UL(
        "<b>More data and more machines:</b> a larger corpus and measurements on other micro-architectures (Intel, ARM) would improve the models "
        "and show how machine-specific the gains are.",
        "<b>Hardware performance counters:</b> running on bare-metal Linux would replace simulated cache features with measured ones.",
        "<b>Richer program representations:</b> graph neural networks over the IR (as in ProGraML) may predict edit effects better than counts.",
        "<b>RL with measured rewards:</b> training the agent partly on real timings, or fine-tuning it per program online, instead of only on the surrogate.",
        "<b>Per-function and profile-guided tuning:</b> different pipelines for hot and cold functions, combined with PGO data.",
        "<b>Integration:</b> a build-system plugin (CMake) and caching of tuned pipelines per program version for continuous integration.",
        "<b>Multiple inputs:</b> verifying and timing on several inputs to make the correctness evidence and the gains more general."))

    # ================= REFERENCES
    A.append(unnumbered("References", "HREF"))
    refs = [
        "C. Lattner and V. Adve, “LLVM: A compilation framework for lifelong program analysis &amp; transformation,” in <i>Proc. CGO</i>, 2004, pp. 75–86.",
        "K. D. Cooper, P. J. Schielke and D. Subramanian, “Optimizing for reduced code space using genetic algorithms,” in <i>Proc. LCTES</i>, 1999, pp. 1–9.",
        "F. Agakov, E. Bonilla, J. Cavazos, B. Franke, G. Fursin, M. F. P. O'Boyle, J. Thomson, M. Toussaint and C. K. I. Williams, “Using machine learning to focus iterative optimization,” in <i>Proc. CGO</i>, 2006.",
        "G. Fursin et al., “Milepost GCC: Machine learning enabled self-tuning compiler,” <i>International Journal of Parallel Programming</i>, vol. 39, no. 3, pp. 296–327, 2011.",
        "S. Kulkarni and J. Cavazos, “Mitigating the compiler optimization phase-ordering problem using machine learning,” in <i>Proc. OOPSLA</i>, 2012.",
        "J. Ansel, S. Kamil, K. Veeramachaneni, J. Ragan-Kelley, J. Bosboom, U.-M. O'Reilly and S. Amarasinghe, “OpenTuner: An extensible framework for program autotuning,” in <i>Proc. PACT</i>, 2014.",
        "A. Haj-Ali, Q. Huang, J. Xiang, W. Moses, K. Asanović, J. Wawrzynek and I. Stoica, “AutoPhase: Juggling HLS phase orderings in random forests with deep reinforcement learning,” in <i>Proc. MLSys</i>, 2020.",
        "M. Trofin, Y. Qian, E. Brevdo, Z. Lin, K. Choromanski and D. Li, “MLGO: A machine learning guided compiler optimizations framework,” arXiv:2101.04808, 2021.",
        "C. Cummins, B. Wasti, J. Guo, B. Cui, J. Ansel, S. Gomez, S. Jain, J. Liu, O. Teytaud, B. Steiner, Y. Tian and H. Leather, “CompilerGym: Robust, performant compiler optimization environments for AI research,” in <i>Proc. CGO</i>, 2022.",
        "C. Cummins, Z. V. Fisches, T. Ben-Nun, T. Hoefler, M. F. P. O'Boyle and H. Leather, “ProGraML: A graph-based program representation for data flow analysis and compiler optimizations,” in <i>Proc. ICML</i>, 2021.",
        "A. Haj-Ali, N. K. Ahmed, T. Willke, Y. S. Shao, K. Asanović and I. Stoica, “NeuroVectorizer: End-to-end vectorization with deep reinforcement learning,” in <i>Proc. CGO</i>, 2020.",
        "G. Ke, Q. Meng, T. Finley, T. Wang, W. Chen, W. Ma, Q. Ye and T.-Y. Liu, “LightGBM: A highly efficient gradient boosting decision tree,” in <i>Advances in Neural Information Processing Systems (NeurIPS)</i>, 2017.",
        "J. Schulman, F. Wolski, P. Dhariwal, A. Radford and O. Klimov, “Proximal policy optimization algorithms,” arXiv:1707.06347, 2017.",
        "J. Schulman, P. Moritz, S. Levine, M. Jordan and P. Abbeel, “High-dimensional continuous control using generalized advantage estimation,” in <i>Proc. ICLR</i>, 2016.",
        "T. Mytkowicz, A. Diwan, M. Hauswirth and P. F. Sweeney, “Producing wrong data without doing anything obviously wrong!,” in <i>Proc. ASPLOS</i>, 2009.",
        "C. Curtsinger and E. D. Berger, “STABILIZER: Statistically sound performance evaluation,” in <i>Proc. ASPLOS</i>, 2013.",
        "L.-N. Pouchet, “PolyBench/C: The polyhedral benchmark suite,” version 4.2.1. [Online]. Available: https://github.com/MatthiasJReisinger/PolyBenchC-4.2.1",
        "LLVM Project, “LLVM test-suite guide.” [Online]. Available: https://llvm.org/docs/TestSuiteGuide.html",
        "N. Nethercote and J. Seward, “Valgrind: A framework for heavyweight dynamic binary instrumentation,” in <i>Proc. PLDI</i>, 2007.",
        "B. Efron and R. J. Tibshirani, <i>An Introduction to the Bootstrap</i>. New York: Chapman &amp; Hall, 1993.",
        "C. J. C. Burges, “From RankNet to LambdaRank to LambdaMART: An overview,” Microsoft Research, Tech. Rep. MSR-TR-2010-82, 2010.",
        "Z. Wang and M. O'Boyle, “Machine learning in compiler optimization,” <i>Proceedings of the IEEE</i>, vol. 106, no. 11, pp. 1879–1901, 2018.",
        "LLVM Project, “Using the new pass manager.” [Online]. Available: https://llvm.org/docs/NewPassManager.html",
        "D. P. Kingma and J. Ba, “Adam: A method for stochastic optimization,” in <i>Proc. ICLR</i>, 2015.",
        "S. Ramírez, “FastAPI.” [Online]. Available: https://fastapi.tiangolo.com",
    ]
    A.append('<ol class="refs">' + "".join(f"<li>{r}</li>" for r in refs) + "</ol>")

    # ================= APPENDIX
    A.append(unnumbered("Appendix A: Per-Program Test Results", "HAPPA"))
    ms_ = ["tune RL + SL", "tune top-8 (SL)", "RL only", "random search@8", "GA@8", "ML-only top-1", "predict (gated)"]
    progs = sorted(ev["programs"], key=lambda p: -(p.get("tune RL + SL") or 0))
    A.append(P("Speedup over -O3 of the shipped binary of each method on each of the 33 test programs (serial re-measurement; 1.000 = -O3 kept)."))
    A.append(tab("Per-program speedups on the frozen test set", ["Program", "Family"] + [E(m) for m in ms_],
                 [[E(p["id"].split("/")[-1]), E(p["family"].replace("polybench/", "pb/"))] + ["–" if p.get(m) is None else f"{p[m]:.3f}" for m in ms_] for p in progs], "tiny"))
    A.append(unnumbered("Appendix B: Reproducing the Results", "HAPPB"))
    A.append(code("""
python -m nc.cli env ; python -m nc.cli selftest bench/matmul.c
python -m nc.cli corpus fetch ; python -m nc.cli corpus scan --suite singlesource ; python -m nc.cli corpus split
python -m nc.cli search run --sample 15 --budget 25 --methods random,evo,evo2 --exclude-searched
.venv/bin/python scripts/gate_by_sample.py
python -m nc.cli passkb run --winners ; python -m nc.cli collect run --all --budget 40 --methods random,evo,evo2
python -m nc.cli features extract --all --include-test
python -m nc.cli model cv --fsets static,sim,scan ; python -m nc.cli model train --fsets static,sim,scan
python -m nc.cli rl train
python -m nc.cli evaluate run --tag final --k 8 ; python -m nc.cli evaluate report --tag final
python -m nc.cli predict-train ; python -m nc.cli predict-eval
.venv/bin/python scripts/tune_regression_check.py
.venv/bin/python scripts/export_dashboard_data.py
.venv/bin/python scripts/make_vtu_report.py"""))
    A.append(P("Every decision with its result file is recorded in <code>CLAUDE.md</code>; the condensed technical report is "
               "<code>results/FINAL_REPORT.md</code>; installation and usage are described in <code>RUN.md</code>."))
    return "".join(A)


# ------------------------------------------------------------------ styling and printing
BASE_CSS = """
* { box-sizing: border-box; }
body { margin: 0; font-family: 'Times New Roman', Times, serif; font-size: 12pt; line-height: 1.5; color: #000; }
p { text-align: justify; margin: 0 0 9pt; }
.mk { position: absolute; left: 0; top: 0; font-size: 2px; line-height: 1; color: #fff; }
h1, h2, h3, .chap, figcaption, .tcap { position: relative; }
.ph { background: none; }
table.stud, table.stud td { border: 0 !important; background: none; } table.stud { width: auto; }
code { font-family: 'Courier New', monospace; font-size: 10.5pt; }
pre.code { font-family: 'Courier New', monospace; font-size: 9pt; line-height: 1.3; background: #f6f6f6; border: .6pt solid #999;
  padding: 7pt 9pt; white-space: pre-wrap; break-inside: avoid; margin: 6pt 0 10pt; }
ul, ol { margin: 0 0 9pt; padding-left: 22pt; } li { text-align: justify; margin-bottom: 3pt; }
table { border-collapse: collapse; width: 100%; font-size: 10.5pt; line-height: 1.3; }
th, td { border: .6pt solid #000; padding: 3pt 5pt; vertical-align: top; text-align: left; }
th { background: #e8e8e8; }
table.small { font-size: 9.5pt; } table.tiny { font-size: 7.4pt; line-height: 1.15; } table.tiny td, table.tiny th { padding: 1.2pt 3pt; }
.tblock { margin: 8pt 0 12pt; } .tblock.keep { break-inside: avoid; } .tcap { break-after: avoid; text-align: center; font-weight: bold; font-size: 11pt; margin-bottom: 4pt; }
tr { break-inside: avoid; } thead { display: table-header-group; }
figure { margin: 10pt 0 14pt; text-align: center; break-inside: avoid; }
figure svg { max-width: 100%; height: auto; }
figure.shot img { max-width: 100%; max-height: 190mm; border: .6pt solid #555; }
figcaption { font-weight: bold; font-size: 11pt; margin-top: 5pt; text-align: center; }
.eq { display: block; text-align: center; font-style: italic; margin: 4pt 0; }
"""

MAIN_CSS = """
@page { size: A4; margin: 30mm 22mm 27mm 30mm;
  @top-right { content: "%TITLE%"; font: italic 10pt 'Times New Roman'; vertical-align: bottom; padding-bottom: 4mm; }
  @bottom-left { content: "%DEPT%, %COLLEGE%"; font: 10pt 'Times New Roman'; vertical-align: top; padding-top: 4mm; }
  @bottom-center { content: counter(page); font: 11pt 'Times New Roman'; vertical-align: top; padding-top: 4mm; }
  @bottom-right { content: "%YEAR%"; font: 10pt 'Times New Roman'; vertical-align: top; padding-top: 4mm; } }
.chap { break-before: page; text-align: center; margin: 4mm 0 10mm; }
.chap:first-child { break-before: auto; }
.chapno { font-size: 15pt; font-weight: bold; letter-spacing: .5pt; }
.chap h1 { font-size: 17pt; margin: 3mm 0 0; }
h2 { font-size: 14pt; margin: 12pt 0 6pt; break-after: avoid; }
h3 { font-size: 12pt; margin: 10pt 0 4pt; break-after: avoid; }
ol.refs li { margin-bottom: 5pt; font-size: 11pt; }
"""

FRONT_CSS = """
@page { size: A4; margin: 28mm 22mm 26mm 28mm;
  @bottom-center { content: counter(page, lower-roman); font: 11pt 'Times New Roman'; vertical-align: top; padding-top: 4mm; } }
.fmsec { break-before: page; } .fmsec:first-child { break-before: auto; }
h1.fm { text-align: center; font-size: 16pt; margin: 2mm 0 8mm; }
.kw { margin-top: 8pt; }
table.stud { width: auto; margin: 0 auto; border: 0; font-size: 12pt; }
table.stud td { border: 0; padding: 1pt 14pt; font-weight: bold; }
table.stud.right { margin: 12mm 0 0 auto; }
.toc .t0, .toc .t1 { display: flex; align-items: baseline; gap: 4pt; font-size: 11.5pt; line-height: 1.45; }
.toc .t0 { font-weight: bold; margin-top: 5pt; } .toc .t1 { padding-left: 16pt; }
.toc .tl { flex: 0 1 auto; } .toc .dots { flex: 1 1 auto; border-bottom: 1pt dotted #000; transform: translateY(-3pt); min-width: 10pt; }
.toc .pg { flex: 0 0 auto; min-width: 18pt; text-align: right; }
.toc .hd { margin-bottom: 4pt; }
table.abbr td { border: 0; border-bottom: .4pt solid #bbb; padding: 1.6pt 6pt; font-size: 10.5pt; }
table.abbr td:first-child { width: 30%; }
"""

COVER_CSS = """
@page { size: A4; margin: 22mm 22mm 20mm 24mm; }
section { break-after: page; text-align: center; } section:last-child { break-after: auto; }
.uni { color: #8b1a1a; font-size: 17pt; font-weight: bold; letter-spacing: .3pt; margin-top: 2mm; }
.uniaddr { font-size: 10.5pt; font-weight: bold; }
img.vtu { width: 28mm; margin: 5mm 0 4mm; } img.jss { width: 24mm; margin: 6mm 0 3mm; }
.logo-ph { display: inline-block; width: 26mm; height: 26mm; border: 1pt dashed #999; border-radius: 50%; font-size: 8pt; line-height: 26mm; margin: 5mm 0; }
.kind { font-family: Arial, sans-serif; font-weight: bold; font-size: 13pt; } .on { font-family: Arial, sans-serif; font-weight: bold; font-size: 11pt; }
.ptitle { color: #b42318; font-weight: bold; font-size: 14.5pt; line-height: 1.3; margin: 3mm 8mm 4mm; }
.sub { font-size: 10.5pt; font-weight: bold; } .deg { font-weight: bold; font-size: 12.5pt; margin: 4mm 0; line-height: 1.4; }
.by { font-weight: bold; font-size: 11pt; margin-bottom: 2mm; }
table.stud { margin: 0 auto 5mm; border-collapse: collapse; } table.stud td { padding: .5pt 20pt; font-weight: bold; font-size: 12pt; text-align: left; }
.ug { font-size: 11pt; } .gname { font-weight: bold; font-size: 13pt; } .gdes { font-size: 11pt; line-height: 1.35; }
.col { font-weight: bold; font-size: 13pt; margin-top: 2mm; } .col.big { font-size: 16pt; } .yr { font-weight: bold; font-size: 12.5pt; margin-top: 3mm; }
.cert p { text-align: justify; font-size: 12pt; line-height: 1.6; }
.certh { color: #8b1a1a; font-size: 18pt; font-weight: bold; margin: 2mm 0 6mm; }
table.sig { width: 100%; margin-top: 14mm; } table.sig td { border: 0; width: 33%; text-align: center; font-size: 11pt; line-height: 1.35; vertical-align: top; }
table.sig .line { border-top: .8pt solid #000; width: 75%; margin: 0 auto 3pt; }
.ext { font-weight: bold; margin: 8mm 0 3mm; }
table.exam { width: 100%; } table.exam th, table.exam td { border: 0; background: none; text-align: left; padding: 4mm 2mm; font-size: 11.5pt; }
.decl { text-align: left; } .decl p { line-height: 1.7; }
h1.fm { text-align: center; font-size: 16pt; margin: 6mm 0 10mm; }
table.stud.right { margin: 10mm 0 0 auto; }
"""


def page_html(body: str, css: str, title: str) -> str:
    css = (css.replace("%TITLE%", CONFIG["short_title"]).replace("%DEPT%", CONFIG["dept_short"])
           .replace("%COLLEGE%", CONFIG["college_short"]).replace("%YEAR%", CONFIG["year_short"]))
    return f'<!doctype html><html lang="en"><head><meta charset="utf-8"><title>{E(title)}</title><style>{BASE_CSS}{css}</style></head><body>{body}</body></html>'


def print_pdf(html_text: str, name: str, work: Path) -> Path:
    exe = R.chrome()
    if not exe:
        sys.exit("no Chrome/Chromium/Edge found")
    if exe[0].startswith("/mnt/"):
        tmp, base = Path("/mnt/c/Users/Public/nc_vtu_tmp"), "C:\\Users\\Public\\nc_vtu_tmp\\"
        uri = f"file:///C:/Users/Public/nc_vtu_tmp/{name}.html"
    else:
        tmp, base = work, str(work) + "/"
        uri = (work / f"{name}.html").as_uri()
    if not (tmp / "assets").exists():
        tmp.mkdir(parents=True, exist_ok=True)
        shutil.copytree(ASSETS, tmp / "assets")
    (tmp / f"{name}.html").write_text(html_text)
    subprocess.run(exe + ["--headless=new", "--disable-gpu", "--no-pdf-header-footer", "--virtual-time-budget=5000",
                          f"--print-to-pdf={base}{name}.pdf", uri], capture_output=True, timeout=300)
    out = work / f"{name}.pdf"
    shutil.copy2(tmp / f"{name}.pdf", out)
    return out


def marker_pages(pdf: Path) -> dict[str, int]:
    doc = pdfium.PdfDocument(str(pdf))
    found: dict[str, int] = {}
    for i in range(len(doc)):
        txt = doc[i].get_textpage().get_text_range()
        for m in re.findall(r"@@([A-Z]+[\d.]*[A-Z]*)@@", txt.replace("\r", "").replace("\n", "")):
            found.setdefault(m, i + 1)
    return found


def add_border(doc: pdfium.PdfDocument) -> None:
    mm = 72 / 25.4
    for page in doc:
        w, h = page.get_size()
        for inset, width in ((11, 2.4), (12.8, 0.7)):
            o = pdfraw.FPDFPageObj_CreateNewRect(inset * mm, inset * mm, w - 2 * inset * mm, h - 2 * inset * mm)
            pdfraw.FPDFPageObj_SetStrokeColor(o, 0, 0, 0, 255)
            pdfraw.FPDFPageObj_SetStrokeWidth(o, width)
            pdfraw.FPDFPath_SetDrawMode(o, pdfraw.FPDF_FILLMODE_NONE, True)
            pdfraw.FPDFPage_InsertObject(page.raw, o)
        pdfraw.FPDFPage_GenerateContent(page.raw)


def main() -> None:
    work = REPO / "work" / "vtu_report"
    work.mkdir(parents=True, exist_ok=True)
    shutil.rmtree("/mnt/c/Users/Public/nc_vtu_tmp", ignore_errors=True)
    body = chapters()
    main_pdf = print_pdf(page_html(body, MAIN_CSS, "chapters"), "main", work)
    pages = marker_pages(main_pdf)
    missing = [m for *_, m in TOC if m not in pages] + [m for *_, m in FIGS + TABS if m not in pages]
    if missing:
        print("warning: markers not found:", missing[:10])
    cover_pdf = print_pdf(page_html(cover() + certificate() + declaration(), COVER_CSS, "cover"), "cover", work)
    front = (abstract() + acknowledgement() + toc_page(pages) + list_page("LIST OF FIGURES", FIGS, pages, "Figure")
             + list_page("LIST OF TABLES", TABS, pages, "Table") + abbr_page())
    front_pdf = print_pdf(page_html(front, FRONT_CSS, "front"), "front", work)
    out = pdfium.PdfDocument.new()
    for p in (cover_pdf, front_pdf, main_pdf):
        out.import_pages(pdfium.PdfDocument(str(p)))
    add_border(out)
    dst = OUT / f"{NAME}.pdf"
    out.save(str(dst))
    shutil.rmtree("/mnt/c/Users/Public/nc_vtu_tmp", ignore_errors=True)
    print(f"wrote {dst} ({len(out)} pages, {dst.stat().st_size / 1024:.0f} KB); "
          f"chapters {len(pdfium.PdfDocument(str(main_pdf)))} pages, figures {len(FIGS)}, tables {len(TABS)}")


if __name__ == "__main__":
    main()
