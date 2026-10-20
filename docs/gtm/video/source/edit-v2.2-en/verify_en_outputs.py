from paths import *
import json,subprocess,numpy as np
import build_en
M=json.loads((ROOT/'qa-en/privacy/mask-manifest.json').read_text())
results={}
for vertical in (False,True):
 for variant in ('anim','clip'):
  size='9x16-60s' if vertical else '16x9';name=f'procurepilot-demo-en-{size}-{variant}';W,H=(1080,1920) if vertical else (1920,1080)
  plan=build_en.edl.plan(vertical,variant);starts=[];s=0
  for q in plan:starts.append(s);s+=q['d']
  proc=subprocess.Popen([str(FF),'-v','error','-i',ROOT/(name+'.mp4'),'-f','rawvideo','-pix_fmt','gray','-'],stdout=subprocess.PIPE)
  n=checked=0;bad=[];minmean=255
  while True:
   raw=proc.stdout.read(W*H)
   if len(raw)!=W*H:break
   t=n/30;g=np.frombuffer(raw,np.uint8).reshape(H,W);n+=1
   if t>=s:continue
   slot=max(i for i,a in enumerate(starts) if a<=t+1e-7);q=plan[slot];src=q['src']
   if src not in M or not M[src]['masked_ranges'] or not q['crop']:continue
   move=q['d']-q['freeze'];source=q['a']+min((t-starts[slot])/move,1)*(q['b']-q['a']);source=min(source,q['b']-1/30)
   cx,cy,cw,ch=q['crop'];mw,mh=(972,1040) if vertical else (1800,890);scale=min(mw/cw,mh/ch);sw,sh=round(cw*scale),round(ch*scale);ox=(W-sw)/2;oy=(475 if vertical else 20)+(mh-sh)/2
   did=False
   for a,b,(x,y,w,h),color in M[src]['masked_ranges']:
    # Avoid samples on mask activation edges; separately covered by proof PNGs.
    if not (a+.08<source<b-.08):continue
    x0=max(cx,x)+7;y0=max(cy,y)+7;x1=min(cx+cw,x+w)-7;y1=min(cy+ch,y+h)-7
    if x1-x0<8 or y1-y0<8:continue
    rx0=int(ox+(x0-cx)*scale)+2;ry0=int(oy+(y0-cy)*scale)+2;rx1=int(ox+(x1-cx)*scale)-2;ry1=int(oy+(y1-cy)*scale)-2
    if rx1<=rx0 or ry1<=ry0:continue
    patch=g[ry0:ry1,rx0:rx1];mean=float(patch.mean());minmean=min(minmean,mean);did=True
    if mean<235 or float(patch.std())>12:bad.append({'frame':n-1,'slot':slot,'source_time':source,'mean':round(mean,2),'std':round(float(patch.std()),2)})
   checked+=did
  assert proc.wait()==0
  results[name]={'decoded_frames':n,'frames_with_mask_interiors_checked':checked,'minimum_patch_mean':round(minmean,2),'failed_patches':bad}
  print(name,n,checked,'bad',len(bad),flush=True)
  (ROOT/'qa-en/privacy/output-mask-checks.json').write_text(json.dumps(results,indent=2))
