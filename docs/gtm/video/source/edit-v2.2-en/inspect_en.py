from paths import *
from PIL import Image,ImageDraw
import subprocess,io
SOURCE=Path.home()/'Videos/pp-recording/en'
def frame(src,t):
 r=subprocess.run([str(FF),'-v','error','-ss',str(t),'-i',str(src),'-frames:v','1','-f','image2pipe','-vcodec','png','-threads','1','-'],capture_output=True,check=True)
 return Image.open(io.BytesIO(r.stdout)).convert('RGB')
def sheet(src,times,out,crop=None,tw=480,th=320):
 im=Image.new('RGB',(tw*4,th*((len(times)+3)//4)),'#ddd');d=ImageDraw.Draw(im)
 for i,t in enumerate(times):
  p=frame(src,t)
  if crop:p=p.crop(crop)
  p.thumbnail((tw,th-24));x=i%4*tw;y=i//4*th;im.paste(p,(x,y+24));d.text((x+4,y+3),f'{t:.3f}',fill='black')
 im.save(out)
if __name__=='__main__':
 jobs=[('s0-phone-lowstock',20.8,21.8,(0,100,390,310)),('s1-rfq',42.5,44.1,(650,820,1490,1080)),('s2-quote-photo',25.8,28.5,(930,680,1690,1080)),('s3-guardrail-draft',34.5,35.8,(1040,850,1510,1000)),('s4-phone-approve',11.7,12.8,(0,655,390,780)),('s5-po-savings',20.5,22,(1100,840,1570,1080)),('s5-po-savings',24.6,26,(330,780,1560,1040)),('s5-po-savings',40.5,42,(900,600,1280,800))]
 for j,(src,a,b,crop) in enumerate(jobs):
  times=[round(a+i*.1,3) for i in range(round((b-a)*10)+1)]
  sheet(SOURCE/(src+'.mp4'),times,ROOT/'qa-en'/f'boundary-source-{j}.jpg',crop)
