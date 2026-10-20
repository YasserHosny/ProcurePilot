"""Frame-complete boundary evidence for ALL retained interactive passages.
Adjacent pairs cover preparatory form clicks as well as primary actions, without
claiming a click detector can recognise every click or every cursor shape.
"""
from paths import *
import build_en,subprocess,json,math
from PIL import Image,ImageDraw
QA=ROOT/'qa-en'
for vertical in (False,True):
 size='9x16-60s' if vertical else '16x9';name=f'procurepilot-demo-en-{size}-anim';plan=build_en.edl.plan(vertical,'anim');s=0;windows=[]
 slots={1,2,4,9,11,14} if vertical else {1,3,4,5,6,10,11,12,15,17,19,20,21,23,24}
 for i,p in enumerate(plan):
  if p['src'].startswith('s'):windows.append((i,round(s*30),round((s+p['d']-p['freeze'])*30)-1))
  s+=p['d']
 folder=QA/f'all-click-coverage-{size}';folder.mkdir(exist_ok=True);frames=folder/'frames';frames.mkdir(exist_ok=True)
 # n in filenames is the sequential selected index; manifest maps it to output n.
 expr='+'.join(f'between(n\\,{a}\\,{b})' for _,a,b in windows)
 subprocess.run([str(FF),'-y','-v','error','-i',ROOT/(name+'.mp4'),'-vf',f'select={expr}','-fps_mode','vfr','-q:v','3','-threads','1',frames/'%05d.jpg'],check=True)
 paths=iter(sorted(frames.glob('*.jpg')));mapping=[]
 for slot,a,b in windows:
  for n in range(a,b+1):mapping.append({'slot':slot,'output_frame':n,'time':n/30,'file':str(next(paths).relative_to(folder))})
 pairs=[(a,b) for a,b in zip(mapping,mapping[1:]) if a['slot']==b['slot']]
 tw,th=(216,408) if vertical else (480,294)
 for page in range(0,len(pairs),12):
  subset=pairs[page:page+12];im=Image.new('RGB',(tw*4,th*((len(subset)+1)//2)),'#ddd');d=ImageDraw.Draw(im)
  for j,pair in enumerate(subset):
   for k,entry in enumerate(pair):
    col=(j%2)*2+k;row=j//2;x=col*tw;y=row*th;f=Image.open(folder/entry['file']);f.thumbnail((tw,th-24));im.paste(f,(x,y+24));d.text((x+3,y+4),f"#{entry['slot']} f{entry['output_frame']} {entry['time']:.3f}s",fill='black')
  im.save(folder/f'boundary-pairs-{page//12:03}.jpg',quality=88)
 (folder/'manifest.json').write_text(json.dumps({'windows':windows,'adjacent_pairs':len(pairs),'frames':mapping},indent=2))
 # Opening lengths are identical across variants, so body frame numbers match.
 for variant in ('anim','clip'):
  target=QA/f'procurepilot-demo-en-{size}-{variant}'/'all-click-frame-pairs'
  if not target.exists():target.symlink_to(folder,target_is_directory=True)
 print(size,'full-resolution frames',len(mapping),'adjacent boundary pairs',len(pairs),flush=True)
