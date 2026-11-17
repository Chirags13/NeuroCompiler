"""Build open_day/NeuroCompiler_Open_Day.pptx and SPEAKING_SCRIPT.md from the project's real data.

Run from the repo root:  open_day/.pptxenv/bin/python open_day/build_deck.py
Every result number comes from dashboard/static/data/research.json, a saved run, or a log in open_day/assets/runs/.
"""
import json
import math
import random
import sys
from pathlib import Path

sys.path.insert(0, "open_day")
from deck_lib import *  # noqa: E402,F403
from notes import NOTES, QA, PITCH, TOUR  # noqa: E402

R = json.load(open("dashboard/static/data/research.json"))
RUN = json.load(open("dashboard/saved/tune-interpreter-loop-3-83x-rl-pick.json"))["result"]
PASSES = json.load(open("open_day/assets/pipeline_order.json"))
OUT = Path("open_day")
A = OUT / "assets"
EV = R["eval"]
SUM = EV["summary"]
RS = SUM["tune RL + SL"]


def pct(v, sign=True):
    return f"{(v - 1) * 100:+.2f}%" if sign else f"{(v - 1) * 100:.2f}%"


make_background(A / "bg.jpg")
prs = new_deck(A / "bg.jpg")
LAY = prs.slide_layouts[5]    # Title Only: every slide keeps a real title for outline view and screen readers
n_slide = 0


def slide(title, act, source=None, **kw):
    global n_slide
    n_slide += 1
    s = prs.slides.add_slide(LAY)
    add_title(s, title, **kw)
    chrome(s, act, n_slide, source)
    add_fade(s)
    s.notes_slide.notes_text_frame.text = NOTES[n_slide]["say"] + "\n\nEvidence: " + NOTES[n_slide]["evidence"]
    return s


def card(s, x, y, w, h, head, body, color=AMBER, hsize=20, bsize=16, fill=PANEL):
    box(s, x, y, w, h, fill=fill, line=LINE, radius=0.1)
    box(s, x, y + 0.14, 0.05, h - 0.28, fill=color, radius=0)
    tx(s, x + 0.24, y + 0.16, w - 0.42, 0.45, head, size=hsize, font=DISPLAY_B, color=TEXT)
    tx(s, x + 0.24, y + 0.16 + hsize * 0.0205, w - 0.42, h - 0.6, body, size=bsize, color=MUTE, spacing=1.0, after=4)


# ------------------------------------------------------------ 1 cold open
s = slide("Same code.\n3.83× faster.", 0, y=0.8, h=2.8, size=88)
c = RUN["confirm"]
base, pick = c["base_median_ms"], c["pick_median_ms"]
tx(s, 7.25, 1.35, 5.5, 1.6, "Not one line of the program changed.", size=32, font=DISPLAY, color=MUTE, spacing=0.98)
bx, bw = 2.15, W - M - 2.15
tx(s, M, 3.92, 1.5, 0.75, "-O3", size=26, font=DISPLAY_B, color=SLATE, anchor="m")
box(s, bx, 3.92, bw, 0.75, fill="39424F", radius=0.04, content=f"{base:.1f} ms", size=26, font=DISPLAY_B, align="r", inset=0.2, name="-O3 runtime bar")
tx(s, M, 4.87, 1.55, 0.75, "Tuned", size=26, font=DISPLAY_B, color=AMBER, anchor="m")
bar2 = bw * pick / base
box(s, bx, 4.87, bar2, 0.75, fill=AMBER, radius=0.04, name="Tuned runtime bar")
tx(s, bx + bar2 + 0.18, 4.87, 3, 0.75, f"{pick:.1f} ms", size=26, font=DISPLAY_B, color=AMBER, anchor="m")
tx(s, M, 6.02, W - 2 * M, 0.75,
   f"Best-case demo: an interpreter loop from our validation set, not part of the test result. Confirmed on a fresh 20-round run, "
   f"95% CI {c['ci'][0]:.2f}–{c['ci'][1]:.2f}×, identical-binary control {c['control']:.2f}×. The fair average comes later.",
   size=15, color=MUTE)

# ------------------------------------------------------------ 2 title
s = slide("NeuroCompiler", 0, y=1.28, h=1.5, size=92, color=TEXT)
tx(s, M, 2.72, 11.6, 0.6, "A faster compiler recipe for each program, proved by a stopwatch.", size=28, font=DISPLAY, color=AMBER)
strip(s, PASSES, M, 3.62, W - 2 * M, 0.72)
tx(s, M, 4.42, 9, 0.3, "Each tick is one real pass in LLVM's -O3 pipeline", size=13, color=MUTE, font=MONO)
team = [("Chirag S", "1JS23CS039"), ("Dhanush Singh", "1JS23CS048"), ("Gagan S Shamnur", "1JS23CS052"), ("Nithin Choudhary A", "1JS23CS101")]
for i, (nm, usn) in enumerate(team):
    x = M + i * 2.3
    tx(s, x, 5.1, 2.35, 0.34, nm, size=18, font=BODY_B)
    tx(s, x, 5.44, 2.35, 0.28, usn, size=13, color=MUTE, font=MONO)
tx(s, M + 9.55, 5.1, 2.6, 0.34, "Dr. P.B. Mallikarjuna", size=18, font=BODY_B, color=AMBER)
tx(s, M + 9.55, 5.44, 2.6, 0.28, "Project guide, Professor", size=13, color=MUTE)
box(s, M, 6.0, 0.72, 0.72, fill="FFFFFF", radius=0.08, name="Logo tile")
s.shapes.add_picture("docs/assets/jss_logo.png", Inches(M + .05), Inches(6.05), height=Inches(.62))
box(s, M + 0.84, 6.0, 0.72, 0.72, fill="FFFFFF", radius=0.08, name="Logo tile")
s.shapes.add_picture("docs/assets/vtu_logo.png", Inches(M + .89), Inches(6.05), height=Inches(.62))
tx(s, M + 1.78, 6.02, 10, 0.7, ["Department of Computer Science & Engineering", "JSS Academy of Technical Education, Bengaluru  |  Visvesvaraya Technological University  |  2026-27"],
   size=15, color=MUTE, spacing=1.0)

# ------------------------------------------------------------ 3 recipe
s = slide("Every program gets the same 109-step recipe", 1, source="LLVM 18.1.8 default<O3>, printed by opt")
tx(s, M, 1.62, 11.8, 0.8, "A compiler improves your code through passes, small transformations applied in order. -O3 uses one fixed order, whatever the program does.",
   size=20, color=MUTE)
box(s, M, 3.0, 1.45, 1.3, fill=RAISED, line=LINE, content=[[("source", {"font": MONO, "size": 17})], [("your program", {"size": 13, "color": MUTE})]], radius=0.1)
strip(s, PASSES, 2.3, 3.0, W - 2.3 - 2.3, 1.3)
box(s, W - M - 1.45, 3.0, 1.45, 1.3, fill=RAISED, line=LINE, content=[[("binary", {"font": MONO, "size": 17})], [("what runs", {"size": 13, "color": MUTE})]], radius=0.1)
arrow(s, 2.08, 3.65, 2.26, 3.65)
arrow(s, W - 2.28, 3.65, W - 2.08, 3.65)
leg = [("cleanup", "Clean-up and simplify"), ("loop", "Loop transforms"), ("vector", "Vectorization"), ("inter", "Inlining, whole-program"), ("other", "Other")]
x = 2.3
for k, lb in leg:
    box(s, x, 4.5, 0.17, 0.17, fill=GROUP_COLOR[k], radius=0)
    tx(s, x + 0.25, 4.43, min(1.9, W - M - x - 0.25), 0.3, lb, size=13, color=MUTE)
    x += 0.48 + len(lb) * 0.1
facts = [("109", "pass steps, always in this order"), ("76", "distinct passes"), ("8×", "simplifycfg runs, and instcombine too")]
for i, (a, b) in enumerate(facts):
    x = M + i * 4.1
    tx(s, x, 5.1, 1.5, 0.95, a, size=54, font=DISPLAY_B, color=AMBER, anchor="m")
    tx(s, x + {"109": 1.4, "76": 1.0, "8×": 1.0}[a], 5.1, 2.5, 0.95, b, size=17, color=MUTE, anchor="m")
tx(s, M, 6.25, 11.8, 0.5, "One recipe for every dish. Excellent on average, tailored to nothing.", size=22, font=DISPLAY, color=TEXT)

# ------------------------------------------------------------ 4 same edit
s = slide("The same edit helps one program, hurts another", 1, source="31 programs. Range: screening. Counts: confirmed. results/passkb_attribution_*.csv")
KB = {t["label"]: t for t in R["kb"]["top"]}
rows = [("-force-vector-width=8", "Vectorize 8 lanes wide"), ("-force-vector-width=2", "Vectorize 2 lanes wide"), ("del EVERY simplifycfg", "Delete every simplifycfg"),
        ("-unroll-count=8", "Force loop unroll 8×"), ("-unroll-count=2", "Force loop unroll 2×"), ("del EVERY instcombine", "Delete every instcombine")]
ax0, axw, lo, hi = 4.15, 6.3, 0.7, 7.0
fx = lambda v: ax0 + axw * math.log(v / lo) / math.log(hi / lo)
top, rh = 2.2, 0.66
for i, (key, lb) in enumerate(rows):
    k = KB[key]
    y = top + i * rh
    tx(s, M, y, 3.4, 0.5, lb, size=19, anchor="m")
    box(s, fx(k["min"]), y + 0.1, fx(1) - fx(k["min"]), 0.3, fill=RED, radius=0, name=f"{lb}: slowest {k['min']:.2f}x")
    box(s, fx(1), y + 0.1, fx(k["max"]) - fx(1), 0.3, fill=GREEN, radius=0, name=f"{lb}: fastest {k['max']:.2f}x")
    tx(s, fx(k["min"]) - 0.88, y, 0.76, 0.5, f"{k['min']:.2f}×", size=14, color=RED, font=MONO, align="r", anchor="m")
    tx(s, fx(k["max"]) + 0.12, y, 0.9, 0.5, f"{k['max']:.2f}×", size=14, color=GREEN, font=MONO, anchor="m")
    tx(s, 11.3, y, 0.7, 0.5, f"+{k['faster']}", size=20, font=DISPLAY_B, color=GREEN, align="c", anchor="m")
    tx(s, 11.95, y, 0.75, 0.5, f"−{k['slower']}" if k["slower"] else "0", size=20, font=DISPLAY_B, color=RED, align="c", anchor="m")
box(s, fx(1) - 0.008, 1.95, 0.016, 4.2, fill=TEXT, radius=0)
tx(s, fx(1) - 0.75, 1.62, 1.5, 0.3, "-O3 = 1.00×", size=14, color=TEXT, font=MONO, align="c")
tx(s, 11.2, 1.56, 1.55, 0.55, ["confirmed", "faster / slower"], size=12, color=MUTE, align="c", spacing=0.95)
tx(s, M, 6.27, 11.8, 0.5, "There is no universally better recipe. The right one depends on the program.", size=22, font=DISPLAY)

# ------------------------------------------------------------ 5 try everything
s = slide("Why not just try everything?", 1, source="Calculated from 346 catalogued edits; bars not to scale. Ashouri et al., ACM CSUR 2018")
N = R["kb"]["edits"]
comb = [N, math.comb(N, 2), math.comb(N, 3), math.comb(N, 4)]
lab = ["1 edit", "2 edits", "3 edits", "4 edits"]
wd = [0.75, 2.3, 4.0, 5.9]
for i in range(4):
    y = 1.95 + i * 1.02
    col = AMBER if i == 3 else "39424F"
    box(s, M, y, wd[i], 0.82, fill=col, radius=0.04)
    tx(s, M + wd[i] + 0.16, y - 0.02, 3.0, 0.5, f"{comb[i]:,}" if i < 3 else "", size=24, font=DISPLAY_B, color=TEXT, anchor="m")
    tx(s, M + wd[i] + 0.16, y + 0.42, 2, 0.34, lab[i] if i < 3 else "", size=14, color=MUTE)
tx(s, M + 0.15, 4.98, 3, 0.82, "4 edits", size=20, font=DISPLAY_B, color=INK, anchor="m")
secs = comb[3]
yrs = secs / (365.25 * 24 * 3600)
tx(s, 7.15, 1.95, 5.6, 1.15, f"{comb[3] / 1e6:.0f} million", size=66, font=DISPLAY_B, color=AMBER, anchor="m")
tx(s, 7.15, 3.1, 5.6, 0.9, "recipes, from just four edits out of the 346 we catalogued", size=21, color=TEXT)
tx(s, 7.15, 4.1, 5.6, 0.8, [[(f"{yrs:.1f} years", {"font": DISPLAY_B, "size": 40, "color": TEXT})]], anchor="m")
tx(s, 7.15, 4.9, 5.6, 0.7, "to time them at one second each, and we need many rounds per recipe", size=18, color=MUTE)
tx(s, M, 6.2, 11.8, 0.5, "Choosing and ordering passes has been an open problem in compilers for decades.", size=22, font=DISPLAY)

# ------------------------------------------------------------ 6 scoreboard
ir = R["ir"]
s = slide("The easy scoreboard lies", 1, source=f"Sample of 700 from {ir['n']:,} timed candidates. research.json: ir")
random.seed(3)
pts = [p for p in ir["sample"] if 0.5 <= p[0] <= 1.5 and 0.7 <= p[1] <= 1.5]
pts = random.sample(pts, 700)
cd = XyChartData()
se = cd.add_series("Candidate")
for a, b in pts:
    se.add_data_point(a, b)
gf = s.shapes.add_chart(XL_CHART_TYPE.XY_SCATTER, Inches(M), Inches(1.6), Inches(7.9), Inches(5.25), cd)
set_descr(gf, "Scatter of IR size vs speedup. No visible relationship.")
ch = gf.chart
ch.has_legend = ch.has_title = False
ser = ch.plots[0].series[0]
ser.format.line.fill.background()
ser.marker.style = XL_MARKER_STYLE.CIRCLE
ser.marker.size = 4
ser.marker.format.fill.solid()
ser.marker.format.fill.fore_color.rgb = rgb(CYAN)
ser.marker.format.line.fill.background()
va, ca = ch.value_axis, ch.category_axis
va.minimum_scale, va.maximum_scale, va.major_unit = 0.7, 1.5, 0.2
ca.minimum_scale, ca.maximum_scale, ca.major_unit = 0.5, 1.5, 0.25
for ax, ttl in ((va, "Speedup vs -O3"), (ca, "IR instructions vs -O3 (left = smaller code)")):
    style_axis_text(ax, 13)
    ax.has_title = True
    ax.axis_title.text_frame.text = ttl
    r_ = ax.axis_title.text_frame.paragraphs[0].runs[0]
    r_.font.size, r_.font.color.rgb, r_.font.bold, r_.font.name = Pt(14), rgb(MUTE), False, BODY
    ax.has_major_gridlines = True
    ax.major_gridlines.format.line.color.rgb = rgb("1E252F")
    ax.format.line.color.rgb = rgb(LINE)
va.tick_labels.number_format, va.tick_labels.number_format_is_linked = '0.0"×"', False
ca.tick_labels.number_format, ca.tick_labels.number_format_is_linked = '0.00"×"', False
tx(s, 8.95, 1.72, 3.8, 1.2, f"ρ = {ir['rho']:.2f}".replace("-", "−"), size=62, font=DISPLAY_B, color=AMBER, anchor="m")
tx(s, 8.95, 2.95, 3.8, 0.8, "Rank correlation between smaller code and faster code: nearly none.", size=18, color=MUTE)
tx(s, 8.95, 3.9, 3.8, 0.85, f"{ir['fewer_ir_faster_pct']:.0f}%", size=50, font=DISPLAY_B, anchor="m")
tx(s, 8.95, 4.75, 3.8, 0.8, "of noticeably smaller candidates were faster. Barely better than a coin flip.", size=18, color=MUTE)
tx(s, 8.95, 5.8, 3.8, 0.9, "An earlier attempt shrank the code and did not move runtime. So we judge one thing: time.", size=18, color=TEXT)

# ------------------------------------------------------------ 7 idea
s = slide("Models shortlist. The stopwatch decides.", 2, size=44, y=0.74, source="Counts from the interpreter demo run. Full loop: nc/deploy.py")
stages = [(1.35, 3.2, "935", "candidates", "22 from RL\n913 from the library", ROSE, CYAN), (4.0, 2.5, f"{RUN['n_compiled']}", "compiled", "in ranked order,\noutput checked", CYAN, CYAN),
          (6.65, 1.8, f"{RUN['n_timed']}", "timed", "against -O3,\n10 shuffled rounds", AMBER, AMBER), (9.3, 1.25, "1", "proven", "on 20 fresh rounds", AMBER, AMBER)]
cy = 3.82
for i, (x, h, a, b, c_, col, col2) in enumerate(stages):
    w = 2.25
    box(s, x, cy - h / 2, w, h, fill=PANEL if i < 3 else AMBER, line=col if i < 3 else None, lw=1.75, radius=0.1)
    fg = INK if i == 3 else TEXT
    tx(s, x, cy - 0.62 if i < 3 else cy - 0.58, w, 0.75, a, size=44 if i < 3 else 40, font=DISPLAY_B, color=fg, align="c", anchor="m")
    tx(s, x, cy + 0.1 if i < 3 else cy + 0.1, w, 0.36, b, size=18, font=BODY_B, color=fg, align="c")
    if i < 3:
        arrow(s, x + w + 0.05, cy, stages[i + 1][0] - 0.05, cy, color=TEXT, lw=2)
for i, (x, h, a, b, c_, col, col2) in enumerate(stages):
    tx(s, x - 0.1, 5.75 if i == 0 else 5.75, 2.45, 0.65, c_.split("\n"), size=14, color=MUTE, align="c", spacing=0.98)
arrow(s, 11.6, cy, 11.9, cy, color=TEXT, lw=2)
box(s, 11.9, cy - 0.55, 0.85, 1.1, fill=RAISED, line=SLATE, content=[[("-O3", {"font": DISPLAY_B, "size": 17})], [("if not", {"size": 12, "color": MUTE})]], radius=0.08)
tx(s, 1.35, 1.78, 4.9, 0.3, "MODELS: fast, cheap, imperfect", size=14, font=MONO, color=CYAN)
tx(s, 6.65, 1.78, 5, 0.3, "STOPWATCH: slow, honest, final", size=14, font=MONO, color=AMBER)
tx(s, M, 6.42, 12, 0.5, "Like scouts and a race: scouts suggest who to enter. Only the race picks the winner.", size=22, font=DISPLAY)

# ------------------------------------------------------------ 8 architecture
s = slide("The whole system", 3, source="Module names as in nc/. Dashboard: dashboard/server.py (FastAPI)")
col_w, col_gap = 1.57, 0.155
cx = lambda i: M + 0.2 + i * (col_w + col_gap)
box(s, M, 1.55, W - 2 * M, 1.55, fill="0E1218", line=LINE, radius=0.12, name="Offline lane")
tx(s, M + 0.2, 1.6, 7, 0.3, "OFFLINE  building the knowledge, hours to days", size=13, font=MONO, color=MUTE)
off = [("Corpus", "corpus.py\n146 programs"), ("Build", "toolchain.py\nopt + llc"), ("Search + KB", "search.py\npasskb.py"), ("Timing", "timing.py\ninterleaved"),
       ("Dataset", "db.py\n70,409 recipes"), ("Features", "features.py\n~130 each"), ("Train", "model.py\nrl.py")]
oshape = []
for i, (a, b) in enumerate(off):
    q = box(s, cx(i), 1.92, col_w, 1.05, fill=RAISED, line=LINE, content=[[(a, {"font": BODY_B, "size": 16})]] + [[(l, {"font": MONO, "size": 12, "color": MUTE})] for l in b.split("\n")], radius=0.08, inset=0.05, name=a)
    oshape.append(q)
    if i:
        arrow(s, 0, 0, 0, 0, begin=(oshape[i - 1], 3), end=(q, 1))
ppo_x, lgb_x = cx(2), cx(3)
ppo = box(s, ppo_x, 3.3, col_w, 0.5, fill=PANEL, line=ROSE, lw=1.5, content="PPO policy", size=15, font=BODY_B, color=ROSE, radius=0.08, name="PPO policy")
lgb = box(s, lgb_x, 3.3, col_w, 0.5, fill=PANEL, line=CYAN, lw=1.5, content="LightGBM", size=15, font=BODY_B, color=CYAN, radius=0.08, name="LightGBM model")
tx(s, cx(4), 3.3, 4.6, 0.5, "frozen models, hash-checked on load", size=14, color=MUTE, font=MONO, anchor="m")
tr_x = cx(6) + col_w / 2
arrow(s, tr_x, 2.97, tr_x, 3.2, head=False)
arrow(s, tr_x, 3.2, ppo_x + col_w / 2, 3.2, head=False)
arrow(s, ppo_x + col_w / 2, 3.2, ppo_x + col_w / 2, 3.3, lw=1.5)
arrow(s, lgb_x + col_w / 2, 3.2, lgb_x + col_w / 2, 3.3, lw=1.5)
box(s, M, 3.97, W - 2 * M, 2.0, fill="141108", line=AMBER, lw=1.25, radius=0.12, name="Online lane")
tx(s, M + 0.2, 4.03, 3, 0.3, "ONLINE  your program", size=13, font=MONO, color=AMBER)
tx(s, cx(4), 4.03, 5.0, 0.3, "median about 139 s per program", size=13, font=MONO, color=AMBER, align="r")
on = [("Your source", "C or C++", TEXT), ("Features", "static IR +\nquick scan", TEXT), ("Propose", "RL: up to 24", ROSE), ("Rank", "pool of ~935", CYAN), ("Compile, verify", "output must\nmatch -O0", TEXT),
      ("Time, confirm", "against -O3,\nwith A/A control", AMBER), ("Binary + proof", "or -O3 fallback,\nJSON report", AMBER)]
onshape = []
for i, (a, b, col) in enumerate(on):
    q = box(s, cx(i), 4.4, col_w, 1.4, fill=RAISED, line=col if col != TEXT else LINE, lw=1.25, content=[[(a, {"font": BODY_B, "size": 15})]] + [[(l, {"size": 13, "color": MUTE})] for l in b.split("\n")], radius=0.08, inset=0.04, name=a)
    onshape.append(q)
    if i:
        arrow(s, 0, 0, 0, 0, begin=(onshape[i - 1], 3), end=(q, 1), color=TEXT)
arrow(s, 0, 0, 0, 0, begin=(ppo, 2), end=(onshape[2], 0), color=ROSE)
arrow(s, 0, 0, 0, 0, begin=(lgb, 2), end=(onshape[3], 0), color=CYAN)
tx(s, M, 6.13, 12.1, 0.7, [[("Use it from ", {"color": MUTE}), ("bin/neurocompiler", {"font": MONO, "color": TEXT}), (" or a web dashboard. Built with LLVM 18, Python, LightGBM, NumPy, FastAPI.", {"color": MUTE})]], size=17)

# ------------------------------------------------------------ 9 data
C = R["corpus"]
s = slide(f"{70409:,} recipes, measured the hard way", 3, source="corpus/manifest.jsonl, corpus/split.json, results/dataset.sqlite")
tx(s, M, 1.75, 3.9, 0.3, "THE CORPUS", size=14, font=MONO, color=MUTE)
tx(s, M, 2.05, 3.9, 1.05, [[(f"{C['scanned']}", {"color": MUTE}), (" → ", {"color": MUTE, "size": 34}), (f"{C['usable']}", {"color": AMBER})]], size=60, font=DISPLAY_B, anchor="m")
tx(s, M, 3.12, 3.9, 1.2, "programs scanned, then kept only if they build, run identically at every level, and last long enough to time well.", size=17, color=MUTE)
bs = C["by_suite"]
for i, (a, b) in enumerate([("PolyBench", bs["polybench"]), ("LLVM SingleSource", bs["singlesource"]), ("LLVM MultiSource", bs["multisource"])]):
    y = 4.5 + i * 0.5
    tx(s, M, y, 2.7, 0.42, a, size=17, anchor="m")
    tx(s, M + 2.7, y, 1.1, 0.42, str(b), size=22, font=DISPLAY_B, align="r", anchor="m")
tx(s, 5.0, 1.75, 3.8, 0.3, "THE MEASUREMENTS", size=14, font=MONO, color=MUTE)
for i, (a, b) in enumerate([("70,409", "candidate recipes recorded"), ("19,534", "timing measurements"), ("346", "single edits studied one by one")]):
    y = 2.05 + i * 1.32
    tx(s, 5.0, y, 3.5, 0.8, a, size=46, font=DISPLAY_B, color=TEXT if i else AMBER, anchor="m")
    tx(s, 5.0, y + 0.78, 3.5, 0.4, b, size=17, color=MUTE)
tx(s, 9.0, 1.75, 3.75, 0.3, "THE SPLIT, BY FAMILY", size=14, font=MONO, color=MUTE)
sp = C["split"]["counts"]
cd = CategoryChartData()
cd.categories = ["Programs"]
for k, lb in (("train", "Train"), ("val", "Validation"), ("test", "Test")):
    cd.add_series(lb, [sp[k]])
gf = s.shapes.add_chart(XL_CHART_TYPE.BAR_STACKED, Inches(9.0), Inches(2.05), Inches(3.75), Inches(1.2), cd)
set_descr(gf, "Stacked bar: 91 train, 22 validation, 33 test programs")
ch = gf.chart
ch.has_legend, ch.has_title = False, False
ch.plots[0].gap_width = 15
ch.plots[0].overlap = 100
for se_, col in zip(ch.plots[0].series, ("39424F", "5A6474", AMBER)):
    se_.format.fill.solid()
    se_.format.fill.fore_color.rgb = rgb(col)
    se_.data_labels.show_value = True
    se_.data_labels.font.size, se_.data_labels.font.name = Pt(18), DISPLAY_B
    se_.data_labels.font.color.rgb = rgb(INK if col == AMBER else TEXT)
ch.value_axis.visible = ch.category_axis.visible = False
ch.value_axis.has_major_gridlines = False
ch.value_axis.maximum_scale = sum(sp.values())
tx(s, 9.0, 3.25, 3.75, 0.34, "train  |  validation  |  test", size=14, color=MUTE, font=MONO)
tx(s, 9.0, 3.8, 3.75, 2.2, ["Programs from one family share code, so a whole family stays on one side of the line.", [("The 33 test programs come from 11 families the models never saw.", {"color": TEXT})]],
   size=18, color=MUTE, after=8)
tx(s, 5.0, 6.2, 7.75, 0.6, "Split frozen before any modelling.", size=22, font=DISPLAY)

# ------------------------------------------------------------ 10 genome
s = slide("A recipe becomes a short list of edits", 4, source="Genome: nc/pipeline.py. Example: the interpreter demo's shipped pipeline")
marks = {i for i, p in enumerate(PASSES) if p["name"] in ("simplifycfg", "instcombine")}
tx(s, M, 1.68, 11, 0.4, [[("-O3 unchanged: ", {"color": MUTE}), ("0 edits", {"color": TEXT, "font": BODY_B}), ("   |   Our demo: ", {"color": MUTE}), ("4 edits", {"color": AMBER, "font": BODY_B}),
                         (f", which remove {len(marks)} of 109 steps", {"color": MUTE})]], size=19)
strip(s, PASSES, M, 2.2, W - 2 * M, 0.82, marks=marks, name="Pipeline strip: removed steps highlighted")
ed = [("BACK END", "tail duplication size 6", CYAN), ("KNOB", "unroll at most 4×", CYAN), ("REMOVE ALL", "all 8 simplifycfg steps", RED), ("REMOVE ALL", "all 8 instcombine steps", RED)]
for i, (a, b, col) in enumerate(ed):
    x = M + i * 3.07
    box(s, x, 3.3, 2.92, 1.15, fill=PANEL, line=LINE, radius=0.08)
    tx(s, x + 0.18, 3.42, 2.6, 0.3, a, size=13, font=MONO, color=col)
    tx(s, x + 0.18, 3.72, 2.6, 0.62, b, size=18, font=BODY_B, spacing=0.95)
for i, (a, b) in enumerate([("Portable", "Edits point at steps in -O3, so a recipe found on one program can be tried on another."),
                            ("Always valid", "Inserted passes come from the same stage, so a recipe stays a legal pipeline."),
                            ("Explainable", "Remove one edit and re-time it, and you learn what actually mattered.")]):
    x = M + i * 4.1
    tx(s, x, 4.72, 3.85, 0.4, a, size=22, font=DISPLAY_B, color=AMBER)
    tx(s, x, 5.14, 3.85, 1.0, b, size=17, color=MUTE)
tx(s, M, 6.33, 12, 0.4, [[("Edit types  ", {"color": MUTE}), ("delete  duplicate  swap  insert  knob  back-end level  option flip  flip all  delete all", {"font": MONO, "color": TEXT})]], size=15)

# ------------------------------------------------------------ 11 stopwatch
H_ = R["harness"]["selftest_v14"][-1]
s = slide("A stopwatch you can trust", 4, source="Round diagram is schematic. nc/timing.py, results/selftest_*.json. Mytkowicz et al., ASPLOS 2009")
tx(s, M, 1.62, 6.5, 0.8, "Harmless-looking details can bias a benchmark, so every comparison is built to cancel them.", size=19, color=MUTE)
names = [("-O3", "39424F", TEXT), ("Copy", "5A6474", TEXT), ("Cand. 1", CYAN, INK), ("Cand. 2", AMBER, INK)]
rnd = random.Random(11)
for r_i in range(4):
    y = 2.72 + r_i * 0.62
    tx(s, M, y, 1.05, 0.5, f"Round {r_i + 1}", size=14, font=MONO, color=MUTE, anchor="m")
    o = names[:]
    rnd.shuffle(o)
    for j, (a, col, fg) in enumerate(o):
        box(s, M + 1.1 + j * 1.3, y, 1.22, 0.5, fill=col, radius=0.05, content=a, size=14, font=BODY_B, color=fg, inset=0.02)
tx(s, M, 5.25, 6.4, 0.4, "Shuffled every round, on one pinned core", size=18, font=BODY_B)
tx(s, M, 5.65, 6.4, 0.9, "Each pair runs in the same conditions, so machine drift hits both sides. “Copy” is a byte-identical -O3 and must read 1.00×.", size=16, color=MUTE)
stats = [(f"{H_['ci_halfwidth_pct']:.2f}%", "timing uncertainty, 95% CI half-width", GREEN), (f"{abs(H_['aa'] - 1) * 100:.2f}%", "bias between identical binaries", GREEN)]
for i, (a, b, col) in enumerate(stats):
    y = 1.72 + i * 1.3
    tx(s, 7.5, y, 2.6, 1.0, a, size=46, font=DISPLAY_B, color=col, anchor="m")
    tx(s, 10.0, y, 2.75, 1.0, b, size=17, color=MUTE, anchor="m")
for i, (a, b) in enumerate([("Pinned, quiet, ASLR off", "Waits for other load to clear before timing"), ("Output checked against -O0", "A wrong answer disqualifies the recipe"),
                            ("Tested the tester", "Five parallel cores: noise 5–40× worse. We use three")]):
    y = 4.3 + i * 0.84
    box(s, 7.5, y + 0.08, 0.05, 0.6, fill=AMBER, radius=0)
    tx(s, 7.7, y, 5, 0.38, a, size=18, font=BODY_B)
    tx(s, 7.7, y + 0.37, 5.05, 0.36, b, size=15, color=MUTE)

# ------------------------------------------------------------ 12 two models
M_ = R["models"]
g = M_["tune_cv"]["summary"]["gbr"]
s = slide("Two models, two jobs", 4, source="nc/rl.py, nc/model.py, results/models/cv_latest.json. Gate 7B met narrowly")
hw = (W - 2 * M - 0.25) / 2
for i, (x, col, name, role) in enumerate([(M, ROSE, "PPO", "Reinforcement learning proposes"), (M + hw + 0.25, CYAN, "LightGBM", "Supervised learning ranks")]):
    box(s, x, 1.62, hw, 5.2, fill=PANEL, line=LINE, radius=0.12)
    tx(s, x + 0.28, 1.76, hw - 0.5, 0.65, name, size=36, font=DISPLAY_B, color=col)
    tx(s, x + 0.28, 2.42, hw - 0.5, 0.4, role, size=19, font=BODY_B)
bl = [("State", "program features + edits so far"), ("Actions", f"{M_['rl_tune_actions']} macro-edits or STOP, up to 4 edits"), ("Reward", "the gain LightGBM predicts"), ("Built", "from scratch in NumPy")]
for i, (a, b) in enumerate(bl):
    y = 2.92 + i * 0.37
    tx(s, M + 0.28, y, 1.0, 0.34, a, size=15, color=ROSE, font=MONO, anchor="m")
    tx(s, M + 1.28, y, 4.6, 0.34, b, size=16, color=TEXT, anchor="m")
hist = M_["rl_tune_history"]
cd = CategoryChartData()
cd.categories = [str(i) for i in range(len(hist))]
cd.add_series("Predicted return", hist)
gf = s.shapes.add_chart(XL_CHART_TYPE.LINE, Inches(M + 0.2), Inches(4.45), Inches(hw - 0.4), Inches(2.0), cd)
set_descr(gf, "PPO training: mean predicted return rises from 0.01 to 0.22 log speedup over 200 iterations")
ch = gf.chart
ch.has_legend = ch.has_title = False
se_ = ch.plots[0].series[0]
se_.format.line.color.rgb, se_.format.line.width, se_.smooth = rgb(ROSE), Pt(2), False
ch.value_axis.has_major_gridlines = True
ch.value_axis.major_gridlines.format.line.color.rgb = rgb("1E252F")
ch.value_axis.minimum_scale, ch.value_axis.maximum_scale, ch.value_axis.major_unit = 0, 0.3, 0.1
style_axis_text(ch.value_axis, 12)
ch.value_axis.format.line.fill.background()
ch.value_axis.tick_labels.number_format, ch.value_axis.tick_labels.number_format_is_linked = "0.0", False
ch.category_axis.tick_label_position = XL_TICK_LABEL_POSITION.NONE
ch.category_axis.major_tick_mark = XL_TICK_MARK.NONE
ch.category_axis.format.line.color.rgb = rgb(LINE)
tx(s, M + 0.28, 6.42, hw - 0.5, 0.32, "Predicted gain during training: the model's view, not measured.", size=13, color=MUTE)
x = M + hw + 0.25
bl = [("Input", f"~130 program + ~98 recipe features"), ("Trained", "on real timings, tested on held-out families")]
for i, (a, b) in enumerate(bl):
    y = 2.92 + i * 0.37
    tx(s, x + 0.28, y, 1.0, 0.34, a, size=15, color=CYAN, font=MONO, anchor="m")
    tx(s, x + 1.28, y, 4.75, 0.34, b, size=16, anchor="m", color=TEXT)
tx(s, x + 0.28, 3.95, 3, 1.2, f"{g['spearman']:+.2f}", size=70, font=DISPLAY_B, color=CYAN, anchor="m")
tx(s, x + 2.95, 3.95, 3.05, 1.2, "rank correlation on unseen families (95% CI +0.06 to +0.15)", size=16, color=MUTE, anchor="m")
tx(s, x + 0.28, 5.28, hw - 0.5, 1.4, ["That is a weak signal on its own.", [("So neither model picks the winner. They only decide what is worth timing.", {"color": AMBER})]], size=20, font=BODY_B, after=6)

# ------------------------------------------------------------ 13 proof
s = slide("Nothing ships without proof", 4, source="nc/deploy.py select_topk. Branchy run: open_day/assets/runs/tune_branchy_2026-10-30.log")
gates = [("1", "Same answer?", "Output must exactly match the -O0 build"), ("2", "Faster in the race?", "CI above 1.00 over 10 shuffled rounds"), ("3", "Faster again?", "Fresh 20 rounds, CI above 1.01, clean A/A control")]
gw, gy = 3.05, 1.68
gs = []
for i, (n_, a, b) in enumerate(gates):
    x = M + i * (gw + 0.27)
    q = box(s, x, gy, gw, 1.9, fill=PANEL, line=LINE, radius=0.1)
    gs.append(q)
    tx(s, x + 0.2, gy + 0.12, 0.6, 0.55, n_, size=30, font=DISPLAY_B, color=AMBER)
    tx(s, x + 0.2, gy + 0.68, gw - 0.35, 0.42, a, size=21, font=BODY_B)
    tx(s, x + 0.2, gy + 1.1, gw - 0.35, 0.75, b, size=16, color=MUTE, spacing=0.98)
ship = box(s, 10.85, gy, 1.88, 1.9, fill=AMBER, radius=0.1, content=[[("Ship", {"font": DISPLAY_B, "size": 24, "color": INK})], [("tuned binary", {"size": 15, "color": INK})]])
for i in range(2):
    arrow(s, 0, 0, 0, 0, begin=(gs[i], 3), end=(gs[i + 1], 1), color=TEXT, lw=2)
arrow(s, 0, 0, 0, 0, begin=(gs[2], 3), end=(ship, 1), color=TEXT, lw=2)
rail = box(s, M, 4.0, W - 2 * M, 0.6, fill=RAISED, line=SLATE, radius=0.08, content=[[("Otherwise -O3 ships. ", {"font": BODY_B, "size": 18}), ("-O3 is always the safe answer.", {"size": 17, "color": MUTE})]])
for i in range(3):
    xm = M + i * (gw + 0.27) + gw / 2
    arrow(s, xm, gy + 1.9, xm, 4.0, color=SLATE, dash=True)
ps = [(f"{RS['no_gain']} of 33", "test programs kept -O3. The default is working, not failing.", TEXT), ("0.979×", "An early run shipped lencod slower than -O3. Gate 3 exists because of that.", RED), ("1.014×", "In a fresh run, branchy's best pick just missed gate 3. -O3 shipped.", AMBER)]
for i, (a, b, col) in enumerate(ps):
    x = M + i * 4.1
    tx(s, x, 4.82, 3.9, 0.85, a, size=40, font=DISPLAY_B, color=col, anchor="m")
    tx(s, x, 5.68, 3.85, 1.0, b, size=17, color=MUTE)

# ------------------------------------------------------------ 14 mystery
s = slide("The mystery solved: one jump for everything", 5, source="Jump counts measured with llvm-objdump. CPython figures: Elhage, 2025")
pw = 5.95
for i, (x, col, head, nm, sub) in enumerate([(M, RED, "With -O3", "2", "indirect jumps in the binary"), (M + pw + 0.25, GREEN, "After tuning", "63", "indirect jumps in the binary")]):
    box(s, x, 1.62, pw, 3.62, fill=PANEL, line=LINE, radius=0.12)
    tx(s, x + 0.25, 1.72, 3.2, 0.42, head, size=22, font=BODY_B, color=col)
    tx(s, x + 3.25, 1.68, 1.15, 1.0, nm, size=50, font=DISPLAY_B, color=col, align="r", anchor="m")
    tx(s, x + 4.48, 1.74, 1.35, 0.9, sub, size=13, color=MUTE, anchor="m", spacing=0.95)
ops = ["add", "load", "jump", "print", "sub", "…"]
# left: all handlers funnel to one dispatch
for i, o in enumerate(ops):
    x = M + 0.28 + i * 0.92
    h_ = box(s, x, 2.82, 0.8, 0.5, fill=RAISED, line=LINE, content=o, size=13, font=MONO, inset=0.01, radius=0.05)
    arrow(s, x + 0.4, 3.32, M + pw / 2, 4.08, color=RED, lw=1.25)
box(s, M + pw / 2 - 1.15, 4.08, 2.3, 0.5, fill=RED, radius=0.06, content="one shared jump", size=15, font=BODY_B, color=INK)
tx(s, M + 0.25, 4.68, pw - 0.5, 0.45, "The CPU gets one place to guess what runs next.", size=16, color=MUTE, align="c")
x0 = M + pw + 0.25
for i, o in enumerate(ops):
    x = x0 + 0.28 + i * 0.92
    box(s, x, 2.82, 0.8, 0.5, fill=RAISED, line=LINE, content=o, size=13, font=MONO, inset=0.01, radius=0.05)
    arrow(s, x + 0.4, 3.32, x + 0.4, 4.08, color=GREEN, lw=1.25)
    box(s, x, 4.08, 0.8, 0.5, fill=GREEN, radius=0.05, content="jump", size=13, font=BODY_B, color=INK, inset=0.01)
tx(s, x0 + 0.25, 4.68, pw - 0.5, 0.45, "Each operation predicts its own successor.", size=16, color=MUTE, align="c")
tx(s, M, 5.42, 6.1, 1.4, [[("848 ms → 222 ms", {"font": DISPLAY_B, "size": 34, "color": AMBER})], "Program logic untouched. A clean-up pass was merging code it should have left alone."], size=17, color=MUTE, after=3)
box(s, 6.95, 5.42, W - M - 6.95, 1.38, fill=RAISED, line=LINE, radius=0.1)
tx(s, 7.15, 5.5, 5.4, 1.25, [[("Not a toy problem. ", {"font": BODY_B, "color": TEXT})], "A Clang 19 change merged CPython's dispatch the same way: 332 indirect jumps became 3, about 9–12% slower."], size=16, color=MUTE, after=2)

# ------------------------------------------------------------ 15 demo
s = slide("It runs. Ask us to show you.", 5, source="Screenshot: dashboard, interpreter demo. Terminal: fresh run, 2026-10-30, open_day/assets/runs/")
im = Image.open("docs/assets/shots/tune_summary.jpg")
im.crop((14, 34, 1426, 744)).save(A / "dash_tune.jpg", quality=93)
pic = s.shapes.add_picture(str(A / "dash_tune.jpg"), Inches(5.15), Inches(1.62), width=Inches(7.58))
pic.line.color.rgb, pic.line.width = rgb(LINE), Pt(1)
set_descr(pic, "NeuroCompiler dashboard: result of tuning the interpreter demo, 3.83x, every timed candidate vs -O3")
tx(s, 5.15, 5.5, 7.58, 0.5, "The dashboard: upload code, watch it run, see every candidate.", size=17, color=MUTE)
box(s, M, 1.62, 4.35, 3.82, fill="06080B", line=LINE, radius=0.1, name="Terminal")
for i, col in enumerate((RED, AMBER, GREEN)):
    box(s, M + 0.18 + i * 0.22, 1.76, 0.12, 0.12, fill=col, radius=0.06, shape=MSO_SHAPE.OVAL)
term = [[("$ ", {"color": AMBER}), ("bin/neurocompiler matmul.c \\", {})], [("    --out matmul --args 800", {})], "",
        [("24 RL + 913 library pipelines", {"color": MUTE})], [("8 timed against -O3", {"color": MUTE})], "",
        [("shipped: ", {"color": MUTE}), ("library pipeline", {"color": TEXT})], [("confirmed ", {"color": MUTE}), ("1.485×", {"color": AMBER}), (" [1.384, 1.534]", {"color": MUTE})],
        [("928.8 ms → 629.5 ms", {"color": GREEN}), ("  175 s", {"color": MUTE})], "",
        [("$ ", {"color": AMBER}), ("bin/neurocompiler branchy.c ...", {})], [("shipped: ", {"color": MUTE}), ("-O3", {"color": TEXT}), (" (pick not confirmed)", {"color": MUTE})]]
tx(s, M + 0.2, 2.0, 4.05, 3.4, term, size=14.5, font=MONO, spacing=1.0)
tx(s, M, 6.15, 12.1, 0.5, "Live at the stall: pick an example or bring your own C program.", size=22, font=DISPLAY)

# ------------------------------------------------------------ 16 results
s = slide(f"33 programs it had never seen: {pct(RS['geomean'])} over -O3", 5, source="Serial re-measurement; bars are geometric means, whiskers 95% CI. research.json: eval.summary")
order = [("-Os", "-Os"), ("-O2", "-O2"), ("random top-8", "Random top-8"), ("GA@8", "Genetic algorithm @8"), ("ML-only top-1", "ML pick, no timing"), ("RL only", "RL only"),
         ("random search@8", "Random search @8"), ("tune top-8 (SL)", "LightGBM + timing"), ("tune RL + SL", "NeuroCompiler (RL + LightGBM)")]
cd = CategoryChartData(number_format='0.0')
cd.categories = [f"{lb}  {(SUM[k]['geomean'] - 1) * 100:+.2f}%" for k, lb in order]
vals = [(SUM[k]["geomean"] - 1) * 100 for k, _ in order]
cd.add_series("Geomean vs -O3 (%)", vals)
gf = s.shapes.add_chart(XL_CHART_TYPE.BAR_CLUSTERED, Inches(M), Inches(1.62), Inches(8.55), Inches(5.3), cd)
set_descr(gf, "Bar chart of geomean speedup vs -O3 per method. NeuroCompiler highest at +8.09%.")
ch = gf.chart
ch.has_legend = ch.has_title = False
pl = ch.plots[0]
pl.gap_width = 45
se_ = pl.series[0]
se_.invert_if_negative = False
se_.format.fill.solid()
se_.format.fill.fore_color.rgb = rgb("4B5A70")
pt = se_.points[len(order) - 1]
pt.format.fill.solid()
pt.format.fill.fore_color.rgb = rgb(AMBER)
pt = se_.points[len(order) - 2]
pt.format.fill.solid()
pt.format.fill.fore_color.rgb = rgb(CYAN)
plus = [(SUM[k]["ci"][1] - SUM[k]["geomean"]) * 100 for k, _ in order]
minus = [(SUM[k]["geomean"] - SUM[k]["ci"][0]) * 100 for k, _ in order]


def numlit(vs):
    return "<c:numLit><c:formatCode>General</c:formatCode>" + f'<c:ptCount val="{len(vs)}"/>' + "".join(f'<c:pt idx="{i}"><c:v>{v:.4f}</c:v></c:pt>' for i, v in enumerate(vs)) + "</c:numLit>"


err = etree.fromstring(
    '<c:errBars xmlns:c="http://schemas.openxmlformats.org/drawingml/2006/chart" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
    '<c:errBarType val="both"/><c:errValType val="cust"/><c:noEndCap val="0"/>'
    f"<c:plus>{numlit(plus)}</c:plus><c:minus>{numlit(minus)}</c:minus>"
    f'<c:spPr><a:ln w="15875"><a:solidFill><a:srgbClr val="{TEXT}"/></a:solidFill></a:ln></c:spPr></c:errBars>')
se_._element.find(qn("c:cat")).addprevious(err)
ca, va = ch.category_axis, ch.value_axis
style_axis_text(ca, 15, TEXT)
ca.tick_label_position = XL_TICK_LABEL_POSITION.LOW
ca.major_tick_mark = XL_TICK_MARK.NONE
ca.format.line.color.rgb = rgb(SLATE)
va.minimum_scale, va.maximum_scale, va.major_unit = -6, 18, 6
style_axis_text(va, 13)
va.tick_labels.number_format, va.tick_labels.number_format_is_linked = '+0"%";-0"%";0"%"', False
va.has_major_gridlines = True
va.major_gridlines.format.line.color.rgb = rgb("1E252F")
va.format.line.fill.background()
k = [(pct(RS["geomean"]), "faster than -O3, geomean", AMBER), (pct(RS["excl_largest"]), "without the largest win", TEXT), (f"{RS['ge5']}/33", "programs at least 5% faster", TEXT), (f"{RS['slower']}/33", "measurably slower", GREEN)]
for i, (a, b, col) in enumerate(k):
    y = 1.68 + i * 1.02
    tx(s, 9.4, y, 3.35, 0.65, a, size=38, font=DISPLAY_B, color=col, anchor="m")
    tx(s, 9.4, y + 0.62, 3.35, 0.34, b, size=16, color=MUTE)
tx(s, 9.4, 5.8, 3.35, 1.1, f"95% CI {pct(RS['ci'][0])} to {pct(RS['ci'][1])}. The margin over random search at equal budget is not significant.", size=14, color=MUTE)

# ------------------------------------------------------------ 17 per program
P = sorted(EV["programs"], key=lambda p: -p["tune RL + SL"])
s = slide("Inside the average: a few big wins, most stay safe", 5, source="Same run as the previous slide. Log scale. research.json: eval.programs")
sh = lambda i: i.split("/")[-1]
cd = CategoryChartData(number_format='0.00')
cd.categories = [sh(p["id"]) for p in P]
cd.add_series("Speedup vs -O3", [p["tune RL + SL"] for p in P])
gf = s.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, Inches(M), Inches(1.55), Inches(8.9), Inches(5.35), cd)
set_descr(gf, "Sorted speedup of 33 test programs. Durbin 2.81x, then 3mm 1.43x, ft 1.36x; 21 programs at exactly 1.00x.")
ch = gf.chart
ch.has_legend = ch.has_title = False
pl = ch.plots[0]
pl.gap_width = 30
se_ = pl.series[0]
se_.invert_if_negative = False
se_.format.fill.solid()
se_.format.fill.fore_color.rgb = rgb("4B5A70")
va, ca = ch.value_axis, ch.category_axis
scal = va._element.find(qn("c:scaling"))
lb_ = etree.SubElement(scal, qn("c:logBase"))
lb_.set("val", "2")
scal.insert(0, lb_)
va.minimum_scale, va.maximum_scale = 0.97, 3.1
va.crosses_at = 0.97
va.has_major_gridlines = False
va.tick_label_position = XL_TICK_LABEL_POSITION.NONE
va.major_tick_mark = XL_TICK_MARK.NONE
va.format.line.fill.background()
style_axis_text(ca, 11)
ca.tick_label_position = XL_TICK_LABEL_POSITION.LOW
ca.major_tick_mark = XL_TICK_MARK.NONE
ca.format.line.color.rgb = rgb(TEXT)
for i, p in enumerate(P):
    v = p["tune RL + SL"]
    if v >= 1.05:
        pt = se_.points[i]
        pt.format.fill.solid()
        pt.format.fill.fore_color.rgb = rgb(AMBER)
    if v >= 1.05:
        dl = se_.points[i].data_label
        dl.position = XL_LABEL_POSITION.OUTSIDE_END
        tf_ = dl.text_frame
        tf_.text = f"{v:.2f}"
        r_ = tf_.paragraphs[0].runs[0]
        r_.font.size, r_.font.name = Pt(11), BODY_B
        r_.font.color.rgb = rgb(TEXT)
med = sorted(p["tune RL + SL"] for p in P)[16]
k = [(f"{P[0]['tune RL + SL']:.2f}×", f"largest win: {sh(P[0]['id'])}", AMBER), (f"{RS['no_gain']}/33", "kept -O3, at 1.00×", TEXT), (f"{med:.2f}×", "the median program", TEXT)]
for i, (a, b, col) in enumerate(k):
    y = 1.7 + i * 1.28
    tx(s, 9.75, y, 3, 0.75, a, size=42, font=DISPLAY_B, color=col, anchor="m")
    tx(s, 9.75, y + 0.74, 3, 0.36, b, size=16, color=MUTE)
tx(s, 9.75, 5.55, 3, 1.3, f"One program moves the geomean from {pct(RS['excl_largest'])} to {pct(RS['geomean'])}, so we report both.", size=16, color=TEXT)

# ------------------------------------------------------------ 18 lessons
PR = SUM["predict (gated)"]
ML = SUM["ML-only top-1"]
s = slide("We put it to the test. Here is what we learned.", 5, source="results/FINAL_REPORT.md, rl_paired.txt, phase5_report.txt, predict/modes_paired.txt, gate_by_sample_20261023.txt")
box(s, M, 1.62, 4.15, 4.3, fill=PANEL, line=LINE, radius=0.12, name="Biggest lesson")
tx(s, M + 0.28, 1.76, 3.6, 0.32, "THE BIGGEST LESSON", size=14, font=MONO, color=AMBER)
tx(s, M + 0.28, 2.14, 3.6, 0.36, "Programs slower than -O3", size=18, color=MUTE)
tx(s, M + 0.28, 2.54, 3.6, 0.95, f"{ML['slower']}/33", size=60, font=DISPLAY_B, color=SLATE, anchor="m")
tx(s, M + 0.28, 3.47, 3.6, 0.36, "ML pick alone", size=18, font=BODY_B)
arrow(s, M + 0.55, 3.9, M + 0.55, 4.25, color=TEXT, lw=2)
tx(s, M + 0.28, 4.22, 3.6, 0.95, f"{RS['slower']}/33", size=60, font=DISPLAY_B, color=GREEN, anchor="m")
tx(s, M + 0.28, 5.15, 3.6, 0.36, "ML shortlist + stopwatch", size=18, font=BODY_B, color=GREEN)
qs = [("How much room is there above -O3?", "Our first sample fell short: 4 of 15 programs gained 5%, and we wanted 30%. We reset the target on record, searched wider and found +15.6%.", CYAN),
      ("Does RL beat LightGBM?", "Not yet: +0.2%, not significant, and it shipped on 1 of 33 programs. It stays by team decision. Next: train it on real timings.", ROSE),
      ("Can we skip running the program?", f"Partly. {pct(PR['geomean'])} with a CI that includes zero, under the +1.5% goal we set first, but in about 0.6 s extra. So it ships as advice, with -O3 by default.", AMBER)]
for i, (q_, a_, col) in enumerate(qs):
    y = 1.62 + i * 1.47
    box(s, 5.0, y, W - M - 5.0, 1.36, fill=PANEL, line=LINE, radius=0.1)
    box(s, 5.0, y + 0.14, 0.05, 1.08, fill=col, radius=0)
    tx(s, 5.24, y + 0.1, 7.3, 0.42, q_, size=21, font=DISPLAY_B)
    tx(s, 5.24, y + 0.52, 7.32, 0.8, a_, size=16, color=MUTE, spacing=0.98)
tx(s, M, 6.13, 12.1, 0.7, [[("Measured so far: ", {"color": AMBER, "font": BODY_B}), ("one machine, 33 test programs, one input per program, single-threaded code. Output checks are strong evidence, not proof.", {"color": TEXT})]], size=17)

# ------------------------------------------------------------ 19 real world
s = slide("Where this could matter", 6, source="External figures are other projects (Elhage 2025; AutoFDO 2016; MLGO 2021). Nothing here is deployed")
cols = [("DEMONSTRATED", "Works today, measured here", GREEN, [("Numerical kernels", "A parameter sweep runs one kernel thousands of times. Tune once. In the test set: durbin 2.81×, 3mm 1.43×."),
                                                             ("Compiler bug hunting", "Search and pass diffs turn a mystery slowdown into a concrete lead, as with the interpreter.")]),
        ("ADAPTABLE", "Needs some engineering", AMBER, [("Language runtimes", "Merged dispatch cost CPython about 9–12%. Timing real workloads can catch that class of bug."),
                                                       ("Release builds", "A build job tunes a CPU-heavy tool on its benchmark and keeps the proof, with -O3 as fallback.")]),
        ("FUTURE POTENTIAL", "Needs major development", SLATE, [("Data-centre fleets", ["Small gains pay at scale: Google deployed ML-guided register allocation for 0.3–1.5% more queries per second, and AutoFDO reported 10.5%.",
                                                                                     [("Ours would first need multi-threaded support, live-traffic testing and much stronger safety checks.", {"color": TEXT})]])])]
cw = (W - 2 * M - 0.4) / 3
for i, (lab, sub, col, items) in enumerate(cols):
    x = M + i * (cw + 0.2)
    box(s, x, 1.62, cw, 0.055, fill=col, radius=0)
    tx(s, x, 1.75, cw, 0.35, lab, size=15, font=MONO, color=col)
    tx(s, x, 2.07, cw, 0.35, sub, size=16, color=MUTE)
    for j, (a, b) in enumerate(items):
        y = 2.55 + j * 2.15
        hh = 2.02 if len(items) > 1 else 4.17
        box(s, x, y, cw, hh, fill=PANEL, line=LINE, radius=0.1)
        tx(s, x + 0.2, y + 0.14, cw - 0.38, 0.42, a, size=21, font=BODY_B)
        tx(s, x + 0.2, y + 0.6, cw - 0.38, hh - 0.7, b, size=16, color=MUTE, spacing=0.98, after=10)

# ------------------------------------------------------------ 20 economics and roadmap
s = slide("It pays off where a program runs again and again", 6, source="Calculated from measured values: median 139 s to tune, +8.09% geomean. Illustrative, results vary by program")
gain = 1 - 1 / RS["geomean"]
runs = 139 / gain
tx(s, M, 1.7, 5.8, 1.35, f"≈ {round(runs, -1):,.0f} runs", size=70, font=DISPLAY_B, color=AMBER, anchor="m")
tx(s, M, 3.05, 5.7, 0.8, "to repay one tuning session, for a one-second job at the average gain", size=20, color=TEXT)
for i, (a, b) in enumerate([("139 s", "median cost to tune once"), (f"{gain * 1000:.0f} ms", "saved per run of a 1 s job"), ("Once", "tuned, then reused until the code changes")]):
    y = 4.08 + i * 0.86
    tx(s, M, y, 2.0, 0.7, a, size=32, font=DISPLAY_B, anchor="m")
    tx(s, M + 2.1, y, 3.6, 0.7, b, size=17, color=MUTE, anchor="m")
x = 6.95
box(s, x, 1.62, W - M - x, 2.55, fill=PANEL, line=LINE, radius=0.1)
tx(s, x + 0.24, 1.74, 5, 0.4, "To reach production", size=22, font=DISPLAY_B, color=AMBER)
tx(s, x + 0.24, 2.22, 5.4, 1.9, ["Verify on many inputs, not one", "Support multi-threaded and I/O-heavy programs", "Test on more CPUs and real machines", "Combine with PGO, LTO and BOLT"], size=18, color=TEXT, after=4)
box(s, x, 4.35, W - M - x, 2.5, fill=PANEL, line=LINE, radius=0.1)
tx(s, x + 0.24, 4.47, 5, 0.4, "Next, not built yet", size=22, font=DISPLAY_B, color=CYAN)
tx(s, x + 0.24, 4.95, 5.4, 1.9, ["Hardware counters on bare metal", "Graph neural program features", "RL trained on real timings", "Per-function tuning"], size=18, color=TEXT, after=4)

# ------------------------------------------------------------ 21 closing
s = slide("-O3 is a great default.\nNow it has to prove it.", 7, y=0.95, h=2.3, size=64)
k = [(pct(RS["geomean"]), f"on 33 unseen programs ({pct(RS['excl_largest'])} without the largest win)", AMBER), ("0/33", "measurably slower", GREEN), ("3.83×", "best demo, root cause explained", TEXT)]
wd_ = [4.7, 3.2, 3.8]
x = M
for (a, b, col), w_ in zip(k, wd_):
    tx(s, x, 3.3, w_, 1.0, a, size=56, font=DISPLAY_B, color=col, anchor="m")
    tx(s, x, 4.32, w_ - 0.25, 0.8, b, size=17, color=MUTE)
    x += w_ + 0.1
strip(s, PASSES, M, 5.22, W - 2 * M, 0.2, marks={i for i, p in enumerate(PASSES) if p["name"] in ("simplifycfg", "instcombine")})
tx(s, M, 5.6, 7.6, 0.6, "Models shortlist. The stopwatch decides.", size=28, font=DISPLAY, color=TEXT)
tx(s, 7.7, 5.62, W - M - 7.7, 0.6, "Bring a C program. Let's race it.", size=22, font=BODY_B, color=AMBER, align="r", anchor="m")
tx(s, M, 6.33, 12.1, 0.6, "Chirag S  |  Dhanush Singh  |  Gagan S Shamnur  |  Nithin Choudhary A     Guide: Dr. P.B. Mallikarjuna     JSSATE, Bengaluru", size=15, color=MUTE)

# ------------------------------------------------------------ 22 sources
s = slide("References", 7, source=None)
refs = ["Chen et al. AutoFDO. CGO 2016.", "Panchenko et al. BOLT. CGO 2019.", "Trofin et al. MLGO. arXiv 2101.04808, 2021.", "Ashouri et al. Survey on Compiler Autotuning using ML. ACM CSUR 2018.",
        "Mytkowicz et al. Producing Wrong Data Without Doing Anything Obviously Wrong! ASPLOS 2009.", "Kanev et al. Profiling a Warehouse-Scale Computer. ISCA 2015.",
        "Elhage. Performance of the Python 3.14 tail-call interpreter. blog.nelhage.com, 2025.", "PolyBench/C 4.2.1. LLVM test-suite. LLVM Project."]
tx(s, M, 1.8, W - 2 * M, 5.0, refs, size=19, color=TEXT, after=11)

prs.core_properties.title = "NeuroCompiler: Open Day"
prs.core_properties.author = "Chirag S, Dhanush Singh, Gagan S Shamnur, Nithin Choudhary A"
prs.save(OUT / "NeuroCompiler_Open_Day.pptx")

# ------------------------------------------------------------ speaking script
md = ["# NeuroCompiler Open Day: speaking script", "", "Full talk: about 14 minutes. The script for each slide is also in that slide's speaker notes.", "",
      "## 60-second pitch", "", PITCH, "", "## 3-minute stall tour", "", TOUR, "", "## Full talk", ""]
for i in range(1, n_slide + 1):
    n = NOTES[i]
    md += [f"### Slide {i}: {prs.slides[i - 1].shapes.title.text_frame.text.replace(chr(10), ' ').replace(chr(11), ' ')} ({n['t']})", "", n["say"], "", f"*Evidence: {n['evidence']}*", ""]
md += ["## Likely questions", ""]
for q, a in QA:
    md += [f"**{q}**", "", a, ""]
(OUT / "SPEAKING_SCRIPT.md").write_text("\n".join(md))
print("slides", n_slide)
