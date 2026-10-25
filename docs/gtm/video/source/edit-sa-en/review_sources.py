"""Source review sheets, from masked copies only; these are not final-cut contact sheets."""
from privacy import ROOT,FF
from PIL import Image,ImageDraw
import subprocess
for p in sorted((ROOT/'masked').glob('*/*.mp4')):
    out=ROOT/'proof/source-frames'/p.parent.name/p.stem;out.mkdir(parents=True,exist_ok=True)
    subprocess.run([FF,'-v','error','-y','-threads','2','-i',str(p),'-vf',"select='not(mod(n,60))',scale=480:-1",'-fps_mode','vfr','-threads','1','-q:v','3',str(out/'%03d.jpg')],check=True)
    frames=sorted(out.glob('*.jpg'));w,h=Image.open(frames[0]).size
    sh=Image.new('RGB',(w*4,(h+24)*((len(frames)+3)//4)),'#C9D6E3');d=ImageDraw.Draw(sh)
    for i,f in enumerate(frames):
        x=i%4*w;y=i//4*(h+24);sh.paste(Image.open(f),(x,y+24));d.text((x+5,y+5),f'{i*2:02d}s',fill='black')
    dst=ROOT/'proof'/f'source-{p.parent.name}-{p.stem}.jpg';sh.save(dst,quality=92)
    print('SOURCE_SHEET',dst.name,flush=True)
