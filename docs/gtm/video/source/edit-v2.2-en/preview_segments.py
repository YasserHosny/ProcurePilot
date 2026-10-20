from paths import *
import subprocess,sys
sys.path.insert(0,str(ROOT/'deps'))
from PIL import Image,ImageDraw
for tag in ['ar','en','ar-v','en-v']:
 folder=ROOT/'segments'/tag
 images=[]
 for p in sorted(folder.glob('*.mp4')):
  out=ROOT/'analysis'/f'preview-{tag}-{p.stem}.jpg'
  if p.stat().st_size<1000:continue
  r=subprocess.run([str(FF),'-y','-v','error','-ss','1','-i',str(p),'-frames:v','1','-vf','scale=640:-2',str(out)],capture_output=True)
  if not r.returncode:images.append(out)
 if not images:continue
 w,h=(320,205) if '-v' not in tag else (240,450)
 im=Image.new('RGB',(w*4,h*((len(images)+3)//4)),'#eeeeee');d=ImageDraw.Draw(im)
 for i,p in enumerate(images):
  pic=Image.open(p);pic.thumbnail((w,h-22));x=i%4*w;y=i//4*h;im.paste(pic,(x,y+22));d.text((x,y),p.stem,fill='black')
 im.save(ROOT/'analysis'/f'preview-{tag}.jpg')
