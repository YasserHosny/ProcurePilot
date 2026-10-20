import subprocess, json, numpy as np, os
from PIL import Image
import os
V=os.environ.get('PP_CUT',os.path.join(os.path.dirname(os.path.abspath(__file__)),'../../cuts/v2.1/procurepilot-demo-ar-16x9.mp4'))
SEG=[('low',3.0,14.0),('rfqlist',14.0,16.5),('rfqform',16.5,33.4),('inbox',33.5,34.6),('photo',35.5,40.5),
('fields',40.5,45.0),('lines',45.0,49.5),('auth',49.5,50.1),('compare',53.5,58.5),('prices',58.5,64.0),
('draft',64.0,68.5),('submit',68.5,75.6),('approve',76.5,87.0),('po',87.0,94.0),('sent',97.9,102.9),
('outcome',102.9,108.9),('result',108.9,113.4),('ledger',118.4,125.4),('kitchen',0.0,3.0)]
def frame(t):
    raw=subprocess.run(['ffmpeg','-v','error','-ss',str(t),'-i',V,'-frames:v','1','-f','rawvideo','-pix_fmt','rgb24','-'],capture_output=True).stdout
    return np.frombuffer(raw,np.uint8).reshape(1080,1920,3).astype(int)
meta={}
for n,a,b in SEG:
    x0,y0,x1,y1=1920,1080,0,0
    for t in np.linspace(a+0.05,b-0.05,6):
        f=frame(t); d=np.abs(f-np.array([9,35,68])).sum(2)>40; d[910:]=False
        ys,xs=np.where(d)
        x0=min(x0,xs.min());y0=min(y0,ys.min());x1=max(x1,xs.max()+1);y1=max(y1,ys.max()+1)
    if n=='kitchen': x0,y0,x1,y1=0,0,1920,905
    w=(x1-x0)//2*2;h=(y1-y0)//2*2
    os.makedirs(f'plates/{n}',exist_ok=True)
    subprocess.run(['ffmpeg','-v','error','-y','-ss',str(a),'-t',str(b-a),'-i',V,'-vf',f'crop={w}:{h}:{x0}:{y0}','-q:v','2',f'plates/{n}/%04d.jpg'])
    cnt=len(os.listdir(f'plates/{n}'))
    meta[n]=dict(src=[a,b],box=[int(x0),int(y0),int(w),int(h)],frames=cnt)
    print(n,meta[n],flush=True)
json.dump(meta,open('plates/meta.json','w'),indent=1)
