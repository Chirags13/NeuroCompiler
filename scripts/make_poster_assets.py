#!/usr/bin/env python3
"""Build the poster images (docs/poster/*.png), one per template section, plus a filled preview of the layout.

Numbers come from dashboard/static/data/research.json and the saved interpreter run, the same sources as the report.
The text of each section is in docs/poster/Poster_Content.md, and the preview reads it from TEXT below.
Images are printed with headless Chrome at 3x, on white.

Usage: .venv/bin/python scripts/make_poster_assets.py
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import make_report_pdf as R  # noqa: E402  (data, chrome())

REPO = R.REPO
D = R.D
OUT = REPO / "docs/poster"
FONTS = REPO / "dashboard/static/vendor/fonts"
TMP, WTMP = Path("/mnt/c/Users/Public/nc_poster_tmp"), "C:\\Users\\Public\\nc_poster_tmp\\"
NAVY, BLUE, TEAL, PURPLE, ORANGE, RED, PINK, GREEN = "#2a1458", "#1b7fb5", "#0f9d8a", "#6b3fa0", "#f39c12", "#e6003c", "#f25c78", "#16a34a"

H = D["headline"]["tune_rlsl"]
DEMO = json.loads((REPO / "dashboard/saved/tune-interpreter-loop-3-83x-rl-pick.json").read_text())["result"]
O3_MS, PICK_MS, DEMO_X = DEMO["confirm"]["base_median_ms"], DEMO["confirm"]["pick_median_ms"], DEMO["confirm"]["speedup"]

BASE = f"""
@font-face{{font-family:Inter;font-weight:400;src:url(inter-400.woff2)}}@font-face{{font-family:Inter;font-weight:500;src:url(inter-500.woff2)}}
@font-face{{font-family:Inter;font-weight:600;src:url(inter-600.woff2)}}@font-face{{font-family:Inter;font-weight:700;src:url(inter-700.woff2)}}
@font-face{{font-family:Mono;font-weight:400;src:url(jbmono-400.woff2)}}@font-face{{font-family:Mono;font-weight:500;src:url(jbmono-500.woff2)}}
*{{box-sizing:border-box}} html,body{{margin:0;background:#fff;font-family:Inter,Arial,sans-serif;color:{NAVY}}}
"""


def icon(kind: str, c: str = "#fff", s: int = 44) -> str:
    p = {
        "code": f'<path d="M17 16 7 25l10 9M31 16l10 9-10 9M27 11l-6 28" fill="none" stroke="{c}" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>',
        "db": f'<ellipse cx="24" cy="12" rx="16" ry="6" fill="{c}"/><path d="M8 12v24c0 3.3 7 6 16 6s16-2.7 16-6V12c0 3.3-7 6-16 6S8 15.300 8 12z" fill="{c}" opacity=".78"/>',
        "filter": f'<path d="M6 9h36L28 26v14l-8 4V26z" fill="{c}"/>',
        "brain": f'<circle cx="24" cy="24" r="6" fill="{c}"/>' + "".join(f'<circle cx="{x}" cy="{y}" r="4" fill="{c}"/><line x1="24" y1="24" x2="{x}" y2="{y}" stroke="{c}" stroke-width="2.6"/>' for x, y in [(9, 11), (39, 11), (9, 37), (39, 37), (24, 5), (24, 43)]),
        "watch": f'<rect x="20" y="3" width="8" height="5" rx="1" fill="{c}"/><circle cx="24" cy="27" r="17" fill="none" stroke="{c}" stroke-width="4"/><path d="M24 27V16" stroke="{c}" stroke-width="4" stroke-linecap="round"/>',
        "rocket": f'<path d="M24 3c8 6 11 15 9 26H15C13 18 16 9 24 3z" fill="{c}"/><path d="M15 25l-7 9 8-1zM33 25l7 9-8-1z" fill="{c}" opacity=".8"/><path d="M20 33h8l-4 11z" fill="{c}" opacity=".7"/><circle cx="24" cy="17" r="4" fill="#fff" opacity=".85"/>',
        "chart": f'<rect x="7" y="26" width="8" height="15" fill="{c}"/><rect x="20" y="16" width="8" height="25" fill="{c}"/><rect x="33" y="7" width="8" height="34" fill="{c}"/>',
        "user": f'<circle cx="24" cy="15" r="9" fill="{c}"/><path d="M7 43c1-12 8-17 17-17s16 5 17 17z" fill="{c}"/>',
        "sci": f'<path d="M19 5h10M21 5v14L9 38c-1.600 3 0 5 3 5h24c3 0 4.600-2 3-5L27 19V5" fill="none" stroke="{c}" stroke-width="4" stroke-linejoin="round"/><path d="M15 31h18l5 10H10z" fill="{c}"/>',
        "term": f'<rect x="4" y="8" width="40" height="32" rx="4" fill="none" stroke="{c}" stroke-width="4"/><path d="M12 18l7 6-7 6M24 31h11" fill="none" stroke="{c}" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>',
        "cloud": f'<path d="M14 38C7 38 3 33 3 28c0-6 5-10 10-10 2-7 8-11 14-11 8 0 14 6 14 14 4 1 6 4 6 8 0 5-4 9-9 9z" fill="{c}"/>',
        "gear": f'<circle cx="24" cy="24" r="8" fill="none" stroke="{c}" stroke-width="5"/>' + "".join(f'<rect x="21" y="3" width="6" height="9" fill="{c}" transform="rotate({a} 24 24)"/>' for a in range(0, 360, 45)),
        "book": f'<path d="M24 11C19 6 11 6 5 8v31c6-2 14-2 19 3 5-5 13-5 19-3V8c-6-2-14-2-19 3z" fill="none" stroke="{c}" stroke-width="4" stroke-linejoin="round"/><path d="M24 11v31" stroke="{c}" stroke-width="4"/>',
    }[kind]
    return f'<svg width="{s}" height="{s}" viewBox="0 0 48 48">{p}</svg>'


ARROW = f'<svg width="46" height="30" viewBox="0 0 46 30"><path d="M0 9h26V1l18 14-18 14v-8H0z" fill="{BLUE}"/></svg>'


# ------------------------------------------------------------------ section images
def architecture() -> str:
    def rows():
        items = [("Static + dynamic features", "#e7dbf5"), ("PPO agent proposes 24 pipelines", "#fbe3f0"), ("LightGBM ranks ≈940 candidates", "#dbeafe"), ("Top 8: compile · verify · time", "#fdeecb")]
        return "".join(f'<div style="background:{c};font-weight:600;font-size:20px;padding:9px 8px;margin-top:8px;border-radius:4px;text-align:center">{t}</div>' for t, c in items)

    def block(ic, bg, title, sub):
        return f'''<div style="width:232px;text-align:center"><div style="width:120px;height:120px;border-radius:50%;background:{bg};display:flex;align-items:center;justify-content:center;margin:0 auto">{icon(ic, s=68)}</div>
        <div style="font-weight:700;font-size:22px;color:{BLUE};margin-top:12px;line-height:1.2">{title}</div><div style="font-size:19px;color:#374151;margin-top:5px;line-height:1.3">{sub}</div></div>'''
    return f'''<div style="width:1400px;height:440px;display:flex;align-items:center;justify-content:space-between;padding:14px 18px">
      {block("code", BLUE, "INPUT PROGRAM", "C / C++ source,<br>arguments and stdin")}{ARROW}
      <div style="width:410px;border:2px solid #b9a7d9;background:#f7f3fc;border-radius:12px;padding:14px 16px">
        <div style="text-align:center;font-weight:700;font-size:21px">NEUROCOMPILER CORE</div>{rows()}</div>{ARROW}
      <div style="width:232px;text-align:center"><div style="width:120px;height:120px;border-radius:50%;background:{GREEN};display:flex;align-items:center;justify-content:center;margin:0 auto">{icon("watch", s=70)}</div>
        <div style="font-weight:700;font-size:22px;color:{BLUE};margin-top:12px;line-height:1.2">CONFIRMED OUTPUT</div><div style="font-size:19px;color:#374151;margin-top:5px;line-height:1.3">fresh 20-round test;<br>faster binary, or -O3</div></div>{ARROW}
      {block("user", PURPLE, "CLI + DASHBOARD", "runtimes in ms and<br>every changed pass")}</div>'''


def methodology() -> str:
    steps = [("Data Collection", "146 real programs from PolyBench and the LLVM test-suite", "#d6e8f7", BLUE, "db"),
             ("Data Preprocessing", "Quality filters, 35 families, frozen train / val / test split", "#d7f0df", TEAL, "filter"),
             ("Model Development", "Search → 70,409 candidates → LightGBM + PPO", "#f9ecc9", "#b7791f", "brain"),
             ("Testing & Evaluation", "33 unseen programs, serial timing, A/A noise control", "#fbdfe3", "#c8506a", "watch"),
             ("Deployment", "Command-line tool + live web dashboard", "#e8dcf6", PURPLE, "rocket")]
    h = ""
    for i, (t, d, bg, c, ic) in enumerate(steps):
        h += f'''<div style="width:232px;height:400px;background:{bg};border-radius:12px;padding:16px 12px;text-align:center;display:flex;flex-direction:column;align-items:center">
          <div style="font-weight:700;font-size:23px;line-height:1.15;height:56px;display:flex;align-items:center">{t}</div>
          <div style="width:112px;height:112px;background:{c};border-radius:20px;display:flex;align-items:center;justify-content:center;margin-top:10px">{icon(ic, s=72)}</div>
          <div style="font-size:22px;color:#1f2937;margin-top:14px;line-height:1.3">{d}</div></div>'''
        if i < 4:
            h += '<svg width="24" height="26" viewBox="0 0 24 26"><path d="M0 7h12V0l12 13-12 13v-7H0z" fill="#c5b2e6"/></svg>'
    return f'<div style="width:1400px;height:440px;display:flex;align-items:center;justify-content:space-between;padding:14px 12px">{h}</div>'


def chart() -> str:
    ev = D["eval"]["summary"]
    order = [("tune RL + SL", "Ours<br>(RL + SL)", RED), ("tune top-8 (SL)", "LightGBM +<br>timing", BLUE), ("random search@8", "Random<br>search", "#9ca3af"),
             ("RL only", "PPO<br>only", PINK), ("GA@8", "Genetic<br>algorithm", ORANGE), ("random top-8", "Random<br>shortlist", "#9ca3af"), ("-O2", "clang<br>-O2", NAVY), ("-Os", "clang<br>-Os", NAVY)]
    W, Hh, x0, y0, y1 = 960, 490, 66, 22, 372
    lo, hi = -7, 19
    sy = lambda p: y1 - (p - lo) / (hi - lo) * (y1 - y0)
    bw, step = 66, (W - x0 - 10) / len(order)
    s = [f'<svg width="{W}" height="{Hh}" viewBox="0 0 {W} {Hh}" font-family="Inter">']
    for t in (-5, 0, 5, 10, 15):
        s.append(f'<line x1="{x0}" x2="{W}" y1="{sy(t)}" y2="{sy(t)}" stroke="{"#374151" if t == 0 else "#e5e7eb"}" stroke-width="{1.6 if t == 0 else 1}"/><text x="{x0 - 8}" y="{sy(t) + 5}" text-anchor="end" font-size="16" fill="#4b5563">{t:+d}%</text>')
    for i, (k, lab, c) in enumerate(order):
        v = ev[k]
        p, a, b = (v["geomean"] - 1) * 100, (v["ci"][0] - 1) * 100, (v["ci"][1] - 1) * 100
        x = x0 + step * i + (step - bw) / 2
        top = min(sy(p), sy(0))
        s.append(f'<rect x="{x}" y="{top}" width="{bw}" height="{abs(sy(p) - sy(0))}" fill="{c}" rx="3"/>')
        cx = x + bw / 2
        s.append(f'<path d="M{cx} {sy(a)}V{sy(b)}M{cx - 7} {sy(a)}h14M{cx - 7} {sy(b)}h14" stroke="#111827" stroke-width="1.8" fill="none"/>')
        s.append(f'<text x="{cx}" y="{(sy(b) - 8) if p >= 0 else (sy(a) + 22)}" text-anchor="middle" font-size="19" font-weight="700" fill="{c if c != "#9ca3af" else "#4b5563"}">{p:+.2f}%</text>')
        for j, ln in enumerate(lab.split("<br>")):
            s.append(f'<text x="{cx}" y="{424 + j * 20}" text-anchor="middle" font-size="18" font-weight="{700 if i == 0 else 500}" fill="#1f2937">{ln}</text>')
    s.append('</svg>')
    return (f'<div style="width:980px;padding:8px 10px;background:#fff">' + "".join(s) +
            '<div style="font-size:19px;color:#4b5563;margin-top:0">Geomean speedup vs clang -O3 on 33 unseen programs (11 families). Whiskers: 95% CI.</div></div>')


def kpis() -> str:
    items = [(f"+{(H['geomean'] - 1) * 100:.2f}%", "faster than -O3 (geomean)", RED), (f"+{(H['excl_largest'] - 1) * 100:.2f}%", "without the largest win", BLUE),
             (f"{H['slower']} / {H['n']}", "programs measurably slower", GREEN), (f"{H['ge5']} / {H['n']}", "programs ≥ 5% faster", PURPLE)]
    return '<div style="width:1000px;display:flex;gap:14px;padding:8px">' + "".join(
        f'<div style="flex:1;border:2px solid {c};border-radius:12px;padding:12px 8px;text-align:center"><div style="font-size:36px;font-weight:700;color:{c}">{v}</div><div style="font-size:18px;color:#374151;margin-top:2px">{t}</div></div>' for v, t, c in items) + "</div>"


def sample_input() -> str:
    lines = ["<c>/* evalloop.c: a bytecode interpreter */</c>", "<k>void</k> eval(<k>int</k> *p) {", "  <k>static void</k> *dispatch[32] = {", "    &amp;&amp;L0, ... &amp;&amp;L31 };",
             "  <k>while</k> (1) {", "    <k>switch</k> (*p++) {", "      TARGET(1) { execute(opcode);", "        <k>goto</k> *dispatch[*p++]; }", "      ..."]
    code = "<br>".join(ln.replace(" ", "&nbsp;") .replace("<k>", '<span style="color:#c4a7ff">').replace("</k>", "</span>").replace("<c>", '<span style="color:#7c8aa5">').replace("</c>", "</span>").replace("<span&nbsp;", "<span ") for ln in lines)
    return f'''<div style="width:560px;height:400px;background:#0f1424;border-radius:10px;padding:22px 24px;color:#eef1f8;font-family:Mono;font-size:21px;line-height:1.42;overflow:hidden">{code}</div>'''


def sample_output() -> str:
    rel = PICK_MS / O3_MS * 100
    return f'''<div style="width:560px;height:400px;background:#fff;border:2px solid #d1d5db;border-radius:10px;padding:14px 22px">
      <div style="font-size:72px;font-weight:700;color:{GREEN};line-height:1">{DEMO_X:.2f}×</div><div style="font-size:21px;font-weight:600;margin-top:2px">faster · confirmed in a fresh 20-round run</div>
      <div style="margin-top:12px;font-family:Mono;font-size:20px">clang -O3</div><div style="display:flex;align-items:center;gap:10px"><div style="height:34px;width:100%;background:#94a3b8;border-radius:4px;flex:0 0 76%"></div><b style="font-size:23px">{O3_MS:.1f} ms</b></div>
      <div style="margin-top:10px;font-family:Mono;font-size:19px">NeuroCompiler (RL pick)</div><div style="display:flex;align-items:center;gap:10px"><div style="height:34px;background:{GREEN};border-radius:4px;flex:0 0 {76 * rel / 100:.1f}%"></div><b style="font-size:23px">{PICK_MS:.1f} ms</b></div>
      <div style="font-size:19px;color:#4b5563;margin-top:10px;line-height:1.25">Pick deletes every simplifycfg, the pass that merges this interpreter's dispatch jumps. Demo program, not in the 33-program test.</div></div>'''


APPS = [("sci", "#e6003c", "Scientific Computing", "linear-algebra kernels"), ("term", "#f39c12", "Language Runtimes", "interpreters, VMs"),
        ("cloud", "#22a24a", "Cloud Workloads", "less CPU time per job"), ("gear", "#7c3aed", "Build Pipelines", "per-program tuning"), ("book", "#1e88e5", "Compiler Research", "pipeline data")]


def app_html(i, scale=1.0):
    ic, c, t, s = APPS[i]
    return f'''<div style="width:{190 * scale}px;text-align:center"><div style="width:{104 * scale}px;height:{104 * scale}px;background:{c};border-radius:50%;display:flex;align-items:center;justify-content:center;margin:0 auto">{icon(ic, s=int(62 * scale))}</div>
      <div style="font-weight:700;font-size:{19 * scale}px;color:{BLUE};margin-top:{8 * scale}px;line-height:1.15">{t}</div><div style="font-size:{15 * scale}px;color:#4b5563;margin-top:{3 * scale}px">{s}</div></div>'''


def applications() -> str:
    return '<div style="width:1000px;display:flex;justify-content:space-between;padding:10px 6px">' + "".join(app_html(i) for i in range(5)) + "</div>"


TEXT = {
    "abstract": f"Every program compiled with <b>-O3</b> gets the same 109 LLVM passes in the same order. <b>NeuroCompiler</b> finds a faster recipe for each program. A reinforcement-learning agent (PPO) proposes pipelines, a LightGBM model ranks them, and real timing picks the winner. On 33 unseen programs it runs <b>8.09% faster than -O3</b> (+4.92% without the largest win), with <b>none measurably slower</b>.",
    "problem": "One fixed compiler recipe cannot suit every program: the same edit makes some programs faster and others slower. Testing every option is impossible, and easy metrics mislead. Across 18,637 timed candidates, IR instruction count barely predicted runtime (ρ = −0.08). <b>Can we find a faster pipeline per program, and prove it?</b>",
    "objectives": ["Build a timing harness precise to within 1%", "Collect 146 real programs, split by family", "Train LightGBM and PPO to shortlist pipelines", "Beat -O3 on unseen programs, with identical output", "Ship a CLI and a live dashboard"],
    "conclusion": "<b>-O3 can be beaten, program by program, with proof.</b> Models shortlist and the stopwatch decides: +8.09% over -O3 on unseen programs, none slower. RL's extra gain over LightGBM was +0.2% (not significant); measurement gives the reliability.",
    "future": "<b>Next:</b> hardware counters on bare metal, graph neural program features, RL trained on real timings, per-function tuning.",
}


# ------------------------------------------------------------------ preview in the template's layout
def preview() -> str:
    def head(t, c, h=30):
        return f'<div style="background:{c};color:#fff;font-weight:700;font-size:20px;padding:6px 12px;height:{h + 8}px">{t}</div>'

    def box(t, c, body, style):
        return f'<div style="border:1px solid #b9a7d9;border-radius:6px;overflow:hidden;background:#fff;{style}">{head(t, c)}<div style="padding:8px 12px;font-size:14.3px;line-height:1.36;color:#1f2937">{body}</div></div>'
    obj = '<ul style="margin:0;padding-left:17px">' + "".join(f"<li>{o}</li>" for o in TEXT["objectives"]) + "</ul>"
    apps = '<div style="display:flex;justify-content:space-between;zoom:.62">' + "".join(app_html(i) for i in range(5)) + "</div>"
    return f'''<div style="width:1250px;padding:12px;background:#fff;display:grid;grid-template-columns:repeat(12,1fr);gap:9px">
      {box("ABSTRACT", RED, TEXT["abstract"], "grid-column:span 4")}
      {box("PROBLEM STATEMENT", ORANGE, TEXT["problem"], "grid-column:span 4")}
      {box("OBJECTIVES", PURPLE, obj, "grid-column:span 4")}
      <div style="grid-column:span 6;border:1px solid #b9a7d9;border-radius:6px;overflow:hidden">{head("SYSTEM ARCHITECTURE / BLOCK DIAGRAM", NAVY)}<img src="01_architecture.png" style="width:100%;display:block"></div>
      <div style="grid-column:span 6;border:1px solid #b9a7d9;border-radius:6px;overflow:hidden">{head("METHODOLOGY", ORANGE)}<img src="02_methodology.png" style="width:100%;display:block"></div>
      <div style="grid-column:span 7;border:1px solid #b9a7d9;border-radius:6px;overflow:hidden">{head("RESULTS AND PERFORMANCE ANALYSIS", NAVY)}
        <div style="display:flex;gap:8px;padding:6px"><div style="width:53%"><div style="font-weight:700;color:{BLUE};font-size:14px">PERFORMANCE COMPARISON</div><img src="03_performance_chart.png" style="width:100%;display:block"><img src="04_key_numbers.png" style="width:100%;display:block"></div>
        <div style="width:47%"><div style="font-weight:700;color:{BLUE};font-size:14px">SAMPLE OUTPUT: INTERPRETER DEMO</div><div style="display:flex;align-items:center;gap:6px;margin-top:6px"><div style="flex:1;text-align:center;font-weight:700;font-size:13px">INPUT<img src="05_sample_input.png" style="width:100%;display:block;margin-top:3px"></div>{ARROW.replace('width="46"', 'width="24"')}<div style="flex:1;text-align:center;font-weight:700;font-size:13px">OUTPUT<img src="06_sample_output.png" style="width:100%;display:block;margin-top:3px"></div></div></div></div></div>
      <div style="grid-column:span 5;display:flex;flex-direction:column;gap:9px">{box("CONCLUSION AND FUTURE WORK", NAVY, TEXT["conclusion"] + '<div style="margin-top:6px">' + TEXT["future"] + "</div>", "")}
        <div style="border:1px solid #b9a7d9;border-radius:6px;overflow:hidden;flex:1">{head("APPLICATIONS", PINK)}<div style="padding:8px 6px">{apps}</div></div></div>
    </div>'''


# ------------------------------------------------------------------ render
def shot(body: str, name: str, w: int, h: int, scale: int = 3) -> None:
    (TMP / f"{name}.html").write_text(f"<!doctype html><meta charset=utf-8><style>{BASE}</style><body>{body}</body>")
    exe = R.chrome()
    subprocess.run(exe + ["--headless=new", "--disable-gpu", "--hide-scrollbars", f"--force-device-scale-factor={scale}", f"--window-size={w},{h}",
                          "--default-background-color=ffffffff", "--virtual-time-budget=3000", f"--screenshot={WTMP}{name}.png", f"file:///C:/Users/Public/nc_poster_tmp/{name}.html"],
                   capture_output=True, timeout=120)
    shutil.copy2(TMP / f"{name}.png", OUT / f"{name}.png")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    shutil.rmtree(TMP, ignore_errors=True)
    TMP.mkdir()
    for f in FONTS.glob("*.woff2"):
        shutil.copy2(f, TMP / f.name)
    shot(architecture(), "01_architecture", 1400, 440)
    shot(methodology(), "02_methodology", 1400, 440)
    shot(chart(), "03_performance_chart", 1000, 560)
    shot(kpis(), "04_key_numbers", 1016, 130)
    shot(sample_input(), "05_sample_input", 560, 400)
    shot(sample_output(), "06_sample_output", 560, 400)
    shot(applications(), "07_applications", 1016, 210)
    for i, a in enumerate(APPS):
        shot(f'<div style="padding:8px">{app_html(i, 1.5)}</div>', f"08_app_{i + 1}_{a[2].split()[0].lower()}", 300, 280)
    for f in OUT.glob("0[1-7]*.png"):
        shutil.copy2(f, TMP / f.name)
    shot(preview(), "Poster_Preview", 1274, 850, 2)
    shutil.rmtree(TMP, ignore_errors=True)
    print(sorted(p.name for p in OUT.glob("*.png")))


if __name__ == "__main__":
    main()
