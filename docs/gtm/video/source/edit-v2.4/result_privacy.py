"""Every-frame audit and full-duration identity masks for the four result inserts."""
import json,subprocess
import numpy as np
from privacy import ROOT,FF,templates,sample,scan,match,match_numpy
NAMES=('s2r-authorised','s4r-approved')

def result_templates():
    ts=templates();rng=np.random.default_rng(24)
    for lang,x in [('ar',1030),('en',672)]:
        a=sample(lang,'s4r-approved',2)[838:855,x:x+245]
        black=np.argwhere(a<100);white=np.argwhere(a>245)
        assert len(black)>30 and len(white)>30
        ink=[(*p,True) for p in black[rng.choice(len(black),20,replace=False)]]
        clear=[(*p,False) for p in white[rng.choice(len(white),12,replace=False)]]
        anchors=[v for pair in zip(ink[:12],clear) for v in pair]+ink[12:]
        ts.append(('result-approver-'+lang,a<185,anchors))
    return ts

def boxes(lang,name):
    if name=='s2r-authorised':return [(798 if lang=='ar' else 972,610,152,110)]
    return [(580,833,760,28)]

def main():
    ts=result_templates();report={}
    for lang in ['ar','en']:
        for name in NAMES:
            src=ROOT/'raw'/lang/(name+'.mp4');dst=ROOT/'masked'/lang/src.name
            g=sample(lang,name,2);assert sorted(match(g,ts))==sorted(match_numpy(g,ts))
            before=scan(src,ts);rects=boxes(lang,name)
            assert before['matches']>0,'Known visible identity must be detected'
            for hh in before['detections'].values():
                for _,x,y,w,h in hh:
                    assert any(x>=bx and y>=by and x+w<=bx+bw and y+h<=by+bh for bx,by,bw,bh in rects),(lang,name,x,y,w,h)
            baseline=sum(not h[0].startswith('result-') for hh in before['detections'].values() for h in hh)
            vf=','.join(f'drawbox=x={x}:y={y}:w={w}:h={h}:color=white:t=fill' for x,y,w,h in rects)
            subprocess.run([FF,'-v','error','-y','-i',str(src),'-vf',vf,'-c:v','libx264','-preset','fast','-crf','12','-threads','4','-pix_fmt','yuv420p','-an',str(dst)],check=True)
            after=scan(dst,ts);assert after['frames']==before['frames'] and after['matches']==0
            key=lang+'/'+src.name
            report[key]={'before':before,'after':after,'legacy_template_hits':baseline,'boxes':rects,'colour':'#FFFFFF','window':'entire clip'}
            (ROOT/'proof/results-privacy.json').write_text(json.dumps(report,indent=2)+'\n')
            print(f"RESULT_PRIVACY {key} frames={before['frames']} before_frames={before['matching_frames']} before_hits={before['matches']} legacy_hits={baseline} after_hits={after['matches']} boxes={rects} white entire_clip",flush=True)
    assert len(report)==4
if __name__=='__main__':main()
