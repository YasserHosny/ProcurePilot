"""PPS-84 Arabic re-shoot (2026-10-27/28): mask the owner's email in the new raw clips before any plate is made.

Same detector as ../edit-v2.4/privacy.py (glyph templates, every frame, native resolution, matcher.c), with
templates sampled from the re-shoot clips themselves: the quote review's «رُفع بواسطة» lines and the phone
approval's «مقدم الطلب» lines (list and detail). Templates stay in RAM; no private strings or crops are written.

usage: python reshoot_privacy.py before|mask|after|control
  raw:    ~/Videos/pp-recording/v25-reshoot/<market>/*.mp4   (market: ar = «مطاعم سند», sa-ar = «مطاعم رواق»)
  masked: ~/Videos/pp-recording/v25-reshoot/masked/<market>/*.mp4
"""
from pathlib import Path
import sys, json, subprocess, io, shutil
import numpy as np
from PIL import Image
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'edit-v2.4'))
from privacy import FF, match, scan  # noqa: E402  (v2.4 detector, unchanged)

ROOT = Path(__file__).resolve().parent
RAW = Path.home() / 'Videos/pp-recording/v25-reshoot'
OUT = RAW / 'masked'
MARKETS = ['ar', 'sa-ar']
# (label, clip, seconds, box) per market; boxes are the email ink only, measured on these clips. The approval block
# («معيّن إلى» on the request page, beat 11's insert) uses a smaller font than the quote review, so it has its own template.
SPECS = {
    'ar': [('quote-l1', 's2-quote-photo', 12, (818, 881, 938, 894)), ('quote-l2', 's2-quote-photo', 12, (808, 898, 937, 912)),
           ('phone-detail', 's4-phone-approve', 10, (44, 236, 280, 252)), ('phone-list', 's4-phone-approve', 5.5, (175, 67, 290, 83)),
           ('approval-block', 's4r-approved', 1.2, (1033, 840, 1270, 854))],
    'sa-ar': [('quote-l1', 's2-quote-photo', 12, (797, 934, 938, 947)), ('quote-l2', 's2-quote-photo', 12, (808, 951, 937, 965)),
              ('phone-detail', 's4-phone-approve', 10, (24, 236, 280, 252)), ('phone-list', 's4-phone-approve', 5.5, (155, 67, 290, 83)),
              ('approval-block', 's4r-approved', 1.2, (1013, 840, 1270, 854))],
}

def sample(market, clip, t):
    b = subprocess.run([FF, '-v', 'error', '-ss', str(t), '-i', str(RAW / market / (clip + '.mp4')), '-frames:v', '1',
                        '-f', 'image2pipe', '-vcodec', 'png', '-'], capture_output=True, check=True).stdout
    return np.asarray(Image.open(io.BytesIO(b)).convert('L'))

def templates():
    # Templates from every market, applied to every clip: a market's email never appears in the other's clips,
    # but scanning with all of them costs little and catches a mix-up.
    out = []; rng = np.random.default_rng(7)
    for market, specs in SPECS.items():
        for label, clip, t, (x, y, x1, y1) in specs:
            a = sample(market, clip, t)[y:y1, x:x1]; mask = a < 185
            ink = np.argwhere(a < 100); white = np.argwhere(a > 230)
            assert len(ink) > 30, (market, label, len(ink))
            black = [(*p, True) for p in ink[rng.choice(len(ink), 20, replace=False)]]
            clear = [(*p, False) for p in white[rng.choice(len(white), 12, replace=False)]]
            anchors = [q for pair in zip(black[:12], clear) for q in pair] + black[12:]
            out.append((f'{market}:{label}', mask, anchors))
    return out

def clips(folder):
    return sorted(p for m in MARKETS for p in (folder / m).glob('*.mp4'))

def mask(src, result):
    dst = OUT / src.parent.name / src.name; dst.parent.mkdir(parents=True, exist_ok=True)
    phone = 'phone' in src.stem; W, H = (390, 844) if phone else (1920, 1080)
    colour = '0xf3f4f9' if phone else 'white'
    boxes = {}
    # Five-frame temporal halo around every detection; a phone-list hit (email line 1) also covers line 2 below it.
    for f, hits in result['detections'].items():
        for k in range(max(0, int(f) - 5), min(result['frames'], int(f) + 6)):
            for label, x, y, w, h in hits:
                if label.endswith('phone-list'): x0, y0, x1, y1 = 0, y - 5, W, y + h + 30
                else: x0, y0, x1, y1 = x - 8, y - 5, x + w + 8, y + h + 5
                boxes.setdefault(k, set()).add((max(0, x0), max(0, y0), min(W, x1), min(H, y1)))
    spans = sorted((f / 30, (f + 1) / 30, (x, y, x1 - x, y1 - y)) for f, rs in boxes.items() for x, y, x1, y1 in rs)
    merged = []
    for a, b, r in sorted(spans, key=lambda s: (s[2], s[0])):
        if merged and merged[-1][2] == r and a <= merged[-1][1] + 1e-5: merged[-1] = (merged[-1][0], max(b, merged[-1][1]), r)
        else: merged.append((a, b, r))
    if merged:
        filt = ','.join(f"drawbox=x={r[0]}:y={r[1]}:w={r[2]}:h={r[3]}:color={colour}:t=fill:enable='gte(t,{a:.6f})*lt(t,{b:.6f})'" for a, b, r in merged)
        fp = ROOT / 'proof' / f'reshoot-{src.parent.name}-{src.stem}.filter'; fp.write_text(filt)
        subprocess.run([FF, '-v', 'error', '-y', '-i', str(src), '-filter_script:v', str(fp), '-c:v', 'libx264', '-preset', 'fast',
                        '-crf', '12', '-threads', '4', '-pix_fmt', 'yuv420p', '-an', str(dst)], check=True)
    else: shutil.copyfile(src, dst)
    return len(merged)

def main():
    mode = sys.argv[1]; (ROOT / 'proof').mkdir(exist_ok=True)
    rep = ROOT / 'proof' / f'reshoot-{mode}.json'
    if mode == 'mask':
        before = json.loads((ROOT / 'proof/reshoot-before.json').read_text())
        for key, value in before.items(): print('MASK', key, mask(RAW / key, value), 'rectangles', flush=True)
        return
    ts = templates(); report = {}
    paths = clips(OUT if mode == 'after' else RAW)
    if mode == 'control': paths = [RAW / m / 's2-quote-photo.mp4' for m in MARKETS] + [RAW / m / 's4-phone-approve.mp4' for m in MARKETS] + [RAW / m / 's4r-approved.mp4' for m in MARKETS]
    for p in paths:
        v = scan(p, ts); key = p.parent.name + '/' + p.name; report[key] = v
        print(mode.upper(), key, 'frames', v['frames'], 'matching_frames', v['matching_frames'], 'matches', v['matches'], flush=True)
    rep.write_text(json.dumps(report))
    if mode == 'after': assert len(report) == len(clips(RAW)) and not any(v['matches'] for v in report.values()), 'email still visible'
    if mode == 'control': assert all(v['matches'] > 0 for v in report.values()), 'detector misses the raw email'

if __name__ == '__main__': main()
