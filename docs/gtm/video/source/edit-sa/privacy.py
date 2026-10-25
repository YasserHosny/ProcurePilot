"""Offline, every-frame native-resolution glyph audit; templates remain in RAM.
No private strings or template images are written. All matches searched across the full frame.
"""
from pathlib import Path
import subprocess, json, io, shutil, hashlib, os
import numpy as np
from PIL import Image
ROOT=Path(__file__).resolve().parent
FF='/home/yasserhosny/Work/pp-video-env/lib/python3.12/site-packages/imageio_ffmpeg/binaries/ffmpeg-linux-x86_64-v7.0.2'

def sample(lang,name,t):
    b=subprocess.run([FF,'-v','error','-ss',str(t),'-i',str(ROOT/'raw'/lang/(name+'.mp4')),'-frames:v','1','-f','image2pipe','-vcodec','png','-'],capture_output=True,check=True).stdout
    return np.asarray(Image.open(io.BytesIO(b)).convert('L'))

def templates():
    # Saudi owner address (+pp-sa-owner) wraps onto two lines: one template per line, so both lines are masked.
    specs=[('quote-ar-1','ar','s2-quote-photo',10,(798,931,938,950)),('quote-ar-2','ar','s2-quote-photo',10,(806,950,939,968)),
           ('quote-en-1','en','s2-quote-photo',10,(980,932,1124,950)),('quote-en-2','en','s2-quote-photo',10,(980,950,1113,968)),
           ('phone-list-ar-1','ar','s4-phone-approve',5,(155,64,374,82)),('phone-list-ar-2','ar','s4-phone-approve',5,(248,83,374,100)),
           ('phone-detail-ar','ar','s4-phone-approve',9,(23,233,290,251)),
           ('phone-list-en-1','en','s4-phone-approve',5,(69,64,230,82)),('phone-list-en-2','en','s4-phone-approve',5,(16,83,142,100)),
           ('phone-detail-en','en','s4-phone-approve',9,(97,233,365,251))]
    out=[];rng=np.random.default_rng(7)
    for label,lang,name,t,(x,y,x1,y1) in specs:
        a=sample(lang,name,t)[y:y1,x:x1];mask=a<185
        ink=np.argwhere(a<100);white=np.argwhere(a>230)
        assert len(ink)>30,(label,len(ink))
        black=[(*p,True) for p in ink[rng.choice(len(ink),20,replace=False)]]
        clear=[(*p,False) for p in white[rng.choice(len(white),12,replace=False)]]
        anchors=[a for pair in zip(black[:12],clear) for a in pair]+black[12:]
        out.append((label,mask,anchors))
    return out

def match_numpy(g,ts):
    b=g<185;H,W=b.shape;hits=[]
    for label,t,aa in ts:
        h,w=t.shape;hh,ww=H-h+1,W-w+1
        if hh<1 or ww<1:continue
        cand=np.ones((hh,ww),dtype=bool)
        for y,x,v in aa[:8]:
            patch=b[y:y+hh,x:x+ww];cand &= patch if v else ~patch
        yy,xx=np.where(cand)
        for y,x,v in aa[8:]:
            ok=b[yy+y,xx+x]==v;yy,xx=yy[ok],xx[ok]
            if not len(yy):break
        for y,x in zip(yy,xx):
            diff=np.mean(b[y:y+h,x:x+w]!=t)
            if diff<.12:hits.append([label,int(x),int(y),w,h])
    return hits


_NATIVE=None
_PREPARE=None
def match(g,ts):
    global _NATIVE,_PREPARE
    import ctypes
    if _NATIVE is None:
        folder=ROOT/'tmp';folder.mkdir(exist_ok=True);lib=folder/f'matcher-{os.getpid()}.so'
        subprocess.run(['cc','-O3','-shared','-fPIC',str(ROOT/'matcher.c'),'-o',str(lib)],check=True)
        library=ctypes.CDLL(str(lib));_NATIVE=library.glyph_matches
        _PREPARE=library.prepare_frame;_PREPARE.argtypes=[ctypes.c_void_p,ctypes.c_int,ctypes.c_int]
        _NATIVE.argtypes=[ctypes.c_void_p,ctypes.c_int,ctypes.c_int,ctypes.c_void_p,ctypes.c_int,ctypes.c_int,ctypes.c_void_p,ctypes.c_int,ctypes.c_void_p,ctypes.c_int]
        _NATIVE.restype=ctypes.c_int
    g=np.ascontiguousarray(g);H,W=g.shape;_PREPARE(g.ctypes.data,H,W);hits=[];out=np.empty((2048,2),dtype=np.int32)
    for label,t,anchors in ts:
        t=np.ascontiguousarray(t,dtype=np.uint8);aa=np.ascontiguousarray(anchors,dtype=np.int32);h,w=t.shape
        n=_NATIVE(g.ctypes.data,H,W,t.ctypes.data,h,w,aa.ctypes.data,len(aa),out.ctypes.data,len(out))
        assert n>=0,'Detector hit buffer exhausted'
        hits += [[label,int(x),int(y),w,h] for x,y in out[:n]]
    return hits

def scan(src,ts):
    phone='phone' in src.stem;W,H=(390,844) if phone else (1920,1080)
    p=subprocess.Popen([FF,'-v','error','-threads','2','-i',str(src),'-f','rawvideo','-pix_fmt','gray','-'],stdout=subprocess.PIPE)
    n=0;det={};cache={}
    while True:
        raw=p.stdout.read(W*H)
        if not raw:break
        assert len(raw)==W*H
        digest=hashlib.sha256(raw).digest()
        if digest not in cache:cache[digest]=match(np.frombuffer(raw,np.uint8).reshape(H,W),ts)
        hits=cache[digest]
        if hits:det[n]=hits
        n+=1
    assert p.wait()==0
    return {'frames':n,'unique_decoded_frames':len(cache),'matching_frames':len(det),'matches':sum(map(len,det.values())),'detections':det}

def mask(src,result):
    lang=src.parent.name;dst=ROOT/'masked'/lang/src.name;dst.parent.mkdir(parents=True,exist_ok=True)
    phone='phone' in src.stem;H=844 if phone else 1080;W=390 if phone else 1920
    boxes={}
    # Five-frame temporal halo and scroll corridor: each detection follows native coordinates.
    for f,hh in result['detections'].items():
        for k in range(max(0,int(f)-5),min(result['frames'],int(f)+6)):
            for _,x,y,w,h in hh:boxes.setdefault(k,[]).append((max(0,x-8),max(0,y-5),min(W,x+w+8),min(H,y+h+5)))
    # Cover narrow identity-column scroll corridors independently of glyph detections.
    # Restricted to quote review, not the inbox. Also cover partial glyphs at scene transitions.
    extra=[]
    if src.stem=='s2-quote-photo':
        # Saudi rounds: the information panel scrolls off the top at 24.6–26.4 s in both languages.
        x=790 if lang=='ar' else 976
        extra=[(24.6,26.4,(x,58,156,960),'white')]
    if src.stem=='s4-phone-approve':
        list_end=max((int(f)/30 for f,hh in result['detections'].items() if any(h[0].startswith('phone-list') for h in hh)),default=6.5)+.5
        extra=[(1.5,max(7.0,list_end),(0,58,390,43),'0xf3f4f9'),
               (5.8,result['frames']/30,(0,228,390,27),'0xf3f4f9')]
    spans=[]
    for f,rs in boxes.items():
        for x,y,x1,y1 in set(rs):spans.append((f/30,(f+1)/30,(x,y,x1-x,y1-y),'0xf3f4f9' if phone else 'white'))
    spans+=extra
    merged=[]
    for a,b,r,c in sorted(spans,key=lambda s:(s[2],s[3],s[0])):
        if merged and merged[-1][2:]==(r,c) and a<=merged[-1][1]+.00001:merged[-1]=(merged[-1][0],max(b,merged[-1][1]),r,c)
        else:merged.append((a,b,r,c))
    if merged:
        filt=','.join(f"drawbox=x={r[0]}:y={r[1]}:w={r[2]}:h={r[3]}:color={c}:t=fill:enable='gte(t,{a:.6f})*lt(t,{b:.6f})'" for a,b,r,c in merged)
        fp=ROOT/'proof'/f'{lang}-{src.stem}.filter';fp.write_text(filt)
        subprocess.run([FF,'-v','error','-y','-i',str(src),'-filter_script:v',str(fp),'-c:v','libx264','-preset','fast','-crf','12','-threads','4','-pix_fmt','yuv420p','-an',str(dst)],check=True)
    else:shutil.copyfile(src,dst)
    return {'rectangles':len(merged),'fixed_corridors':extra}

def main():
    import argparse
    ap=argparse.ArgumentParser();ap.add_argument('mode',choices=['before','mask','after','control']);ap.add_argument('--resume',action='store_true');ap.add_argument('--report-tag',default='native');args=ap.parse_args()
    tag='-'+args.report_tag if args.report_tag else ''
    (ROOT/'proof').mkdir(exist_ok=True)
    if args.mode=='mask':
        report=json.loads((ROOT/'proof'/f'before{tag}.json').read_text())
        assert len(report)==16,'All 16 raw clips must finish their audit before the masking pass'
        masks={}
        for key,value in report.items():
            masks[key]=mask(ROOT/'raw'/key,value);print('MASK',key,masks[key]['rectangles'],flush=True)
        (ROOT/'proof/masks.json').write_text(json.dumps(masks,indent=2));return
    ts=templates();report={}
    saved=ROOT/'proof'/f'{args.mode}{tag}.json'
    if args.resume and saved.exists():report=json.loads(saved.read_text())
    paths=[ROOT/'raw/ar/s2-quote-photo.mp4'] if args.mode=='control' else sorted((ROOT/('masked' if args.mode=='after' else 'raw')).glob('*/*.mp4'))
    paths=[p for p in paths if p.parent.name in ('ar','en') and p.stem not in ('s2r-authorised','s4r-approved')]
    for p in paths:
        key=p.parent.name+'/'+p.name
        v=report[key] if key in report else scan(p,ts);report[key]=v
        print(args.mode.upper(),key,'frames',v['frames'],'matching_frames',v['matching_frames'],'matches',v['matches'],flush=True)
        (ROOT/'proof'/f'{args.mode}{tag}.json').write_text(json.dumps(report))
    if args.mode=='after':assert len(report)==16 and not any(v['matches'] for v in report.values())
    if args.mode=='control':assert report['ar/s2-quote-photo.mp4']['matches']>0
if __name__=='__main__':main()
