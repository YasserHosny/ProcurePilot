# Supplementary scan of the compact approval-list identity, which is omitted from all EDLs.
import sys,json,subprocess,re,io
from paths import *
sys.path.insert(0,str(ROOT/'deps'))
from PIL import Image
import numpy as np
from audit import match_frame
capture=subprocess.run([str(FF),'-v','error','-ss','7','-i',str(RAW/'s4-phone-approve.mp4'),'-frames:v','1','-f','image2pipe','-vcodec','png','-'],capture_output=True,check=True)
im=Image.open(io.BytesIO(capture.stdout)).convert('L');box=(233,92,373,106);a=np.asarray(im.crop(box));t=a<185
rng=np.random.default_rng(17);black=np.argwhere(a<100);white=np.argwhere(a>245)
anchors=[(*p,True) for p in black[rng.choice(len(black),12,False)]]+[(*p,False) for p in white[rng.choice(len(white),6,False)]]
log=open(ROOT/'analysis/phone-list-pts.log','w');proc=subprocess.Popen([str(FF),'-v','info','-i',str(RAW/'s4-phone-approve.mp4'),'-vf','showinfo','-fps_mode','passthrough','-f','rawvideo','-pix_fmt','gray','-'],stdout=subprocess.PIPE,stderr=log)
hits=[];n=0
while True:
 data=proc.stdout.read(390*844)
 if len(data)!=390*844:break
 m=match_frame(np.frombuffer(data,np.uint8).reshape(844,390),[('phone-list',t,anchors)])
 if m:hits.append({'frame':n,'matches':m})
 n+=1
proc.wait();log.close();pts=[float(x) for x in re.findall(r'pts_time:([0-9.]+)',(ROOT/'analysis/phone-list-pts.log').read_text())];assert len(pts)==n
for h in hits:h['time']=pts[h['frame']]
(ROOT/'analysis/phone-list-audit.json').write_text(json.dumps(hits,indent=2));print('compact list',len(hits),[h['time'] for h in hits])
