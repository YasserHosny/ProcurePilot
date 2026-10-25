"""The approved Markdown is the only source of caption copy. Offline, no downloads."""
from pathlib import Path
import json
ROOT=Path(__file__).resolve().parent

# Liffey Kitchen Group — all-English eurozone demo, Ireland (PPS-65), forked from edit-sa. Saudi demo (PPS-39): the approved Saudi script is the only source of caption copy; [sa] marks figures filled from
# each language's own recorded round (Arabic UI = round A, English UI = round E, docs/gtm/gcc/rounds/README.md).
FILL={'ar':{8:['-','-','-'],13:['-']},'en':{8: ['Brennan & Walsh', '13', 'oil'], 13: ['53.50']}}
OVERRIDE_EN={0: 'Three suppliers. Three formats. Drums, bags and boxes, all retyped by hand.', 6: 'Items, euro prices, VAT and validity, read automatically. The total checks out.'}

def captions():
    text=(ROOT/'../../../gcc/script-saudi.md').resolve().read_text();out={}
    for line in text.split('## Beats — 16:9')[1].split('9:16: only')[0].splitlines():
        parts=[p.strip() for p in line.split('|')]
        if len(parts)>6 and parts[1].isdigit():
            beat=int(parts[1]);copy={'ar':parts[3].strip('«»'),'en':parts[4].strip('"')}
            for lang in copy:
                for v in FILL[lang].get(beat,[]):copy[lang]=copy[lang].replace('**[sa]**',v,1)
                assert '[sa]' not in copy[lang],(beat,lang)
            copy['en']=copy['en'].replace('SAR ','€')  # the Saudi script's figures are in riyals; Liffey's are euro
            if beat in OVERRIDE_EN:copy['en']=OVERRIDE_EN[beat]
            out[beat]=copy
    assert set(out)==set(range(16))-{4},sorted(out)  # beat 4 is not in the Saudi script (dropped since v2.4)
    return out

def generate():
    copy=captions()
    # [beat, seconds, {lang: [[source,start,end,slotSeconds]]}, crop]. Source times are per language: the Arabic and
    # English rounds were recorded separately. Final spans hold a result for >=1.5 s.
    def both(spans):return {'ar':spans,'en':spans}
    h=[(0,4,both([['opening-h',0,4,4]]),None),
       (1,8,{'ar':[['s5-po-savings',27,29,4],['s5-po-savings',43,43,4]],'en':[['s5-po-savings',27,29,4],['s5-po-savings',44,44,4]]},None),
       (2,7,{'ar':[['s0-phone-lowstock',1.5,3.5,1],['s0-phone-lowstock',9.5,21,4],['s0-phone-lowstock',22.0,22.2,2]],
             'en':[['s0-phone-lowstock',1.5,3.5,1],['s0-phone-lowstock',11,21,4],['s0-phone-lowstock',22.5,22.8,2]]},None),
       (3,11,{'ar':[['s1-rfq',8,24,3],['s1-rfq',26,35,3.5],['s1-rfq',48,51,3],['s1-rfq',52.3,52.3,1.5]],
              'en':[['s1-rfq',8,24,3],['s1-rfq',25,35,3.5],['s1-rfq',41.5,46.5,3],['s1-rfq',47.1,47.1,1.5]]},None),
       (5,5,both([['s2-quote-photo',.3,4.8,5]]),None),
       (6,12,both([['s2-quote-photo',8,11,3],['s2-quote-photo',21.2,22.7,3],['s2-quote-photo',24.5,25.3,4],['s2-quote-photo',8.5,8.5,2]]),None),
       (7,5,both([['s2-quote-photo',25.5,27.5,3.2],['s2r-authorised',.5,2.3,1.8]]),None),
       (8,11,both([['s3c-smart-compare',10.5,14,3],['s3c-smart-compare',18,25,5.5],['s3c-smart-compare',29,29,2.5]]),None),
       (10,10,{'ar':[['s3-guardrail-draft',6,10,4],['s3-guardrail-draft',16,22,4],['s3-guardrail-draft',22.6,25.2,2]],
               'en':[['s3-guardrail-draft',6,10,4],['s3-guardrail-draft',16,22,4],['s3-guardrail-draft',22.6,26,2]]},None),
       (11,8,both([['s4-phone-approve',5,5.5,1],['s4-phone-approve',7,8,2],['s4-phone-approve',12.4,15.6,3.2],['s4r-approved',.5,2.3,1.8]]),None),
       (12,9,both([['s5-po-savings',3,9,2.5],['s5-po-savings',13,20,2.5],['s5-po-savings',22,23.2,2],['s5-po-savings',27,27,2]]),None),
       (13,7,{'ar':[['s5-po-savings',32,35,2],['s5-po-savings',36,39,3],['s5-po-savings',43,43,2]],
              'en':[['s5-po-savings',32,35,2],['s5-po-savings',37,40,3],['s5-po-savings',44,44,2]]},None),
       (14,6,both([['s6-savings-close',4,8,6]]),None)]
    v=[(0,3,both([['opening-v',0,3,3]]),None),
       (1,4,{'ar':[['s5-po-savings',27,27,2.5],['s5-po-savings',43,43,1.5]],'en':[['s5-po-savings',27,27,2.5],['s5-po-savings',44,44,1.5]]},[300,100,1320,900]),
       (3,172/30,{'ar':[['s1-rfq',26,31,82/30],['s1-rfq',48,51,1.5],['s1-rfq',52.3,52.3,1.5]],
                  'en':[['s1-rfq',25,31,82/30],['s1-rfq',41.5,46.5,1.5],['s1-rfq',47.1,47.1,1.5]]},None),
       (5,3,both([['s2-quote-photo',.3,4.8,3]]),None),
       (6,7,both([['s2-quote-photo',8,11,2],['s2-quote-photo',24.5,25.3,3],['s2-quote-photo',8.5,8.5,2]]),None),
       (7,3,both([['s2-quote-photo',25.5,27.5,1.2],['s2r-authorised',.5,2.3,1.8]]),None),
       (8,7,both([['s3c-smart-compare',18,25,5],['s3c-smart-compare',29,29,2]]),None),
       (10,5,both([['s3-guardrail-draft',6,10,3],['s3-guardrail-draft',20.5,23.5,2]]),None),
       (11,5,both([['s4-phone-approve',7,8,1],['s4-phone-approve',12.4,15.6,2.2],['s4r-approved',.5,2.3,1.8]]),None),
       (12,112/30,both([['s5-po-savings',22,23.2,52/30],['s5-po-savings',27,27,2]]),None),
       (13,4.5,{'ar':[['s5-po-savings',36,39,2.5],['s5-po-savings',43,43,2]],'en':[['s5-po-savings',37,40,2.5],['s5-po-savings',44,44,2]]},None)]
    timelines={}
    for fmt,rows in [('h',h),('v',v)]:
        t=0;scenes=[]
        for beat,dur,by_lang,crop in rows:
            for spans in by_lang.values():assert abs(sum(p[3] for p in spans)-dur)<.001,(fmt,beat)
            scenes.append(dict(beat=beat,start=t,duration=dur,spans=by_lang['ar'],crop=crop,copy=copy[beat]));t+=dur
        assert round(t*30)==(3090 if fmt=='h' else 1529)
        assert all(s['beat'] not in (4,9) for s in scenes)
        for scene,(_,_,by_lang,_) in zip(scenes,rows):
            scene['spans_by_language']=by_lang
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
