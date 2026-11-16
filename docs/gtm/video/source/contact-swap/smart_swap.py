"""Replace a video's closing frames without touching anything before them (owner, 2026-11-16: "the change must
only be in its place").

The video stream up to the last keyframe at or before the first replaced frame is stream-copied, so those frames
are byte-for-byte the original packets. Only the short stretch from that keyframe to the end is re-encoded: the
original frames up to the replacement, then the replacement frames. The audio track is copied unchanged.

The re-encoded tail uses x264's medium preset at High profile, level 4.0, like the originals, so its SPS/PPS
match the copied head and the two join cleanly. verify() decodes the result and proves it: same frame count,
no decode errors, every head frame identical to the original (frame MD5s), and the audio packets unchanged.

usage (module): swap(orig, out, start_frame, frames) where `frames` is an image glob or a video whose frames
[start_frame, n) are the replacement (same frame numbering as the original).
"""
import json
import subprocess
import tempfile
from pathlib import Path


def run(*args, **kw):
    return subprocess.run(['ffmpeg', '-v', 'error', '-nostdin', '-y', *args], check=True, **kw)


def info(path):
    out = json.loads(subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries',
                                     'stream=width,height,time_base,profile,level', '-of', 'json', str(path)],
                                    capture_output=True, text=True, check=True).stdout)['streams'][0]
    pk = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'packet=pts_time,flags',
                         '-of', 'csv=p=0', str(path)], capture_output=True, text=True, check=True).stdout.split()
    frames = sorted(round(float(p.split(',')[0]) * 30) for p in pk)
    keys = sorted(round(float(p.split(',')[0]) * 30) for p in pk if 'K' in p.split(',')[1])
    return out, len(frames), keys


def framemd5(path, stream, limit=None):
    args = ['ffmpeg', '-v', 'error', '-i', str(path), '-map', f'0:{stream}']
    if stream == 'v' and limit:
        args += ['-frames:v', str(limit)]
    args += (['-c', 'copy'] if stream == 'a' else []) + ['-f', 'framemd5', '-']
    lines = subprocess.run(args, capture_output=True, text=True, check=True).stdout.splitlines()
    return [l.split(',')[-1].strip() for l in lines if l and not l.startswith('#')]


def swap(orig, out, start, frames):
    orig, out = Path(orig), Path(out)
    meta, n, keys = info(orig)
    k = max(x for x in keys if x <= start)
    tb = meta['time_base'].split('/')[1]
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        run('-i', str(orig), '-map', '0:v', '-c', 'copy', '-frames:v', str(k), str(d / 'head.mp4'))
        is_glob = any(ch in str(frames) for ch in '*?[')
        src = (['-framerate', '30', '-pattern_type', 'glob', '-i', str(frames)] if is_glob
               else ['-i', str(frames)])
        rep = '[1:v]format=yuv420p,setpts=PTS-STARTPTS[b]' if is_glob else \
              f'[1:v]trim=start_frame={start},setpts=PTS-STARTPTS,format=yuv420p[b]'
        run('-i', str(orig), *src, '-filter_complex',
            f'[0:v]trim=start_frame={k}:end_frame={start},setpts=PTS-STARTPTS,format=yuv420p[a];{rep};'
            '[a][b]concat=n=2:v=1:a=0[v]', '-map', '[v]', '-frames:v', str(n - k), '-r', '30',
            '-c:v', 'libx264', '-preset', 'medium', '-crf', '16', '-profile:v', 'high', '-level', '4.0',
            '-pix_fmt', 'yuv420p', '-video_track_timescale', tb, str(d / 'tail.mp4'))
        (d / 'list.txt').write_text(f"file '{d / 'head.mp4'}'\nfile '{d / 'tail.mp4'}'\n")
        run('-f', 'concat', '-safe', '0', '-i', str(d / 'list.txt'), '-i', str(orig), '-map', '0:v', '-map', '1:a?',
            '-c', 'copy', '-movflags', '+faststart', str(out))
    verify(orig, out, k, n)
    return k, n


def verify(orig, out, k, n):
    _, m, _ = info(out)
    assert m == n, (out, m, n)
    err = subprocess.run(['ffmpeg', '-v', 'error', '-i', str(out), '-f', 'null', '-'], capture_output=True,
                         text=True).stderr.strip()
    assert not err, (out, err[:300])
    assert framemd5(orig, 'v', k) == framemd5(out, 'v', k), (out, 'head frames differ')
    assert framemd5(orig, 'a') == framemd5(out, 'a'), (out, 'audio differs')
