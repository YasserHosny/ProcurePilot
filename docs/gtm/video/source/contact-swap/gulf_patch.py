"""Company-only contact block for the 2026-10-21 Gulf editorial cut (marketing/ProcurePilot/demo-video/
v2.3-editorial-gulf-pp_2026-10-21), whose engine source was never committed, so its outro cannot be re-rendered.

On the end-card frames only, this redraws the phone number as the company number in the card's own font, weight,
size, colour and right edge (fitted against the original number on the card's settled frame), and puts
www.iron-sys.com and hello@iron-sys.com where the founder line and the personal email were, at the sizes the
editorial engines use for those lines (as on the other editorial cuts, #580). The number keeps the original fade: each frame's opacity is
measured from the original number's ink in that frame. Everything else (panel, underline, the rest of the
card, the Iron Systems closing, the audio) is untouched.

usage: python gulf_patch.py <in.mp4> <out.mp4> <h|v> <ReadexPro.ttf>
"""
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

OLD, NEW = '+20 102 735 4140', '+20 10 5087 8238'
# fmt: (card first frame, closing first frame, a settled card frame)
RANGES = {'h': (3412, 3569, 3540), 'v': (1437, 1602, 1590)}
W = {'h': (1920, 1080), 'v': (1080, 1920)}
# (text, size, weight) for the two lines under the underline, per format (the editorial specs' sizes)
LINES = {'h': [('www.iron-sys.com', 42, 500), ('hello@iron-sys.com', 36, 400)],
         'v': [('www.iron-sys.com', 38, 500), ('hello@iron-sys.com', 32, 400)]}
# where the underline under the number sits: x0, y0, x1, y1
TEAL = np.array([18, 165, 148], float)
SEARCH = {'h': (800, 600, 1840, 820), 'v': (20, 1100, 1060, 1300)}


def one_frame(path, fmt, n):
    w, h = W[fmt]
    raw = subprocess.run(['ffmpeg', '-v', 'error', '-i', path, '-vf', f'select=eq(n\\,{n})', '-frames:v', '1',
                          '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'], capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(h, w, 3)


def bands(mask_rows, min_h=8, gap=6):
    """Text lines as row ranges: runs of rows with ink, joining gaps up to `gap` rows, at least `min_h` tall."""
    out, start = [], None
    for y, on in enumerate(mask_rows):
        if on and start is None:
            start = y
        elif not on and start is not None:
            out.append((start, y)); start = None
    if start is not None:
        out.append((start, len(mask_rows)))
    merged = []
    for a, b in out:
        if merged and a - merged[-1][1] <= gap:
            merged[-1] = (merged[-1][0], b)
        else:
            merged.append((a, b))
    return [r for r in merged if r[1] - r[0] >= min_h]


def layout(frame, fmt):
    """Find the number band (just above the teal underline) and the founder/email bands below it."""
    g = frame.astype(int)
    teal = (np.abs(g[..., 0] - 18) < 30) & (np.abs(g[..., 1] - 165) < 30) & (np.abs(g[..., 2] - 148) < 30)
    # search only inside the paper panel's contact area (the teal panel itself is excluded)
    sx0, sy0, sx1, sy1 = SEARCH[fmt]
    rows = teal[sy0:sy1, sx0:sx1].sum(1)
    uy = sy0 + int(np.argmax(rows > 200))               # first row of the underline
    ux = sx0 + np.where(teal[uy + 2, sx0:sx1])[0]
    x0, x1 = int(ux.min()), int(ux.max()) + 1           # the underline spans the number's width
    bg = np.median(g[uy - 140:uy - 120, x1 + 10:x1 + 30].reshape(-1, 3), 0)
    dark = (np.abs(g - bg).sum(2) > 60) & ~teal
    right = x1
    left = 40 if fmt == 'v' else 820
    above = bands(dark[:uy, left:right + 4].any(1))
    num = above[-1]                                     # the number line
    below = bands(dark[uy + 20:, left:right + 4].any(1))
    founder, email = [(a + uy + 20, b + uy + 20) for a, b in below[:2]]
    return dict(uy=uy, x0=x0, x1=x1, right=right, bg=bg, num=num, founder=founder, email=email, left=left)


def fit(frame, L, font_path):
    x0, x1 = L['left'], L['right'] + 4
    y0, y1 = L['num'][0] - 6, L['num'][1] + 6
    reg = frame[y0:y1, x0:x1].astype(float).mean(2)
    bgl, ink = np.median(reg), reg.min()
    tgt = np.clip((bgl - reg) / (bgl - ink), 0, 1)
    best = None
    for wt in (600, 650, 700):
        for size in range(70, 130, 1):
            f = ImageFont.truetype(font_path, size); f.set_variation_by_axes([wt])
            bb = ImageDraw.Draw(Image.new('L', (1, 1))).textbbox((0, 0), OLD, font=f)
            for dy in range(-6, 7, 2):
                for dx in range(-10, 3, 2):
                    img = Image.new('L', (x1 - x0, y1 - y0), 0)
                    ImageDraw.Draw(img).text((L['right'] - x0 - bb[2] + dx, 6 - bb[1] + dy), OLD, font=f, fill=255)
                    e = np.abs(np.asarray(img) / 255 - tgt).mean()
                    if best is None or e < best[0]:
                        best = (e, wt, size, dx, dy)
    return best, (x0, y0, x1, y1), tgt


def main(src, dst, fmt, font_path):
    c0, c1, settled = RANGES[fmt]
    ref = one_frame(src, fmt, settled)
    L = layout(ref, fmt)
    (err, wt, size, dx, dy), (x0, y0, x1, y1), tgt_final = fit(ref, L, font_path)
    print(fmt, 'fit error %.3f weight %d size %d' % (err, wt, size))
    assert err < 0.06, err
    reg = ref[y0:y1, x0:x1]
    ink = reg.reshape(-1, 3)[np.argmin(reg.sum(2))].astype(float)
    bg = L['bg'].astype(float)
    f = ImageFont.truetype(font_path, size); f.set_variation_by_axes([wt])
    ob = ImageDraw.Draw(Image.new('L', (1, 1))).textbbox((0, 0), OLD, font=f)
    nb = ImageDraw.Draw(Image.new('L', (1, 1))).textbbox((0, 0), NEW, font=f)
    cov = Image.new('L', (x1 - x0, y1 - y0), 0)
    ImageDraw.Draw(cov).text((L['right'] - x0 - nb[2] + dx, 6 - ob[1] + dy), NEW, font=f, fill=255)
    cov = np.asarray(cov, float)[..., None] / 255
    # the original number slides up into place as it fades in, so clear down to the underline, not just its band
    py1 = L['uy'] - 2
    cov = np.concatenate([cov, np.zeros((py1 - y1, cov.shape[1], 1))], 0)
    full = tgt_final.sum()
    fy0, fy1 = L['founder'][0] - 8, L['email'][1] + 8
    # the company lines, drawn once as coverage masks over the cleared founder/email area
    lx0, lx1 = L['left'], L['right'] + 4
    sub = ref[L['founder'][0]:L['founder'][1], lx0:lx1].astype(float)
    sdiff = np.abs(sub - bg).sum(2)
    line_ink = np.median(sub[sdiff > 0.85 * sdiff.max()], 0)
    lines = np.zeros((fy1 - fy0, lx1 - lx0, 1))
    for (text, lsize, lwt), band in zip(LINES[fmt], (L['founder'], L['email'])):
        lf = ImageFont.truetype(font_path, lsize); lf.set_variation_by_axes([lwt])
        lb = ImageDraw.Draw(Image.new('L', (1, 1))).textbbox((0, 0), text, font=lf)
        img = Image.new('L', (lx1 - lx0, fy1 - fy0), 0)
        cy = (band[0] + band[1]) / 2 - fy0
        ImageDraw.Draw(img).text((L['right'] - lx0 - lb[2], cy - (lb[1] + lb[3]) / 2), text, font=lf, fill=255)
        lines = np.maximum(lines, np.asarray(img, float)[..., None] / 255)
    w, h = W[fmt]
    dec = subprocess.Popen(['ffmpeg', '-v', 'error', '-i', src, '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'],
                           stdout=subprocess.PIPE)
    enc = subprocess.Popen(['ffmpeg', '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{w}x{h}',
                            '-r', '30', '-i', '-', '-i', src, '-map', '0:v', '-map', '1:a', '-c:v', 'libx264',
                            '-preset', 'slow', '-crf', '16', '-pix_fmt', 'yuv420p', '-c:a', 'copy',
                            '-movflags', '+faststart', dst], stdin=subprocess.PIPE)
    size_b = w * h * 3
    i = patched = 0
    while True:
        buf = dec.stdout.read(size_b)
        if len(buf) < size_b:
            break
        if c0 <= i < c1:
            fr = np.frombuffer(buf, np.uint8).reshape(h, w, 3).astype(float)
            corner = fr[y0:y0 + 4, x1 - 4:x1]
            if np.abs(corner - bg).max() <= 6:          # the card panel is on screen (not a wipe frame)
                r = fr[y0:py1, x0:x1].mean(2)
                m = np.median(r)
                a = np.clip(np.clip((m - r) / max(m - ink.mean(), 1), 0, 1).sum() / full, 0, 1)
                fr[y0:py1, x0:x1] = bg * (1 - cov * a) + ink * (cov * a)
                fr[fy0:fy1, lx0:lx1] = bg * (1 - lines * a) + line_ink * (lines * a)
                # while sliding in, the old number's lower part sits over and under the underline: keep only teal there
                zone = fr[py1:L['uy'] + 48, x0:x1]
                is_teal = (np.abs(zone - TEAL).sum(2) < 90) | (np.abs(zone - bg).sum(2) < 4)
                zone[~is_teal] = bg
                buf = np.clip(fr, 0, 255).astype(np.uint8).tobytes()
                patched += 1
        enc.stdin.write(buf)
        i += 1
    enc.stdin.close()
    assert dec.wait() == 0 and enc.wait() == 0
    print(fmt, 'frames', i, 'patched', patched)
    return L


if __name__ == '__main__':
    main(*sys.argv[1:5])
