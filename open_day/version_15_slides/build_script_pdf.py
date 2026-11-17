"""Print the speaking script as a PDF, one block per slide with a thumbnail.
Run from the repo root after render.sh:  open_day/.pptxenv/bin/python open_day/build_script_pdf.py"""
import base64
import html
import io
import re
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image
from pptx import Presentation

sys.path.insert(0, "open_day")
from notes import NOTES, PITCH, QA, TOUR  # noqa: E402

prs = Presentation("open_day/NeuroCompiler_Open_Day.pptx")
E = html.escape


def md(t):
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", E(t))


def thumb(i):
    im = Image.open(f"open_day/review/s{i:02d}.png").convert("RGB").resize((800, 450))
    b = io.BytesIO()
    im.save(b, "JPEG", quality=85)
    return "data:image/jpeg;base64," + base64.b64encode(b.getvalue()).decode()


blocks = []
for i, n in NOTES.items():
    title = re.sub(r"[\n\x0b]", " ", prs.slides[i - 1].shapes.title.text_frame.text)
    blocks.append(f"""<section class="s"><div class="l"><img src="{thumb(i)}" alt="Slide {i}"><div class="t">{E(n['t'])}</div></div>
<div class="r"><h3><span>{i}</span>{E(title)}</h3><p class="say">{E(n['say'])}</p><p class="ev"><b>If asked:</b> {E(n['evidence'])}</p></div></section>""")
tour = "".join(f"<li>{md(re.sub(r'^[0-9]+[.] ', '', x))}</li>" for x in TOUR.split("\n"))
qa = "".join(f'<div class="q"><b>{E(q)}</b><p>{E(a)}</p></div>' for q, a in QA)
doc = f"""<!doctype html><html><head><meta charset="utf-8"><title>NeuroCompiler Speaking Script</title><style>
@page {{ size: A4; margin: 15mm 14mm 16mm; @bottom-right {{ content: counter(page); font: 9pt 'Segoe UI'; color: #667; }} @bottom-left {{ content: "NeuroCompiler Open Day: speaking script"; font: 9pt 'Segoe UI'; color: #667; }} }}
body {{ font: 11pt/1.45 'Segoe UI', sans-serif; color: #15191f; margin: 0; }}
h1 {{ font: 600 25pt Bahnschrift, 'Segoe UI'; margin: 0 0 2mm; }}
h2 {{ font: 600 14.5pt Bahnschrift, 'Segoe UI'; margin: 7mm 0 2.5mm; padding-bottom: 1mm; border-bottom: 1.5pt solid #e09a10; break-after: avoid; }}
.sub {{ color: #556; margin: 0 0 3mm; }}
.pitch {{ background: #fff6e3; border-left: 3pt solid #e09a10; padding: 3mm 4mm; }}
ol {{ margin: 0; padding-left: 5mm; }}
.s {{ display: flex; gap: 5mm; padding: 3.5mm 0; border-bottom: .5pt solid #ccd; break-inside: avoid; }}
.l {{ flex: 0 0 56mm; }} .l img {{ width: 56mm; display: block; border-radius: 1mm; }}
.t {{ font: 9pt Consolas, monospace; color: #667; margin-top: 1mm; }}
.r {{ flex: 1; min-width: 0; }}
h3 {{ font: 600 12pt Bahnschrift, 'Segoe UI'; margin: 0 0 1.5mm; }} h3 span {{ color: #b87800; margin-right: 2mm; }}
.say {{ margin: 0 0 1.5mm; }} .ev {{ margin: 0; font-size: 8.5pt; line-height: 1.35; color: #556; overflow-wrap: anywhere; }}
.q {{ margin-bottom: 2.5mm; break-inside: avoid; }} .q p {{ margin: .5mm 0 0; }}
</style></head><body>
<h1>NeuroCompiler</h1><p class="sub">Open Day speaking script. 15 slides, about 7 minutes. The main text is what to say; "If asked" is backup detail.</p>
<h2>60-second pitch</h2><div class="pitch">{E(PITCH)}</div>
<h2>3-minute stall tour</h2><ol>{tour}</ol>
<h2>Full talk, slide by slide</h2>{''.join(blocks)}
<h2>Likely questions</h2>{qa}
</body></html>"""
out = Path("open_day/NeuroCompiler_Speaking_Script.pdf")
tmp = Path("/mnt/c/Users/Public/nc_script_tmp")
tmp.mkdir(exist_ok=True)
(tmp / "script.html").write_text(doc, encoding="utf8")
base = "C:\\Users\\Public\\nc_script_tmp\\"
subprocess.run(["/mnt/c/Program Files/Google/Chrome/Application/chrome.exe", "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                f"--print-to-pdf={base}script.pdf", f"file:///{base}script.html".replace("\\", "/")], check=True, timeout=120, capture_output=True)
shutil.copy(tmp / "script.pdf", out)
print(out, out.stat().st_size)
