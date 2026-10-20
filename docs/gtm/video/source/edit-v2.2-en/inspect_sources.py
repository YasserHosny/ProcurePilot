from paths import *
import subprocess,sys,math
sys.path.insert(0,str(ROOT/'deps'))
from PIL import Image,ImageDraw
ranges={'s0-phone-lowstock-v3':(17,23,.25),'s1-rfq':(39,48,.25),'s2-quote-photo':(24,33,.25),'s3-guardrail-draft':(24,32,.25),'s4-phone-approve':(12,20,.25),'s5-po-savings':(17,54,.5)}
folder=ROOT/'qa-v2.2/source';folder.mkdir(parents=True,exist_ok=True)
for src,(a,b,step) in ranges.items():
 files=[]
 for k in range(round((b-a)/step)+1):
  t=a+k*step;p=folder/f'{src}-{t:05.2f}.jpg'
  subprocess.run([str(FF),'-v','error','-ss',str(t),'-i',str(RAW/(src+'.mp4')),'-frames:v','1','-vf','scale=640:-2',str(p)],check=True)
  files.append(p)
 for page in range(math.ceil(len(files)/20)):
  part=files[page*20:(page+1)*20];w=480;h=310 if 'phone' not in src else 560
  im=Image.new('RGB',(w*4,h*math.ceil(len(part)/4)),'#ddd');d=ImageDraw.Draw(im)
  for n,p in enumerate(part):
   pic=Image.open(p);pic.thumbnail((w-8,h-28));x=n%4*w;y=n//4*h;im.paste(pic,(x+(w-pic.width)//2,y+25));d.text((x+8,y+5),p.stem,fill='black')
  im.save(folder/f'{src}-sheet-{page}.jpg')
