import subprocess, os, sys, json
S = '/tmp/claude-1000/-media-yasserhosny-My-Passport-Work-Projects-ProcurePilot/1c3520f5-a777-4834-b5ef-0684f2157c72/scratchpad'
FF = S + '/vid/lib/python3.12/site-packages/imageio_ffmpeg/binaries/ffmpeg-linux-x86_64-v7.0.2'
V = os.path.expanduser('~/Videos/pp-recording'); E = S + '/edit'; SEG = E + '/seg'; os.makedirs(SEG, exist_ok=True)
STOCK = '/media/yasserhosny/My Passport/Work/Projects/ProcurePilot/docs/gtm/video/source/stock/pexels-4253325-kitchen-2048x1080.mp4'
OUT_ENC = ['-c:v', 'libx264', '-preset', 'medium', '-crf', '18', '-pix_fmt', 'yuv420p', '-r', '30', '-an']
NORM = 'scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,fps=30,format=yuv420p,setsar=1'
def run(args): subprocess.run([FF, '-y', '-loglevel', 'error'] + args, check=True)
def web(i, src, a, b, dur, extra=''):
    sp = (b - a) / dur
    run(['-ss', str(a), '-to', str(b), '-i', f'{V}/{src}', '-vf', f'setpts=(PTS-STARTPTS)/{sp},{NORM}{extra}', '-t', str(dur)] + OUT_ENC + [f'{SEG}/{i:02d}.mp4'])
def stock(i, a, dur):
    run(['-ss', str(a), '-i', STOCK, '-vf', f'{NORM},eq=brightness=-0.05:saturation=0.9', '-t', str(dur)] + OUT_ENC + [f'{SEG}/{i:02d}.mp4'])
def card(i, name, dur=None):
    args = ['-framerate', '30', '-i', f'{E}/frames/{name}/%04d.png']
    if dur: args = ['-framerate', '30', '-i', f'{E}/frames/{name}/%04d.png']
    run(args + ['-vf', NORM] + (['-t', str(dur)] if dur else []) + OUT_ENC + [f'{SEG}/{i:02d}.mp4'])
def phone(i, src, a, b, dur):
    sp = (b - a) / dur
    fc = (f'[1:v]setpts=(PTS-STARTPTS)/{sp},fps=30,scale=437:945,format=rgba[ph];[2:v]format=gray[m];[ph][m]alphamerge[phm];'
          f'[0:v][phm]overlay=741:67:shortest=1,format=yuv420p,setsar=1[v]')
    run(['-loop', '1', '-framerate', '30', '-i', f'{E}/frames/phoneframe/0000.png', '-ss', str(a), '-to', str(b), '-i', f'{V}/{src}',
         '-loop', '1', '-i', f'{E}/phonemask.png', '-filter_complex', fc, '-map', '[v]', '-t', str(dur)] + OUT_ENC + [f'{SEG}/{i:02d}.mp4'])
plan = [
  ('stock', 0, 6.0), ('card', 'card0'), ('stock', 22, 4.0), ('card', 'card1'),
  ('phone', 's0-phone-lowstock.mp4', 1.5, 22.5, 10.0), ('card', 'card2'),
  ('web', 's1-rfq.mp4', 2.5, 47.0, 15.0), ('card', 'card3'),
  ('web', 's2-quote-photo.mp4', 2.5, 13.0, 6.0), ('web', 's2b-photo-closeup.mp4', 1.0, 22.0, 15.0), ('web', 's2-quote-photo.mp4', 18.0, 32.5, 7.0),
  ('card', 'card4'), ('web', 's3c-smart-compare.mp4', 2.5, 31.5, 14.0),
  ('web', 's3-guardrail-draft.mp4', 2.5, 31.0, 14.0),
  ('card', 'notify'), ('card', 'card5'),
  ('phone', 's4-phone-approve.mp4', 1.5, 18.5, 12.0), ('card', 'card6'),
  ('web', 's5-po-savings.mp4', 2.5, 58.0, 22.0), ('card', 'counter'),
  ('web', 's6-savings-close.mp4', 1.5, 21.3, 14.75),
]
for i, p in enumerate(plan):
    k = p[0]
    if k == 'stock': stock(i, p[1], p[2])
    elif k == 'card': card(i, p[1])
    elif k == 'web': web(i, *p[1:])
    elif k == 'phone': phone(i, *p[1:])
    print(i, p[0], p[1], flush=True)
with open(E + '/list.txt', 'w') as f:
    for i in range(len(plan)): f.write(f"file '{SEG}/{i:02d}.mp4'\n")
run(['-f', 'concat', '-safe', '0', '-i', E + '/list.txt', '-c', 'copy', E + '/body-silent.mp4'])
print('body done')
