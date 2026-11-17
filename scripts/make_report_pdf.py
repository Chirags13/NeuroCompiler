#!/usr/bin/env python3
"""Build the full project report (docs/NeuroCompiler_Report.html -> .pdf).

Every number comes from result files in the repo: dashboard/static/data/research.json (itself exported by
scripts/export_dashboard_data.py), results/FINAL_REPORT.md and the decisions recorded in CLAUDE.md, plus the
saved dashboard runs in dashboard/saved/. Charts are inline SVG. The PDF is printed with headless Chrome
(Windows Chrome via WSL interop, or a Linux chrome/chromium if present).

Usage: .venv/bin/python scripts/make_report_pdf.py
"""
from __future__ import annotations

import html
import json
import math
import shutil
import subprocess
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
D = json.loads((REPO / "dashboard/static/data/research.json").read_text())
OUT = REPO / "docs"
E = html.escape


def pct(v, d=2):
    return "–" if v is None else f"{'+' if v >= 1 else ''}{(v - 1) * 100:.{d}f}%"


def xx(v, d=3):
    return "–" if v is None else f"{v:.{d}f}×"


def ci(c, d=1):
    return f"{pct(c[0], d)} … {pct(c[1], d)}" if c else ""


# ---------------------------------------------------------------- SVG charts
COL = {"ok": "#059669", "bad": "#dc2626", "warn": "#d97706", "acc": "#6d28d9", "acc2": "#0891b2", "rl": "#db2777",
       "lib": "#2563eb", "o3": "#64748b", "pred": "#7c3aed", "ga": "#ea580c", "grid": "#e5e7eb", "text": "#1f2937",
       "muted": "#6b7280"}


def hbar(rows, title="", ref=None, log=False, width=760, bar_h=20, gap=6, label_w=210, fmt=lambda v: xx(v),
         vmin=None, vmax=None, ci_key=None):
    """rows: list of dicts {label, value, color, ci?}."""
    vals = [r["value"] for r in rows] + [c for r in rows for c in (r.get("ci") or []) if c is not None]
    lo = vmin if vmin is not None else min(vals + ([ref] if ref else []))
    hi = vmax if vmax is not None else max(vals + ([ref] if ref else []))
    if log:
        lo, hi = math.log(lo * 0.98), math.log(hi * 1.02)
        f = math.log
    else:
        pad = (hi - lo) * 0.05 or 0.05
        lo, hi = (lo - pad if vmin is None else lo), hi + pad
        f = lambda v: v
    plot_w = width - label_w - 70
    sx = lambda v: label_w + (f(v) - lo) / (hi - lo) * plot_w
    h = len(rows) * (bar_h + gap) + 44
    s = [f'<svg viewBox="0 0 {width} {h}" width="100%" xmlns="http://www.w3.org/2000/svg" font-family="Inter,Arial" font-size="11">']
    if title:
        s.append(f'<text x="0" y="12" font-weight="600" fill="{COL["text"]}" font-size="12">{E(title)}</text>')
    y0 = 22
    # ticks
    nt = 5
    for i in range(nt + 1):
        tv = lo + (hi - lo) * i / nt
        v = math.exp(tv) if log else tv
        x = label_w + plot_w * i / nt
        s.append(f'<line x1="{x:.1f}" y1="{y0}" x2="{x:.1f}" y2="{h - 18}" stroke="{COL["grid"]}"/>')
        s.append(f'<text x="{x:.1f}" y="{h - 5}" fill="{COL["muted"]}" text-anchor="middle">{fmt(v) if fmt else f"{v:.2f}"}</text>')
    base = sx(ref) if ref is not None else label_w
    for i, r in enumerate(rows):
        y = y0 + i * (bar_h + gap)
        x1, x2 = sorted((base, sx(r["value"])))
        s.append(f'<text x="{label_w - 8}" y="{y + bar_h * 0.7:.1f}" text-anchor="end" fill="{COL["text"]}">{E(r["label"])}</text>')
        s.append(f'<rect x="{x1:.1f}" y="{y}" width="{max(x2 - x1, 1):.1f}" height="{bar_h}" rx="3" fill="{r.get("color", COL["acc"])}" opacity=".85"/>')
        c = r.get("ci")
        if c and c[0] is not None:
            a, b = sx(c[0]), sx(c[1])
            m = y + bar_h / 2
            s.append(f'<path d="M{a:.1f} {m}H{b:.1f}M{a:.1f} {m - 4}V{m + 4}M{b:.1f} {m - 4}V{m + 4}" stroke="#111827" stroke-width="1.2"/>')
        tx = max(sx(r["value"]), sx(c[1]) if c and c[1] is not None else 0) + 6
        s.append(f'<text x="{tx:.1f}" y="{y + bar_h * 0.7:.1f}" fill="{COL["text"]}" font-weight="600">{fmt(r["value"]) if fmt else r["value"]}</text>')
    if ref is not None:
        s.append(f'<line x1="{base:.1f}" y1="{y0 - 4}" x2="{base:.1f}" y2="{h - 18}" stroke="#111827" stroke-dasharray="4 3"/>')
    s.append("</svg>")
    return "".join(s)


def vbars(values, colors, title="", width=760, height=220, log=False, ref=None, vmin=None, labels=None, ylab=""):
    n = len(values)
    lo = vmin if vmin is not None else min(values)
    hi = max(values)
    f = math.log if log else (lambda v: v)
    lo_, hi_ = f(lo), f(hi * 1.02)
    pl, pb, pt = 50, 30 if labels is None else 70, 22
    pw, ph = width - pl - 10, height - pb - pt
    sy = lambda v: pt + ph - (f(max(v, lo)) - lo_) / (hi_ - lo_) * ph
    s = [f'<svg viewBox="0 0 {width} {height}" width="100%" xmlns="http://www.w3.org/2000/svg" font-family="Inter,Arial" font-size="10">']
    if title:
        s.append(f'<text x="0" y="12" font-weight="600" fill="{COL["text"]}" font-size="12">{E(title)}</text>')
    for i in range(5):
        tv = lo_ + (hi_ - lo_) * i / 4
        v = math.exp(tv) if log else tv
        y = pt + ph - ph * i / 4
        s.append(f'<line x1="{pl}" y1="{y:.1f}" x2="{width - 10}" y2="{y:.1f}" stroke="{COL["grid"]}"/>')
        s.append(f'<text x="{pl - 5}" y="{y + 3:.1f}" text-anchor="end" fill="{COL["muted"]}">{v:.2f}{"×" if log else ""}</text>')
    bw = pw / n
    for i, (v, c) in enumerate(zip(values, colors)):
        x = pl + i * bw
        y = sy(v)
        s.append(f'<rect x="{x + bw * 0.1:.1f}" y="{y:.1f}" width="{bw * 0.8:.1f}" height="{pt + ph - y:.1f}" fill="{c}" opacity=".85"/>')
        if labels:
            s.append(f'<text transform="translate({x + bw / 2:.1f},{pt + ph + 6}) rotate(55)" fill="{COL["text"]}" font-size="8.5">{E(labels[i])}</text>')
    if ref is not None:
        y = sy(ref)
        s.append(f'<line x1="{pl}" y1="{y:.1f}" x2="{width - 10}" y2="{y:.1f}" stroke="{COL["warn"]}" stroke-dasharray="4 3"/>')
    if ylab:
        s.append(f'<text transform="translate(10,{pt + ph / 2}) rotate(-90)" text-anchor="middle" fill="{COL["muted"]}">{E(ylab)}</text>')
    s.append("</svg>")
    return "".join(s)


def lines(series, labels, title="", width=760, height=240, ylab="", yfmt=lambda v: f"{v:.2f}"):
    allv = [v for _, vs, _ in series for v in vs]
    lo, hi = min(allv), max(allv)
    pad = (hi - lo) * 0.08 or 0.01
    lo, hi = lo - pad, hi + pad
    pl, pb, pt = 56, 40, 22
    pw, ph = width - pl - 10, height - pb - pt
    n = len(labels)
    sx = lambda i: pl + pw * i / max(n - 1, 1)
    sy = lambda v: pt + ph - (v - lo) / (hi - lo) * ph
    s = [f'<svg viewBox="0 0 {width} {height}" width="100%" xmlns="http://www.w3.org/2000/svg" font-family="Inter,Arial" font-size="10">']
    if title:
        s.append(f'<text x="0" y="12" font-weight="600" fill="{COL["text"]}" font-size="12">{E(title)}</text>')
    for i in range(5):
        v = lo + (hi - lo) * i / 4
        y = sy(v)
        s.append(f'<line x1="{pl}" y1="{y:.1f}" x2="{width - 10}" y2="{y:.1f}" stroke="{COL["grid"]}"/>')
        s.append(f'<text x="{pl - 5}" y="{y + 3:.1f}" text-anchor="end" fill="{COL["muted"]}">{yfmt(v)}</text>')
    step = max(1, n // 10)
    for i in range(0, n, step):
        s.append(f'<text x="{sx(i):.1f}" y="{pt + ph + 14}" text-anchor="middle" fill="{COL["muted"]}">{E(str(labels[i]))}</text>')
    lx = pl + 10
    for name, vs, c in series:
        pts = " ".join(f"{sx(i):.1f},{sy(v):.1f}" for i, v in enumerate(vs))
        dash = ' stroke-dasharray="5 4"' if name.startswith("random") or name.startswith("oracle") else ""
        s.append(f'<polyline points="{pts}" fill="none" stroke="{c}" stroke-width="2"{dash}/>')
        s.append(f'<rect x="{lx}" y="{height - 14}" width="10" height="10" fill="{c}"/><text x="{lx + 14}" y="{height - 5}" fill="{COL["text"]}">{E(name)}</text>')
        lx += 18 + 6.2 * len(name)
    if ylab:
        s.append(f'<text transform="translate(10,{pt + ph / 2}) rotate(-90)" text-anchor="middle" fill="{COL["muted"]}">{E(ylab)}</text>')
    s.append("</svg>")
    return "".join(s)


def scatter(pts, title="", width=760, height=300, xlab="", ylab="", log=True, rng=(0.5, 2.5), color=COL["acc2"]):
    pl, pb, pt = 56, 40, 22
    pw, ph = width - pl - 10, height - pb - pt
    f = math.log if log else (lambda v: v)
    lo, hi = f(rng[0]), f(rng[1])
    sx = lambda v: pl + (f(min(max(v, rng[0]), rng[1])) - lo) / (hi - lo) * pw
    sy = lambda v: pt + ph - (f(min(max(v, rng[0]), rng[1])) - lo) / (hi - lo) * ph
    s = [f'<svg viewBox="0 0 {width} {height}" width="100%" xmlns="http://www.w3.org/2000/svg" font-family="Inter,Arial" font-size="10">']
    if title:
        s.append(f'<text x="0" y="12" font-weight="600" fill="{COL["text"]}" font-size="12">{E(title)}</text>')
    for v in (0.5, 0.75, 1, 1.5, 2, 2.5):
        if rng[0] <= v <= rng[1]:
            s.append(f'<line x1="{sx(v):.1f}" y1="{pt}" x2="{sx(v):.1f}" y2="{pt + ph}" stroke="{COL["grid"]}"/>')
            s.append(f'<line x1="{pl}" y1="{sy(v):.1f}" x2="{pl + pw}" y2="{sy(v):.1f}" stroke="{COL["grid"]}"/>')
            s.append(f'<text x="{sx(v):.1f}" y="{pt + ph + 14}" text-anchor="middle" fill="{COL["muted"]}">{v}×</text>')
            s.append(f'<text x="{pl - 5}" y="{sy(v) + 3:.1f}" text-anchor="end" fill="{COL["muted"]}">{v}×</text>')
    for a, b in pts:
        s.append(f'<circle cx="{sx(a):.1f}" cy="{sy(b):.1f}" r="1.6" fill="{color}" opacity=".45"/>')
    s.append(f'<line x1="{sx(1):.1f}" y1="{pt}" x2="{sx(1):.1f}" y2="{pt + ph}" stroke="#111827" stroke-dasharray="4 3"/>')
    s.append(f'<line x1="{pl}" y1="{sy(1):.1f}" x2="{pl + pw}" y2="{sy(1):.1f}" stroke="#111827" stroke-dasharray="4 3"/>')
    s.append(f'<text x="{pl + pw / 2}" y="{height - 4}" text-anchor="middle" fill="{COL["muted"]}">{E(xlab)}</text>')
    s.append(f'<text transform="translate(12,{pt + ph / 2}) rotate(-90)" text-anchor="middle" fill="{COL["muted"]}">{E(ylab)}</text>')
    s.append("</svg>")
    return "".join(s)


def table(head, rows, cls=""):
    th = "".join(f"<th>{h}</th>" for h in head)
    tr = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return f'<table class="{cls}"><thead><tr>{th}</tr></thead><tbody>{tr}</tbody></table>'


# ---------------------------------------------------------------- architecture diagram (static SVG)
def arch_svg():
    lanes = [("1 · Data & measurement (offline)", "#0891b2", 20), ("2 · Learning (offline)", "#db2777", 175),
             ("3 · Deployment per program (online)", "#2563eb", 330), ("4 · Interfaces & environment", "#64748b", 520)]
    nodes = [  # lane y, x, title, sub
        (0, 20, "Benchmark sources", "PolyBench · test-suite"), (0, 175, "Corpus builder", "build·run·filter·split"),
        (0, 330, "Timing harness", "pinned·interleaved·A/A"), (0, 485, "Pipeline search", "GA·evo·random·KB"),
        (0, 640, "Dataset", "dataset.sqlite"),
        (1, 20, "Program features", "static·scan·sim·remarks"), (1, 175, "SL surrogate", "LightGBM ranker"),
        (1, 330, "RL agent (PPO)", "edit sequences"), (1, 485, "Pipeline library", "≈913 pipelines"),
        (1, 640, "Predict models", "7×LGBM + harm"),
        (2, 20, "Your program", "C/C++ · args · stdin"), (2, 175, "LLVM 18 toolchain", "clang→opt→llc"),
        (2, 330, "Tune: rank top-8", "RL + SL pool"), (2, 485, "Time + confirm", "20 rounds + A/A"),
        (2, 640, "Binary + report", "pick or -O3"),
        (3, 20, "WSL2 env", "14 vCPU · 10 GB"), (3, 175, "CLI", "tune·predict·compare"),
        (3, 330, "Dashboard", "FastAPI · SSE"), (3, 485, "Frozen models", "MANIFEST hashes"),
        (3, 640, "Reports", "scripts → results"),
    ]
    W, H = 140, 48
    s = ['<svg viewBox="0 0 800 640" width="100%" xmlns="http://www.w3.org/2000/svg" font-family="Inter,Arial">',
         '<defs><marker id="a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto"><path d="M0 0L10 5L0 10z" fill="#6b7280"/></marker></defs>']
    for name, c, y in lanes:
        hh = 140 if y < 330 else (175 if y == 330 else 100)
        s.append(f'<rect x="8" y="{y}" width="784" height="{hh}" rx="10" fill="{c}" fill-opacity=".05" stroke="{c}" stroke-opacity=".35"/>')
        s.append(f'<text x="18" y="{y + 18}" font-size="11" font-weight="700" fill="{c}">{E(name.upper())}</text>')
    ys = [55, 210, 380, 560]
    pos = {}
    for i, (ln, x, t, sub) in enumerate(nodes):
        y = ys[ln] + (25 if ln == 2 and x in (20, 175, 640) else 0)
        if ln == 2 and x == 330:
            y = ys[ln] - 5
        if ln == 2 and x == 485:
            y = ys[ln] - 5
        pos[i] = (x, y)
        c = lanes[ln][1]
        s.append(f'<rect x="{x}" y="{y}" width="{W}" height="{H}" rx="8" fill="#fff" stroke="{c}" stroke-width="1.4"/>')
        s.append(f'<text x="{x + 10}" y="{y + 20}" font-size="11.5" font-weight="700" fill="#111827">{E(t)}</text>')
        s.append(f'<text x="{x + 10}" y="{y + 36}" font-size="9.5" fill="#6b7280">{E(sub)}</text>')

    def arrow(a, b, dashed=False, color="#6b7280"):
        (x1, y1), (x2, y2) = pos[a], pos[b]
        if abs(y1 - y2) < 30:
            d = f"M{x1 + W} {y1 + H / 2} L{x2} {y2 + H / 2}"
        else:
            sx_, sy_ = x1 + W / 2, (y1 + H if y2 > y1 else y1)
            ex, ey = x2 + W / 2, (y2 if y2 > y1 else y2 + H)
            d = f"M{sx_} {sy_} C{sx_} {(sy_ + ey) / 2} {ex} {(sy_ + ey) / 2} {ex} {ey}"
        s.append(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="1.3" {"stroke-dasharray=\"5 4\"" if dashed else ""} marker-end="url(#a)"/>')
    for a, b in [(0, 1), (1, 2), (2, 3), (3, 4), (4, 8), (4, 9), (5, 6), (6, 7), (10, 11), (11, 12), (12, 13), (13, 14)]:
        arrow(a, b)
    arrow(4, 6)
    for a, b in [(6, 12), (7, 12), (8, 12)]:
        arrow(a, b, True, "#db2777")
    arrow(9, 11, True, "#7c3aed")
    arrow(17, 10, True)
    s.append('<text x="790" y="633" font-size="9" fill="#6b7280" text-anchor="end">dashed = frozen model used at deployment</text></svg>')
    return "".join(s)


# ---------------------------------------------------------------- content
def build_html() -> str:
    c, H5, G3, ev, md, kb = D["corpus"], D["phase5"], D["gate3"], D["eval"], D["models"], D["kb"]
    hl = D["headline"]
    t = hl["tune_rlsl"]
    S = ev["summary"]
    saved = {p.stem: json.loads(p.read_text()) for p in sorted((REPO / "dashboard/saved").glob("*.json"))}
    parts = []
    A = parts.append

    # ---- cover
    A(f"""<section class="cover">
      <div class="logo">N</div>
      <h1>NeuroCompiler</h1>
      <p class="subtitle">Hybrid machine-learning and reinforcement-learning guided LLVM pass selection,<br>judged only by measured runtime against <code>clang -O3</code></p>
      <div class="cover-kpis">
        <div><b>{pct(t['geomean'], 1)}</b><span>tune (RL + SL) geomean vs -O3 on 33 unseen programs</span></div>
        <div><b>{t['slower']} / {t['n']}</b><span>test programs measurably slower than -O3</span></div>
        <div><b>{pct(hl['phase5']['geomean'], 1)}</b><span>search headroom on 115 unseen programs</span></div>
      </div>
      <p class="meta">Complete project report · generated {time.strftime('%Y-%m-%d')} from the result files in the repository<br>
      Machine: AMD Ryzen 9 270 (Zen 4) · WSL2 Ubuntu · LLVM 18.1.8 (pinned)</p>
    </section>""")

    # ---- contents
    toc = ["Executive summary", "The problem and the goals", "Background: LLVM pass pipelines", "Environment and toolchain",
           "Phase 1 · Measurement harness", "Phase 2 · Corpus", "Phase 3 · Search and the headroom gate",
           "Phase 4 · Pass knowledge base", "Phase 5 · Data collection and wider search", "Phase 6 · Features",
           "Phase 7 · Supervised surrogate", "Phase 8 · Reinforcement learning (PPO)", "The deployed system: tune (RL + SL)",
           "Phase 9 · Evaluation on the frozen test set", "Predict mode", "IR count is not runtime",
           "Accuracy and reliability of the models", "Demonstration runs", "Dashboard and command-line interface",
           "System architecture", "Code map", "Configuration reference", "Timeline and decisions on record",
           "Limitations", "How to reproduce", "Appendix A · Per-program test results", "Appendix B · Glossary"]
    A('<section class="toc"><h2>Contents</h2><ul class="tocl">' + "".join(f"<li><span>{i + 1 if i < 25 else ''}</span>{E(x)}</li>" for i, x in enumerate(toc)) + "</ul></section>")

    # ---- 1 executive summary
    A(f"""<section class="pb"><h2>1. Executive summary</h2>
    <p>NeuroCompiler chooses, for each C/C++ program, a better LLVM optimization pipeline than the standard <code>-O3</code>.
    It edits the -O3 pass pipeline (removing, repeating, reordering or inserting passes, changing pass options and global
    knobs, and changing code-generator flags), and it judges every change only by <b>measured runtime</b>: a candidate
    must produce exactly the same output as the unoptimized program and be measurably faster than -O3, otherwise -O3 is used.</p>
    <p>The final system (<b>tune, RL + SL</b>) works in four steps:</p>
    <ol>
      <li>A reinforcement-learning agent (PPO) proposes 24 pipelines for the new program.</li>
      <li>A supervised LightGBM model ranks them together with a library of ~913 pipelines found by search on training programs.</li>
      <li>The 8 best-ranked candidates are compiled, checked for identical output, and timed against -O3 on an isolated CPU core.</li>
      <li>The fastest is shipped only if a fresh 20-round confirmation run, with a byte-identical copy of -O3 as noise control, shows it is more than 1% faster. Otherwise -O3 ships.</li>
    </ol>
    <div class="kpis">
      <div><b>{pct(t['geomean'])}</b><span>geomean vs -O3, 33 held-out programs (CI {ci(t['ci'])})</span></div>
      <div><b>{pct(t['excl_largest'])}</b><span>excluding the largest result</span></div>
      <div><b>{t['ge5']}/{t['n']}</b><span>programs ≥ +5% faster</span></div>
      <div><b>{t['slower']}</b><span>programs measurably slower</span></div>
    </div>
    <p><b>Key findings</b></p>
    <ul>
      <li><b>There is real headroom over -O3, but it is uneven.</b> An expensive search finds {pct(hl['phase5']['geomean'], 1)} (geomean) on 115 programs it had never seen,
          but {hl['phase5']['no_gain']} of those programs have no measurable gain at all.</li>
      <li><b>Models alone are weak; models plus measurement work.</b> On unseen program families the supervised model ranks pipelines with Spearman ≈ 0.11.
          Trusting its single best guess without timing gives +2.4% but makes 16 of 33 programs slower. Using it to shortlist 8 candidates and then timing them gives +7.5–8.1% with 0–1 regressions.</li>
      <li><b>Reinforcement learning adds little.</b> PPO alone reaches +3.4%; pooled with the library (the final RL + SL) it is +0.2% over SL alone, not significant. It is kept in the final version at the user's request, and this report says so.</li>
      <li><b>Predicting without running is hard.</b> The compile-only predict mode reached {pct(hl['predict']['geomean'])} (CI includes 0) and missed its pre-registered success criterion, so it ships as advisory.</li>
      <li><b>IR instruction count says nothing about runtime</b> (Spearman {D['ir']['rho']:.2f} over {D['ir']['n']:,} measured candidates). An earlier attempt that optimized IR count and size did not improve runtime; this project optimizes runtime directly.</li>
      <li><b>One pre-registered gate was missed</b> (Phase 3 headroom: +4.0%, 4/15 programs ≥ +5%, needed 30%). The project continued under a documented re-scope to the "good" tier (+2–4%), which the final system meets.</li>
    </ul></section>""")

    # ---- 2 problem and goals
    A("""<section><h2>2. The problem and the goals</h2>
    <p>Compilers apply a fixed sequence of optimization passes (<code>-O3</code>) to every program. That sequence is a compromise tuned
    for typical code; for a specific program, a different sequence or different pass parameters can be faster. The search space is enormous
    (the LLVM 18 -O3 pipeline has 109 leaf passes, each with options, plus dozens of global knobs and code-generator flags), and the effect of
    an edit depends on the program's loops, data sizes, memory behaviour and branches.</p>
    <h3>Objective</h3>
    <ul>
      <li><b>Success = measurable, reproducible runtime improvement over -O3 on programs not used in training.</b></li>
      <li>Never slower than -O3 beyond measurement noise; ideally a few percent faster.</li>
      <li>Binary size (<code>.text</code> ≤ ~1.10× -O3, soft penalty), IR instruction count and compile time are <i>constraints only</i>, never objectives.</li>
      <li>Deployment model: the system proposes top-k pipelines, they are compiled and briefly timed, -O3 is always among them, the fastest wins.</li>
    </ul>
    <h3>Success tiers (defined before the work)</h3>""" + table(["tier", "definition"], [
        ["minimum", "no regressions and no miscompiles"],
        ["good", "geomean +2–4% with the 95% CI excluding 0, and ≥ 20–30% of programs ≥ +5%"],
        ["strong", "geomean ≥ +5%"]]) + """
    <h3>Ground rules followed throughout</h3>
    <ul>
      <li>Only confirmed numbers count (30 interleaved rounds + A/A control); gates use validated (independently re-measured) numbers. Screening overstates.</li>
      <li>Geomeans are always reported with and without the largest single result.</li>
      <li>Thresholds and gates are never relaxed to get a pass; the data split is never redone after seeing results.</li>
      <li>Measured and estimated values are labelled; every number is reproducible from scripts and result files in the repository.</li>
      <li>No CPU-heavy work while a timing job runs; the machine is shared, so a "quiet guard" waits for other load to stop before timing.</li>
    </ul></section>""")

    # ---- 3 background
    A("""<section><h2>3. Background: LLVM pass pipelines</h2>
    <p>LLVM's new pass manager describes an optimization level as a textual <b>pipeline</b>: a nested list of passes running at module,
    call-graph (CGSCC), function and loop level, e.g. <code>function&lt;eager-inv&gt;(sroa&lt;modify-cfg&gt;,early-cse&lt;&gt;,simplifycfg&lt;…&gt;)</code>.
    <code>opt -passes=default&lt;O3&gt; -print-pipeline-passes</code> prints the exact -O3 pipeline for LLVM 18, which this project parses into a tree
    (109 leaf passes). Every candidate is "-O3 plus a short list of edits", called a <b>genome</b>.</p>
    <h3>Edit types (action spaces v1 and v2)</h3>""" + table(["edit", "meaning", "example"], [
        ["del", "delete one pass instance", "remove one <code>licm</code>"],
        ["dup", "run a pass instance twice", "repeat <code>instcombine</code>"],
        ["swap", "swap a pass with its neighbour", "reorder two function passes"],
        ["ins", "insert a pass at a valid position", "add <code>dfa-jump-threading</code> after <code>jump-threading</code>"],
        ["param", "change one option of one pass instance", "simplifycfg <code>no-switch-range-to-icmp → switch-range-to-icmp</code>"],
        ["param_all", "change an option on every instance of a pass", "every simplifycfg: <code>sink-common-insts</code> off"],
        ["del_all", "delete every instance of a pass", "remove every <code>simplifycfg</code>"],
        ["knob", "global opt flag", "<code>-force-vector-width=4</code>, <code>-unroll-max-count=2</code>, <code>-inline-threshold=1000</code>"],
        ["llc flag", "code-generator flag", "<code>-tail-dup-size=6</code>, <code>-align-loops=32</code>"],
        ["backend", "code-generator optimization level", "<code>llc -O2</code> instead of <code>-O3</code>"],
        ["raw (level seed)", "a whole standard pipeline in place of -O3's", "<code>default&lt;O2&gt;</code>, <code>default&lt;O0&gt;</code> + <code>llc -O3</code>"]]) + """
    <p>Action space v1 (delete / duplicate / swap / insert, six knobs, llc level) was extended to v2 (pass-option flips on one or all instances,
    family-wide deletes, more knobs, llc backend flags such as tail duplication, tail merging, loop alignment, cmov conversion, scheduling and
    jump tables, and more insertable passes such as <code>dfa-jump-threading</code> and <code>gvn-sink</code>). v2 found the fix for the
    <b>evalloop</b> interpreter: -O3's SimplifyCFG "sink common instructions" merges the interpreter's 31 indirect dispatch jumps into one, which
    destroys branch prediction; turning that option off restores them (up to 3.7× faster).</p></section>""")

    # ---- 4 environment
    A("""<section><h2>4. Environment and toolchain</h2>""" + table(["item", "value"], [
        ["machine", "AMD Ryzen 9 270 (Zen 4, AVX-512), laptop; host 8 cores / 16 threads"],
        ["OS", "Windows + WSL2 Ubuntu; since 2026-10-23 WSL2 has 14 vCPUs (SMT pairs 0-1 … 12-13) and 10 GB RAM"],
        ["machine_id", "<code>wsl2-ryzen9-270</code> (8 vCPUs, data before 2026-10-23), <code>wsl2-ryzen9-270-v14</code> (14 vCPUs)"],
        ["compiler", "LLVM 18.1.8 pinned at /usr/lib/llvm-18/bin (the OS default LLVM 21 is never used for data)"],
        ["timing CPU", "vCPU 6 for serial timing; vCPUs 2, 6, 10 for parallel screening (siblings idle)"],
        ["Python", "3.14 virtual environment (.venv): numpy, scipy, LightGBM; PPO written in numpy"],
        ["dynamic features", "valgrind cachegrind (simulated, labelled as such; binaries built with -march=x86-64-v3 because valgrind cannot run AVX-512). No hardware perf counters in WSL2"],
        ["storage", "SQLite: results/dataset.sqlite (search, measurements, features), results/predict.sqlite, results/deploy.sqlite"]]) + """
    <h3>How a build works</h3>
    <pre>clang -O3 -march=native -Xclang -disable-llvm-passes  →  start IR (with TBAA and attributes, no passes)
opt -passes=&lt;pipeline&gt; [knobs]                        →  optimized IR
llc -O3 [backend flags] -relocation-model=pic          →  object file
clang object -lm                                       →  binary</pre>
    <p>The start IR is taken from clang with LLVM passes disabled, not from -O0, so it keeps the metadata (TBAA, attributes) that a real -O3 build sees;
    otherwise the baseline would be weaker than real -O3. Multi-file programs are compiled per file and <code>llvm-link</code>ed into one module.
    Binaries are cached by the hash of the optimized IR, so identical IR is never compiled or timed twice. The -O3 inliner settings are passed
    explicitly so that the printed -O3 pipeline reproduces <code>default&lt;O3&gt;</code>; 20 programs still differ bit-for-bit (flagged
    <code>o3_mismatch</code>), and all speedups are measured against the real <code>default&lt;O3&gt;</code> binary.</p></section>""")

    # ---- 5 harness
    st = D["harness"]["selftest_v8"] + D["harness"]["selftest_v14"]
    aa = D["harness"]["aatests"]
    A("""<section><h2>5. Phase 1 · Measurement harness</h2>
    <p>Nothing downstream can be trusted unless timing is trustworthy, so the harness came first and has its own pass/fail selftest.</p>
    <h3>How one comparison is measured</h3>
    <ul>
      <li><b>Pinning and isolation:</b> benchmark processes run on one vCPU; the harness and compiles run elsewhere. ASLR is disabled for benchmark children; a 3 s busy warm-up lets frequency settle.</li>
      <li><b>Interleaving:</b> -O3 and the candidates run in randomized round-robin order (30 rounds plus 5 warm-up for confirmation), so slow drift affects all equally.</li>
      <li><b>Paired statistics:</b> speedup = median of per-round ratios; 95% confidence interval by bootstrap (4,000 resamples). A win requires the CI lower bound above 1.</li>
      <li><b>A/A control:</b> a byte-identical copy of the -O3 binary at a different path is timed in the same run. If it deviates from 1.0 by more than 1%, the measurement is repeated once and flagged.</li>
      <li><b>Correctness:</b> every candidate's output hash must equal the -O0 build's output hash (the oracle); otherwise it is discarded.</li>
      <li><b>Quiet guard:</b> before each timing block, the harness waits (up to 30 min) while processes from other sessions use more than 0.6 cores, and records the load.</li>
      <li><b>Screening vs confirmation:</b> search uses cheap screening (1 round, 2 more only if ≥ 0.98×; runs slower than 1.3× -O3 killed), then all shortlists are confirmed together in one 30-round run, the winner is minimized (useless edits removed) and validated in a fresh, independent run.</li>
    </ul>
    <h3>Selftests</h3>""" + table(["file", "verdict", "median", "CI half-width", "drift", "A/A", "-O0/-O3"], [
        [E(s["file"]), s["verdict"], f"{s['median_ms']:.0f} ms", f"{s['ci_halfwidth_pct']:.2f}%", f"{s['drift_pct']:.2f}%", xx(s["aa"]), f"{s['o0_vs_o3']:.2f}×"] for s in st]) + """
    <p>Thresholds: CI half-width &lt; 1%, A/A bias &lt; 1%, drift &lt; 2%, -O0/-O3 gap ≥ 1.2×. The first 14-vCPU selftest failed under other load
    and passed when re-run on a quiet machine (CI ±0.12%). The minimum program runtime (floor 0.35 s) was set from the selftest: 220 ms was too noisy, 400 ms passed.</p>
    <h3>Parallel timing (multi-core A/A tests)</h3>""" + hbar([
        {"label": f"{len(a['cores'])} cores · {a['file'][7:22]}", "value": max(abs(p['parallel']['aa_bias_pct']) for p in a['programs']),
         "color": COL["ok"] if a["pass"] else COL["bad"]} for a in aa], title="worst |A/A bias| (%) when timing on several cores at once (green = passed)",
        fmt=lambda v: f"{v:.2f}%", vmin=0) + """
    <p>Timing several programs at once on different cores distorted memory-bound programs. Three workers on vCPUs 2, 6, 10 (siblings idle),
    with at most one memory-heavy program at a time (simulated L2 misses ≥ 20 per 1000 instructions), passed: bias ≤ 0.46%, noise about serial,
    known speedups within 0.2%. Five workers kept speedups unbiased but made noise 5–40× larger, so they were not used. Every reported number is
    in any case a serial re-measurement on one core. Code-layout randomization was tested and gave no benefit (results/layout_test_20261023-102201.json).</p></section>""")

    # ---- 6 corpus
    rej = sum(r[1] for r in c["rejections"])
    A(f"""<section><h2>6. Phase 2 · Corpus</h2>
    <p>Sources: <b>PolyBench/C 4.2.1</b> (kernels, problem sizes scaled continuously) and the <b>LLVM test-suite</b> SingleSource (C and C++, programs
    scaled through <code>argv[1]</code>) and MultiSource (multi-file benchmarks and applications, built through a small CMake interpreter, inputs
    in per-program run directories). {c['scanned']} candidate programs were scanned; {rej} were rejected; <b>{c['usable']} usable programs in {c['families']} families</b>.</p>
    <p>A program is kept only if it builds at -O0/-O1/-O2/-O3/-Os, produces identical output at every level (the -O0 output is the oracle),
    is deterministic, needs under 3 GB, and runs 0.35–3 s at -O3 on this machine. A <i>family</i> groups programs that share code (e.g. all
    PolyBench linear-algebra kernels); families are kept together when splitting, so test programs come from families never seen in training.</p>
    """ + hbar([{"label": r[0], "value": r[1], "color": COL["bad"]} for r in c["rejections"]], title="rejection reasons (programs)",
               fmt=lambda v: f"{v:.0f}", vmin=0) + table(["suite", "usable programs"], [[k, v] for k, v in c["by_suite"].items()]) + f"""
    <p>{c['levels_differ_3pct']} programs differ by ≥ 3% between -O levels, and on {c['level_beats_o3']} a lower level (-O1, -O2 or -Os) beats -O3,
    an early sign that -O3 is not always best.</p>
    <h3>Frozen split (2026-10-24, seed 0, before any modelling)</h3>""" + table(["split", "programs", "families"], [
        [k, c["split"]["counts"][k], f"{len(c['split']['groups'][k])}: " + E(", ".join(c["split"]["groups"][k]))] for k in ("train", "val", "test")]) + """
    <p>Rule: a family enters test or validation only if it fits the remaining budget (TSVC, 33 programs, therefore falls to train).
    The split file refuses to be overwritten.</p></section>""")

    # ---- 7 phase 3
    g = G3["fresh_summary"]
    allg = sorted([dict(p, s="fresh") for p in G3["fresh"]] + [dict(p, s="original") for p in G3["original"]], key=lambda p: -p["speedup"])
    A(f"""<section><h2>7. Phase 3 · Search and the headroom gate</h2>
    <p>Question: is there anything to gain over -O3 at all? Each program was searched with standard-level seeds plus random search,
    a genetic/evolutionary search on action space v1 (<code>evo</code>) and on v2 (<code>evo2</code>), budget 25 unique timed binaries per method,
    then confirmation, minimization and independent validation. The gate required, on validated numbers, ≥ 30% of programs at ≥ +5%.</p>
    """ + vbars([p["speedup"] for p in allg], [COL["acc2"] if p["s"] == "fresh" else COL["acc"] for p in allg],
                title="best validated speedup per program (cyan = fresh sample, purple = original sample; dashed = +5%)",
                log=True, ref=1.05, vmin=0.98, labels=[p["id"].split("/")[-1] for p in allg]) + table(
        ["sample", "n", "geomean (95% CI)", "excl. largest", "median", "≥ +5%"],
        [["fresh (decisive)", g["n"], f"{pct(g['geomean'])} ({ci(g['ci'], 2)})", pct(g["excl_largest"]), pct(g["median"]), f"{g['ge5']}/{g['n']}"],
         ["original", G3["original_summary"]["n"], f"{pct(G3['original_summary']['geomean'])} ({ci(G3['original_summary']['ci'], 2)})",
          pct(G3["original_summary"]["excl_largest"]), pct(G3["original_summary"]["median"]), f"{G3['original_summary']['ge5']}/{G3['original_summary']['n']}"]]) + """
    <div class="callout warn"><b>Gate NOT MET</b> on the decisive fresh sample: 4 of 15 programs (26.7%) reached +5%, below the required 30%.
    The pooled 30 programs pass at exactly 30.0% only by counting polybench/jacobi-1d, whose A/A control was noisy, so the pooled pass was not used.
    <br><b>Decision (user):</b> continue with the target lowered to the "good" tier (+2–4%), without a separate re-test; use the Phase 5 wider search on never-searched programs as an
    out-of-sample re-measurement of headroom. Later gates stay strict, and this miss is reported. Reproduce: <code>scripts/gate_by_sample.py</code> → <code>results/gate_by_sample_20261023.txt</code>.</div></section>""")

    # ---- 8 phase 4
    A(f"""<section><h2>8. Phase 4 · Pass knowledge base</h2>
    <p>To learn <i>which</i> edits matter, {kb['edits']} single edits around -O3 were tried on {kb['programs']} training programs that had a confirmed gain
    (19 families): leave-one-out deletion of every pass, option flips, family-wide edits, add-one insertions and knob settings
    ({", ".join(f"{k}: {v}" for k, v in kb['by_kind'].items())}).</p>
    """ + table(["edit", "kind", "programs", "confirmed faster", "confirmed slower", "screening effect ≥ ±2%", "identical binary", "screening range"],
                [[f"<code>{E(r['label'])}</code>", r["kind"], r["programs"], r["faster"], r["slower"], r["big"], r["noop"], f"{r['min']:.2f}–{r['max']:.2f}×"] for r in kb["top"][:16]], "small") + """
    <p style="font-size:8.6pt;color:#4b5563"><i>confirmed faster / slower</i>: confirmation CI entirely above / below 1. <i>screening effect ≥ ±2%</i>: programs where the cheap screening run moved by at least 2% in either direction.
    <i>identical binary</i>: the edit changes nothing on that program.</p>
    <p>Findings: the strongest levers are the loop cost-model overrides, in both directions (<code>-force-vector-width=8</code> confirmed faster on 5 programs and slower on 0;
    <code>-unroll-count=2</code> faster on 4 but slower on 6). Most single edits do nothing on a given program (250–320 of 346 give an identical binary).
    Every edit hurts some program, so no single global change beats -O3: selection has to be per program. The knowledge base also produced the
    pruned action set used by the RL agent (<code>results/passkb_actions.json</code>) and predict's safe edit pool.</p></section>""")

    # ---- 9 phase 5
    vals = sorted([v for v in H5["values"] if not v["suspect"]], key=lambda v: -v["speedup"])
    sa, sf = H5["summary_all"], H5["summary_family"]
    A(f"""<section><h2>9. Phase 5 · Data collection and wider search</h2>
    <p>The training data for the models: evo + evo2 with the full v2 action space, budget 50 each, on the 116 programs never searched before,
    every winner re-validated serially. This doubled as the out-of-sample re-measurement of headroom decided in Phase 3.</p>
    """ + vbars([v["speedup"] for v in vals], [("#94a3b8" if v["source"] == "no winner" else COL["ok"] if v["speedup"] >= 1.05 else COL["acc2"]) for v in vals],
                title="best validated speedup per program, sorted (grey = no winner, -O3 kept; dashed = +5%)", log=True, ref=1.05, vmin=0.98, height=200) + table(
        ["view", "n", "geomean (95% CI)", "excl. largest", "median", "≥ +5%", "no gain"],
        [["all programs (excl. artifact)", sa["n"], f"{pct(sa['geomean'], 1)} ({ci(sa['ci'])})", pct(sa["excl_largest"], 1), pct(sa["median"], 1), f"{sa['ge5']}/{sa['n']}", sa["no_gain"]],
         ["one value per family", sf["n"], f"{pct(sf['geomean'], 1)} ({ci(sf['ci'])})", pct(sf["excl_largest"], 1), pct(sf["median"], 1), f"{sf['ge5']}/{sf['n']}", sf["no_gain"]]]) + f"""
    <h3>Artifact check</h3>
    <p>Winners ≥ {H5['rule']['min_speedup']}× were re-checked with cachegrind instruction counts. <code>ss/Misc-C++/mandel-text</code> (no input) ran 217× fewer
    instructions with identical output: the compiler had computed the answer at compile time. It is excluded from every summary.</p>
    """ + table(["program", "speedup", "instruction ratio", "verdict"], [[E(a["program"]), xx(a["speedup"], 2), f"{a['instr_ratio']:.2f}×" if a.get("instr_ratio") else "–",
                                                                         "excluded" if a["suspect_compile_time_eval"] else "real"] for a in H5["artifact"]], "small") + """
    <h3>Data quality</h3>
    <p>15 of 146 programs (10.3%) had a noisy accepted A/A control, marginally over the 10% limit, so the dataset is marginally NOT clean. Mitigation was decided before modelling:
    those programs' labels are weighted 0.3, and all labels are capped at |log 3|. Parallel (3-core) vs serial validation differed by a median of −0.15%.
    Dataset version 692d2418a83f (<code>results/dataset_version.json</code>).</p></section>""")

    # ---- 10 features
    fs = md["feature_sets"]
    A(f"""<section><h2>10. Phase 6 · Features</h2>
    """ + table(["set", "count", "what it contains", "needs running?"], [
        ["static", fs["static"], "IR statistics of the canonicalized and the -O3 IR: instruction mix (loads, stores, branches, calls, FP, vector, phi, …), loop counts and depths, function counts, -O3/canonical size ratio", "no"],
        ["scan", fs["scan"], "runtime at -O0/-O1/-O2/-O3/-Os, level spread, -O0/-O3 ratio, binary size, distinct level binaries", "yes (quick scan)"],
        ["sim", fs["sim"], "cachegrind simulation: instructions, L1/LL cache miss rates and MPKI, branch mispredict rates (labelled simulated)", "yes (cachegrind)"],
        ["sim_l2", fs["sim_l2"], "simulated 1 MB private L2 miss rate and MPKI (also used by the memory-aware parallel scheduler)", "yes"],
        ["remarks", fs["remarks"], "counts of LLVM -O3 optimization remarks: loops vectorized / not vectorized and why, inlining decisions, unrolling, LICM, GVN …", "no (predict only)"],
        ["candidate encoding", "≈ 98", "the genome: edits by pass family and stage, knob values, llc flags and level, raw level seeds", "no"]]) + """
    <p>Tune's surrogate uses static + scan + sim features (sim adds about +0.01 Spearman; an ablation without them measured +6.1% instead of +7.5% on the test set, not significant).
    Predict, which must not run the program, uses static + remarks only. Features of compiled candidates were also tried and made the model worse.</p></section>""")

    # ---- 11 surrogate
    tc = md["tune_cv"]["summary"]
    ks = [1, 3, 5, 10]
    A(f"""<section><h2>11. Phase 7 · Supervised surrogate (LightGBM)</h2>
    <p>The surrogate predicts log-speedup vs -O3 for a (program, pipeline) pair. Two forms were trained: a LightGBM regressor and a LightGBM
    lambdarank ranker (300 trees, learning rate 0.05, 15 leaves, subsampling 0.8). Training data: every validated, confirmed and screened measurement
    of the training families, weighted by stage reliability, noisy programs down-weighted to 0.3, labels capped at |log 3|.
    Evaluation: leave-one-family-out cross-validation on the 24 development families (test families excluded automatically).</p>
    <p><b>Metrics.</b> <i>Spearman</i> = rank correlation between predicted and true speedups of a held-out program's candidates (1 = perfect, 0 = random).
    <i>gain@k</i> = the best true speedup among the model's top-k candidates, averaged (geomean) over programs; compared with k random candidates (<i>rand_gain@k</i>) and the best in the library (<i>oracle</i>).</p>
    """ + lines([("regressor (used by tune)", [tc["gbr"][f"gain@{k}"] for k in ks], COL["lib"]),
                 ("ranker", [tc["rank"][f"gain@{k}"] for k in ks], COL["acc"]),
                 ("random", [tc["gbr"][f"rand_gain@{k}"] for k in ks], COL["o3"]),
                 ("oracle", [tc["gbr"]["oracle"]] * 4, COL["ok"])], [f"top-{k}" for k in ks],
                title="gain@k on held-out families: best true speedup among the top-k (latest CV, after Phase 4 data)", yfmt=lambda v: f"{v:.2f}×") + table(
        ["model", "Spearman (95% CI)", "gain@1", "gain@5", "rand gain@5", "recall@5"],
        [[m, f"{tc[m]['spearman']:+.3f} ({tc[m]['spearman_ci'][0]:+.2f}…{tc[m]['spearman_ci'][1]:+.2f})", xx(tc[m]["gain@1"]), xx(tc[m]["gain@5"]), xx(tc[m]["rand_gain@5"]), f"{tc[m]['recall@5'] * 100:.1f}%"]
         for m in ("gbr", "rank", "transfer", "random")], "small") + """
    <h3>Gate 7B: does the surrogate rank unseen families better than random?</h3>
    <p><b>First run (before the Phase 4 data was complete): NOT MET.</b> Regressor Spearman +0.124 (+0.05…+0.20) but gain@5 1.097× &lt; random 1.109×; ranker gain@5 1.122× with Spearman +0.075.
    <b>Re-run after Phase 4 data, in the plan's order: narrowly MET.</b> Regressor Spearman +0.111 (+0.06…+0.15), gain@5 1.107× vs random 1.091× (<code>results/models/cv_latest.json</code>).
    Both are reported; because the pass is narrow and came after seeing the first result, the RL work that followed is labelled exploratory.</p>
    <p>Offline the model ranks only slightly better than chance; in deployment (Phase 9) it nevertheless beats a random shortlist from the same library by +5.8% (CI excludes 0), because a shortlist of 8 only needs the good pipelines to be somewhere near the top.</p></section>""")

    # ---- 12 RL
    rt = md["rl_tune_history"]
    sm = [sum(rt[max(0, i - 9):i + 1]) / len(rt[max(0, i - 9):i + 1]) for i in range(len(rt))]
    A(f"""<section><h2>12. Phase 8 · Reinforcement learning (PPO)</h2>
    <p><b>Design</b> (<code>nc/rl.py</code>): an episode builds a pipeline for one program, one edit per step (horizon 4), choosing from {md['rl_tune_actions']} macro-actions taken from
    the knowledge base (knobs, llc flags, family-wide deletes and option flips). The state is the program's features plus the edits chosen so far; the reward is the surrogate's
    predicted log-speedup of the finished pipeline. Policy and value function are one-hidden-layer MLPs in numpy, trained with PPO (clip 0.2, entropy bonus 0.01, 4 epochs per update,
    Adam lr 3e-3, GAE λ = 0.95). Training: the 113 train+val programs, 200 iterations × 64 episodes.</p>
    """ + lines([("tune RL, mean reward (moving average of 10)", sm, COL["rl"])], list(range(1, len(sm) + 1)), title="PPO learning curve (reward = surrogate's predicted log speedup)", yfmt=lambda v: f"{v:+.3f}") + f"""
    <p>The predicted return reached +0.22 log speedup, but that is the surrogate's opinion, far above what is measured. The learned policy favours <code>-inline-threshold=1000</code>,
    <code>-unroll-max-count=2/4</code>, llc <code>tail-dup-size</code> 4/6 and deleting every simplifycfg / instcombine. Its proposals collapse to about 5 distinct binaries per program.</p>
    """ + table(["method (33 test programs, serial)", "geomean (95% CI)", "excl. largest", "≥ +5%", "regressions"], [
        ["model top-8 (re-run, same session)", "+7.92% (+2.57…+16.23)", "+4.74%", "9/33", "0"],
        ["RL proposals only", "+3.35% (+1.12…+6.19)", "+2.51%", "6/33", "0"],
        ["RL proposals + library, surrogate ranks (RL + SL)", "+8.09% (+2.60…+16.35)", "+4.92%", "9/33", "0"]]) + """
    <p>Paired per program: RL only vs top-8 −4.2% (−11.0…+0.6); RL + library vs top-8 +0.2% (−0.2…+0.7, not significant). By the plan's rule ("RL only if it beats top-k and GA at equal budget") RL was
    <b>not adopted</b> as a result. The user then chose <b>RL + SL as the final version for the presentation</b>; its measured effect over SL is +0.2% (n.s.), and an RL proposal was the shipped pipeline on 1 of 33 test programs (fibo, 1.231×).</p></section>""")

    # ---- 13 tune
    A("""<section><h2>13. The deployed system: tune (RL + SL)</h2>
    <p><code>bin/neurocompiler tune prog.c --args … --out prog</code> (tune is the default mode). For a new program:</p>
    <ol>
      <li><b>Reference:</b> build at -O0, run with the given arguments/stdin, hash the output. Every candidate must reproduce it.</li>
      <li><b>Features:</b> static IR features and a quick scan of -O0…-O3/-Os runtimes (and, with <code>--dynamic</code>, cachegrind).</li>
      <li><b>RL proposes:</b> the PPO policy generates 24 pipelines (3 × k) for this program.</li>
      <li><b>SL ranks:</b> the surrogate scores the 24 RL proposals + ~913 library pipelines (winners from training programs plus random pipelines).</li>
      <li><b>Compile + verify:</b> candidates are compiled in ranked order (in parallel) until 8 distinct binaries with correct output exist; binaries identical to -O3 are skipped.</li>
      <li><b>Selection timing:</b> the 8 candidates and -O3 are timed interleaved, 10 rounds, on the pinned core.</li>
      <li><b>Confirmation:</b> the fastest is re-measured in a fresh 20-round run with an A/A control. It ships only if the CI lower bound exceeds 1.01 and the control is clean. This removes the "winner's curse" of picking the best of 8 noisy numbers.</li>
      <li><b>Output:</b> the binary (pick or -O3) and a JSON report: shipped pipeline and edits, where it came from (RL agent or library), the -O3 pipeline, every timed candidate with runtime in ms, speedup and CI, code size, and the model's top-10 ranking.</li>
    </ol>
    <p><b>Cost:</b> about 24–80 compiles and a few minutes of timing per program (≈ 80–190 s for the demo programs).
    <b>Frozen:</b> tune loads its model files only through <code>results/models/tune/MANIFEST.json</code> (SHA-256 hashes) and refuses to run if any changed;
    <code>scripts/tune_regression_check.py</code> confirms tune's top-8 order is identical before and after every code change (last run: IDENTICAL).
    <code>--no-rl</code> gives SL only.</p>
    <p><b>Why the confirmation step exists:</b> in the first Phase 9 run, ms/Applications/JM/lencod shipped at 0.979×: its pick won a 10-round selection run under parallel load and did not hold up.
    With the confirmation step, lencod ships -O3 (post-hoc illustration, not a re-scored result). The first demo run on "branchy" shows the same protection: the best candidate measured 1.044× in selection but 1.015× in confirmation, so -O3 shipped.</p></section>""")

    # ---- 14 evaluation
    order = sorted(S.items(), key=lambda kv: -kv[1]["geomean"])
    colmap = {"tune RL + SL": COL["rl"], "tune top-8 (SL)": COL["lib"], "predict (gated)": COL["pred"], "predict ungated": "#a78bfa", "GA@8": COL["ga"],
              "-O2": COL["o3"], "-Os": COL["o3"], "RL only": "#f472b6", "random search@8": "#9ca3af", "random top-8": "#94a3b8", "ML-only top-1": "#818cf8", "no dynamic features": "#93c5fd"}
    pv = sorted(ev["paired_vs_tune_top8"].items(), key=lambda kv: -kv[1]["mean"])
    A(f"""<section><h2>14. Phase 9 · Evaluation on the frozen test set</h2>
    <p>33 programs from 11 families never used for training, model selection or threshold tuning; evaluated once. Every method's shipped binary was re-measured serially,
    in the same runs as -O3, with an A/A control. Equal budget: top-8, random search@8 and GA@8 each time 8 binaries.</p>
    """ + hbar([{"label": k, "value": v["geomean"], "ci": v["ci"], "color": colmap.get(k, COL["o3"])} for k, v in order], title="geomean speedup vs -O3 with 95% CI (33 test programs)",
               ref=1.0, fmt=lambda v: xx(v)) + table(["method", "geomean", "95% CI", "excl. largest", "median", "≥ +5%", "measurably slower"],
                                                     [[E(k), pct(v["geomean"]), ci(v["ci"]), pct(v["excl_largest"]), pct(v["median"]), v["ge5"], v["slower"]] for k, v in order], "small") + """
    <p><b>Method definitions.</b> <i>tune top-8 (SL)</i>: surrogate ranks the library, 8 timed. <i>tune RL + SL</i>: final version. <i>RL only</i>: only RL proposals timed.
    <i>no dynamic features</i>: surrogate without cachegrind features. <i>ML-only top-1</i>: model's single best guess, no timing. <i>random top-8</i>: 8 random pipelines from the same library, timed.
    <i>random search@8</i>: 8 random genomes. <i>GA@8</i>: genetic algorithm (6 + 18) with 8 timed binaries. <i>predict</i>: compile-only mode (section 15).</p>
    <h3>Paired comparison (per program, ratio tune top-8 / method; &gt; 1 means tune top-8 is faster)</h3>
    """ + hbar([{"label": k, "value": v["mean"], "ci": v["ci"], "color": colmap.get(k, COL["o3"])} for k, v in pv], ref=1.0, fmt=lambda v: xx(v)) + f"""
    <p>Top-8 beats random top-8 by +5.8% (CI +1.0…+13.9) and the GA at equal budget by +5.3% (+0.3…+13.4); vs random search@8 +2.1% (not significant). Timing is essential: top-8 vs ML-only top-1 +5.0% (+2.3…+8.3).</p>
    <h3>Against the tiers</h3>
    <ul><li><b>good: met</b> — +4.3% to +4.9% excluding the largest result, CI excludes 0, 24–27% of programs ≥ +5%.</li>
        <li><b>strong (≥ +5%): only with the largest result</b> (polybench/durbin 2.84×) included.</li>
        <li><b>minimum (no regressions): met by RL + SL</b> (0 slower); missed by one program in the first SL run (lencod 0.979×), which motivated the confirmation step.</li></ul>
    <p>Size: tune's picks stay close to -O3's code size (soft cap 1.10×); -Os is smaller but {pct(S['-Os']['geomean'])} slower on average, and -O2 {pct(S['-O2']['geomean'])}.
    Reproducibility: the top-8 evaluation re-run on another day measured +7.92% vs the original +7.51% (difference +0.4%, CI −0.1…+1.0).</p></section>""")

    # ---- 15 predict
    pc = md["predict_cv"]
    A(f"""<section><h2>15. Predict mode</h2>
    <p>Goal: return a pipeline <b>without running the program</b> (compile + analysis only), in seconds. Criteria were recorded before building and not changed afterwards:</p>
    <ul><li>geomean ≥ +1.5% with 95% CI above 0 on the 33 test programs (serial re-measurement);</li>
        <li>at most 2 programs measurably slower (CI upper bound &lt; 1.0);</li>
        <li>added time over a plain -O3 build ≤ 10 s (median; maximum reported).</li></ul>
    <h3>Design</h3>
    <ul>
      <li><b>Separate models</b> in <code>results/models/predict/</code> with their own MANIFEST; predict never reads tune's models.</li>
      <li><b>Features:</b> {fs['static']} static IR features + {fs['remarks']} -O3 optimization-remark counts.</li>
      <li><b>Candidate pool ("safe pool"):</b> {md['predict_pool']['singles']} knowledge-base single edits that never appeared in a wrong-output candidate and are harmful on ≤ 10% of the programs they change, plus {md['predict_pool']['pairs']} pairs of the top 40 ({md['predict_pool']['wrong_output_edits_excluded']} edits excluded for wrong output), plus proposals from its own PPO policy (pessimistic reward).</li>
      <li><b>Ensemble:</b> 7 LightGBM regressors (bootstrap members) predict speedup; a LightGBM classifier predicts the probability that a candidate is harmful.</li>
      <li><b>Safety gate:</b> ship only if the pessimistic estimate (mean − 1.28 × std across members) &gt; 1 + margin, ≥ 80% of members agree, and harm probability ≤ τ.
          Thresholds (margin {md['predict_thresholds']['margin']}, τ {md['predict_thresholds']['tau']}) chosen on leave-one-family-out out-of-fold predictions of train+val only: objective = {E(pc['objective'])}.
          Out-of-fold: {pc['chosen']['shipped']} of {pc['chosen']['programs']} programs changed, {pc['chosen']['regressions']} regressions.</li>
    </ul>
    <h3>Result (test set, evaluated once)</h3>""" + table(["variant", "geomean (95% CI)", "excl. largest", "≥ +5%", "measurably slower", "programs changed"], [
        ["predict (RL + SL, gated)", "+0.64% (−0.16…+2.05)", "+0.02%", "1", "1 (lencod 0.971×)", "5"],
        ["predict_sl (SL only, gated)", "+0.64% (−0.14…+1.97)", "+0.03%", "1", "1", "5"],
        ["predict ungated", "−0.69% (−3.02…+1.44)", "−1.34%", "2", "8 (+2 wrong-output picks)", "24"]]) + f"""
    <p>Added time: median +0.62 s over a plain -O3 build, maximum +17.8 s (lencod). <b>Criteria: gain NOT MET, regressions MET, time MET</b>, so predict ships as
    <b>advisory: it writes the -O3 binary by default</b> and reports its recommendation; <code>--apply</code> writes the recommended pipeline. RL added nothing (predict = predict_sl).
    Without the gate predict is worse than -O3 and chose 2 pipelines with wrong output (polybench/deriche, doitgen), which shows why the gate and the output check matter.</p>
    <p><b>Why it is hard:</b> the effect of a pass edit depends on trip counts, data sizes, cache and branch behaviour, which the compile-time view does not contain.
    The ensemble ranks candidates with Spearman {md['predict_train_vs_heldout']['train'][0]:.2f} on its training programs but only {md['predict_train_vs_heldout']['heldout'][0]:.2f} on held-out families.</p>
    <h3>Measurement of the pick (added 2026-10-26, user request)</h3>
    <p>After the compile-only choice, predict now compiles its top-ranked sequence (the gated recommendation, or its best guess if the gate rejected it), checks the output against -O0,
    and times it against -O3 (20 interleaved rounds with an A/A control), reporting both runtimes in ms and the measured vs predicted speedup. This is reporting only: the choice,
    the gate, the advisory binary rule and the test-set result above are unchanged, and the added-time metric excludes it. <code>--no-measure</code> restores compile-only behaviour.</p></section>""")

    # ---- 16 IR
    A(f"""<section><h2>16. IR count is not runtime</h2>
    """ + scatter(D["ir"]["sample"], title=f"IR instructions vs measured speedup, {len(D['ir']['sample']):,} of {D['ir']['n']:,} candidates (Spearman ρ = {D['ir']['rho']:.3f})",
                  xlab="IR instruction count relative to -O3", ylab="measured speedup vs -O3") + f"""
    <p>An earlier attempt at this project reduced IR instruction count and binary size but not runtime. Across {D['ir']['n']:,} measured candidates, the change in IR count and the change
    in runtime are essentially uncorrelated; candidates with &gt; 1% fewer IR instructions were faster only {D['ir']['fewer_ir_faster_pct']:.0f}% of the time. Fewer instructions often means
    less unrolling or vectorization, which is slower. This is why every decision here is made from timed runs.</p></section>""")

    # ---- 17 accuracy
    A(f"""<section><h2>17. Accuracy and reliability of the models</h2>
    <p>These are regression/ranking models, so "accuracy" means how well they order candidate pipelines for a program they have not seen.</p>
    """ + table(["model", "on unseen families", "on its own", "inside the system"], [
        ["tune surrogate (LightGBM)", f"Spearman +0.11 (CI +0.06…+0.15); gain@5 1.107× vs random 1.091×; true best in its top-5 only 6% of the time",
         "ML-only top-1: +2.36%, 16/33 slower", "top-8 + timing: +7.51%, 1 slower; beats random top-8 by +5.8%"],
        ["RL agent (PPO)", "reward is the surrogate's prediction (+0.22 log predicted, not measured)", "RL only: +3.35%, 0 slower", "RL + SL: +8.09%, 0 slower; +0.2% over SL (n.s.)"],
        ["predict ensemble + harm classifier", f"Spearman {md['predict_train_vs_heldout']['heldout'][0]:.2f} (vs {md['predict_train_vs_heldout']['train'][0]:.2f} on training programs)",
         "ungated: −0.69%, 8 slower, 2 wrong output", "gated: +0.64% (CI includes 0), 1 slower"]], "small") + """
    <p><b>Reliability comes from measurement, not from the models.</b> The timing harness has A/A bias ≤ 0.3% and CI half-widths of 0.12–0.41%; every candidate's output is checked against -O0;
    a pick ships only after a fresh confirmation with CI &gt; 1.01; otherwise -O3. Results reproduce: the test evaluation re-run gave +7.92% vs +7.51%; demo reruns gave matmul 1.663×/1.656×,
    interpreter 3.824×/3.830×, Fibonacci 1.143×/1.141×. A separate accuracy figure for the harm classifier alone was not computed and is not quoted.</p>
    <p class="callout">In one sentence: the models narrow ~940 candidate pipelines down to 8 worth trying; they are weak predictors on their own (Spearman ≈ 0.1 on unseen programs), and measurement turns that weak signal into a reliable +8% with no regressions.</p></section>""")

    # ---- 18 demo runs
    rows = []
    for slug, j in saved.items():
        r = j.get("result") or {}
        name = j.get("saved_name", slug)
        if j["mode"] == "tune":
            cf = r.get("confirm") or {}
            ok = r.get("choice") == "candidate"
            rows.append([E(name), "tune", f"{r.get('base_median_ms', 0):.1f} ms",
                         f"{cf.get('pick_median_ms', 0):.1f} ms" if ok else "–",
                         f"{cf['speedup']:.3f}× [{cf['ci'][0]:.3f}, {cf['ci'][1]:.3f}]" if ok and cf.get("speedup") else "-O3 kept",
                         E(r.get("shipped_from") or r.get("reason", ""))[:90]])
        elif j["mode"] == "predict":
            m = r.get("measured") or {}
            rows.append([E(name), "predict", f"{m.get('o3_median_ms', 0):.1f} ms" if m.get("status") == "ok" else "–",
                         f"{m.get('pick_median_ms', 0):.1f} ms" if m.get("status") == "ok" else "–",
                         f"{m['speedup']:.3f}× [{m['ci'][0]:.3f}, {m['ci'][1]:.3f}] (predicted {r.get('predicted_speedup', 0):.3f}×)" if m.get("status") == "ok" else E(m.get("status", "")),
                         "recommended" if r.get("recommended") else "gate kept -O3"])
        elif j["mode"] == "compare":
            rows.append([E(name), "compare", f"{r.get('o3_median_ms', 0):.1f} ms", "–",
                         "; ".join(f"{x['method']} {x['speedup']:.3f}×" for x in r.get("rows", [])), "one interleaved run, A/A control"])
    A("""<section><h2>18. Demonstration runs</h2>
    <p>Runs made through the dashboard on 2026-10-26 (measured on this machine; saved in <code>dashboard/saved/</code> and replayable in the dashboard).</p>""" +
      table(["run", "mode", "-O3 runtime", "pick runtime", "measured speedup [95% CI]", "note"], rows, "small") + """
    <p>Highlights: the interpreter loop (evalloop) ships a pipeline from the RL agent at 3.83× (the -O3 binary takes 848 ms, the pick 221 ms); a library candidate that is just
    <code>default&lt;O0&gt;</code> passes with <code>llc -O3</code> already reaches 3.36×, consistent with the SimplifyCFG dispatch-merging finding. Branchy code shows the -O3 fallback.
    Predict's gate correctly rejected its matmul guess, which measured 0.990× (slower).</p></section>""")

    # ---- 19 dashboard & CLI
    A("""<section><h2>19. Dashboard and command-line interface</h2>
    <h3>Command line</h3>
    <pre>bin/neurocompiler tune    prog.c --args "..." --out prog     # default mode (RL + SL); --no-rl = SL only; --dynamic adds cachegrind
bin/neurocompiler predict prog.c --args "..." --out prog     # choose without running, then time the top pick; --apply, --no-measure
bin/neurocompiler compare prog.c --args "..."                # -O3, -O2, -Os, predict, tune, random@8, GA@8 + A/A control, one run</pre>
    <p>Research commands live in <code>python -m nc.cli</code>: env, o3pipeline, baselines, selftest, cpusweep, aatest, corpus, search, passkb, collect, features, model, rl, evaluate, predict-train/eval/time, tune-freeze.</p>
    <h3>Dashboard (local web app)</h3>
    <ul>
      <li><b>Start:</b> <code>./dashboard/run.sh</code> in WSL, or <code>dashboard\\windows\\Start-NeuroCompiler.bat</code> on Windows (boots WSL, starts the server, opens http://localhost:8000). Works offline (fonts, Chart.js and CodeMirror are vendored).</li>
      <li><b>Run page:</b> choose Tune / Predict / Compare; paste code, upload files or load an example; arguments, flags, stdin; an environment card checks WSL2, LLVM 18.1.8, model hashes, machine load and the last selftest, and can run a selftest;
          a single-worker job queue prevents overlapping timings; the terminal panel streams the job's output live (Server-Sent Events). Results show the selected sequence next to the -O3 sequence pass by pass, every edit explained in words,
          runtimes in ms for -O3 and every candidate with CIs, the model ranking, and downloads (binary, JSON). Finished runs can be saved and replayed.</li>
      <li><b>Research &amp; results page:</b> corpus, measurement, gates, wider search, knowledge base, training/validation, test results, IR vs runtime, timeline — generated from <code>dashboard/static/data/research.json</code> (<code>scripts/export_dashboard_data.py</code>).</li>
      <li><b>Architecture page:</b> clickable system diagram, tune and predict flows, edit types, technology, limits.</li>
      <li><b>Stack:</b> FastAPI + uvicorn (127.0.0.1:8000), vanilla JavaScript modules, Chart.js 4.4.4, CodeMirror 5.65. Jobs are stored in <code>work/dashboard/jobs/&lt;id&gt;/</code>.</li>
    </ul></section>""")

    # ---- 20 architecture
    A("""<section class="pb"><h2>20. System architecture</h2>""" + arch_svg() + """
    <p><b>Offline</b> (lanes 1–2): benchmark sources become a filtered, family-split corpus; the timing harness and the pipeline search produce labelled measurements in
    <code>dataset.sqlite</code>; features are extracted; the supervised surrogate, the RL agent, the pipeline library and predict's models are trained and frozen with hashed manifests.
    <b>Online</b> (lane 3): for a new program, the toolchain builds the reference and features, tune pools RL proposals with the library, the surrogate ranks them, the top 8 are compiled,
    verified and timed, and a confirmed winner or -O3 is written; predict scores its safe pool with its ensemble and gate. <b>Interfaces</b> (lane 4): CLI and dashboard in WSL2.</p></section>""")

    # ---- 21 code map
    A("""<section><h2>21. Code map</h2>""" + table(["file", "role"], [
        ["nc/toolchain.py", "build with any pass pipeline (single or multi-file, C or C++), knobs and llc flags; IR-hash cache; clang-direct builds; -O3 pipeline printing"],
        ["nc/timing.py", "pinned interleaved runner, bootstrap CIs, paired speedup, output hashing, quiet guard, SMT-sibling handling, A/A"],
        ["nc/envcheck.py", "environment report and warnings"],
        ["nc/corpus.py, nc/msource.py", "fetch suites, prescan, pinned scan with quality filters, frozen family split, report; MultiSource adapter (mini CMake interpreter)"],
        ["nc/pipeline.py", "-O3 pass tree parsing/rendering, genome, edit operators, action spaces v1 and v2, materialize()"],
        ["nc/search.py", "levels / random / evo / random2 / evo2 search, screening, merged confirmation, minimization, validation, reports"],
        ["nc/passkb.py", "Phase 4 knowledge base: leave-one-out, option flips, family edits, add-one inserts, knobs; attribution and pruned action set"],
        ["nc/collect.py", "Phase 5 data-collection driver; data-quality report and dataset version tag"],
        ["nc/parallel.py", "multi-core timing workers with the memory-aware scheduler; aatest"],
        ["nc/features.py, nc/remarks.py", "static IR, scan and cachegrind features; genome encoding; optimization-remark features (predict)"],
        ["nc/model.py", "LightGBM regressor and ranker, leave-one-family-out CV, gate 7B"],
        ["nc/rl.py", "PPO in numpy: macro-actions, environment with surrogate reward, training, proposals"],
        ["nc/deploy.py", "tune: RL + SL pool, ranking, compile + verify, selection timing, confirmation, JSON report"],
        ["nc/tunelock.py", "tune freeze: MANIFEST with SHA-256 hashes, verified loading"],
        ["nc/predict.py", "predict mode: safe pool, ensemble, harm classifier, gate, own PPO, evaluation, compare, measurement of the pick"],
        ["nc/evaluate.py", "Phase 9 frozen-test evaluation of all methods, report, reproduction run"],
        ["nc/db.py", "SQLite dataset access"],
        ["nc/cli.py, bin/neurocompiler", "command line (research commands and the tune / predict / compare modes)"],
        ["dashboard/", "server.py (FastAPI), static/ (HTML, CSS, JS, vendored libs, research.json), examples/, saved/, windows launcher, run.sh"],
        ["scripts/", "gate_by_sample, phase5_report, artifact_check, phase9_paired, modes_paired, rl_eval, tune_regression_check, export_dashboard_data, make_report_pdf, long-run shell drivers"]], "small") + "</section>")

    # ---- 22 config
    A("""<section><h2>22. Configuration reference (config.toml)</h2>""" + table(["setting", "value", "meaning"], [
        ["machine_id", "wsl2-ryzen9-270-v14", "tags every measurement; never mix machines in one table"],
        ["timing_cpu", "6", "vCPU benchmark binaries are pinned to"],
        ["llvm_bin_dir / march", "/usr/lib/llvm-18/bin / native", "one LLVM version; same -march for all builds including -O3"],
        ["reps / warmup", "30 / 5", "interleaved rounds per confirmation measurement / discarded rounds"],
        ["settle_s / no_aslr / timeout_s", "3.0 / true / 60", "busy warm-up; ASLR off for children; per-run timeout"],
        ["floor_s / ceiling_s", "0.35 / 3.0", "allowed -O3 runtime range for corpus programs"],
        ["budget / batch / screen_reps", "60 / 8 / 3", "unique timed binaries per program and method; screening batch; screening rounds"],
        ["screen_halving / screen_keep / screen_abort", "true / 0.98 / 1.30", "successive halving; keep threshold; kill slower runs"],
        ["size_cap", "1.10", "soft penalty when .text grows beyond 1.10× -O3"],
        ["confirm_top / merged_confirm / validate", "3 / true / true", "winners confirmed together; independent validation run"],
        ["control_max_dev_pct", "1.0", "A/A control tolerance before a confirmation is repeated"],
        ["quiet_max_busy / quiet_max_wait_s", "0.6 / 1800", "foreign load tolerated before timing / max wait"],
        ["isolate_sibling", "false", "keep the harness off the timing CPU's SMT sibling (changes conditions)"],
        ["selftest thresholds", "CI 1%, A/A 1%, drift 2%, -O0/-O3 ≥ 1.2×", "harness pass criteria"],
        ["tune (nc/deploy.py)", "k = 8, reps = 10, confirm 20 rounds, margin 0.01, 24 RL proposals", "deployment loop"],
        ["predict (nc/predict.py)", "margin 0.03, τ 0.5, agree 0.8, pessimistic z 1.28, 7 members", "safety gate"]], "small") + "</section>")

    # ---- 23 timeline
    tl = D["timeline"]
    A("""<section><h2>23. Timeline and decisions on record</h2>""" + table(["date", "phase", "event", "detail"],
                                                                            [[t_["date"], t_["phase"], E(t_["title"]), E(t_["detail"])] for t_ in tl], "small") + """
    <ul class="small">
      <li>2026-10-23: Phase 3 headroom gate NOT MET; re-scope to the good tier (user decision); measurement protocol unchanged (layout randomization no benefit); 3 timing workers on vCPUs 2, 6, 10.</li>
      <li>2026-10-24: Phase 5 wider search +15.6% out of sample; data quality marginally not clean (10.3%), mitigated by down-weighting; split frozen; Gate 7B NOT MET (first run).</li>
      <li>2026-10-25: Phase 9 test: top-8 + timing +7.51%; confirmation step added; Gate 7B narrowly met after Phase 4 data; supervised version backed up; RL trained and evaluated (exploratory, not adopted); final version RL + SL (user decision); predict criteria recorded before building.</li>
      <li>2026-10-26: predict result +0.64% → advisory; dashboard built; predict now measures its top pick (reporting only).</li>
    </ul></section>""")

    # ---- 24 limitations
    A("""<section><h2>24. Limitations</h2><ul>
      <li>One machine and microarchitecture (Zen 4, AVX-512) under WSL2; gains may differ elsewhere.</li>
      <li>33 test programs in 11 families: wide confidence intervals; the largest result (durbin 2.84×) moves the SL geomean from +4.3% to +7.5%.</li>
      <li>The Phase 3 headroom gate was missed; the project continued under a documented re-scope.</li>
      <li>Data quality marginally over the noisy-control limit (mitigated by down-weighting those labels).</li>
      <li>Gate 7B: NOT MET before the Phase 4 data, narrowly met after; RL (exploratory) did not beat top-k; RL is in the final version for presentation with a measured effect of +0.2% (n.s.).</li>
      <li>Predict missed its gain criterion and is advisory.</li>
      <li>Output correctness is checked on one input per program (hash equality vs -O0): evidence, not proof. Gains are specific to the workload given (arguments/stdin).</li>
      <li>Deployment cost: tens of compiles and minutes of timing per program for tune.</li>
      <li>20 programs are o3_mismatch (printed -O3 pipeline does not reproduce default&lt;O3&gt; bit for bit); their speedups are still measured against real -O3.</li>
      <li>Fixed-input benchmarks allow compile-time evaluation (mandel-text); screened by instruction counts.</li></ul></section>""")

    # ---- 25 reproduce
    A("""<section><h2>25. How to reproduce</h2>
    <pre># environment and harness
python -m nc.cli env ; python -m nc.cli selftest bench/matmul.c ; python -m nc.cli cpusweep bench/matmul.c
# corpus (Phase 2)
python -m nc.cli corpus fetch ; python -m nc.cli corpus prescan --suite multisource ; python -m nc.cli corpus scan --suite singlesource
python -m nc.cli corpus report ; python -m nc.cli corpus split
# search and headroom gate (Phase 3)
python -m nc.cli search run --sample 15 --budget 25 --methods random,evo,evo2 --exclude-searched
.venv/bin/python scripts/gate_by_sample.py
# knowledge base, data collection, features, models (Phases 4-7)
python -m nc.cli passkb run --winners ; python -m nc.cli passkb report
python -m nc.cli collect run --all --budget 40 --methods random,evo,evo2 ; python -m nc.cli collect quality
python -m nc.cli features extract --all --include-test
python -m nc.cli model cv --fsets static,sim,scan ; python -m nc.cli model train --fsets static,sim,scan
python -m nc.cli rl train
# evaluation (Phase 9) and reports
python -m nc.cli evaluate run --tag final --k 8 ; python -m nc.cli evaluate report --tag final
.venv/bin/python scripts/phase9_paired.py ; .venv/bin/python scripts/modes_paired.py
# predict
python -m nc.cli predict-train ; python -m nc.cli predict-eval ; python -m nc.cli predict-time --on test
# freeze check, dashboard data, this report
.venv/bin/python scripts/tune_regression_check.py
.venv/bin/python scripts/export_dashboard_data.py
.venv/bin/python scripts/make_report_pdf.py</pre>
    <p>Long runs are resumable (<code>scripts/phase5.sh</code>, <code>scripts/pipeline_rest.sh</code>) and were auto-restarted by cron (<code>scripts/phase5_autoresume.sh</code>) after WSL restarts.
    Every decision with its result file is recorded in <code>CLAUDE.md</code>; the condensed report is <code>results/FINAL_REPORT.md</code>; usage is in <code>RUN.md</code>.</p></section>""")

    # ---- appendix A
    ms_ = ["tune RL + SL", "tune top-8 (SL)", "RL only", "random search@8", "GA@8", "ML-only top-1", "predict (gated)", "-O2", "-Os"]

    def cell(v):
        if v is None:
            return "–"
        k = "pos" if v > 1.005 else "neg" if v < 0.995 else ""
        return f'<span class="{k}">{v:.3f}</span>'
    progs = sorted(ev["programs"], key=lambda p: -(p.get("tune RL + SL") or 0))
    A("""<section class="pb"><h2>Appendix A · Per-program test results (speedup vs -O3, serial)</h2>""" +
      table(["program", "family"] + [E(m) for m in ms_], [[E(p["id"].split("/")[-1]), E(p["family"])] + [cell(p.get(m)) for m in ms_] for p in progs], "tiny") + "</section>")

    # ---- appendix B
    A("""<section><h2>Appendix B · Glossary</h2>""" + table(["term", "meaning"], [
        ["-O3", "LLVM's standard highest optimization level; the baseline every result is compared against"],
        ["pass / pipeline", "one optimization step / the ordered, nested list of passes the optimizer runs"],
        ["genome / edit", "a candidate pipeline described as -O3 plus a list of edits"],
        ["speedup", "-O3 runtime divided by candidate runtime (> 1 = faster), from paired per-round ratios"],
        ["geomean", "geometric mean of speedups across programs (the right average for ratios)"],
        ["95% CI", "bootstrap confidence interval; a win needs its lower bound above 1"],
        ["A/A control", "a byte-identical copy of the -O3 binary timed alongside; measures the noise/bias of the run"],
        ["screening / confirmation / validation", "cheap noisy timing to choose / 30-round run with A/A control / fresh independent re-measurement of the winner"],
        ["winner's curse", "picking the best of several noisy measurements overstates it; fixed by a fresh confirmation run"],
        ["family", "programs sharing code; kept together in the split so test families are unseen"],
        ["surrogate", "the supervised model that predicts a pipeline's speedup for a program"],
        ["Spearman ρ", "rank correlation between predicted and true values (1 perfect, 0 random)"],
        ["gain@k", "best true speedup among a model's top-k candidates"],
        ["PPO", "Proximal Policy Optimization, the reinforcement-learning algorithm used for the agent"],
        ["safe pool", "predict's candidate set: edits that never gave wrong output and are rarely harmful"],
        ["o3_mismatch", "program where the printed -O3 pipeline does not reproduce default<O3> bit for bit"],
        ["quiet guard", "waits for other processes' load to drop before timing"],
        ["MANIFEST", "file of SHA-256 hashes that freezes a mode's model files"]], "small") + "</section>")

    css = """
    @page { size: A4; margin: 16mm 15mm 18mm 15mm; @bottom-center { content: counter(page); } }
    * { box-sizing: border-box; }
    body { font-family: Inter, "Segoe UI", Arial, sans-serif; color: #1f2937; font-size: 10.2pt; line-height: 1.5; margin: 0; }
    h1 { font-size: 34pt; margin: 0; letter-spacing: -.02em; }
    h2 { font-size: 16pt; color: #312e81; border-bottom: 2px solid #c7d2fe; padding-bottom: 4px; margin: 0 0 10px; break-after: avoid; }
    h3 { font-size: 11.5pt; color: #3730a3; margin: 14px 0 6px; break-after: avoid; }
    section { margin-top: 22px; } section.toc, section.pb { break-before: page; } section.cover + section { break-before: page; }
    section.cover { break-before: auto; height: 255mm; display: flex; flex-direction: column; justify-content: center; text-align: center;
      background: linear-gradient(160deg, #eef2ff 0%, #ecfeff 100%); border-radius: 14px; padding: 30px; }
    .logo { width: 70px; height: 70px; margin: 0 auto 16px; border-radius: 18px; background: linear-gradient(135deg, #8b5cf6, #6366f1 45%, #22d3ee);
      color: white; font-size: 38pt; font-weight: 800; display: flex; align-items: center; justify-content: center; }
    .subtitle { font-size: 13pt; color: #4b5563; margin: 12px 0 30px; }
    .cover-kpis { display: flex; gap: 14px; justify-content: center; margin-bottom: 30px; }
    .cover-kpis div, .kpis div { background: white; border: 1px solid #e0e7ff; border-radius: 10px; padding: 12px 14px; flex: 1; }
    .cover-kpis b { display: block; font-size: 24pt; color: #4c1d95; }
    .cover-kpis span, .kpis span { font-size: 8.5pt; color: #6b7280; }
    .kpis { display: flex; gap: 10px; margin: 10px 0; } .kpis b { display: block; font-size: 16pt; color: #4c1d95; }
    .meta { color: #6b7280; font-size: 9pt; }
    .tocl { columns: 2; font-size: 10.5pt; list-style: none; margin: 0; } .tocl li { margin: 3px 0; } .tocl span { display: inline-block; width: 24px; color: #6366f1; font-weight: 600; }
    p { margin: 0 0 7px; } ul, ol { margin: 4px 0 8px 18px; padding: 0; } li { margin: 2px 0; }
    code { font-family: "JetBrains Mono", Consolas, monospace; font-size: 8.6pt; background: #f3f4f6; padding: 0 3px; border-radius: 3px; }
    pre { font-family: "JetBrains Mono", Consolas, monospace; font-size: 8pt; background: #0f172a; color: #e2e8f0; padding: 10px 12px; border-radius: 8px; white-space: pre-wrap; break-inside: avoid; }
    table { width: 100%; border-collapse: collapse; margin: 8px 0 12px; font-size: 9pt; break-inside: auto; }
    th { text-align: left; background: #eef2ff; color: #3730a3; font-weight: 600; padding: 5px 6px; border-bottom: 1px solid #c7d2fe; }
    td { padding: 4px 6px; border-bottom: 1px solid #e5e7eb; vertical-align: top; }
    tr { break-inside: avoid; }
    table.small { font-size: 8.4pt; } table.tiny { font-size: 7.4pt; } table.tiny td, table.tiny th { padding: 2px 4px; }
    svg { margin: 6px 0 10px; break-inside: avoid; display: block; }
    .callout { border-left: 4px solid #6366f1; background: #f5f3ff; padding: 8px 12px; border-radius: 6px; margin: 8px 0; }
    .callout.warn { border-left-color: #d97706; background: #fffbeb; }
    .pos { color: #047857; font-weight: 600; } .neg { color: #b91c1c; font-weight: 600; }
    ul.small { font-size: 9pt; }
    """
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>NeuroCompiler — complete project report</title>
<style>{css}</style></head><body>{''.join(parts)}</body></html>"""


def chrome() -> list[str] | None:
    for c in ("google-chrome", "chromium", "chromium-browser"):
        if shutil.which(c):
            return [shutil.which(c)]
    win = Path("/mnt/c/Program Files/Google/Chrome/Application/chrome.exe")
    if win.exists():
        return [str(win)]
    edge = Path("/mnt/c/Program Files (x86)/Microsoft/Edge/Application/msedge.exe")
    return [str(edge)] if edge.exists() else None


def main() -> None:
    OUT.mkdir(exist_ok=True)
    htmlp = OUT / "NeuroCompiler_Report.html"
    pdfp = OUT / "NeuroCompiler_Report.pdf"
    htmlp.write_text(build_html())
    print(f"wrote {htmlp}")
    exe = chrome()
    if not exe:
        print("no Chrome/Chromium/Edge found: open the HTML and print it to PDF")
        return
    if exe[0].startswith("/mnt/"):                      # Windows browser: work in a Windows temp folder
        tmpw = Path("/mnt/c/Users/Public/nc_report_tmp")
        tmpw.mkdir(exist_ok=True)
        shutil.copy2(htmlp, tmpw / htmlp.name)
        winp = "C:\\Users\\Public\\nc_report_tmp\\"
        src, dst = f"file:///C:/Users/Public/nc_report_tmp/{htmlp.name}", winp + pdfp.name
        out = tmpw / pdfp.name
    else:
        src, dst, out = htmlp.as_uri(), str(pdfp), pdfp
    subprocess.run(exe + ["--headless=new", "--disable-gpu", "--no-pdf-header-footer", f"--print-to-pdf={dst}", src],
                   capture_output=True, timeout=180)
    if out != pdfp:
        shutil.copy2(out, pdfp)
        shutil.rmtree(out.parent, ignore_errors=True)
    print(f"wrote {pdfp} ({pdfp.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
