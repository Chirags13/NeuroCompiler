"""Drawing helpers for the Open Day deck (python-pptx, native shapes and charts)."""
from __future__ import annotations

import json
import re
from copy import deepcopy
from pathlib import Path

import numpy as np
from lxml import etree
from PIL import Image
from pptx import Presentation
from pptx.chart.data import CategoryChartData, XyChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LABEL_POSITION, XL_LEGEND_POSITION, XL_MARKER_STYLE, XL_TICK_LABEL_POSITION, XL_TICK_MARK
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.opc.constants import RELATIONSHIP_TYPE as RT
from pptx.oxml.ns import qn
from pptx.util import Emu, Inches, Pt

W, H, M = 13.333, 7.5, 0.6
INK, PANEL, RAISED, LINE = "0A0C10", "12161D", "1A2029", "2B333F"
TEXT, MUTE, AMBER, CYAN, ROSE, GREEN, RED, SLATE = "F4F6F8", "A3ADBB", "FFB224", "3CCFE6", "FF5D8F", "39D98A", "FF5A52", "8A94A3"
DISPLAY, DISPLAY_B, BODY, BODY_B, MONO = "Bahnschrift", "Bahnschrift SemiBold", "Segoe UI", "Segoe UI Semibold", "Consolas"
GROUP_COLOR = {"cleanup": "4B5A70", "loop": CYAN, "vector": AMBER, "inter": ROSE, "other": "343D4B"}
ACTS = ["Curiosity", "The problem", "The idea", "What we built", "Under the hood", "Proof", "Real world", "Impact"]


def rgb(h):
    return RGBColor.from_string(h)


def new_deck(bg_path: Path) -> Presentation:
    """Blank 16:9 deck with a dark theme: theme colours and fonts, dark colour map, vignette background on the master."""
    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(W), Inches(H)
    master = prs.slide_master
    theme = master.part.part_related_by(RT.THEME)
    x = theme.blob.decode("utf8")
    colors = {"dk1": INK, "lt1": TEXT, "dk2": PANEL, "lt2": MUTE, "accent1": AMBER, "accent2": CYAN, "accent3": ROSE,
              "accent4": GREEN, "accent5": RED, "accent6": SLATE, "hlink": CYAN, "folHlink": MUTE}
    for k, v in colors.items():
        x = re.sub(rf"<a:{k}>.*?</a:{k}>", f'<a:{k}><a:srgbClr val="{v}"/></a:{k}>', x, flags=re.S)
    x = re.sub(r'(<a:majorFont>\s*<a:latin typeface=")[^"]*', rf"\g<1>{DISPLAY}", x)
    x = re.sub(r'(<a:minorFont>\s*<a:latin typeface=")[^"]*', rf"\g<1>{BODY}", x)
    x = re.sub(r'<a:clrScheme name="[^"]*"', '<a:clrScheme name="NeuroCompiler"', x)
    x = re.sub(r'<a:fontScheme name="[^"]*"', '<a:fontScheme name="NeuroCompiler"', x)
    theme._blob = x.encode("utf8")
    cm = master._element.find(qn("p:clrMap"))
    cm.set("bg1", "dk1"), cm.set("tx1", "lt1"), cm.set("bg2", "dk2"), cm.set("tx2", "lt2")
    _, rid = master.part.get_or_add_image_part(str(bg_path))
    csld = master._element.find(qn("p:cSld"))
    old = csld.find(qn("p:bg"))
    if old is not None:
        csld.remove(old)
    bg = etree.fromstring(
        '<p:bg xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" '
        'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f'<p:bgPr><a:blipFill dpi="0" rotWithShape="1"><a:blip r:embed="{rid}"/><a:stretch><a:fillRect/></a:stretch></a:blipFill>'
        '<a:effectLst/></p:bgPr></p:bg>')
    csld.insert(0, bg)
    return prs


def make_background(path: Path, seed=7):
    """Very quiet vignette with a faint warm glow, dithered to avoid banding on projectors."""
    w, h = 1920, 1080
    yy, xx = np.mgrid[0:h, 0:w].astype(float)
    glow = np.exp(-(((xx - w * .86) / (w * .55)) ** 2 + ((yy + h * .05) / (h * .7)) ** 2))
    base = np.array([10, 12, 16], float)
    img = base + glow[..., None] * np.array([13, 12, 13], float)
    rng = np.random.default_rng(seed)
    img = np.clip(img + rng.normal(0, .6, img.shape), 0, 255).astype(np.uint8)
    Image.fromarray(img).save(path, quality=95)


def add_title(slide, text, x=M, y=0.72, w=W - 2 * M, h=0.95, size=38, color=TEXT, font=DISPLAY_B, anchor=MSO_ANCHOR.TOP):
    t = slide.shapes.title
    t.left, t.top, t.width, t.height = Inches(x), Inches(y), Inches(w), Inches(h)
    tf = t.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    lines = text.split("\n")
    for i, ln in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = PP_ALIGN.LEFT
        p.line_spacing = 0.95
        r = p.add_run()
        r.text = ln
        r.font.size, r.font.name, r.font.bold = Pt(size), font, False
        r.font.color.rgb = rgb(color)
    return t


def tx(slide, x, y, w, h, content, size=18, color=TEXT, font=BODY, bold=False, align="l", anchor="t", spacing=None, after=None, name=None):
    """content: str | list of paragraphs; a paragraph is str | list of runs; a run is str | (str, dict(color,font,size,bold))."""
    s = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    if name:
        s.name = name
    tf = s.text_frame
    fill_text(tf, content, size, color, font, bold, align, anchor, spacing, after)
    return s


def fill_text(tf, content, size, color, font, bold, align, anchor, spacing=None, after=None, inset=0.0):
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = Inches(inset)
    tf.vertical_anchor = {"t": MSO_ANCHOR.TOP, "m": MSO_ANCHOR.MIDDLE, "b": MSO_ANCHOR.BOTTOM}[anchor]
    paras = content if isinstance(content, list) else [content]
    for i, para in enumerate(paras):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = {"l": PP_ALIGN.LEFT, "c": PP_ALIGN.CENTER, "r": PP_ALIGN.RIGHT}[align]
        if spacing:
            p.line_spacing = spacing
        if after is not None:
            p.space_after = Pt(after)
        for run in (para if isinstance(para, list) else [para]):
            t, o = (run, {}) if isinstance(run, str) else run
            r = p.add_run()
            r.text = t
            r.font.size = Pt(o.get("size", size))
            r.font.name = o.get("font", font)
            r.font.bold = o.get("bold", bold)
            r.font.color.rgb = rgb(o.get("color", color))


def box(slide, x, y, w, h, fill=PANEL, line=None, radius=0.08, lw=1.0, content=None, size=16, color=TEXT, font=BODY, bold=False,
        align="c", anchor="m", inset=0.1, shape=None, spacing=None, after=None, name=None, dash=False):
    kind = shape or (MSO_SHAPE.ROUNDED_RECTANGLE if radius else MSO_SHAPE.RECTANGLE)
    s = slide.shapes.add_shape(kind, Inches(x), Inches(y), Inches(w), Inches(h))
    if name:
        s.name = name
    if kind == MSO_SHAPE.ROUNDED_RECTANGLE:
        s.adjustments[0] = min(0.5, radius / min(w, h))
    s.shadow.inherit = False
    if fill:
        s.fill.solid()
        s.fill.fore_color.rgb = rgb(fill)
    else:
        s.fill.background()
    if line:
        s.line.color.rgb = rgb(line)
        s.line.width = Pt(lw)
        if dash:
            from pptx.enum.dml import MSO_LINE
            s.line.dash_style = MSO_LINE.DASH
    else:
        s.line.fill.background()
    if content is not None:
        fill_text(s.text_frame, content, size, color, font, bold, align, anchor, spacing, after, inset)
    return s


def arrow(slide, x1, y1, x2, y2, color=SLATE, lw=1.5, head=True, begin=None, end=None, kind=MSO_CONNECTOR.STRAIGHT, dash=False):
    c = slide.shapes.add_connector(kind, Inches(x1), Inches(y1), Inches(x2), Inches(y2))
    c.line.color.rgb = rgb(color)
    c.line.width = Pt(lw)
    if begin:
        c.begin_connect(*begin)
    if end:
        c.end_connect(*end)
    ln = c.line._get_or_add_ln()
    if dash:
        d = etree.SubElement(ln, qn("a:prstDash"))
        d.set("val", "dash")
    if head:
        e = etree.SubElement(ln, qn("a:tailEnd"))
        e.set("type", "triangle"), e.set("w", "med"), e.set("len", "med")
    return c


def strip(slide, passes, x, y, w, h, gap=0.3, marks=None, mark_color=AMBER, dim="303946", name="Pipeline strip: the 109 real -O3 pass steps"):
    """One tick per real -O3 pass step, in execution order, as a native group."""
    g = slide.shapes.add_group_shape()
    g.name = name
    n = len(passes)
    step = w / n
    tick = step * (1 - gap)
    for i, p in enumerate(passes):
        col = (mark_color if i in marks else dim) if marks is not None else GROUP_COLOR[p["group"]]
        s = g.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(x + i * step), Inches(y), Inches(tick), Inches(h))
        s.fill.solid()
        s.fill.fore_color.rgb = rgb(col)
        s.line.fill.background()
        s.shadow.inherit = False
    return g


def chrome(slide, act, num, source=None):
    """Kicker, 8-part act tracker, slide number and source line."""
    tx(slide, M, 0.34, 8, 0.3, [[(f"{act + 1:02d}", {"color": AMBER}), ("  ", {}), (ACTS[act].upper(), {"color": MUTE})]],
       size=13, font=MONO, name="Act label")
    for i in range(8):
        col = AMBER if i == act else ("5A6474" if i < act else LINE)
        box(slide, M + i * 0.36, 7.17, 0.3, 0.045, fill=col, radius=0, name=f"Act tracker {i + 1}")
    tx(slide, W - M - 1, 7.08, 1, 0.24, str(num), size=12, color=MUTE, font=MONO, align="r", name="Slide number")
    if source:
        tx(slide, M + 3.1, 7.07, W - 2 * M - 4.2, 0.26, source, size=11, color=MUTE, name="Source")


def style_axis_text(axis, size=12, color=MUTE, font=BODY):
    f = axis.tick_labels.font
    f.size, f.name = Pt(size), font
    f.color.rgb = rgb(color)


def axis_line(axis, color=LINE):
    axis.format.line.color.rgb = rgb(color)


def set_descr(shape, text):
    shape._element.xpath(".//p:cNvPr")[0].set("descr", text)


def add_fade(slide):
    x = etree.fromstring('<p:transition xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" spd="med"><p:fade/></p:transition>')
    sld = slide._element
    ovr = sld.find(qn("p:clrMapOvr"))
    if ovr is not None:
        ovr.addnext(x)
    else:
        sld.find(qn("p:cSld")).addnext(x)
