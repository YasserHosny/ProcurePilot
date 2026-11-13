"""Tighten the generated voiceover (long pauses shortened), lay the nine segments on the timeline and write data.js.
Scene starts follow the voice: each scene begins a short gap after the previous line ends."""
import json,subprocess,wave
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parent;SR=48000;FPS=30
MAXGAP={'default':.40,'s9':.55,'s1':.38,'s8':.62}   # longest pause kept inside a segment (s)
LEAD=.30      # video starts, then the first word
GAP=.38       # between segments
TAIL=3.6      # hold on the end card after the last word
DROP=53.47    # the track's chorus drop (s); it lands on the start of scene s8

def load(p):
    raw=subprocess.check_output(['ffmpeg','-v','error','-i',str(p),'-ac','1','-ar',str(SR),'-f','f32le','-'])
    return np.frombuffer(raw,np.float32).copy()

def tighten(x,words,maxgap):
    """Cut the middle out of every pause longer than maxgap; return audio and shifted word times."""
    out=[];shift=0;pos=0;new=[]
    fade=int(.012*SR)
    for i,(o,d,t) in enumerate(words):
        new.append([round(o-shift,3),round(d,3),t])
        if i+1<len(words):
            end=o+d;gap=words[i+1][0]-end
            if gap>maxgap:
                cut=gap-maxgap;a=int((end+maxgap/2)*SR);b=int((end+maxgap/2+cut)*SR)
                seg=x[pos:a].copy();seg[-fade:]*=np.linspace(1,0,fade);out.append(seg)
                x[b:b+fade]*=np.linspace(0,1,fade);pos=b;shift+=cut
    end=int((words[-1][0]+words[-1][1]+.25)*SR)
    seg=x[pos:min(end,len(x))].copy();seg[-fade:]*=np.linspace(1,0,fade);out.append(seg)
    return np.concatenate(out),new

def main():
    raw=json.loads((ROOT/'vo/raw-timing.json').read_text())
    texts={s['id']:s['text'] for s in json.loads((ROOT/'vo/script.json').read_text())}
    t=LEAD;segs=[];track=[]
    for r in raw:
        x,words=tighten(load(ROOT/'vo'/(r['id']+'.mp3')),r['words'],MAXGAP.get(r['id'],MAXGAP['default']))
        speech=words[-1][0]+words[-1][1]
        segs.append({'id':r['id'],'text':texts[r['id']],'at':round(t,3),'speech':round(speech,3),'words':words})
        track.append((t,x));t+=speech+GAP
    # scene i runs from just before its line to just before the next line
    starts=[0]+[round((s['at']-.18)*FPS)/FPS for s in segs[1:]]
    total=round((segs[-1]['at']+segs[-1]['speech']+TAIL)*FPS)/FPS
    for i,s in enumerate(segs):
        s['start']=starts[i];s['end']=starts[i+1] if i+1<len(segs) else total
    n=int(total*SR);mix=np.zeros(n,np.float32)
    for at,x in track:
        a=int(at*SR);mix[a:a+len(x)]+=x[:max(0,n-a)]
    with wave.open(str(ROOT/'build/vo.wav'),'wb') as w:
        w.setnchannels(1);w.setsampwidth(2);w.setframerate(SR);w.writeframes((np.clip(mix,-1,1)*32767).astype(np.int16).tobytes())
    data={'fps':FPS,'duration':total,'segments':segs,'music_offset':round(DROP-segs[7]['start'],3)}
    (ROOT/'timeline.json').write_text(json.dumps(data,ensure_ascii=False,indent=1)+'\n')
    (ROOT/'build/data.js').write_text('window.AD='+json.dumps(data,ensure_ascii=False)+';\n')
    for s in segs:print(s['id'],s['start'],'->',s['end'],'| voice',s['at'],'+',s['speech'])
    print('total',total,'music offset',data['music_offset'])
    # subtitles for muted autoplay / platform captions
    def ts(v):return '%02d:%02d:%02d,%03d'%(v//3600,v%3600//60,v%60,round(v%1*1000))
    srt=[];k=1
    for s in segs:
        line=[];words=s['words'];toks=s['text'].split()
        j=0
        for i,(o,d,_) in enumerate(words):
            line.append(i)
            last=i+1==len(words)
            if last or words[i+1][0]-(o+d)>.25 or len(line)>=6:
                a=s['at']+words[line[0]][0];b=s['at']+o+d+.15
                srt.append(f"{k}\n{ts(a)} --> {ts(b)}\n{' '.join(w[2] for w in words[line[0]:i+1])}\n");k+=1;line=[]
    (ROOT/'build/captions.srt').write_text('\n'.join(srt))
if __name__=='__main__':
    (ROOT/'build').mkdir(exist_ok=True);main()
