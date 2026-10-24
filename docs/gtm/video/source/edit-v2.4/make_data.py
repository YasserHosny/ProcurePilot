"""The approved Markdown is the only source of caption copy. Offline, no downloads."""
from pathlib import Path
import json
ROOT=Path(__file__).resolve().parent

def captions():
    text=(ROOT/'../../cuts/v2.4-ledger/script.md').resolve().read_text();out={}
    for line in text.split('## Beats — 16:9')[1].split('## Beats — 9:16')[0].splitlines():
        parts=[p.strip() for p in line.split('|')]
        if len(parts)>7 and parts[1].isdigit():
            out[int(parts[1])]={'ar':parts[4].strip('«»'),'en':parts[5].strip('"')}
    assert set(out)==set(range(16))
    return out

def generate():
    copy=captions()
    # [beat, seconds, [[source,start,end,slotSeconds]], crop]
    # Source time jumps remove page navigation/loading. Final spans hold a result for >=1.5 s.
    h=[(0,4,[['opening-h',0,4,4]],None),
       (1,8,[['s5-po-savings',26,28,4],['s5-po-savings',42,42,4]],None),
       (2,7,[['s0-phone-lowstock',1.5,3.5,1],['s0-phone-lowstock',11,20.5,4],['s0-phone-lowstock',21.8,22.1,2]],None),
       (3,11,[['s1-rfq',4,18,3],['s1-rfq',24,34,3.5],['s1-rfq',40.5,43.3,3],['s1-rfq',44.2,44.2,1.5]],None),
       (5,5,[['s2-quote-photo',.3,4.8,5]],None),
       (6,12,[['s2-quote-photo',8,11,3],['s2-quote-photo',22,23,3],['s2-quote-photo',24,25,4],['s2-quote-photo',8.5,8.5,2]],None),
       (7,5,[['s2-quote-photo',24.5,26.3,3.2],['s2r-authorised',.5,2.3,1.8]],None),
       (8,11,[['s3c-smart-compare',10.5,14,3],['s3c-smart-compare',20,27,5.5],['s3c-smart-compare',29,29,2.5]],None),
       (10,10,[['s3-guardrail-draft',5,10,4],['s3-guardrail-draft',16,22,4],['s3-guardrail-draft',22.5,24.1,2]],None),
       (11,8,[['s4-phone-approve',5,5.5,1],['s4-phone-approve',7,8,2],['s4-phone-approve',13.5,15.15,3.2],['s4r-approved',.5,2.3,1.8]],None),
       (12,9,[['s5-po-savings',3,9,2.5],['s5-po-savings',13,20,2.5],['s5-po-savings',22,23.2,2],['s5-po-savings',26,26,2]],None),
       (13,7,[['s5-po-savings',32,35,2],['s5-po-savings',36,38.5,3],['s5-po-savings',42,42,2]],None),
       (14,6,[['s6-savings-close',4,8,6]],None)]
    v=[(0,3,[['opening-v',0,3,3]],None),
       (1,4,[['s5-po-savings',26,26,2.5],['s5-po-savings',42,42,1.5]], [300,100,1320,900]),
       (3,172/30,[['s1-rfq',24,28,82/30],['s1-rfq',40.5,43.3,1.5],['s1-rfq',44.2,44.2,1.5]],None),
       (5,3,[['s2-quote-photo',.3,4.8,3]],None),
       (6,7,[['s2-quote-photo',8,11,2],['s2-quote-photo',24,25,3],['s2-quote-photo',8.5,8.5,2]],None),
       (7,3,[['s2-quote-photo',24.5,26.3,1.2],['s2r-authorised',.5,2.3,1.8]],None),
       (8,7,[['s3c-smart-compare',20,27,5],['s3c-smart-compare',29,29,2]],None),
       (10,5,[['s3-guardrail-draft',5,10,3],['s3-guardrail-draft',20,23,2]],None),
       (11,5,[['s4-phone-approve',7,8,1],['s4-phone-approve',13.5,15.15,2.2],['s4r-approved',.5,2.3,1.8]],None),
       (12,112/30,[['s5-po-savings',22,23.2,52/30],['s5-po-savings',26,26,2]],None),
       (13,4.5,[['s5-po-savings',36,38.5,2.5],['s5-po-savings',42,42,2]],None)]
    timelines={}
    for fmt,rows in [('h',h),('v',v)]:
        t=0;scenes=[]
        for beat,dur,spans,crop in rows:
            assert abs(sum(p[3] for p in spans)-dur)<.001
            scenes.append(dict(beat=beat,start=t,duration=dur,spans=spans,crop=crop,copy=copy[beat]));t+=dur
        assert round(t*30)==(3090 if fmt=='h' else 1529)
        assert all(s['beat'] not in (4,9) for s in scenes)
        for scene in scenes:
            english=[]
            for name,a,b,slot in scene['spans']:
                if name=='s5-po-savings' and a==42 and b==42:a=b=44.5
                if name=='s5-po-savings' and a==36 and b==38.5:a,b=38,40.3
                english.append([name,a,b,slot])
            scene['spans_by_language']={'ar':scene['spans'],'en':english}
            scene['cards_by_language']={}
            for lang in ['ar','en']:
                parts=scene['copy'][lang].split(' / ')
                assert len(parts) in (1,2)
                sequence=parts if fmt=='h' or scene['beat'] in (1,13) else parts[-1:]
                first=2.5 if len(sequence)==2 else scene['duration']
                scene['cards_by_language'][lang]=[
                    {'text':text,'offset':0 if i==0 else first,
                     'duration':first if i==0 else scene['duration']-first,
                     'role':('bridge' if scene['beat']==1 else 'pain') if len(sequence)==2 and i==0 else 'fix'}
                    for i,text in enumerate(sequence)]
        t=round(t*30)/30

        timelines[fmt]=dict(body=t,outro=9.75 if fmt=='h' else 8.5,scenes=scenes)
    (ROOT/'timeline.json').write_text(json.dumps(timelines,ensure_ascii=False,indent=2)+'\n')
    meta=json.loads((ROOT/'plates/meta.json').read_text()) if (ROOT/'plates/meta.json').exists() else {}
    beats=[float(s) for s in (ROOT/'../../music/antalya-beaches-beats.csv').read_text().splitlines() if s and s[0].isdigit()]
    (ROOT/'data.js').write_text('window.TIMELINES='+json.dumps(timelines,ensure_ascii=False)+';\nwindow.PLATE_META='+json.dumps(meta)+';\nwindow.BEATS='+json.dumps(beats)+';\n')
    print('TIMELINES h=103s (3090 frames); v=1529/30s (1529 frames); approved cards parsed verbatim')
if __name__=='__main__':generate()
