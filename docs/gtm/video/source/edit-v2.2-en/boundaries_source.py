from paths import *
import subprocess,sys,math
sys.path.insert(0,str(ROOT/'deps'))
from PIL import Image,ImageDraw
items=[('low','s0-phone-lowstock-v3',18.8,19.9,(0,220,390,150)),('rfq','s1-rfq',41.4,42.4,(420,880,850,180)),('auth','s2-quote-photo',25,25.6,(240,760,720,300)),('confirm','s2-quote-photo',27.2,27.9,(240,760,720,300)),('submit','s3-guardrail-draft',26.6,27.3,(425,850,825,200)),('approve','s4-phone-approve',13.5,14.3,(0,660,390,130)),('po','s5-po-savings',18.4,19.2,(350,880,1220,190)),('save','s5-po-savings',45.5,46.3,(770,650,500,180))]
f=ROOT/'qa-v2.2/source-boundaries';f.mkdir(parents=True,exist_ok=True)
for name,src,a,b,c in items:
 x,y,w,h=c
 subprocess.run([str(FF),'-v','error','-ss',str(a),'-i',str(RAW/(src+'.mp4')),'-t',str(b-a),'-vf',f'fps=15,crop={w}:{h}:{x}:{y},scale=640:-2','-threads','2','-y',str(f/(name+'-%03d.jpg'))],check=True)
 files=sorted(f.glob(name+'-*.jpg'));im=Image.new('RGB',(1280,math.ceil(len(files)/2)*230),'#ddd');d=ImageDraw.Draw(im)
 for n,p in enumerate(files):
  pic=Image.open(p);pic.thumbnail((630,200));x=n%2*640;y=n//2*230;im.paste(pic,(x,y+25));d.text((x+8,y+5),f'{name} {a+n/15:.3f}',fill='black')
 im.save(f/(name+'-sheet.jpg'))
