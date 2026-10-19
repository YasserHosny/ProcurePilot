"""Render all four cuts from raw media, then concatenate the preserved outros and music.
Run with the supplied vid/bin/python. All paths are in paths.py. No git commands.
"""
import sys,json,subprocess,concurrent.futures
from paths import *
from edl import FULL,VERT
ENC=['-c:v','libx264','-preset','fast','-crf','18','-pix_fmt','yuv420p','-r','30','-an','-threads','4']
def run(args,log=None):
 r=subprocess.run([str(FF),'-y','-hide_banner','-loglevel','error',*map(str,args)],capture_output=True,text=True)
 if r.returncode:raise RuntimeError(r.stderr)
 return r

def render_one(lang,vertical,i,p):
 W,H=(1080,1920) if vertical else (1920,1080);tag=lang+('-v' if vertical else '')
 folder=ROOT/'segments'/tag;folder.mkdir(parents=True,exist_ok=True);out=folder/f'{i:02}.mp4'
 if out.exists() and out.stat().st_size>1000:
  from probe_duration import duration
  if abs((duration(out) or 0)-p['d'])<.04:return out
 src=p['src'];dur=p['d'];graphic=ROOT/'graphics'/tag
 if src=='counter':
  run(['-framerate','30','-i',graphic/'counter-%02d.png','-vf',f'tpad=stop_mode=clone:stop_duration={dur},trim=duration={dur},setsar=1',*ENC,out]);return out
 if src=='stock':inp=ASSETS/'source/stock/pexels-4253325-kitchen-2048x1080.mp4'
 elif src=='stock-v':inp=ASSETS/'source/stock/pexels-31735802-chef-grill-2160x3840.mp4'
 else:inp=RAW/(src+'.mp4')
 move=dur-p['freeze'];speed=(p['b']-p['a'])/move
 vf=[]
 if p['mask']:
  x,y,w,h,col=p['mask'];vf.append(f'drawbox=x={x}:y={y}:w={w}:h={h}:color={col}:t=fill')
 vf+=['setpts=PTS-STARTPTS',f'setpts=PTS/{speed}']
 if 'phone' in src:
  if vertical:
   if p['crop']:
    x,y,w,h=p['crop'];vf.append(f'crop={w}:{h}:{x}:{y}')
   vf+=['scale=972:1040:force_original_aspect_ratio=decrease','pad=1080:1920:(ow-iw)/2:475+(1040-ih)/2:color=0x0b2545']
  else:vf+=['scale=-2:885','pad=1920:1080:(ow-iw)/2:25:color=0x0b2545']
 elif p['crop']:
  x,y,w,h=p['crop'];vf.append(f'crop={w}:{h}:{x}:{y}')
  if vertical:
   vf+=['scale=972:1040:force_original_aspect_ratio=decrease','pad=1080:1920:(ow-iw)/2:475+(1040-ih)/2:color=0x0b2545']
  else:
   vf+=['scale=1800:890:force_original_aspect_ratio=decrease','pad=1920:1080:(ow-iw)/2:20+(890-ih)/2:color=0x0b2545']
 else:
  if vertical:vf+=['scale=1080:1920:force_original_aspect_ratio=increase','crop=1080:1920']
  else:vf+=['scale=1920:1080:force_original_aspect_ratio=increase','crop=1920:1080']
  if src.startswith('stock'):vf+=['eq=brightness=-0.08:saturation=0.9']
 vf+=['fps=30',f'tpad=stop_mode=clone:stop_duration={dur}',f'trim=duration={dur}','setsar=1']
 fc=f"[0:v]{','.join(vf)}[base];[base][1:v]overlay=0:0:format=auto,format=yuv420p[v]"
 run(['-ss',p['a'],'-t',p['b']-p['a'],'-i',inp,'-loop','1','-i',graphic/(p['cap']+'.png'),'-filter_complex_threads','1','-filter_complex',fc,'-map','[v]','-t',dur,*ENC,out])
 return out

def build(lang,vertical):
 tag=lang+('-v' if vertical else '');plan=VERT if vertical else FULL;dur=sum(p['d'] for p in plan)
 outs=[]
 for i,p in enumerate(plan):
  outs.append(render_one(lang,vertical,i,p));print(tag,i,p['src'],flush=True)
 listing=ROOT/f'concat-{tag}.txt';listing.write_text(''.join(f"file '{o}'\n" for o in outs))
 body=ROOT/f'body-{tag}.mp4';run(['-f','concat','-safe','0','-i',listing,'-c','copy',body])
 W,H=(1080,1920) if vertical else (1920,1080);size='9x16' if vertical else '16x9'
 outro=REF/'renders'/f'outro-{size}{"-en" if lang=="en" else ""}.mp4'
 output=ROOT/f'procurepilot-demo-{lang}-{size}{"-60s" if vertical else ""}.mp4'
 music=ASSETS/'music/dayfox-antalya-beaches-119047.mp3'
 # Copy the already-encoded body and original outro video packets. Same geometry,
 # pixel format, 30 fps and 15360 timebase; concat's automatic H.264 bitstream
 # filter carries parameter sets across the join. QA fully decodes the result.
 outrovideo=ROOT/f'outro-video-{tag}.mp4'
 run(['-i',outro,'-map','0:v:0','-an','-c:v','copy',outrovideo])
 vl=ROOT/f'video-concat-{tag}.txt';vl.write_text(f"file '{body}'\nfile '{outrovideo}'\n")
 fc=(f'[2:a]atrim=0:{dur},asetpts=PTS-STARTPTS,volume=-6.6dB,afade=t=in:d=0.5,aresample=48000,aformat=channel_layouts=stereo[m];'
 f'[1:a]aresample=48000,aformat=channel_layouts=stereo[oa];[m][oa]concat=n=2:v=0:a=1,volume={0 if vertical else 1.1}dB,alimiter=limit=0.7079:attack=0.5:release=50:level=false,aresample=48000[a]')
 run(['-f','concat','-safe','0','-i',vl,'-i',outro,'-ss',120 if vertical else 0,'-t',dur,'-i',music,'-filter_complex_threads','1','-filter_complex',fc,'-map','0:v:0','-map','[a]','-c:v','copy','-c:a','aac','-b:a','256k','-movflags','+faststart',output])
 (ROOT/f'edl-{tag}.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2));print('FINISHED',output,flush=True)
 return output
if __name__=='__main__':
 jobs=[('ar',False),('en',False),('ar',True),('en',True)]
 if len(sys.argv)>1:jobs=[(sys.argv[1],len(sys.argv)>2 and sys.argv[2]=='v')]
 with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(lambda x:build(*x),jobs))
