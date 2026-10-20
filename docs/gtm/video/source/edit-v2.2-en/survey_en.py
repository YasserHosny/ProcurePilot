from paths import *
from PIL import Image,ImageDraw
import subprocess
RAW=Path.home()/'Videos/pp-recording/en'
for src in sorted(RAW.glob('*.mp4')):
 folder=ROOT/'qa-en/source'/src.stem;folder.mkdir(parents=True,exist_ok=True)
 subprocess.run([str(FF),'-y','-v','error','-i',str(src),'-vf','fps=1',str(folder/'%03d.png')],check=True)
 frames=sorted(folder.glob('*.png'));print(src.name,len(frames),flush=True)
 for part in range(0,len(frames),24):
  subset=frames[part:part+24];tw,th=(480,294) if 'phone' not in src.name else (240,544)
  sheet=Image.new('RGB',(tw*4,th*((len(subset)+3)//4)),'#dddddd');d=ImageDraw.Draw(sheet)
  for j,p in enumerate(subset):
   im=Image.open(p);im.thumbnail((tw,th-24));x=j%4*tw;y=j//4*th;sheet.paste(im,(x,y+24));d.text((x+4,y+4),f'{part+j+0.5:.1f}s',fill='black')
  sheet.save(ROOT/'qa-en/source'/f'{src.stem}-{part//24}.jpg')
