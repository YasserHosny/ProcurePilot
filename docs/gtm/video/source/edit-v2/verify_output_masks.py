"""Verify opaque mask interiors in EVERY final frame of every retained identity slot.
Coverage of all known glyph pixels is separately checked by verify_masks.py.
"""
from paths import *
from edl import FULL,VERT
import sys,subprocess,json,math
sys.path.insert(0,str(ROOT/'deps'))
import numpy as np

def run_one(lang,vertical):
 W,H=(1080,1920) if vertical else (1920,1080);plan=VERT if vertical else FULL
 tag=f'{lang}-'+('9x16-60s' if vertical else '16x9');out=ROOT/f'procurepilot-demo-{tag}.mp4';checks=[];offset=0
 for i,p in enumerate(plan):
  rect=None
  if p['mask']:
   mx,my,mw,mh,_=p['mask']
   if 'phone' in p['src'] and not (vertical and p['crop']):
    h=1040 if vertical else 885;w=round((390*h/844)/2)*2;sx=w/390;sy=h/844;padx=(W-w)//2;pady=475 if vertical else 25
    rect=[padx+mx*sx,pady+my*sy,mw*sx,mh*sy]
   elif p['crop']:
    cx,cy,cw,ch=p['crop']
    if mx>=cx and my>=cy and mx+mw<=cx+cw and my+mh<=cy+ch:
     ratio=min(972/cw,1040/ch) if vertical else min(1800/cw,890/ch)
     w=round(cw*ratio);h=round(ch*ratio);padx=(W-w)//2;pady=475+(1040-h)//2 if vertical else 20+(890-h)//2
     rect=[padx+(mx-cx)*w/cw,pady+(my-cy)*h/ch,mw*w/cw,mh*h/ch]
  if rect:
   x,y,w,h=rect;x=2*((math.ceil(x)+5)//2);y=2*((math.ceil(y)+5)//2);w=2*((math.floor(w)-10)//2);h=2*((math.floor(h)-10)//2)
   # Select exact output frame indices, preserving the entire slot and its frozen frames.
   first=round(offset*30);last=round((offset+p['d'])*30)-1
   vf=f'crop={w}:{h}:{x}:{y}'
   proc=subprocess.Popen([str(FF),'-v','error','-ss',str(offset),'-i',str(out),'-t',str(p['d']),'-vf',vf,'-fps_mode','passthrough','-f','rawvideo','-pix_fmt','gray','-'],stdout=subprocess.PIPE)
   n=0;minimum=255;lowestmean=255.;bad=[]
   while True:
    raw=proc.stdout.read(w*h)
    if len(raw)!=w*h:break
    a=np.frombuffer(raw,np.uint8);v=int(a.min());m=float(a.mean());minimum=min(minimum,v);lowestmean=min(lowestmean,m)
    if v<215 or m<240:bad.append(first+n)
    n+=1
   proc.wait();assert n==last-first+1,(tag,i,n,last-first+1)
   checks.append({'slot':i,'frame_range':[first,last],'checked_frames':n,'interior_roi':[x,y,w,h],'min_gray':minimum,'min_frame_mean':lowestmean,'bad_frames':bad})
  offset+=p['d']
 result={'cut':tag,'checks':checks,'passed':not any(x['bad_frames'] for x in checks)}
 (ROOT/'analysis'/f'output-mask-check-{tag}.json').write_text(json.dumps(result,indent=2));print(tag,result['passed'],[(x['slot'],x['checked_frames'],x['min_gray']) for x in checks],flush=True)
 if not result['passed']:raise SystemExit(1)
if __name__=='__main__':
 for lang,v in [('ar',False),('en',False),('ar',True),('en',True)]:run_one(lang,v)
