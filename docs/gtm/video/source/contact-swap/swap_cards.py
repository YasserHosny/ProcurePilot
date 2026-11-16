"""Company-only contact on every demo cut (owner, 2026-11-15): the end card shows Iron Systems and its contacts
(company WhatsApp +20 10 5087 8238, www.iron-sys.com, hello@iron-sys.com); no founder name, no personal email.

Each cut keeps its body frames and its audio track; only the end-card frames are replaced, and the file is
written back in place (re-encoded at CRF 16).
- Standard cuts end on the approved outro, whose last 157 (16:9) or 165 (9:16) frames are the end card. Those
  frames become the new end card from ../endcard-v2 (rendered by `node render_frames.cjs <dir>`).
- The two editorial cuts (v2.2-editorial, v2.3-brand) end on their own outro. Their engines re-render it
  pixel-for-pixel with the edited specs (`node render.cjs h|v <dir> <f0> <f1>` in each engine folder, with a stub
  plate index: the outro uses no plates), and the frames from the outro start (ST[10]) onwards are replaced.
- The 2026-10-21 Gulf editorial cut has no source in the repo: see gulf_patch.py.
- The Saudi ad (gcc-sa-ad-v1) is rebuilt by its own ../edit-sa-ad/rebuild.sh.

usage: python swap_cards.py <endcard frames dir> <editorial frames dir> [cut ...]
  the editorial frames dir holds brand-h, brand-v, edit-h, edit-v (frames named by absolute frame number)
"""
import json
import subprocess
import sys
from pathlib import Path

CUTS = Path(__file__).resolve().parents[2] / 'cuts'
CARD = {'16x9': 157, '9x16': 165}
# editorial cuts: folder -> (frames subdir prefix, first replaced frame for h and v = the outro start ST[10])
EDITORIAL = {'v2.2-editorial': ('edit', {'h': 3276, 'v': 1347}), 'v2.3-brand': ('brand', {'h': 3276, 'v': 1347})}
SKIP = {'gcc-sa-ad-v1'}


def probe(path):
    """(video frame count, width)."""
    out = json.loads(subprocess.run(['ffprobe', '-v', 'error', '-count_packets', '-select_streams', 'v:0',
                                     '-show_entries', 'stream=nb_read_packets,width', '-of', 'json', str(path)],
                                    capture_output=True, text=True, check=True).stdout)['streams'][0]
    return int(out['nb_read_packets']), int(out['width'])


def replace(path, start, frames_glob, n):
    """Frames [start, n) of `path` become the image sequence `frames_glob` (same count); audio copied."""
    tmp = path.with_suffix('.tmp.mp4')
    subprocess.run(['ffmpeg', '-v', 'error', '-nostdin', '-y', '-i', str(path), '-framerate', '30',
                    '-pattern_type', 'glob', '-i', frames_glob, '-filter_complex',
                    f'[0:v]trim=end_frame={start},setpts=PTS-STARTPTS[a];'
                    f'[1:v]scale=iw:ih,format=yuv420p,setpts=PTS-STARTPTS[b];[a][b]concat=n=2:v=1:a=0[v]',
                    '-map', '[v]', '-map', '0:a', '-c:v', 'libx264', '-preset', 'medium', '-crf', '16',
                    '-pix_fmt', 'yuv420p', '-r', '30', '-c:a', 'copy', '-movflags', '+faststart', str(tmp)],
                   check=True)
    assert probe(tmp) == probe(path), (path, probe(tmp), probe(path))
    tmp.replace(path)


def main(card_dir, ed_dir, only):
    for path in sorted(CUTS.glob('*/*.mp4')):
        folder = path.parent.name
        if folder in SKIP or (only and str(path.relative_to(CUTS)) not in only):
            continue
        n, w = probe(path)
        fmt = 'h' if w > 1200 else 'v'
        if folder in EDITORIAL:
            prefix, starts = EDITORIAL[folder]
            start = starts[fmt]
            frames = Path(ed_dir) / f'{prefix}-{fmt}'
            assert len(list(frames.glob('*.jpg'))) == n - start, (path, n - start)
            replace(path, start, str(frames / '*.jpg'), n)
        else:
            aspect = '16x9' if fmt == 'h' else '9x16'
            english = '-en-' in path.name or path.name.startswith('procurepilot-demo-ie-en')
            board = f"EndCard{'En' if english else ''}{aspect}"
            replace(path, n - CARD[aspect], str(Path(card_dir) / board / 'f*.png'), n)
        print('done', path.relative_to(CUTS), flush=True)


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2], set(sys.argv[3:]))
