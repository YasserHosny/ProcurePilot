from paths import *
import subprocess,json
import numpy as np
from PIL import Image
from audit import match_frame
# Exact English glyphs; audit every masked frame in the English information column.
a=np.asarray(Image.open(ROOT/'qa-en/source/s2b-photo-closeup/006.png').convert('L'))[116:145,980:1115];rng=np.random.default_rng(7)
b=np.argwhere(a<100);w=np.argwhere(a>245)
templates=[('english-bold',a<185,[(*p,True) for p in b[rng.choice(len(b),12,replace=False)]]+[(*p,False) for p in w[rng.choice(len(w),6,replace=False)]])]
results={}
for src in sorted((ROOT/'masked-en').glob('*.mp4')):
 W,H=(390,844) if 'phone' in src.stem else (1920,1080);n=0;hits=[];bad=[]
 p=subprocess.Popen([str(FF),'-v','error','-i',src,'-f','rawvideo','-pix_fmt','gray','-'],stdout=subprocess.PIPE)
 while True:
  raw=p.stdout.read(W*H)
  if len(raw)!=W*H:break
  g=np.frombuffer(raw,np.uint8).reshape(H,W)
  if W>390:
   if match_frame(g[64:,960:1160],templates):hits.append(n)
  elif src.stem=='s4-phone-approve':
   t=n/30
   for a,b,box in [(4,7.5,(3,60,387,112)),(6.5,16.5,(3,228,387,257))]:
    if a<=t<b:
     x,y,xx,yy=box
     if (g[y:yy,x:xx].max()-g[y:yy,x:xx].min())>12:bad.append(n)
  n+=1
 assert p.wait()==0
 results[src.stem]={'frames':n,'English_template_hits':hits,'phone_nonuniform_mask_frames':sorted(set(bad))}
 print(src.stem,n,'hits',len(hits),'phone bad',len(set(bad)),flush=True)
 (ROOT/'qa-en/privacy/masked-audit.json').write_text(json.dumps(results,indent=2))
