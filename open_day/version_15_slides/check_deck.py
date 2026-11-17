"""Automated checks on the built deck: bounds, minimum font sizes, notes, titles, and result numbers vs research.json."""
import json
import re
import sys

from pptx import Presentation
from pptx.util import Emu

d = json.load(open("dashboard/static/data/research.json"))
prs = Presentation("open_day/NeuroCompiler_Open_Day.pptx")
W, H = prs.slide_width, prs.slide_height
bad, small, fonts, txt = [], [], {}, []
for i, s in enumerate(prs.slides, 1):
    assert s.shapes.title is not None and s.shapes.title.text_frame.text.strip(), i
    assert s.has_notes_slide and "Evidence:" in s.notes_slide.notes_text_frame.text, i
    for sh in s.shapes:
        if sh.left is not None and (sh.left < 0 or sh.top < 0 or sh.left + sh.width > W + 2000 or sh.top + sh.height > H + 2000):
            bad.append((i, sh.name))
        if sh.has_text_frame:
            for p in sh.text_frame.paragraphs:
                for r in p.runs:
                    txt.append((i, r.text))
                    if r.font.size:
                        fonts[r.font.name] = fonts.get(r.font.name, 0) + 1
                        if r.font.size.pt < 11:
                            small.append((i, r.text, r.font.size.pt))
print("off-slide:", bad)
print("under 11 pt:", small)
print("fonts:", fonts)
alltxt = " ".join(t for _, t in txt)
S = d["eval"]["summary"]["tune RL + SL"]
need = [f"{(S['geomean'] - 1) * 100:+.2f}%", f"{(S['excl_largest'] - 1) * 100:+.2f}%", f"{S['ge5']}/33", f"{S['slower']}/33", "587 million", "109"]
for n in need:
    print(n, "ok" if n in alltxt else "MISSING")
for bad_word in ("deployed in production", "guarantee", "always faster", "TODO"):
    assert bad_word not in alltxt, bad_word
print("slides", len(prs.slides), "charts", sum(1 for s in prs.slides for x in s.shapes if x.has_chart), "pictures", sum(1 for s in prs.slides for x in s.shapes if x.shape_type == 13))
