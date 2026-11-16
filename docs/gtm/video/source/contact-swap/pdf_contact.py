"""Company-only footer for the two PDFs whose sources are not in the repo (owner, 2026-11-15):
docs/gtm/one-pager/ProcurePilot-one-pager.pdf and marketing/whatsapp/pdf/founding-customer-offer-PRIVATE.pdf.

On each page, the footer line that held the founder's name, his WhatsApp number and his personal email is redacted
(filled with the footer's own colour) and rewritten as "Iron Systems · WhatsApp +20 10 5087 8238 ·
hello@iron-sys.com" in the same size and colour, Arabic on Arabic pages. Nothing else on the page changes.

usage: python pdf_contact.py <in.pdf> <out.pdf> <ReadexPro.ttf>
"""
import sys
from pathlib import Path

import pymupdf

PHONE = '+20 10 5087 8238'
KEYS = ('4140', 'Yasser', 'yasser', 'ياسر', 'حسني', 'المؤسس', 'Founder', 'Hosny', 'WhatsApp:', 'واتساب')


def footer_spans(page):
    """The footer contact line: spans with a contact key, plus every span on the same baseline (e.g. "Dr.")."""
    spans = [s for b in page.get_text('dict')['blocks'] for l in b.get('lines', []) for s in l['spans']
             if s['bbox'][1] > page.rect.height * 0.85 and s['text'].strip()]
    hits = [s for s in spans if any(k in s['text'] for k in KEYS)]
    if not hits:
        return []
    y = hits[0]['bbox'][3]
    return [s for s in spans if abs(s['bbox'][3] - y) < 2.5 and 'Iron Systems' not in s['text']]


def main(src, dst, font):
    doc = pymupdf.open(src)
    for page in doc:
        spans = footer_spans(page)
        if not spans:
            continue
        r = pymupdf.Rect(spans[0]['bbox'])
        for s in spans[1:]:
            r |= pymupdf.Rect(s['bbox'])
        size, color = spans[0]['size'], spans[0]['color']
        arabic = any('؀' <= ch <= 'ۿ' for s in spans for ch in s['text'])
        pix = page.get_pixmap(clip=pymupdf.Rect(r.x0 - 30, r.y0 - 4, r.x0 - 26, r.y0), dpi=72)
        bg = tuple(c / 255 for c in pix.pixel(1, 1))
        box = pymupdf.Rect(r.x0 - 2, r.y0 - 2, r.x1 + 2, r.y1 + 2)
        page.add_redact_annot(box, fill=bg)
        page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE, graphics=pymupdf.PDF_REDACT_LINE_ART_NONE)
        hexcol = '#%06x' % color
        if arabic:
            # The PDF text engine reorders the number's digit groups inside an RTL line, so the Arabic line is drawn
            # with HarfBuzz/FriBidi (Pillow + raqm, number isolated with LRI/PDI) at 8x and placed as an image,
            # right-aligned where the old line ended.
            from PIL import Image, ImageDraw, ImageFont
            k = 8
            f = ImageFont.truetype(font, round(size * k)); f.set_variation_by_axes([400])
            text = f'Iron Systems  ·  واتساب: \u2066{PHONE}\u2069  ·  hello@iron-sys.com'
            bb = ImageDraw.Draw(Image.new('L', (1, 1))).textbbox((0, 0), text, font=f, direction='rtl')
            img = Image.new('RGBA', (bb[2] + 4, round(size * k * 1.35)), (0, 0, 0, 0))
            rgb = tuple((color >> sh) & 255 for sh in (16, 8, 0))
            ImageDraw.Draw(img).text((2, round(size * k * 0.12)), text, font=f, fill=rgb + (255,), direction='rtl')
            png = Path(dst).with_suffix(f'.p{page.number}.png'); img.save(png)
            w, h = img.width / k, img.height / k
            page.insert_image(pymupdf.Rect(r.x1 - w, r.y0 - 1, r.x1, r.y0 - 1 + h), filename=str(png))
            png.unlink()
        else:
            html = (f'<p dir="ltr">Iron Systems &nbsp;·&nbsp; WhatsApp: {PHONE} &nbsp;·&nbsp; '
                    'hello@iron-sys.com</p>')
            css = (f'@font-face{{font-family:rp;src:url({font})}} '
                   f'p{{margin:0;font-family:rp;font-size:{size}px;color:{hexcol};line-height:1.2}}')
            rc = page.insert_htmlbox(pymupdf.Rect(r.x0 - 2, r.y0 - 1, page.rect.width - 30, r.y1 + 6), html, css=css,
                                     archive=pymupdf.Archive('/'))
            assert rc[0] >= 0, ('text did not fit', page.number, rc)
        print('page', page.number, 'rewritten', 'ar' if arabic else 'en', round(size, 1), hexcol)
    doc.save(dst, garbage=3, deflate=True)


if __name__ == '__main__':
    main(*sys.argv[1:4])
