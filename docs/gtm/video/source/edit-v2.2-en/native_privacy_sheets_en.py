from paths import *
from PIL import Image,ImageDraw
import json
samples=json.loads((ROOT/'qa-en/privacy/proof-times.json').read_text())
for name,times in samples.items():
 for a in range(0,len(times),6):
  ts=times[a:a+6];phone='phone' in name;w,h=(390,844) if phone else (200,1016)
  sheet=Image.new('RGB',(w*len(ts)*2,h+30),'#ddd');d=ImageDraw.Draw(sheet)
  for i,t in enumerate(ts):
   for j,kind in enumerate(['raw','masked']):
    im=Image.open(ROOT/'qa-en/privacy'/f'{name}-{t:06.3f}-{kind}.png')
    if not phone:im=im.crop((960,64,1160,1080))
    x=(i*2+j)*w;sheet.paste(im,(x,30));d.text((x+3,5),f'{t:.3f} {kind}',fill='black')
  sheet.save(ROOT/'qa-en/privacy'/f'{name}-native-{a//6}.png')
