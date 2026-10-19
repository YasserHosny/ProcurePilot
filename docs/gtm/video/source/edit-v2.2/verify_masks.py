"""Join actual source PTS detections to EDL, require full identity glyph containment.
The raw detector scans EVERY encoded raw frame, including scrolls and loading transitions.
"""
from paths import *
from edl import FULL,VERT
import json

def verify():
 audit=json.loads((ROOT/'analysis/raw-email-audit.json').read_text());report=[];errors=[]
 for name,plan in [('landscape',FULL),('vertical',VERT)]:
  offset=0
  for i,p in enumerate(plan):
   matches=[]
   for f in audit.get(p['src'],{}).get('detections',[]):
    if p['a']-.001 <= f['time'] <= p['b']+.001:
     for m in f['matches']:
      _,x,y,w,h,_=m
      mask=p['mask'];crop=p['crop']
      # An email glyph entirely outside a crop cannot reach the output.
      outside=crop and (x+w<=crop[0] or x>=crop[0]+crop[2] or y+h<=crop[1] or y>=crop[1]+crop[3])
      covered=mask and x>=mask[0] and y>=mask[1] and x+w<=mask[0]+mask[2] and y+h<=mask[1]+mask[3]
      matches.append({'source_time':f['time'],'bbox':m,'covered':bool(covered),'outside_crop':bool(outside)})
      if not(covered or outside):errors.append([name,i,p['src'],f])
   report.append({'cut':name,'slot':i,'output_start':offset,'output_end':offset+p['d'],'mask':p['mask'],'source':p['src'],'source_span':[p['a'],p['b']],'detections':matches});offset+=p['d']
 (ROOT/'analysis/mask-coverage.json').write_text(json.dumps({'errors':errors,'segments':report},indent=2))
 print('MASK COVERAGE',len(errors),'errors',flush=True)
 for e in errors[:20]:print(e)
 if errors:raise SystemExit(1)
if __name__=='__main__':verify()
