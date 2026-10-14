"""Build outlined ProcurePilot lockup SVGs (Converge mark + Readex Pro 600 wordmark)."""
import io
import os

import uharfbuzz as hb
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont

vf = TTFont("ReadexPro.ttf")
st = instantiateVariableFont(vf, {"wght": 600, "HEXP": 0})
buf = io.BytesIO()
st.save(buf)
data = buf.getvalue()
font = TTFont(io.BytesIO(data))
gs = font.getGlyphSet()
upem = font["head"].unitsPerEm
hbfont = hb.Font(hb.Face(data))

NAVY, TEAL, MIST, TEAL2, WHITE = "#0B2545", "#12A594", "#C9D6E3", "#19B8A4", "#FFFFFF"


def shape(text, rtl=False, track=0.0):
    b = hb.Buffer()
    b.add_str(text)
    b.guess_segment_properties()
    if rtl:
        b.direction = "rtl"
    hb.shape(hbfont, b, {"kern": True, "liga": True})
    out, x = [], 0
    for info, pos in zip(b.glyph_infos, b.glyph_positions):
        out.append((font.getGlyphName(info.codepoint), info.cluster, x + pos.x_offset, pos.y_offset))
        x += pos.x_advance + track * upem
    return out


def text_paths(text, size, color_fn, rtl=False, track=0.0):
    """Paths per colour in y-down coords with the baseline at y=0; bounds (x0, top, x1, bottom)."""
    s = size / upem
    paths, bp = {}, BoundsPen(gs)
    for name, cl, x, y in shape(text, rtl, track):
        t = (s, 0, 0, -s, x * s, -y * s)
        pen = SVGPathPen(gs)
        gs[name].draw(TransformPen(pen, t))
        gs[name].draw(TransformPen(bp, t))
        d = pen.getCommands()
        if d:
            paths.setdefault(color_fn(cl), []).append(d)
    return paths, bp.bounds


def mark(b, w):
    return (
        f'<rect x="6" y="14" width="22" height="8" rx="4" fill="{b}"/>'
        f'<rect x="6" y="28" width="34" height="8" rx="4" fill="{w}"/>'
        f'<path d="M36 20 L58 32 L36 44 Z" fill="{w}" stroke="{w}" stroke-width="3" stroke-linejoin="round"/>'
        f'<rect x="6" y="42" width="16" height="8" rx="4" fill="{b}"/>'
    )


def svg(w, h, body):
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w:.1f} {h:.1f}" width="{w:.0f}" '
        f'height="{h:.0f}" role="img" aria-label="ProcurePilot">{body}</svg>\n'
    )


def group(paths, dx, dy):
    return "".join(
        f'<path fill="{c}" transform="translate({dx:.2f} {dy:.2f})" d="{" ".join(ds)}"/>'
        for c, ds in paths.items()
    )


def side_by_side(text, rtl, color_fn, bars, win, name, M, G, FS, track):
    pad = 20
    paths, (x0, top, x1, bottom) = text_paths(text, FS, color_fn, rtl, track)
    H = max(M, bottom - top) + 2 * pad
    cy = H / 2
    baseline = cy - (top + bottom) / 2  # centre the text box on the mark
    tw = x1 - x0
    if rtl:  # Arabic: text on the left, mark on the right (reading start)
        body = group(paths, pad - x0, baseline)
        body += f'<g transform="translate({pad + tw + G} {cy - M / 2}) scale({M / 64})">{mark(bars, win)}</g>'
    else:
        body = f'<g transform="translate({pad} {cy - M / 2}) scale({M / 64})">{mark(bars, win)}</g>'
        body += group(paths, pad + M + G - x0, baseline)
    open(os.path.join("final", name), "w").write(svg(pad + M + G + tw + pad, H, body))


def stacked():
    M, G, FS, pad = 260, 24, 100, 20
    paths, (x0, top, x1, bottom) = text_paths(
        "ProcurePilot", FS, lambda cl: NAVY if cl < 7 else TEAL, track=-0.01
    )
    W = max(M, x1 - x0) + 2 * pad
    body = f'<g transform="translate({(W - M) / 2} {pad}) scale({M / 64})">{mark(NAVY, TEAL)}</g>'
    baseline = pad + M + G - top
    body += group(paths, (W - (x1 - x0)) / 2 - x0, baseline)
    open("final/procurepilot-stacked.svg", "w").write(svg(W, baseline + bottom + pad, body))


latin = lambda c1, c2: (lambda cl: c1 if cl < 7 else c2)  # "Procure" = clusters 0-6
arabic = lambda c1, c2: (lambda cl: c1 if cl < 7 else c2)  # "بروكيور" = clusters 0-6
AR = "بروكيور بايلوت"

os.makedirs("final", exist_ok=True)
side_by_side("ProcurePilot", False, latin(NAVY, TEAL), NAVY, TEAL, "procurepilot-horizontal.svg", 180, 40, 120, -0.02)
side_by_side("ProcurePilot", False, latin(WHITE, TEAL2), MIST, TEAL2, "procurepilot-horizontal-dark.svg", 180, 40, 120, -0.02)
side_by_side(AR, True, arabic(NAVY, TEAL), NAVY, TEAL, "procurepilot-arabic-horizontal.svg", 170, 36, 110, 0)
side_by_side(AR, True, arabic(WHITE, TEAL2), MIST, TEAL2, "procurepilot-arabic-horizontal-dark.svg", 170, 36, 110, 0)
stacked()
print("built")
