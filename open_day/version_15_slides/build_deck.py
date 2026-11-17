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
KB = {t["label"]: t for t in R["kb"]["top"]}
k8 = KB["-force-vector-width=8"]
s = slide("Every program gets the same 109-step recipe", 1, source="LLVM 18.1.8 default<O3>. Edit range from screening on 31 programs")
tx(s, M, 1.62, 11.8, 0.45, "A compiler improves code in small steps called passes. -O3 runs them in one fixed order.", size=20, color=MUTE)
box(s, M, 2.35, 1.45, 1.3, fill=RAISED, line=LINE, content=[[("source", {"font": MONO, "size": 17})], [("your program", {"size": 13, "color": MUTE})]], radius=0.1)
strip(s, PASSES, 2.3, 2.35, W - 2.3 - 2.3, 1.3)
box(s, W - M - 1.45, 2.35, 1.45, 1.3, fill=RAISED, line=LINE, content=[[("binary", {"font": MONO, "size": 17})], [("what runs", {"size": 13, "color": MUTE})]], radius=0.1)
arrow(s, 2.08, 3.0, 2.26, 3.0)
arrow(s, W - 2.28, 3.0, W - 2.08, 3.0)
tx(s, M, 4.1, 11.8, 0.4, "But the same edit can help one program and hurt another:", size=20)
tx(s, M, 4.55, 2.5, 1.05, f"{k8['max']:.2f}×", size=62, font=DISPLAY_B, color=GREEN, anchor="m")
tx(s, M + 2.6, 4.55, 3, 1.05, "on its best program", size=19, color=MUTE, anchor="m")
tx(s, 6.9, 4.55, 2.5, 1.05, f"{k8['min']:.2f}×", size=62, font=DISPLAY_B, color=RED, anchor="m")
tx(s, 9.5, 4.55, 3.2, 1.05, "on its worst", size=19, color=MUTE, anchor="m")
tx(s, M, 5.95, 11.8, 0.5, "One recipe for every dish, tailored to nothing.", size=24, font=DISPLAY)

# ------------------------------------------------------------ 4 hard
N = R["kb"]["edits"]
c4 = math.comb(N, 4)
yrs = c4 / (365.25 * 24 * 3600)
ir = R["ir"]
s = slide("Why not just try everything?", 1, source=f"Combinations calculated from {N} edits. Chart: 700 sampled from {ir['n']:,} timed recipes. Ashouri et al. 2018")
tx(s, M, 1.85, 5.6, 1.15, f"{c4 / 1e6:.0f} million", size=66, font=DISPLAY_B, color=AMBER, anchor="m")
tx(s, M, 3.0, 5.4, 0.8, f"recipes from just 4 of our {N} catalogued edits", size=21)
tx(s, M, 3.95, 5.6, 0.85, f"{yrs:.1f} years", size=44, font=DISPLAY_B, anchor="m")
tx(s, M, 4.8, 5.4, 0.45, "to time them, at one second each", size=19, color=MUTE)
random.seed(3)
pts = [p for p in ir["sample"] if 0.5 <= p[0] <= 1.5 and 0.7 <= p[1] <= 1.5]
pts = random.sample(pts, 700)
cd = XyChartData()
se = cd.add_series("Candidate")
for a, b in pts:
    se.add_data_point(a, b)
tx(s, 6.75, 1.72, 6, 0.42, [[("Smaller code is no shortcut: ", {"color": TEXT}), (f"ρ = {ir['rho']:.2f}".replace("-", "−"), {"color": AMBER, "font": DISPLAY_B})]], size=21)
gf = s.shapes.add_chart(XL_CHART_TYPE.XY_SCATTER, Inches(6.6), Inches(2.15), Inches(6.15), Inches(3.75), cd)
set_descr(gf, "Scatter of code size vs speedup. No visible relationship.")
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
va.minimum_scale, va.maximum_scale, va.major_unit = 0.7, 1.5, 0.4
ca.minimum_scale, ca.maximum_scale, ca.major_unit = 0.5, 1.5, 0.25
for ax, ttl in ((va, "Speed vs -O3"), (ca, "Code size vs -O3")):
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
tx(s, M, 6.1, 12, 0.5, "So we judge one thing only: time.", size=24, font=DISPLAY)

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

# ------------------------------------------------------------ 12 two models
M_ = R["models"]
g = M_["tune_cv"]["summary"]["gbr"]
s = slide("Two models, two jobs", 4, source="nc/rl.py, nc/model.py. Rank correlation 95% CI +0.06 to +0.15, on families held out of training")
hw = (W - 2 * M - 0.25) / 2
rows = [(M, ROSE, "PPO", "Proposes", "24", "recipes at most per program, learned from the gain LightGBM predicts"),
        (M + hw + 0.25, CYAN, "LightGBM", "Ranks", f"{g['spearman']:+.2f}", "rank correlation on unseen families: useful, but weak alone")]
for x, col, name, role, num, txt_ in rows:
    box(s, x, 1.62, hw, 3.7, fill=PANEL, line=LINE, radius=0.12)
    tx(s, x + 0.28, 1.76, hw - 0.5, 0.65, name, size=36, font=DISPLAY_B, color=col)
    tx(s, x + 0.28, 2.42, hw - 0.5, 0.4, role, size=20, font=BODY_B)
    tx(s, x + 0.28, 2.95, hw - 0.5, 1.2, num, size=70, font=DISPLAY_B, color=col, anchor="m")
    tx(s, x + 0.28, 4.2, hw - 0.56, 0.95, txt_, size=18, color=MUTE)
tx(s, M, 5.6, 12.1, 1.0, "Neither model picks the winner. They only decide what is worth timing.", size=26, font=DISPLAY, color=AMBER)

# ------------------------------------------------------------ 13 proof
s = slide("Nothing ships without proof", 4, source="nc/deploy.py, results/selftest_*.json. Branchy run: open_day/assets/runs/tune_branchy_2026-10-30.log")
H_ = R["harness"]["selftest_v14"][-1]
gates = [("1", "Same answer?", "Output must exactly match the -O0 build"), ("2", "Faster in the race?", "Shuffled rounds on one pinned core"), ("3", "Faster again?", "Fresh 20 rounds, over 1% faster, clean control")]
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
box(s, M, 4.0, W - 2 * M, 0.6, fill=RAISED, line=SLATE, radius=0.08, content=[[("Otherwise -O3 ships.", {"font": BODY_B, "size": 18})]])
for i in range(3):
    xm = M + i * (gw + 0.27) + gw / 2
    arrow(s, xm, gy + 1.9, xm, 4.0, color=SLATE, dash=True)
ps = [(f"{H_['ci_halfwidth_pct']:.2f}%", "timing uncertainty", GREEN), (f"{RS['no_gain']} of 33", "test programs safely kept -O3", TEXT), ("1.014×", "just missed gate 3 in a fresh run, so -O3 shipped", AMBER)]
for i, (a, b, col) in enumerate(ps):
    x = M + i * 4.1
    tx(s, x, 4.85, 3.9, 0.85, a, size=40, font=DISPLAY_B, color=col, anchor="m")
    tx(s, x, 5.72, 3.8, 0.8, b, size=18, color=MUTE)

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
tx(s, 9.4, 5.8, 3.35, 1.1, f"95% CI {pct(RS['ci'][0])} to {pct(RS['ci'][1])}. Median program 1.00×. Lead over random search not significant.", size=14, color=MUTE)

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
qs = [("How much room is above -O3?", "First sample missed our goal, so we reset the target, searched wider and found +15.6%.", CYAN),
      ("Does RL beat LightGBM?", "Not yet: +0.2%, not significant, shipped on 1 of 33. Kept by team decision.", ROSE),
      ("Can we skip running the program?", f"Partly: {pct(PR['geomean'])}, CI includes zero, under our +1.5% goal. It ships as advice only.", AMBER)]
for i, (q_, a_, col) in enumerate(qs):
    y = 1.62 + i * 1.47
    box(s, 5.0, y, W - M - 5.0, 1.36, fill=PANEL, line=LINE, radius=0.1)
    box(s, 5.0, y + 0.14, 0.05, 1.08, fill=col, radius=0)
    tx(s, 5.24, y + 0.1, 7.3, 0.42, q_, size=21, font=DISPLAY_B)
    tx(s, 5.24, y + 0.54, 7.32, 0.75, a_, size=17, color=MUTE, spacing=0.98)
tx(s, M, 6.15, 12.1, 0.5, [[("Scope: ", {"color": AMBER, "font": BODY_B}), ("one machine, 33 test programs, one input each, single-threaded code.", {"color": TEXT})]], size=18)

# ------------------------------------------------------------ 19 real world
s = slide("Where this could matter", 6, source="External figures are other projects (Elhage 2025; MLGO 2021). Nothing here is deployed")
cols = [("DEMONSTRATED", "Works today", GREEN, [("Numerical kernels", "Tune once, run thousands of times. Test set: durbin 2.81×, 3mm 1.43×."),
                                                 ("Compiler bug hunting", "Turn a mystery slowdown into a concrete lead.")]),
        ("ADAPTABLE", "Needs engineering", AMBER, [("Language runtimes", "Merged dispatch cost CPython 9–12%. Timing can catch it."),
                                                  ("Release builds", "Tune on the benchmark, keep the proof.")]),
        ("FUTURE POTENTIAL", "Needs major development", SLATE, [("Data-centre fleets", ["Small gains pay at scale: Google deployed ML wins of 0.3–1.5% QPS.",
                                                                                     [("Needs multi-threaded and live-traffic support first.", {"color": TEXT})]])])]
cw = (W - 2 * M - 0.4) / 3
for i, (lab, sub, col, items) in enumerate(cols):
    x = M + i * (cw + 0.2)
    box(s, x, 1.62, cw, 0.055, fill=col, radius=0)
    tx(s, x, 1.75, cw, 0.35, lab, size=15, font=MONO, color=col)
    tx(s, x, 2.07, cw, 0.35, sub, size=17, color=MUTE)
    for j, (a, b) in enumerate(items):
        y = 2.55 + j * 2.15
        hh = 2.02 if len(items) > 1 else 4.17
        box(s, x, y, cw, hh, fill=PANEL, line=LINE, radius=0.1)
        tx(s, x + 0.2, y + 0.16, cw - 0.38, 0.42, a, size=21, font=BODY_B)
        tx(s, x + 0.2, y + 0.66, cw - 0.38, hh - 0.75, b, size=18, color=MUTE, spacing=0.98, after=10)

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
refs = ["Ashouri et al. Survey on Compiler Autotuning using ML. ACM CSUR 2018.", "Trofin et al. MLGO. arXiv 2101.04808, 2021.",
        "Mytkowicz et al. Producing Wrong Data Without Doing Anything Obviously Wrong! ASPLOS 2009.",
        "Elhage. Performance of the Python 3.14 tail-call interpreter. blog.nelhage.com, 2025.", "PolyBench/C 4.2.1. LLVM test-suite. LLVM Project."]
tx(s, M, 1.8, W - 2 * M, 5.0, refs, size=19, color=TEXT, after=11)

prs.core_properties.title = "NeuroCompiler: Open Day"
prs.core_properties.author = "Chirag S, Dhanush Singh, Gagan S Shamnur, Nithin Choudhary A"
prs.save(OUT / "NeuroCompiler_Open_Day.pptx")

# ------------------------------------------------------------ speaking script
md = ["# NeuroCompiler Open Day: speaking script", "", "Full talk: about 7 minutes. The script for each slide is also in that slide's speaker notes.", "",
      "## 60-second pitch", "", PITCH, "", "## 3-minute stall tour", "", TOUR, "", "## Full talk", ""]
for i in range(1, n_slide + 1):
    n = NOTES[i]
    md += [f"### Slide {i}: {prs.slides[i - 1].shapes.title.text_frame.text.replace(chr(10), ' ').replace(chr(11), ' ')} ({n['t']})", "", n["say"], "", f"*Evidence: {n['evidence']}*", ""]
md += ["## Likely questions", ""]
for q, a in QA:
    md += [f"**{q}**", "", a, ""]
(OUT / "SPEAKING_SCRIPT.md").write_text("\n".join(md))
print("slides", n_slide)
