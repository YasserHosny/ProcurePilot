from paths import *
import subprocess,sys,math
sys.path.insert(0,str(ROOT/'deps'))
from PIL import Image,ImageDraw
ranges={'s0-phone-lowstock-v3':[1.5,3,5,7,9,11,13,15,17,18.5,19,19.25,19.4,19.5],'s1-rfq':[2.5,5,6,10,15,20,25,30,34,37,40,41,41.5,41.6,41.7,41.8,42,43.8,48.3],'s2-quote-photo':[0,1,2,2.5,3,3.5,4,4.5,5,20,22,23,24,24.5,25,25.25,25.5,25.75,26,30,31,32],'s3-guardrail-draft':[9,11,16,20,23,24,25,26,26.25,26.5,26.75,27,29,30,31,32],'s4-phone-approve':[9,12,12.5,13,13.25,13.5,13.75,14,16,17,17.5,18,18.5,19],'s5-po-savings':[7.5,10,15,17,18,18.5,19,19.5,20,21,22,23,25,28,30,32,34,35,36,37,38,39,40,41,42,43,44,45,45.5,46,46.5,47,48,49,50,51,52,53,54,55,56,58]}
f=ROOT/'qa-v2.2/survey';f.mkdir(parents=True,exist_ok=True)
for src,ts in ranges.items():
 pics=[]
 for t in ts:
  p=f/f'{src}-{t:05.2f}.jpg';subprocess.run([str(FF),'-v','error','-ss',str(t),'-i',str(RAW/(src+'.mp4')),'-frames:v','1','-vf','scale=960:-2','-y',str(p)],check=True);pics.append(p)
 for page in range(math.ceil(len(pics)/16)):
  part=pics[page*16:(page+1)*16];w=640;h=400 if 'phone' not in src else 590
  im=Image.new('RGB',(w*4,h*math.ceil(len(part)/4)),'#ddd');d=ImageDraw.Draw(im)
  for n,p in enumerate(part):
   pic=Image.open(p);pic.thumbnail((w-8,h-28));x=n%4*w;y=n//4*h;im.paste(pic,(x+(w-pic.width)//2,y+25));d.text((x+8,y+5),p.stem,fill='black')
  im.save(f/f'{src}-sheet-{page}.jpg')
