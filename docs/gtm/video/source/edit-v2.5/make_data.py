"""v2.5 (owner-approved 2026-10-27): every market's v2.4-structure cut gets a 10-s problem chapter, a brand turn
where the logo builds, a full-page saving and a pain-to-fix recap. The 'Real run · demo data' pill is gone.

Each market keeps its own footage and beats 1-14 exactly as its v1 fork cut them: the fork's committed
timeline.json is the source of spans and caption cards. This file only adds the v2.5 scenes around them.
The new chapter-1, turn, saving and recap copy was approved by the owner in chat (Egyptian, 2026-10-26/27);
the Saudi lines are the same copy in Saudi dialect.
"""
from pathlib import Path
import json,copy as _copy
ROOT=Path(__file__).resolve().parent
FPS=30

EN={
 'p1':'Quotes in every format…',
 0:'…and every price retyped into Excel.',
 'p3':['Chasing each supplier one by one','Comparing packs that don\'t match','And no idea what you saved'],
 'turn':['for restaurant purchasing','handles all of it.'],
 'saving':['Saved on this order','against the last purchase price'],
 'recap':{'title':'Every pain, solved','rows':[['Retyping prices','PDFs and photos read automatically'],['One supplier at a time','One RFQ to every supplier'],['Different pack sizes','Per pack, VAT and delivery included'],['Slow approvals','Approval from the phone'],['What did we save?','A verified savings ledger']]},
}
AR_EG={
 'p1':'عروض في كل صيغة…',
 0:'…وكل سعر بتكتبه بإيدك في الإكسيل.',
 'p3':['بتلف على كل مورد لوحده','بتقارن عبوات مش زي بعض','ومش عارف وفّرت كام'],
 'turn':['لمشتريات المطاعم','بيحلّها كلها.'],
 'saving':['توفير على الطلب ده','مقابل آخر سعر شراء'],
 'recap':{'title':'كل مشكلة وعندنا حلها','rows':[['نسخ الأسعار بإيدك','بيقرا الـPDF والصور لوحده'],['مورد مورد','طلب عرض سعر واحد لكل الموردين'],['عبوات مختلفة','مقارنة بالعبوة شامل الضريبة والتوصيل'],['اعتماد متأخر','اعتماد من الموبايل'],['وفّرنا كام؟','سجل توفير معتمد']]},
}
AR_SA={
 'p1':'عروض في كل صيغة…',
 0:'…وكل سعر تكتبه بيدك في الإكسل.',
 'p3':['تدوّر على كل مورد لحاله','تقارن عبوات مو زي بعض','وما تدري كم وفّرت'],
 'turn':['لمشتريات المطاعم','يحلّها كلها.'],
 'saving':['توفير على هذا الطلب','مقابل آخر سعر شراء'],
 'recap':{'title':'كل مشكلة ولها حل','rows':[['نسخ الأسعار بيدك','يقرأ الـPDF والصور بنفسه'],['مورد مورد','طلب عرض سعر واحد لكل الموردين'],['عبوات مختلفة','مقارنة بالعبوة شامل الضريبة والتوصيل'],['اعتماد متأخر','اعتماد من الجوال'],['كم وفّرنا؟','سجل توفير معتمد']]},
}
EN_IE=_copy.deepcopy(EN)
EN_IE['recap']['rows'][2][1]='Per pack, delivery included'  # Irish quotes are ex-VAT (owner, 2026-10-26)

# Money shown on the number cards (beats 1, 6, 8, 13, 14) and the saving page, as each fork showed it.
MONEY={
 'eg':{'ar':{'cards':{1:'٣٠٠ ج.م',6:'٢٤٬٦٤٠ ج.م',8:'٢٠٠ ج.م',13:'٣٠٠ ج.م',14:'١٬٧٦٠ ج.م'},'saving':300,'decimals':0,'prefix':'','suffix':' ج.م','label':'ج.م'},
       'en':{'cards':{1:'EGP 200',6:'EGP 24,440',8:'EGP 200',13:'EGP 200',14:'EGP 1,760'},'saving':200,'decimals':0,'prefix':'EGP ','suffix':'','label':'EGP'}},
 'sa':{'ar':{'cards':{1:'١٩٠ ر.س',6:'٤٬٩١٠ ر.س',8:'٤٠ ر.س',13:'١٩٠ ر.س',14:'١٩٠ ر.س'},'saving':190,'decimals':0,'prefix':'','suffix':' ر.س','label':'ر.س'},
       'en':{'cards':{1:'SAR 120',6:'SAR 4,790',8:'SAR 40',13:'SAR 120',14:'SAR 310'},'saving':120,'decimals':0,'prefix':'SAR ','suffix':'','label':'SAR'}},
 'sa-en':{'en':{'cards':{1:'SAR 310',6:'SAR 4,790',8:'SAR 40',13:'SAR 310',14:'SAR 310'},'saving':310,'decimals':0,'prefix':'SAR ','suffix':'','label':'SAR'}},
 'ie':{'en':{'cards':{1:'€53.50',6:'€1,289.50',8:'€13',13:'€53.50',14:'€93.50'},'saving':53.5,'decimals':2,'prefix':'€','suffix':'','label':''}},
}
# market: (v1 fork, languages, cut folder, file stem, v2.5 copy per language)
MARKETS={
 'eg':('edit-v2.4',['ar','en'],'v2.5','procurepilot-demo-{lang}',{'ar':AR_EG,'en':EN}),
 'sa':('edit-sa',['ar','en'],'gcc-sa-v2','procurepilot-demo-sa-{lang}',{'ar':AR_SA,'en':EN}),
 'sa-en':('edit-sa-en',['en'],'gcc-sa-en-v2','procurepilot-demo-sa-en',{'en':EN}),
 'ie':('edit-ie',['en'],'eu-en-v2','procurepilot-demo-ie-en',{'en':EN_IE}),
}
# The bridge says who the PO goes to (owner, 2026-10-27).
BRIDGE={'لأمر شراء متبعت…':'لأمر شراء تبعته للموردين…','لأمر شراء منرسل…':'لأمر شراء ترسله للموردين…'}
# New-scene lengths: [p1, opening, p3, turn] before beat 1, recap after the last beat.
LEN={'h':{'p1':2.5,0:5,'p3':3.5,'turn':3.5,'recap':6},'v':{'p1':2.5,0:3,'p3':3,'turn':3,'recap':5}}
SAVING={'h':(2.5,2.8),'v':(2.5,2.3)}  # (offset into beat 13, duration)

def card(text,offset,duration,role='fix'):return {'text':text,'offset':offset,'duration':duration,'role':role}

def build(market,fmt):
    fork,langs,_,_,copy=MARKETS[market]
    src=json.loads((ROOT/'..'/fork/'timeline.json').read_text())[fmt]
    L=LEN[fmt];scenes=[]
    def add(beat,dur,**kw):
        scenes.append(dict(beat=beat,duration=dur,spans=[],crop=None,spans_by_language={l:[] for l in langs},cards_by_language={},**kw))
    add('p1',L['p1'])
    opening=[['opening-'+fmt,0,L[0],L[0]]]
    add(0,L[0]);scenes[-1].update(spans=opening,spans_by_language={l:opening for l in langs},
        cards_by_language={l:[card(copy[l][0],0,L[0])] for l in langs})
    add('p3',L['p3']);add('turn',L['turn'])
    for s in src['scenes']:
        if s['beat']==0:continue
        s={k:v for k,v in s.items() if k not in ('start','copy')}
        s['spans_by_language']={l:s['spans_by_language'][l] for l in langs}
        s['cards_by_language']={l:s['cards_by_language'][l] for l in langs}
        if s['beat']==1:
            # The turn card already introduced the brand: beat 1 drops its name card and opens on the fix.
            for l in langs:
                text=s['cards_by_language'][l][-1]['text']
                for a,b in BRIDGE.items():text=text.replace(a,b)
                s['cards_by_language'][l]=[card(text,0,s['duration'])]
        if s['beat']==13 and fmt=='v':
            # Room for the full-page saving: the ledger hold grows 1.5 s.
            s['duration']+=1.5
            for l in langs:
                spans=[list(p) for p in s['spans_by_language'][l]];spans[-1][3]+=1.5;s['spans_by_language'][l]=spans
            s['spans']=s['spans_by_language'][langs[0]]
        scenes.append(s)
    add('recap',L['recap'])
    t=0
    for s in scenes:
        s['start']=t;t+=s['duration']
        for l in langs:assert not s['spans_by_language'][l] or abs(sum(p[3] for p in s['spans_by_language'][l])-s['duration'])<.001,(market,fmt,s['beat'])
    frames=round(t*FPS);assert abs(t*FPS-frames)<1e-6,(market,fmt,t)
    for l in langs:
        for s in scenes:
            for c in s['cards_by_language'].get(l,[]):
                assert 'وفورات' not in c['text'] and 'وفر ' not in c['text'],c['text']
    return dict(body=frames/FPS,outro=src['outro'],scenes=scenes,langs=langs,
                v25={l:copy[l] for l in langs},money={l:MONEY[market][l] for l in langs},saving_at=SAVING[fmt])

def generate():
    timelines={m:{f:build(m,f) for f in 'hv'} for m in MARKETS}
    (ROOT/'timeline.json').write_text(json.dumps(timelines,ensure_ascii=False,indent=2)+'\n')
    metas={m:json.loads((ROOT/f'plates-{m}/meta.json').read_text()) for m in MARKETS if (ROOT/f'plates-{m}/meta.json').exists()}
    beats=[float(s) for s in (ROOT/'../../music/antalya-beaches-beats.csv').read_text().splitlines() if s and s[0].isdigit()]
    (ROOT/'data.js').write_text('window.MARKETS='+json.dumps(timelines,ensure_ascii=False)+';\nwindow.METAS='+json.dumps(metas)+';\nwindow.BEATS='+json.dumps(beats)+';\n')
    for m in MARKETS:print(m,{f:f"{timelines[m][f]['body']:.2f}s" for f in 'hv'})
if __name__=='__main__':generate()
