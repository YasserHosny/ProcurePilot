"""Rebuild the WhatsApp photo-card videos (docs/gtm/whatsapp-card/pilot-card-{ar,en}-photo.mp4) after the card
became company-only (owner, 2026-11-15). The original composited the card over moving kitchen footage that is not
in the repo, so the old contact line cannot be lifted out. The rebuild keeps the original's first 19 frames
(footage only, no text), cross-fades into the corrected card PNG over frames 19-45 as the original did, and then
holds the card with a slow push-in to the end (8 s, 30 fps, 1080x1350, no audio, like the original).

usage: python pilot_card_video.py <card dir>
"""
import subprocess
import sys
from pathlib import Path


def build(card_dir, lang):
    d = Path(card_dir)
    src, png = d / f'pilot-card-{lang}-photo.mp4', d / f'pilot-card-{lang}-photo.png'
    tmp = src.with_suffix('.tmp.mp4')
    flt = ('[0:v]trim=end_frame=19,setpts=PTS-STARTPTS,format=yuv420p[a];'
           '[0:v]trim=start_frame=18:end_frame=19,setpts=PTS-STARTPTS,loop=26:1:0,setpts=N/30/TB,format=yuv420p[f];'
           "[1:v]loop=221:1:0,setpts=N/30/TB,scale=1080*(1+0.025*n/220):-1:eval=frame,crop=1080:1350,format=yuv420p[c];"
           '[c]split[c1][c2];[c1]trim=end_frame=26,setpts=PTS-STARTPTS[cin];[c2]trim=start_frame=26,setpts=PTS-STARTPTS[chold];'
           '[f][cin]blend=all_expr=A*(1-N/25)+B*(N/25)[x];'
           '[a][x][chold]concat=n=3:v=1:a=0[v]')
    subprocess.run(['ffmpeg', '-v', 'error', '-nostdin', '-y', '-i', str(src), '-loop', '1', '-i', str(png),
                    '-filter_complex', flt, '-map', '[v]', '-frames:v', '240', '-r', '30', '-c:v', 'libx264',
                    '-preset', 'slow', '-crf', '18', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(tmp)],
                   check=True)
    tmp.replace(src)
    print('rebuilt', src.name)


if __name__ == '__main__':
    for lang in ('ar', 'en'):
        build(sys.argv[1], lang)
