"""English per-frame email audit and masking. Does not use Arabic templates.
Set PP_MASK_DIR to relocate copies to ~/Videos/pp-recording/en/masked when writable.
"""
from paths import *
import subprocess,json,os
import numpy as np
from PIL import Image
from audit import match_frame
from probe_duration import duration
SOURCE=Path.home()/'Videos/pp-recording/en'
DEST=Path(os.environ.get('PP_MASK_DIR',ROOT/'masked-en'));DEST.mkdir(parents=True,exist_ok=True)
# Native English two-line glyph template, manually viewed at full resolution.
gray=np.asarray(Image.open(ROOT/'qa-en/source/s2b-photo-closeup/006.png').convert('L'))
a=gray[116:145,980:1115];t=a<185;rng=np.random.default_rng(7)
b=np.argwhere(a<100);w=np.argwhere(a>245)
anchors=[(*p,True) for p in b[rng.choice(len(b),12,replace=False)]]+[(*p,False) for p in w[rng.choice(len(w),6,replace=False)]]
templates=[('english-bold',t,anchors)]
report={}
for src in sorted(SOURCE.glob('*.mp4')):
 name=src.stem;phone='phone' in name;W,H=(390,844) if phone else (1920,1080);det={};n=0
 if not phone:
  proc=subprocess.Popen([str(FF),'-v','error','-i',src,'-f','rawvideo','-pix_fmt','gray','-'],stdout=subprocess.PIPE)
  while True:
   raw=proc.stdout.read(W*H)
   if len(raw)!=W*H:break
   g=np.frombuffer(raw,np.uint8).reshape(H,W);hits=match_frame(g[64:,960:1160],templates)
   if hits:det[n]=[(970,h[2]+64-5,160,42) for h in hits]
   n+=1
  assert proc.wait()==0
 spans=[]
 if name=='s4-phone-approve':
  spans=[(4.0,7.5,(0,57,390,59),'0xfff7ff'),(6.5,16.5,(0,225,390,35),'0xfff7ff')]
 elif det:
  # Five-frame halo. Union boxes in scrolling frames; inside gaps between detections
  # use the full vertical corridor between neighbours, covering partial glyphs.
  keys=sorted(det)
  for f in range(max(0,keys[0]-5),min(n,keys[-1]+6)):
   near=[r for k in range(f-5,f+6) for r in det.get(k,[])]
   if not near:
    prev=max((k for k in keys if k<f),default=keys[0]);nxt=min((k for k in keys if k>f),default=keys[-1]);near=det[prev]+det[nxt]
   y=max(64,min(r[1] for r in near));end=min(1080,max(r[1]+r[3] for r in near))
   spans.append((f/30,(f+1)/30,(970,y,160,end-y),'white'))
  # Guard broad scroll/transition corridors, independent of template matches.
  extra={'s2-quote-photo':[(7,8.1),(23.5,25.8),(30.6,32.8)],'s2b-photo-closeup':[(1.7,4.3),(15.5,17.2)]}
  spans += [(a,b,(970,64,160,1016),'white') for a,b in extra.get(name,[])]
 merged=[]
 for a,b,r,c in sorted(spans,key=lambda q:(q[2],q[3],q[0])):
  if merged and merged[-1][2:]==(r,c) and abs(merged[-1][1]-a)<.001:merged[-1]=(merged[-1][0],b,r,c)
  else:merged.append((a,b,r,c))
 out=DEST/src.name
 if merged:
  filt=','.join(f"drawbox=x={r[0]}:y={r[1]}:w={r[2]}:h={r[3]}:color={c}:t=fill:enable='gte(t,{a:.6f})*lt(t,{b:.6f})'" for a,b,r,c in merged)
  script=ROOT/'qa-en/privacy'/f'{name}.filter';script.write_text(filt)
  subprocess.run([str(FF),'-y','-v','error','-i',src,'-filter_script:v',script,'-c:v','libx264','-crf','12','-preset','fast','-threads','4','-pix_fmt','yuv420p','-r','30',out],check=True)
 else:
  if not out.exists():out.symlink_to(src)
 report[name]={'frames':n,'duration':duration(src),'detections':{str(k):v for k,v in det.items()},'masked_ranges':merged,'symlink':not bool(merged)}
 (ROOT/'qa-en/privacy/mask-manifest.json').write_text(json.dumps(report,indent=2))
 print(name,'detected',len(det),'mask spans',len(merged),flush=True)
