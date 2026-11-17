"""Build open_day/NeuroCompiler_Open_Day.pptx and SPEAKING_SCRIPT.md: the simple 10-slide deck, in the explainer video's order.

Run from the repo root:  open_day/.pptxenv/bin/python open_day/build_deck.py
Result numbers are read from dashboard/static/data/research.json and the saved interpreter run, then rounded as in the video.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, "open_day")
from deck_lib import *  # noqa: E402,F403
from notes import NOTES, NUMBERS, PITCH, QA  # noqa: E402

R = json.load(open("dashboard/static/data/research.json"))
RUN = json.load(open("dashboard/saved/tune-interpreter-loop-3-83x-rl-pick.json"))["result"]
PASSES = json.load(open("open_day/assets/pipeline_order.json"))
OUT = Path("open_day")
A = OUT / "assets"
RS = R["eval"]["summary"]["tune RL + SL"]
GAIN, GAIN_X = round((RS["geomean"] - 1) * 100), round((RS["excl_largest"] - 1) * 100)
C = RUN["confirm"]
BASE_MS, PICK_MS = round(C["base_median_ms"], -1), round(C["pick_median_ms"], -1)

make_background(A / "bg.jpg")
prs = new_deck(A / "bg.jpg")
LAY = prs.slide_layouts[5]    # Title Only: every slide keeps a real title for outline view and screen readers
n_slide = 0


def slide(title, **kw):
    global n_slide
    n_slide += 1
    s = prs.slides.add_slide(LAY)
    add_title(s, title, **{"y": 0.6, "size": 42, **kw})
    tx(s, W - M - 1, 7.0, 1, 0.26, str(n_slide), size=12, color=MUTE, font=MONO, align="r", name="Slide number")
    add_fade(s)
    s.notes_slide.notes_text_frame.text = NOTES[n_slide]["say"] + "\n\nIf asked: " + NOTES[n_slide]["evidence"]
    return s


def team_line(s, y):
    tx(s, M, y, 12.1, 0.4, "Chirag S  |  Dhanush Singh  |  Gagan S Shamnur  |  Nithin Choudhary A     Guide: Dr. P.B. Mallikarjuna", size=16, color=MUTE)


# ------------------------------------------------------------ 1 title
s = slide("NeuroCompiler", y=1.2, h=1.5, size=92)
tx(s, M, 2.65, 11.6, 0.6, "Faster code, measured, not guessed.", size=32, font=DISPLAY, color=AMBER)
strip(s, PASSES, M, 3.62, W - 2 * M, 0.72)
team = [("Chirag S", "1JS23CS039"), ("Dhanush Singh", "1JS23CS048"), ("Gagan S Shamnur", "1JS23CS052"), ("Nithin Choudhary A", "1JS23CS101")]
for i, (nm, usn) in enumerate(team):
    x = M + i * 2.3
    tx(s, x, 4.75, 2.28, 0.34, nm, size=18, font=BODY_B)
    tx(s, x, 5.09, 2.28, 0.28, usn, size=13, color=MUTE, font=MONO)
tx(s, M + 9.55, 4.75, 2.6, 0.34, "Dr. P.B. Mallikarjuna", size=18, font=BODY_B, color=AMBER)
tx(s, M + 9.55, 5.09, 2.6, 0.28, "Project guide, Professor", size=13, color=MUTE)
box(s, M, 5.75, 0.72, 0.72, fill="FFFFFF", radius=0.08, name="Logo tile")
s.shapes.add_picture("docs/assets/jss_logo.png", Inches(M + .05), Inches(5.8), height=Inches(.62))
box(s, M + 0.84, 5.75, 0.72, 0.72, fill="FFFFFF", radius=0.08, name="Logo tile")
s.shapes.add_picture("docs/assets/vtu_logo.png", Inches(M + .89), Inches(5.8), height=Inches(.62))
tx(s, M + 1.78, 5.77, 10, 0.7, ["Department of Computer Science & Engineering", "JSS Academy of Technical Education, Bengaluru  |  Visvesvaraya Technological University"],
   size=15, color=MUTE, spacing=1.0)

# ------------------------------------------------------------ 2 one recipe
s = slide("One recipe for every program")
tx(s, M, 1.55, 12, 0.5, "-O3 runs 109 steps, in the same order, for every program.", size=24, color=MUTE)
box(s, M, 2.4, 1.45, 1.4, fill=RAISED, line=LINE, content="your code", size=18, font=MONO, radius=0.1)
strip(s, PASSES, 2.3, 2.4, W - 2.3 - 2.3, 1.4)
box(s, W - M - 1.45, 2.4, 1.45, 1.4, fill=RAISED, line=LINE, content="program", size=18, font=MONO, radius=0.1)
arrow(s, 2.08, 3.1, 2.26, 3.1)
arrow(s, W - 2.28, 3.1, W - 2.08, 3.1)
tx(s, M, 4.2, 12, 0.5, "That recipe is a compromise. One change can:", size=24)
box(s, M, 4.85, 5.95, 0.85, fill="10251D", line=GREEN, radius=0.08, content="speed some programs up", size=22, font=BODY_B, color=GREEN)
box(s, M + 6.18, 4.85, 5.95, 0.85, fill="2A1414", line=RED, radius=0.08, content="slow others down", size=22, font=BODY_B, color=RED)
tx(s, M, 6.05, 12, 0.5, "We look for a faster recipe for each program.", size=26, font=DISPLAY, color=AMBER)

# ------------------------------------------------------------ 3 one rule
s = slide("One rule: only measured runtime counts")
cw, cy, ch_ = 3.9, 1.8, 3.95
cards = [("Race", "Candidates race -O3 in shuffled rounds.", AMBER), ("Control", "An identical copy of -O3 exposes noise.", CYAN), ("Check", "If the output changes, the candidate is rejected.", GREEN)]
for i, (a, b, col) in enumerate(cards):
    x = M + i * (cw + 0.215)
    box(s, x, cy, cw, ch_, fill=PANEL, line=LINE, radius=0.12)
    tx(s, x + 0.3, cy + 0.22, cw - 0.6, 0.65, a, size=32, font=DISPLAY_B, color=col)
    tx(s, x + 0.3, cy + 2.7, cw - 0.55, 1.1, b, size=21, color=TEXT, spacing=0.98)
x = M + 0.3
for r_i, order in enumerate((("-O3", "A", "B"), ("B", "-O3", "A"), ("A", "B", "-O3"))):
    for j, n_ in enumerate(order):
        fill, fg = ("39424F", TEXT) if n_ == "-O3" else (AMBER, INK)
        box(s, x + j * 1.12, cy + 1.0 + r_i * 0.5, 1.04, 0.42, fill=fill, radius=0.05, content=n_, size=15, font=BODY_B, color=fg, inset=0.02)
x = M + cw + 0.215 + 0.3
for j, (lb, col) in enumerate((("-O3", "39424F"), ("-O3 copy", "39424F"))):
    box(s, x, cy + 1.05 + j * 0.65, 3.3, 0.5, fill=col, radius=0.05, content=lb, size=16, font=BODY_B, inset=0.02)
x = M + 2 * (cw + 0.215) + 0.3
box(s, x, cy + 1.05, 3.3, 0.5, fill="10251D", line=GREEN, radius=0.05, content="same output: stays in", size=16, font=BODY_B, color=GREEN, inset=0.02)
box(s, x, cy + 1.7, 3.3, 0.5, fill="2A1414", line=RED, radius=0.05, content="changed output: out", size=16, font=BODY_B, color=RED, inset=0.02)
tx(s, M, 6.05, 12, 0.5, "If the clock can't prove it, it doesn't count.", size=26, font=DISPLAY, color=AMBER)

# ------------------------------------------------------------ 4 how it works
s = slide("Models shortlist. The stopwatch decides.")
steps = [("PPO", "proposes\nnew recipes", ROSE), ("LightGBM", "ranks them\nall", CYAN), ("Top 8", "are compiled,\nchecked, timed", AMBER), ("Fastest", "must win again\non a fresh run", AMBER)]
sw, sy, sh_ = 2.3, 2.3, 2.1
boxes = []
for i, (a, b, col) in enumerate(steps):
    x = M + i * (sw + 0.32)
    q = box(s, x, sy, sw, sh_, fill=PANEL, line=col, lw=1.75, radius=0.12, name=a)
    boxes.append(q)
    tx(s, x + 0.1, sy + 0.28, sw - 0.2, 0.65, a, size=28, font=DISPLAY_B, color=col, align="c")
    tx(s, x + 0.1, sy + 0.98, sw - 0.2, 0.9, b.split("\n"), size=18, color=TEXT, align="c", spacing=0.98)
ship = box(s, 11.05, sy, W - M - 11.05, sh_, fill=AMBER, radius=0.12, content=[[("Ship", {"font": DISPLAY_B, "size": 26, "color": INK})]])
for i in range(3):
    arrow(s, 0, 0, 0, 0, begin=(boxes[i], 3), end=(boxes[i + 1], 1), color=TEXT, lw=2)
arrow(s, 0, 0, 0, 0, begin=(boxes[3], 3), end=(ship, 1), color=TEXT, lw=2)
tx(s, M, 1.75, 5, 0.34, "THE MODELS", size=15, font=MONO, color=CYAN)
tx(s, M + 2 * (sw + 0.32), 1.75, 5, 0.34, "THE STOPWATCH", size=15, font=MONO, color=AMBER)
rail = box(s, M + 3 * (sw + 0.32), 4.85, W - 2 * M - 3 * (sw + 0.32), 0.62, fill=RAISED, line=SLATE, radius=0.08, content="If it can't: keep -O3", size=19, font=BODY_B)
xf = M + 3 * (sw + 0.32) + sw / 2
arrow(s, xf, sy + sh_, xf, 4.85, color=SLATE, dash=True)
tx(s, M, 4.87, 7.5, 0.6, "Both models learned from 146 real programs.", size=20, color=MUTE, anchor="m")
tx(s, M, 6.05, 12, 0.5, "Scouts suggest. Only the race picks the winner.", size=26, font=DISPLAY, color=AMBER)

# ------------------------------------------------------------ 5 result
s = slide("Tested on 33 programs it had never seen")
items = [(f"{GAIN}%", "faster than -O3,\non average", AMBER), (f"~{GAIN_X}%", "without its\nbiggest win", TEXT), (f"{RS['slower']}", "measurably\nslower", GREEN)]
cw = 3.9
for i, (a, b, col) in enumerate(items):
    x = M + i * (cw + 0.215)
    box(s, x, 1.8, cw, 3.75, fill=PANEL, line=LINE, radius=0.12)
    tx(s, x, 2.0, cw, 1.95, a, size=110, font=DISPLAY_B, color=col, align="c", anchor="m")
    tx(s, x + 0.2, 4.1, cw - 0.4, 1.2, b.split("\n"), size=24, color=TEXT, align="c", spacing=0.98)
tx(s, M, 5.95, 12, 0.5, "Most programs stayed at -O3. A few got much faster.", size=26, font=DISPLAY, color=AMBER)

# ------------------------------------------------------------ 6 best demo
s = slide(f"Best demo: {BASE_MS:.0f} ms down to {PICK_MS:.0f} ms")
bx, bw = 2.15, W - M - 2.15
tx(s, M, 1.85, 1.5, 0.8, "-O3", size=28, font=DISPLAY_B, color=SLATE, anchor="m")
box(s, bx, 1.85, bw, 0.8, fill="39424F", radius=0.04, content=f"{BASE_MS:.0f} ms", size=28, font=DISPLAY_B, align="r", inset=0.2, name="-O3 runtime bar")
tx(s, M, 2.85, 1.55, 0.8, "Tuned", size=28, font=DISPLAY_B, color=AMBER, anchor="m")
bar2 = bw * PICK_MS / BASE_MS
box(s, bx, 2.85, bar2, 0.8, fill=AMBER, radius=0.04, name="Tuned runtime bar")
tx(s, bx + bar2 + 0.18, 2.85, 3, 0.8, f"{PICK_MS:.0f} ms", size=28, font=DISPLAY_B, color=AMBER, anchor="m")
tx(s, M, 4.05, 12.1, 0.5, "Same code. Why faster? An interpreter jumps from one instruction to the next.", size=24)
box(s, M, 4.7, 5.95, 0.9, fill="2A1414", line=RED, radius=0.08, content="-O3 merged its jumps into one", size=22, font=BODY_B, color=RED)
box(s, M + 6.18, 4.7, 5.95, 0.9, fill="10251D", line=GREEN, radius=0.08, content="Our recipe kept them separate", size=22, font=BODY_B, color=GREEN)
tx(s, M, 5.95, 12, 0.5, "This is our best case, not the average, and not one of the 33 test programs.", size=22, font=DISPLAY, color=MUTE)

# ------------------------------------------------------------ 7 dashboard
s = slide("It's real. Try it live.")
im = Image.open("docs/assets/shots/tune_diff.jpg")
im.crop((28, 0, 1412, 700)).save(A / "dash_diff.jpg", quality=93)
pic = s.shapes.add_picture(str(A / "dash_diff.jpg"), Inches(2.33), Inches(1.6), width=Inches(8.67))
pic.line.color.rgb, pic.line.width = rgb(LINE), Pt(1)
set_descr(pic, "NeuroCompiler dashboard comparing the -O3 pass sequence with the tuned sequence")
tx(s, M, 6.1, 12.13, 0.5, "Built on LLVM 18, with a live dashboard showing every changed pass.", size=24, font=DISPLAY, color=AMBER, align="c")

# ------------------------------------------------------------ 8 lesson
s = slide("What we learned")
hw = (W - 2 * M - 0.25) / 2
for x, col, lead, big, sub in ((M, RED, "MODELS ALONE", "Weak", "Many programs got slower"), (M + hw + 0.25, GREEN, "MODELS + STOPWATCH", "Reliable", "None got measurably slower")):
    box(s, x, 1.7, hw, 2.75, fill=PANEL, line=LINE, radius=0.12)
    box(s, x, 1.86, 0.05, 2.43, fill=col, radius=0)
    tx(s, x + 0.32, 1.9, hw - 0.6, 0.36, lead, size=15, font=MONO, color=MUTE)
    tx(s, x + 0.32, 2.3, hw - 0.6, 1.15, big, size=58, font=DISPLAY_B, color=col, anchor="m")
    tx(s, x + 0.32, 3.55, hw - 0.6, 0.5, sub, size=22)
tx(s, M, 4.75, 12.1, 0.55, [[("RL added little: ", {"font": BODY_B, "color": ROSE}), ("+0.2%, not significant. We kept it by choice, and we say so.", {})]], size=23)
tx(s, M, 5.33, 12.1, 0.5, [[("Our scope: ", {"font": BODY_B, "color": MUTE}), ("one machine, one input per program.", {})]], size=23)
tx(s, M, 6.05, 12, 0.5, "Measurement is what makes it reliable.", size=26, font=DISPLAY, color=AMBER)

# ------------------------------------------------------------ 9 uses
s = slide("Where this could help")
cols = [("WORKS TODAY", GREEN, ["Programs that run again and again", "Finding where a compiler hurts"]),
        ("NEEDS MORE WORK", AMBER, ["Interpreters and language runtimes", "Release builds"]),
        ("FUTURE", SLATE, ["Data centres"])]
cw = (W - 2 * M - 0.4) / 3
for i, (lab, col, items) in enumerate(cols):
    x = M + i * (cw + 0.2)
    box(s, x, 1.8, cw, 3.75, fill=PANEL, line=LINE, radius=0.12)
    box(s, x + 0.28, 2.02, cw - 0.56, 0.05, fill=col, radius=0)
    tx(s, x + 0.28, 2.17, cw - 0.56, 0.4, lab, size=17, font=MONO, color=col)
    tx(s, x + 0.28, 2.75, cw - 0.56, 2.6, items, size=24, after=16, spacing=0.98)
tx(s, M, 5.95, 12, 0.5, "Nothing here is deployed in production yet.", size=26, font=DISPLAY, color=AMBER)

# ------------------------------------------------------------ 10 close
s = slide("Faster code,\nmeasured, not guessed.", y=1.15, h=2.5, size=72)
strip(s, PASSES, M, 3.95, W - 2 * M, 0.32)
tx(s, M, 4.6, 12, 0.6, "Bring a C program. Let's race it.", size=32, font=DISPLAY, color=AMBER)
team_line(s, 5.5)
tx(s, M, 5.9, 12, 0.4, "JSS Academy of Technical Education, Bengaluru", size=16, color=MUTE)

prs.core_properties.title = "NeuroCompiler: Open Day"
prs.core_properties.author = "Chirag S, Dhanush Singh, Gagan S Shamnur, Nithin Choudhary A"
prs.save(OUT / "NeuroCompiler_Open_Day.pptx")

# ------------------------------------------------------------ speaking script
md = ["# NeuroCompiler Open Day: speaking script", "", "Full talk: about 5 minutes, plus any live demo. The script for each slide is also in that slide's speaker notes.", "",
      "## 60-second pitch", "", PITCH, "", "## Full talk", ""]
for i in range(1, n_slide + 1):
    n = NOTES[i]
    title = prs.slides[i - 1].shapes.title.text_frame.text.replace(chr(10), " ").replace(chr(11), " ")
    md += [f"### Slide {i}: {title} ({n['t']})", "", n["say"], "", f"*If asked: {n['evidence']}*", ""]
md += ["## Every number, explained", ""] + [f"- **{a}:** {b}" for a, b in NUMBERS] + ["", "## Likely questions", ""]
for q, a in QA:
    md += [f"**{q}**", "", a, ""]
(OUT / "SPEAKING_SCRIPT.md").write_text("\n".join(md))
print("slides", n_slide, "gain", GAIN, GAIN_X, "ms", BASE_MS, PICK_MS)
