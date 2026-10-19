from paths import *
import sys,json,subprocess,re
sys.path.insert(0,str(ROOT/'deps'))
import numpy as np
from audit import load_templates,match_frame
src=RAW/'old-s6-savings-pending.mp4';log=open(ROOT/'analysis/old-s6-pts.log','w')
p=subprocess.Popen([str(FF),'-v','info','-i',str(src),'-vf','showinfo','-fps_mode','passthrough','-f','rawvideo','-pix_fmt','gray','-'],stdout=subprocess.PIPE,stderr=log)
templates=load_templates();hits=[];n=0
while True:
 raw=p.stdout.read(1920*1080)
 if len(raw)!=1920*1080:break
 matches=match_frame(np.frombuffer(raw,np.uint8).reshape(1080,1920),templates)
 if matches:hits.append({'frame':n,'matches':matches})
 n+=1
p.wait();log.close();pts=[float(x) for x in re.findall(r'pts_time:([0-9.]+)',(ROOT/'analysis/old-s6-pts.log').read_text())];assert len(pts)==n
for h in hits:h['time']=pts[h['frame']]
(ROOT/'analysis/old-s6-audit.json').write_text(json.dumps({'frame_count':n,'detections':hits},indent=2));print(n,len(hits))
