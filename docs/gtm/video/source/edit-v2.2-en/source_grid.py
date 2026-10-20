from paths import *
import subprocess,sys,math
sys.path.insert(0,str(ROOT/'deps'))
from PIL import Image,ImageDraw
f=ROOT/'qa-v2.2/source';f.mkdir(parents=True,exist_ok=True)
for src,a,b in [('s3-guardrail-draft',24,32.5),('s4-phone-approve',12,19),('s5-po-savings',17,58),('s2-quote-photo',24,32.5)]:
 prefix=f/(src+'-q')
 subprocess.run([str(FF),'-v','error','-ss',str(a),'-i',str(RAW/(src+'.mp4')),'-t',str(b-a),'-vf','fps=4,scale=960:-2','-threads','2','-y',str(prefix)+'%03d.jpg'],check=True)
 files=sorted(f.glob(src+'-q*.jpg'));w=640;h=390 if 'phone' not in src else 600
 for page in range(math.ceil(len(files)/16)):
  part=files[page*16:(page+1)*16];im=Image.new('RGB',(w*4,h*math.ceil(len(part)/4)),'#ddd');d=ImageDraw.Draw(im)
  for n,p in enumerate(part):
   pic=Image.open(p);pic.thumbnail((w-8,h-28));x=n%4*w;y=n//4*h;im.paste(pic,(x+(w-pic.width)//2,y+25));d.text((x+8,y+5),f'{src} {a+(page*16+n)*.25:.2f}',fill='black')
  im.save(f/f'{src}-grid-{page}.jpg')
