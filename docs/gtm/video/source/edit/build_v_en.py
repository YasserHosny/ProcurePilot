import subprocess, os
S = '/tmp/claude-1000/-media-yasserhosny-My-Passport-Work-Projects-ProcurePilot/1c3520f5-a777-4834-b5ef-0684f2157c72/scratchpad'
FF = S + '/vid/lib/python3.12/site-packages/imageio_ffmpeg/binaries/ffmpeg-linux-x86_64-v7.0.2'
V = os.path.expanduser('~/Videos/pp-recording'); E = S + '/edit'; SEG = E + '/segv_en'; os.makedirs(SEG, exist_ok=True)
STOCK = '/media/yasserhosny/My Passport/Work/Projects/ProcurePilot/docs/gtm/video/source/stock/pexels-31735802-chef-grill-2160x3840.mp4'
ENC = ['-c:v', 'libx264', '-preset', 'medium', '-crf', '18', '-pix_fmt', 'yuv420p', '-r', '30', '-an']
NAVY = '0x0B2545'
def run(a): subprocess.run([FF, '-y', '-loglevel', 'error'] + a, check=True)
def stock(i, a, dur): run(['-ss', str(a), '-i', STOCK, '-vf', 'scale=1080:1920,fps=30,format=yuv420p,setsar=1,eq=brightness=-0.04', '-t', str(dur)] + ENC + [f'{SEG}/{i:02d}.mp4'])
def card(i, name, dur=None): run(['-framerate', '30', '-i', f'{E}/frames/{name}/%04d.png', '-vf', 'scale=1080:1920,fps=30,format=yuv420p,setsar=1'] + (['-t', str(dur)] if dur else []) + ENC + [f'{SEG}/{i:02d}.mp4'])
def phone(i, src, a, b, dur):
    sp = (b - a) / dur
    run(['-ss', str(a), '-to', str(b), '-i', f'{V}/{src}', '-vf', f'setpts=(PTS-STARTPTS)/{sp},scale=1080:2338,crop=1080:1920:0:110,fps=30,format=yuv420p,setsar=1', '-t', str(dur)] + ENC + [f'{SEG}/{i:02d}.mp4'])
def web(i, src, a, b, dur, crop, sw):
    sp = (b - a) / dur
    run(['-ss', str(a), '-to', str(b), '-i', f'{V}/{src}', '-vf', f'setpts=(PTS-STARTPTS)/{sp},crop={crop},scale={sw}:-2,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color={NAVY},fps=30,format=yuv420p,setsar=1', '-t', str(dur)] + ENC + [f'{SEG}/{i:02d}.mp4'])
plan = [
  ('stock', 0.5, 3.0), ('card', 'env_card0'), ('card', 'env_card1'),
  ('phone', 's0-phone-lowstock.mp4', 1.5, 22.5, 8.0), ('card', 'env_card3'),
  ('web', 's2b-photo-closeup.mp4', 1.0, 22.0, 8.0, '1080:1080:620:0', 1080),
  ('web', 's3c-smart-compare.mp4', 5.0, 28.0, 6.0, '1350:1080:420:0', 1080),
  ('web', 's3-guardrail-draft.mp4', 6.0, 28.0, 5.5, '1080:1080:300:0', 1080),
  ('card', 'env_card5'),
  ('phone', 's4-phone-approve.mp4', 5.0, 17.0, 4.44),
  ('card', 'env_counter', 3.6),
]
for i, p in enumerate(plan):
    k = p[0]
    if k == 'stock': stock(i, *p[1:])
    elif k == 'card': card(i, *p[1:])
    elif k == 'phone': phone(i, *p[1:])
    elif k == 'web': web(i, *p[1:])
    print(i, k, p[1], flush=True)
with open(E + '/listv_en.txt', 'w') as f:
    for i in range(len(plan)): f.write(f"file '{SEG}/{i:02d}.mp4'\n")
run(['-f', 'concat', '-safe', '0', '-i', E + '/listv_en.txt', '-c', 'copy', E + '/body-v-en-silent.mp4'])
print('body-v done')
