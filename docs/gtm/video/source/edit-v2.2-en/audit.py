"""Every-frame raw audit. Binary glyph templates with anchor rejection, then full-patch validation.
No OCR service. Known raw template captures were visually inspected at native resolution.
"""
import sys,json,subprocess,time,io
from paths import *
sys.path.insert(0,str(ROOT/'deps'))
import numpy as np
from PIL import Image
TEMPLATES=[('bold-last','s2b-photo-closeup-4',(813,133,940,148)),('bold-first','s2b-photo-closeup-4',(821,117,939,132)),('web-single','s3-guardrail-draft-5',(1053,844,1277,857)),('phone-single','s4-phone-approve-9',(39,236,299,250))]
def load_templates():
 out=[]
 rng=np.random.default_rng(7)
 for name,src,box in TEMPLATES:
  source,stamp=src.rsplit('-',1)
  capture=subprocess.run([str(FF),'-v','error','-ss',stamp,'-i',str(RAW/(source+'.mp4')),'-frames:v','1','-f','image2pipe','-vcodec','png','-'],capture_output=True,check=True)
  a=np.asarray(Image.open(io.BytesIO(capture.stdout)).convert('L').crop(box));t=a<185
  # Stay inside strong glyph ink and clearly white background to reduce aliasing sensitivity.
  black=np.argwhere(a<100);white=np.argwhere(a>245)
  anchors=[(*p,True) for p in black[rng.choice(len(black),12,replace=False)]]+[(*p,False) for p in white[rng.choice(len(white),6,replace=False)]]
  out.append((name,t,anchors))
 return out
def match_frame(gray,templates):
 b=gray<185;H,W=b.shape;found=[]
 for name,t,anchors in templates:
  h,w=t.shape
  if w>W:continue
  cand=np.ones((H-h+1,W-w+1),dtype=bool)
  for y,x,v in anchors:
   cand &= b[y:y+H-h+1,x:x+W-w+1] if v else ~b[y:y+H-h+1,x:x+W-w+1]
   if not cand.any():break
  ys,xs=np.where(cand)
  for y,x in zip(ys,xs):
   diff=np.mean(b[y:y+h,x:x+w]!=t)
   if diff<.12:found.append([name,int(x),int(y),w,h,round(float(diff),4)])
 return found
if __name__=='__main__':
 templates=load_templates();results={}
 for src in sorted(RAW.glob('*.mp4')):
  if src.stem.startswith('old'):continue
  phone='phone' in src.stem;W,H=(390,844) if phone else (1920,1080)
  log=open(ROOT/'analysis'/(src.stem+'-pts.log'),'w');proc=subprocess.Popen([str(FF),'-v','info','-i',str(src),'-vf','showinfo','-fps_mode','passthrough','-f','rawvideo','-pix_fmt','gray','-'],stdout=subprocess.PIPE,stderr=log)
  frames=[];n=0;t0=time.time()
  while True:
   raw=proc.stdout.read(W*H)
   if len(raw)!=W*H:break
   found=match_frame(np.frombuffer(raw,np.uint8).reshape(H,W),templates)
   if found:frames.append({'frame':n,'time':round(n/30,5),'matches':found})
   n+=1
  proc.wait();log.close();import re;pts=[float(x) for x in re.findall(r'pts_time:([0-9.]+)',(ROOT/'analysis'/(src.stem+'-pts.log')).read_text())];assert len(pts)==n,(len(pts),n);[f.update(time=pts[f['frame']]) for f in frames];results[src.stem]={'frame_count':n,'detections':frames}
  (ROOT/'analysis'/'raw-email-audit.json').write_text(json.dumps(results,ensure_ascii=False))
  print(src.stem,n,len(frames),round(time.time()-t0,1),flush=True)
