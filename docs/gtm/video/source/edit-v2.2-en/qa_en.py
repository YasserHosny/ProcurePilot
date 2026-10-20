"""Final delivery QA: full decode, R128/true peak, 2-second contact sheets,
full-resolution action boundaries and privacy samples. No raw media is rendered.
"""
from inspect_en import frame
from paths import *
from probe_duration import duration
from PIL import Image,ImageDraw
import build_en,subprocess,json,re,concurrent.futures
QA=ROOT/'qa-en'
# Source-time primary actions; t chosen on last active frame, before busy state.
ACTIONS_FULL=[(1,21.27,'Low stock submit'),(5,42.03,'Send RFQ'),(6,4.03,'Open photo quote'),(10,26.07,'Open authorisation'),(11,28.30,'Confirm authorisation'),(15,35.33,'Submit request'),(17,12.37,'Approve'),(20,20.53,'Create purchase order'),(21,25.03,'Submit purchase order'),(24,40.53,'Save three outcomes')]
ACTIONS_VERT=[(2,21.27,'Low stock submit'),(9,35.33,'Submit request'),(11,12.37,'Approve'),(14,40.53,'Save three outcomes')]
def make_sheet(frames,labels,out,vertical=False):
 tw,th=(240,452) if vertical else (480,294);cols=4
 im=Image.new('RGB',(tw*cols,th*((len(frames)+cols-1)//cols)),'#ddd');d=ImageDraw.Draw(im)
 for i,f in enumerate(frames):
  f=f.copy();f.thumbnail((tw,th-24));x=i%cols*tw;y=i//cols*th;im.paste(f,(x,y+24));d.text((x+4,y+4),labels[i],fill='black')
 im.save(out)
def check(vertical,variant):
 name=f'procurepilot-demo-en-'+('9x16-60s' if vertical else '16x9')+'-'+variant
 src=ROOT/(name+'.mp4');folder=QA/name;folder.mkdir(exist_ok=True)
 if (folder/'measurements.json').exists() and (folder/'measurements.json').stat().st_mtime>src.stat().st_mtime:return json.loads((folder/'measurements.json').read_text())
 dur=duration(src);plan=build_en.edl.plan(vertical,variant);starts=[];s=0
 for p in plan:starts.append(s);s+=p['d']
 # Single pass full decode at original frame rate plus audio measurement.
 r=subprocess.run([str(FF),'-hide_banner','-i',src,'-filter:a','ebur128=peak=true','-f','null','-'],capture_output=True,text=True)
 (folder/'decode-loudness.log').write_text(r.stderr);assert r.returncode==0
 summary=r.stderr.rsplit('Summary:',1)[-1];lufs=re.search(r'I:\s*(-?[\d.]+) LUFS',summary);peak=re.search(r'Peak:\s*(-?[\d.]+) dBFS',summary)
 # Every two seconds, timestamp 0,2,4... at source resolution then downsized sheets.
 outframes=folder/'contact-frames';outframes.mkdir(exist_ok=True)
 subprocess.run([str(FF),'-y','-v','error','-i',src,'-vf',r'select=not(mod(n\,60))','-fps_mode','vfr','-threads','1',outframes/'%03d.jpg'],check=True)
 files=sorted(outframes.glob('*.jpg'))
 for a in range(0,len(files),24):
  make_sheet([Image.open(f) for f in files[a:a+24]],[f'{(a+i)*2:.1f}s' for i in range(len(files[a:a+24]))],folder/f'contact-{a//24}.jpg',vertical)
 actions=ACTIONS_VERT if vertical else ACTIONS_FULL;aframes=[];labels=[];am=[]
 for slot,t,label in actions:
  p=plan[slot];move=p['d']-p['freeze'];ot=starts[slot]+(t-p['a'])/(p['b']-p['a'])*move
  center=max(round(starts[slot]*30)+1,min(round((starts[slot]+move)*30)-2,round(ot*30)))
  for offset,kind in [(-1,'before'),(1,'after')]:
   stamp=(center+offset)/30;f=frame(src,stamp);f.save(folder/f'action-{slot:02}-{kind}.png');aframes.append(f);labels.append(f'#{slot} {kind} {stamp:.3f}s')
  am.append({'slot':slot,'action':label,'source_time':t,'output_center':center/30})
 make_sheet(aframes,labels,folder/'action-boundaries.jpg',vertical)
 (folder/'actions.json').write_text(json.dumps(am,indent=2))
 # All slots that touch masked sources: beginning, midpoint, final moving frame,
 # plus endpoint hold. Full-resolution PNGs and overview sheet.
 pf=[];pl=[];pm=[]
 for i,p in enumerate(plan):
  if p['src'] not in ('s2-quote-photo','s2b-photo-closeup','s4-phone-approve'):continue
  for local in sorted(set([0,p['d']/2,max(0,p['d']-p['freeze']-1/30),p['d']-1/30])):
   stamp=round((starts[i]+local)*30)/30;f=frame(src,stamp);f.save(folder/f'privacy-slot-{i:02}-{stamp:07.3f}.png');pf.append(f);pl.append(f'#{i} {stamp:.3f}s');pm.append({'slot':i,'time':stamp})
 make_sheet(pf,pl,folder/'privacy-sheet.jpg',vertical)
 (folder/'privacy-samples.json').write_text(json.dumps(pm,indent=2))
 result={'file':src.name,'duration':dur,'fps':30,'resolution':[1080,1920] if vertical else [1920,1080],'integrated_LUFS':float(lufs[1]),'true_peak_dBTP':float(peak[1]),'full_decode_ok':True,'contact_frames':len(files),'action_pairs':len(actions),'privacy_proof_frames':len(pm)}
 (folder/'measurements.json').write_text(json.dumps(result,indent=2));print(result,flush=True);return result
if __name__=='__main__':
 with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
  results=list(pool.map(lambda q:check(*q),[(False,'anim'),(True,'anim'),(False,'clip'),(True,'clip')]))
 (QA/'measurements.json').write_text(json.dumps(results,indent=2))
