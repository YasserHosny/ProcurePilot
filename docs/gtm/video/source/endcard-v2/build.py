"""Build the v2 outros and swap them into the latest cuts.

usage: python build.py <framesDir>     (framesDir from `node render_frames.cjs <framesDir>`)

1. renders/outro-{16x9,9x16}{,-en}.mp4: the approved logo sting frames of the v1 outro (first 135 / 90
   frames) followed by the v2 end card frames, with the v1 outro's audio unchanged (the end card keeps
   the v1 timing, so every sound cue still lands). renders/end-card-* get the v2 card alone.
2. Each cut in CUTS keeps its body untouched (stream copy up to the outro, which starts on a keyframe)
   and its audio track unchanged; only the outro video is replaced.
"""
import subprocess
import sys
import tempfile
from pathlib import Path

FF = '/home/yasserhosny/Work/pp-video-env/lib/python3.12/site-packages/imageio_ffmpeg/binaries/ffmpeg-linux-x86_64-v7.0.2'
VIDEO = Path(__file__).resolve().parents[2]
RENDERS = VIDEO / 'renders'
CUTS = VIDEO / 'cuts'
# aspect: (sting frames, card frames, body frames in a cut)
ASPECTS = {'16x9': (135, 157, 3090), '9x16': (90, 165, 1529)}
ENC = ['-c:v', 'libx264', '-preset', 'slow', '-crf', '12', '-pix_fmt', 'yuv420p', '-profile:v', 'high',
       '-r', '30', '-video_track_timescale', '15360']
# cut file (relative to cuts/) -> outro language suffix
LATEST = {
    'v2.4.2-ledger/procurepilot-demo-ar-16x9.mp4': '', 'v2.4.2-ledger/procurepilot-demo-ar-9x16-60s.mp4': '',
    'v2.4.2-ledger/procurepilot-demo-en-16x9.mp4': '-en', 'v2.4.2-ledger/procurepilot-demo-en-9x16-60s.mp4': '-en',
    'gcc-sa-v1/procurepilot-demo-sa-ar-16x9.mp4': '', 'gcc-sa-v1/procurepilot-demo-sa-ar-9x16-60s.mp4': '',
    'gcc-sa-en-v1/procurepilot-demo-sa-en-16x9.mp4': '-en', 'gcc-sa-en-v1/procurepilot-demo-sa-en-9x16-60s.mp4': '-en',
    'eu-en-v1/procurepilot-demo-ie-en-16x9.mp4': '-en', 'eu-en-v1/procurepilot-demo-ie-en-9x16-60s.mp4': '-en',
}


def ff(*args):
    subprocess.run([FF, '-v', 'error', '-nostdin', '-y', *args], check=True)


def frames(path):
    out = subprocess.run([FF, '-v', 'error', '-i', str(path), '-map', '0:v', '-c', 'copy', '-f', 'framemd5', '-'],
                         capture_output=True, text=True, check=True).stdout
    return sum(1 for line in out.splitlines() if line.startswith('0,'))


def build_outros(frames_dir):
    for aspect, (sting, card, _) in ASPECTS.items():
        for suffix in ('', '-en'):
            board = f"EndCard{'En' if suffix else ''}{aspect}"
            pngs = str(Path(frames_dir) / board / 'f%04d.png')
            old = RENDERS / f'outro-{aspect}{suffix}.mp4'
            with tempfile.TemporaryDirectory() as tmp:
                src = Path(tmp) / 'old.mp4'
                src.write_bytes(old.read_bytes())
                ff('-i', str(src), '-framerate', '30', '-i', pngs, '-filter_complex',
                   f'[0:v]trim=end_frame={sting},setpts=PTS-STARTPTS[s];[1:v]format=yuv420p,setpts=PTS-STARTPTS[c];'
                   '[s][c]concat=n=2:v=1:a=0[v]', '-map', '[v]', '-map', '0:a', *ENC, '-c:a', 'copy', str(old))
            ff('-framerate', '30', '-i', pngs, *ENC, str(RENDERS / f'end-card-{aspect}{suffix}.mp4'))
            assert frames(old) == sting + card, (old, frames(old))
            print('outro', old.name, sting + card, 'frames')


def swap(cut, suffix):
    aspect = '9x16' if '9x16' in cut else '16x9'
    sting, card, body = ASPECTS[aspect]
    path = CUTS / cut
    assert frames(path) == body + sting + card, (cut, frames(path))
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        orig = tmp / 'orig.mp4'
        orig.write_bytes(path.read_bytes())
        ff('-i', str(orig), '-map', '0:v', '-c', 'copy', '-frames:v', str(body), str(tmp / 'body.mp4'))
        ff('-i', str(RENDERS / f'outro-{aspect}{suffix}.mp4'), '-map', '0:v', '-c', 'copy', str(tmp / 'outro.mp4'))
        (tmp / 'list.txt').write_text(f"file '{tmp / 'body.mp4'}'\nfile '{tmp / 'outro.mp4'}'\n")
        ff('-f', 'concat', '-safe', '0', '-i', str(tmp / 'list.txt'), '-i', str(orig),
           '-map', '0:v', '-map', '1:a', '-c', 'copy', '-movflags', '+faststart', str(path))
    assert frames(path) == body + sting + card, (cut, frames(path))
    print('cut', cut, 'outro swapped')


if __name__ == '__main__':
    build_outros(sys.argv[1])
    for cut, suffix in LATEST.items():
        swap(cut, suffix)
