"""Mask the owner's email in raw clips, per encoded frame, from the v2 template audit.

Each detection's box holds from its frame's timestamp until the next encoded frame. A frame
with no detection between two detected frames gets the union of both neighbours' boxes.
"""
import json, os, subprocess, sys
S = os.path.dirname(os.path.abspath(__file__))
FF = S + '/vid/lib/python3.12/site-packages/imageio_ffmpeg/binaries/ffmpeg-linux-x86_64-v7.0.2'
RAW = os.path.expanduser('~/Videos/pp-recording'); OUT = RAW + '/masked'
audit = json.load(open(S + '/edit/v2/analysis/raw-email-audit.json'))
pts = json.load(open(S + '/edit/v2/analysis/source-pts.json'))
COLOR = {'s4-phone-approve': '0xfff7ff'}

def box(m):
    name, x, y, w, h = m[:5]
    if name.startswith('bold'):  # quote review side panel: the email wraps inside a ~150 px column
        return (796, y - 5, 158, h + 10)
    return (x - 10, y - 5, w + 20, h + 10)

HALO = 3  # frames before/after a detected run that still show the email mid-transition
for src, v in audit.items():
    det = {d['frame']: [box(m) for m in d['matches']] for d in v['detections']}
    if not det: continue
    t = pts[src]; n = len(t); first, last = min(det), max(det)
    spans = []
    if src == 's4-phone-approve':
        # The template audit misses the approvals-list card and the detail screen's slide-in,
        # so the phone gets fixed boxes over whole time windows (checked frame by frame).
        end = t[last + 1] if last + 1 < n else t[last] + 1.0
        spans = [(5.5, 8.45, (140, 55, 250, 65)), (8.0, end + 0.5, (25, 222, 300, 48))]
    else:
        for f in range(max(0, first - HALO), min(n - 1, last + HALO) + 1):
            near = [r for k in range(f - HALO, f + HALO + 1) for r in det.get(k, [])]
            if not near:  # inside a scroll gap: carry both neighbours
                prev = max(k for k in det if k < f); nxt = min(k for k in det if k > f)
                near = det[prev] + det[nxt]
            end = t[f + 1] if f + 1 < n else t[f] + 1.0
            spans += [(t[f], end, r) for r in dict.fromkeys(near)]
    col = COLOR.get(src, 'white')
    # merge identical rects over consecutive spans to keep the filter short
    merged = []
    for a, b, r in sorted(spans, key=lambda s: (s[2], s[0])):
        if merged and merged[-1][2] == r and abs(merged[-1][1] - a) < 1e-3:
            merged[-1] = (merged[-1][0], b, r)
        else:
            merged.append((a, b, r))
    vf = ','.join(f"drawbox=x={r[0]}:y={r[1]}:w={r[2]}:h={r[3]}:color={col}:t=fill:enable='between(t,{a-0.0005:.4f},{b-0.0005:.4f})'" for a, b, r in merged)
    script = f'{OUT}/{src}.filter'
    open(script, 'w').write(vf)
    subprocess.run([FF, '-y', '-loglevel', 'error', '-i', f'{RAW}/{src}.mp4', '-filter_script:v', script, '-fps_mode', 'passthrough',
                    '-c:v', 'libx264', '-crf', '12', '-preset', 'medium', '-pix_fmt', 'yuv420p', f'{OUT}/{src}.mp4'], check=True)
    print(src, 'frames', first, last, 'boxes', len(merged), flush=True)
