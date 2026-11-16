"""Company-only contact on the four WhatsApp-kit images that carry it (owner, 2026-11-15). Their sources were never
committed (marketing/whatsapp, PR #579), so each text run is replaced in place: the old run is located inside a
known box, its font size and weight are fitted against the pixels (Readex Pro, the kit's font), the run is painted
out with the surrounding background, and the new run is drawn in the same colour, size and weight, keeping the
edge that sits next to the neighbouring text.

usage: python kit_patch.py <marketing/whatsapp/images dir> <ReadexPro.ttf>
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

OLD_NUM, NEW_NUM = '+20 102 735 4140', '+20 10 5087 8238'
# file -> [(search box x0,y0,x1,y1, old text, new text, edge kept, direction)]
JOBS = {
    'deal/5-founding-pilot-invite-ar.png': [((200, 1035, 516, 1100), OLD_NUM, NEW_NUM, 'right', 'ltr')],
    'deal/5-founding-pilot-invite-en.png': [((490, 1080, 810, 1130), OLD_NUM, NEW_NUM, 'left', 'ltr')],
    'send/card-general-ar.png': [((60, 1185, 352, 1235), OLD_NUM, NEW_NUM, 'right', 'ltr'),
                                 ((680, 1185, 1020, 1235), 'د. ياسر حسني — المؤسس', 'تواصل معنا', 'right', 'rtl')],
    'send/card-general-en.png': [((720, 1185, 1020, 1235), OLD_NUM, NEW_NUM, 'right', 'ltr'),
                                 ((60, 1185, 445, 1235), 'Dr. Yasser Hosny — Founder', 'Get in touch', 'left', 'ltr')],
}


def font(path, size, wt):
    f = ImageFont.truetype(path, size)
    f.set_variation_by_axes([wt])
    return f


def mask_of(text, f, direction, w, h, x, y):
    img = Image.new('L', (w, h), 0)
    ImageDraw.Draw(img).text((x, y), text, font=f, fill=255, direction=direction)
    return np.asarray(img, float) / 255


def patch(im, box, old, new, edge, direction, font_path):
    a = np.asarray(im).astype(float)
    x0, y0, x1, y1 = box
    reg = a[y0:y1, x0:x1]
    # background: for each column, a vertical blend between the rows just above and just below the box, so a
    # soft gradient behind the text is kept rather than flattened into a visible block
    top = np.median(a[y0 - 6:y0 - 2, x0:x1], 0)
    bot = np.median(a[y1 + 2:y1 + 6, x0:x1], 0)
    t = np.linspace(0, 1, y1 - y0)[:, None, None]
    bg = top[None] * (1 - t) + bot[None] * t                         # (h, w, 3)
    diff = np.abs(reg - bg).sum(2)
    ink = diff > 60
    ys, xs = np.where(ink)
    tx0, tx1, ty0, ty1 = xs.min(), xs.max() + 1, ys.min(), ys.max() + 1
    tgt = np.clip(diff / diff.max(), 0, 1)
    colour = np.median(reg[tgt > 0.85], 0)                          # the text colour: fully covered pixels
    best = None
    d = ImageDraw.Draw(Image.new('L', (1, 1)))
    for wt in (400, 500, 600, 700):
        for size in range(16, 60):
            f = font(font_path, size, wt)
            bb = d.textbbox((0, 0), old, font=f, direction=direction)
            if abs((bb[2] - bb[0]) - (tx1 - tx0)) > 6:
                continue
            for dy in range(-3, 4):
                x = (tx1 - bb[2]) if edge == 'right' else (tx0 - bb[0])
                m = mask_of(old, f, direction, x1 - x0, y1 - y0, x, ty0 - bb[1] + dy)
                e = np.abs(m - tgt).mean()
                if best is None or e < best[0]:
                    best = (e, wt, size, dy)
    assert best is not None, (box, old)
    e, wt, size, dy = best
    f = font(font_path, size, wt)
    ob = d.textbbox((0, 0), old, font=f, direction=direction)
    nb = d.textbbox((0, 0), new, font=f, direction=direction)
    x = (tx1 - nb[2]) if edge == 'right' else (tx0 - nb[0])
    m = mask_of(new, f, direction, x1 - x0, y1 - y0, x, ty0 - ob[1] + dy)[..., None]
    pad = 3
    out = reg.copy()
    sy, sx = slice(max(ty0 - pad, 0), ty1 + pad), slice(max(tx0 - pad, 0), tx1 + pad)
    out[sy, sx] = bg[sy, sx]
    out = out * (1 - m) + colour[None, None] * m
    a[y0:y1, x0:x1] = out
    print(f'  {old!r} -> {new!r}: weight {wt} size {size} fit {e:.3f}')
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))


def main(root, font_path):
    for name, jobs in JOBS.items():
        p = Path(root) / name
        im = Image.open(p).convert('RGB')
        print(name)
        for job in jobs:
            im = patch(im, *job, font_path)
        im.save(p)


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
