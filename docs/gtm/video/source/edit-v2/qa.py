"""Final-cut QA: audio measurement, 3 s contact sheets, 0.25 s masking evidence.
Full-size evidence PNGs plus enlarged identity-region sheets for human inspection.
"""
import sys,subprocess,json,re,math,concurrent.futures
from paths import *
sys.path.insert(0,str(ROOT/'deps'))
from PIL import Image,ImageDraw
from edl import FULL,VERT
from probe_duration import duration

def run(args):return subprocess.run([str(FF),'-y','-hide_banner',*map(str,args)],capture_output=True,text=True,check=True)
def sheet(images,out,cols=5,thumb=(384,240),rois=None,perpage=40):
 pages=[]
 for page in range(math.ceil(len(images)/perpage)):
  part=images[page*perpage:(page+1)*perpage];w,h=thumb
  im=Image.new('RGB',(cols*w,math.ceil(len(part)/cols)*h),'#d9e0e6');d=ImageDraw.Draw(im)
  for k,p in enumerate(part):
   pic=Image.open(p).convert('RGB')
   if rois:pic=pic.crop(rois[p.name])
   pic.thumbnail((w-8,h-28));x=k%cols*w;y=k//cols*h
   im.paste(pic,(x+(w-pic.width)//2,y+26));d.text((x+5,y+5),p.stem,fill='black')
  dest=out if len(images)<=perpage else out.with_name(out.stem+f'-{page+1:02}'+out.suffix)
  im.save(dest);pages.append(str(dest.relative_to(ROOT)))
 return pages

def qa(lang,vertical):
 size='9x16-60s' if vertical else '16x9';tag=f'{lang}-{size}';out=ROOT/f'procurepilot-demo-{tag}.mp4'
 plan=VERT if vertical else FULL;dur=duration(out);folder=ROOT/'sheets'/tag;folder.mkdir(exist_ok=True,parents=True)
 # Exact 0,3,6... seconds of the 30 fps finished export.
 run(['-v','error','-i',out,'-vf',r'select=not(mod(n\,90)),scale=480:-2','-fps_mode','vfr',folder/'%03d.jpg'])
 frames=sorted(folder.glob('[0-9]*.jpg'))
 for i,p in enumerate(frames):p.rename(folder/f't{i*3:06.2f}.jpg')
 contact=sheet(sorted(folder.glob('t*.jpg')),ROOT/'sheets'/f'{tag}.jpg',cols=5 if not vertical else 6,thumb=(384,242) if not vertical else (216,410),perpage=100)
 r=run(['-i',out,'-vn','-af','loudnorm=I=-14:TP=-1:LRA=11:print_format=json','-f','null','-']);(ROOT/'analysis'/f'loudness-{tag}.log').write_text(r.stderr)
 match=re.search(r'\{\s*"input_i".*?\}',r.stderr,re.S);loud=json.loads(match.group())
 # One complete decode checks both streams and prints ebur128 measured true peak.
 r=run(['-i',out,'-af','ebur128=peak=true','-f','null','-']);(ROOT/'analysis'/f'decode-ebur128-{tag}.log').write_text(r.stderr)
 proofdir=ROOT/'proof'/tag;proofdir.mkdir(exist_ok=True,parents=True);proof=[];rois={};offset=0
 for i,p in enumerate(plan):
  if p['mask']:
   # Extend 0.5 seconds on both sides, retaining adjacent-shot context.
   begin=max(0,offset-.5);end=offset+p['d']+.5
   for k in range(round((end-begin)*4)+1):
    t=round(begin+k*.25,4);fn=f's{i:02}-t{t:07.3f}.png';dest=proofdir/fn
    run(['-v','error','-ss',t,'-i',out,'-frames:v','1',dest]);proof.append(dest)
    if 'phone' in p['src']:roi=((110,1020,840,1120) if i==9 else (0,475,1080,1515)) if vertical else (765,250,1100,325)
    elif vertical:roi=(0,475,1080,1515) # mask is outside the retained crop; show entire viewport
    elif i==7:roi=(790,48,965,172)
    else:roi=(0,0,1920,900) # fields crop excludes the identity panel
    # Boundary samples show context, not an unrelated ROI on adjacent shots.
    if t<offset or t>=offset+p['d']:roi=(0,0,1080,1920) if vertical else (0,0,1920,1080)
    rois[fn]=roi
   (proofdir/f's{i:02}-window.json').write_text(json.dumps({'slot':i,'output_window':[offset,offset+p['d']],'source':p,'proof_window':[begin,end]},indent=2))
  offset+=p['d']
 pages=sheet(proof,ROOT/'proof'/f'{tag}-inspection.jpg',cols=5,thumb=(400,260),rois=rois)
 result={'file':out.name,'duration':dur,'loudnorm':loud,'contact_sheets':contact,'proof_sheets':pages,'proof_frames':[str(x.relative_to(ROOT)) for x in proof]}
 (ROOT/'analysis'/f'qa-{tag}.json').write_text(json.dumps(result,indent=2));print(tag,dur,loud['input_i'],loud['input_tp'],len(proof),flush=True);return result
if __name__=='__main__':
 jobs=[('ar',False),('en',False),('ar',True),('en',True)]
 if len(sys.argv)>1:jobs=[(sys.argv[1],len(sys.argv)>2 and sys.argv[2]=='v')]
 with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(lambda x:qa(*x),jobs))
