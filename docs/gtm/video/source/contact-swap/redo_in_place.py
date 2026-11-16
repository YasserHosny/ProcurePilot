"""Rebuild every contact-updated video from its untouched original with smart_swap (owner, 2026-11-16).

The first pass (swap_cards.py, gulf_patch.py, the ad rebuild) re-encoded each whole file. This pass starts again from
the originals in git (`ORIG_REF`, the commit before the contact change) and replaces only the closing frames, so
everything before the last keyframe ahead of the end card is the original, byte for byte.

usage: python redo_in_place.py <endcard frames dir> <editorial frames dir> <ad frames root> <gulf patched dir>
  endcard frames: EndCard{,En}{16x9,9x16}/f*.png from ../endcard-v2/render_frames.cjs
  editorial frames: {brand,edit}-{h,v}/<frame>.jpg from each editorial engine's render.cjs (outro range)
  ad frames root: ../edit-sa-ad/build (frames-h/, frames-v/ with the new closing scene rendered)
  gulf patched dir: gulf-h-new.mp4 and gulf-v-new.mp4 from gulf_patch.py
"""
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import smart_swap

ORIG_REF = 'origin/main'
REPO = Path(__file__).resolve().parents[5]
CUTS = 'docs/gtm/video/cuts'
GULF = 'marketing/ProcurePilot/demo-video/v2.3-editorial-gulf-pp_2026-10-21'
CARD = {'h': 157, 'v': 165}
EDITORIAL = {'v2.2-editorial': 'edit', 'v2.3-brand': 'brand'}
OUTRO_START = {'h': 3276, 'v': 1347}       # ST[10] of the editorial specs
AD_CTA = 1825                               # first frame of the ad's closing scene (s9)
GULF_CARD = {'h': 3412, 'v': 1437}


def original(rel, dst):
    blob = subprocess.run(['git', 'show', f'{ORIG_REF}:{rel}'], cwd=REPO, capture_output=True, check=True).stdout
    data = subprocess.run(['git', 'lfs', 'smudge', rel], cwd=REPO, input=blob, capture_output=True, check=True).stdout
    Path(dst).write_bytes(data)


def jobs(card_dir, ed_dir, ad_root, gulf_dir, tmp):
    out = []
    files = subprocess.run(['git', 'ls-tree', '-r', '--name-only', ORIG_REF, CUTS + '/'], cwd=REPO,
                           capture_output=True, text=True, check=True).stdout.split()
    for rel in sorted(f for f in files if f.endswith('.mp4')):
        folder, name = rel.split('/')[-2:]
        fmt = 'v' if '9x16' in name else 'h'
        if folder == 'gcc-sa-ad-v1':
            sub = Path(tmp) / f'ad-{fmt}'
            if not sub.exists():
                sub.mkdir()
                for f in sorted((Path(ad_root) / f'frames-{fmt}').glob('*.jpg')):
                    if int(f.stem) >= AD_CTA:
                        (sub / f.name).symlink_to(f.resolve())
            out.append((rel, lambda n, s=sub: (AD_CTA, str(s / '*.jpg'))))
        elif folder in EDITORIAL:
            d = Path(ed_dir) / f'{EDITORIAL[folder]}-{fmt}'
            out.append((rel, lambda n, d=d, f=fmt: (OUTRO_START[f], str(d / '*.jpg'))))
        else:
            english = '-en-' in name or name.startswith('procurepilot-demo-ie-en')
            board = f"EndCard{'En' if english else ''}{'16x9' if fmt == 'h' else '9x16'}"
            out.append((rel, lambda n, b=board, f=fmt: (n - CARD[f], str(Path(card_dir) / b / 'f*.png'))))
    for fmt, aspect in (('h', '16x9'), ('v', '9x16')):
        rel = f'{GULF}/procurepilot-demo-ar-{aspect}-gulf-pp.mp4'
        out.append((rel, lambda n, f=fmt: (GULF_CARD[f], str(Path(gulf_dir) / f'gulf-{f}-new.mp4'))))
    return out


def one(job, tmp):
    rel, plan = job
    src = Path(tmp) / (rel.replace('/', '_'))
    original(rel, src)
    _, n, _ = smart_swap.info(src)
    start, frames = plan(n)
    k, n = smart_swap.swap(src, REPO / rel, start, frames)
    src.unlink()
    return f'{rel}: original kept for frames 0-{k - 1} ({k / 30:.1f} s), re-encoded {k}-{n - 1}'


def main(card_dir, ed_dir, ad_root, gulf_dir):
    with tempfile.TemporaryDirectory() as tmp:
        js = jobs(card_dir, ed_dir, ad_root, gulf_dir, tmp)
        with ThreadPoolExecutor(2) as pool:
            for line in pool.map(lambda j: one(j, tmp), js):
                print(line, flush=True)


if __name__ == '__main__':
    main(*sys.argv[1:5])
