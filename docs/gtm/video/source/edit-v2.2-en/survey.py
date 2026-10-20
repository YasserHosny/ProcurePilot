from paths import *
from PIL import Image,ImageDraw
import subprocess,io
for src in sorted(RAW.glob('*.mp4')):
 if src.name.startswith('old'):continue
 folder=ROOT/'analysis'/src.stem;folder.mkdir(exist_ok=True)
 subprocess.run([str(FF),'-y','-loglevel','error','-i',str(src),'-vf','fps=1/2,scale=640:-1',str(folder/'%03d.jpg')],check=True)
 frames=list(sorted(folder.glob('*.jpg'))); thumb=(480,300) if 'phone' not in src.name else (240,550)
 sheet=Image.new('RGB',(thumb[0]*4,thumb[1]*((len(frames)+3)//4)), '#cccccc');d=ImageDraw.Draw(sheet)
 for i,p in enumerate(frames):
  im=Image.open(p);im.thumbnail((thumb[0],thumb[1]-24));x=i%4*thumb[0];y=i//4*thumb[1];sheet.paste(im,(x,y+24));d.text((x+4,y+4),f'{src.stem} ~{i*2+1}s',fill='black')
 sheet.save(ROOT/'analysis'/f'{src.stem}.jpg')
