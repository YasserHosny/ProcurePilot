from inspect_en import frame
from paths import *
from PIL import Image,ImageDraw
import build_en,json
for vertical in (False,True):
 size='9x16-60s' if vertical else '16x9';plan=build_en.edl.plan(vertical,'anim')
 actions=[(2,21.333333,'Low stock submit'),(9,35.366667,'Submit request'),(11,12.466667,'Approve'),(14,40.566667,'Save outcomes')] if vertical else [(1,21.333333,'Low stock submit'),(5,42.1,'Send RFQ'),(6,4.133333,'Open quote'),(10,26.1,'Authorisation panel'),(11,28.366667,'Confirm authorisation'),(15,35.366667,'Submit request'),(17,12.466667,'Approve'),(20,20.566667,'Create PO'),(21,25.066667,'Submit PO'),(24,40.566667,'Save outcomes')]
 folder=ROOT/'qa-en'/f'procurepilot-demo-en-{size}-anim'/'source-click-frames';folder.mkdir(exist_ok=True)
 sheet=Image.new('RGB',(1920,300*((len(actions)+1)//2)),'#ddd');d=ImageDraw.Draw(sheet)
 for j,(slot,t,label) in enumerate(actions):
  for k,(offset,kind) in enumerate([(-1/30,'before'),(1/30,'after')]):
   stamp=t+offset;im=frame(ROOT/'masked-en'/(plan[slot]['src']+'.mp4'),stamp);im.save(folder/f'{slot:02}-{kind}.png');im.thumbnail((480,276));x=(j%2*2+k)*480;y=j//2*300;sheet.paste(im,(x,y+24));d.text((x+4,y+4),f'#{slot} {label} {kind} {stamp:.6f}',fill='black')
 sheet.save(folder/'source-action-boundaries.jpg');(folder/'actions.json').write_text(json.dumps(actions,indent=2))
 target=ROOT/'qa-en'/f'procurepilot-demo-en-{size}-clip'/'source-click-frames'
 if not target.exists():target.symlink_to(folder,target_is_directory=True)
 print(size, len(actions),'source action pairs',flush=True)
