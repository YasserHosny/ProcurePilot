"""Sound for the ad: voiceover (build/vo.wav), the licensed track ducked under the voice, and synthesised
sound effects placed on the same word timings the picture uses. Outputs (48 kHz stereo): build/mix.wav with the
voice, build/mix-novo.wav with music and effects only."""
import json,subprocess,wave,re
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parent;B=ROOT/'build';SR=48000
TL=json.loads((ROOT/'timeline.json').read_text());SEG={s['id']:s for s in TL['segments']};DUR=TL['duration']
MUSIC=ROOT/'../../music/dayfox-antalya-beaches-119047.mp3'
rng=np.random.default_rng(11)
def wt(i,k):return SEG[i]['at']+SEG[i]['words'][k][0]
def env(n,a,d):
    t=np.arange(n)/SR;return np.minimum(1,t/max(a,1e-4))*np.exp(-np.maximum(0,t-a)/d)
def lp(x,fc):
    # one-pole low-pass, vectorised through cumulative filtering in blocks
    a=np.exp(-2*np.pi*fc/SR);y=np.empty_like(x);acc=0.0
    for i in range(len(x)):acc=a*acc+(1-a)*x[i];y[i]=acc
    return y
def whoosh(d=.5,f0=500,f1=3500):
    n=int(d*SR);x=rng.normal(0,1,n);t=np.arange(n)/SR
    # band noise swept by ring-modulating low-passed noise with a rising sine
    base=lp(x,900);f=f0+(f1-f0)*(t/d)**1.5;car=np.sin(2*np.pi*np.cumsum(f)/SR)
    w=np.sin(np.pi*t/d)**2;return base*car*w*3.2
def tick():
    n=int(.05*SR);t=np.arange(n)/SR;return np.sin(2*np.pi*2100*t)*np.exp(-t/.008)*.6+rng.normal(0,1,n)*np.exp(-t/.003)*.15
def pop(f=520):
    n=int(.16*SR);t=np.arange(n)/SR;fr=f*(1+1.2*np.exp(-t/.02));return np.sin(2*np.pi*np.cumsum(fr)/SR)*np.exp(-t/.045)*.8
def thump():
    n=int(.5*SR);t=np.arange(n)/SR;fr=46+90*np.exp(-t/.035);return np.sin(2*np.pi*np.cumsum(fr)/SR)*np.exp(-t/.14)
def chime(notes=(880,1318.5),gap=.11):
    n=int(1.6*SR);y=np.zeros(n);t=np.arange(n)/SR
    for k,f in enumerate(notes):
        s=int(k*gap*SR);tt=t[:n-s];y[s:]+=(np.sin(2*np.pi*f*tt)+.35*np.sin(2*np.pi*2*f*tt)+.12*np.sin(2*np.pi*3.01*f*tt))*np.exp(-tt/.38)*np.minimum(1,tt/.004)
    return y*.4
def riser(d=1.2):
    n=int(d*SR);t=np.arange(n)/SR;x=lp(rng.normal(0,1,n),2500);f=300+2600*(t/d)**2
    return x*np.sin(2*np.pi*np.cumsum(f)/SR)*(t/d)**2*3
def shimmer():
    n=int(1.0*SR);t=np.arange(n)/SR;y=sum(np.sin(2*np.pi*f*t)*np.exp(-t/.3) for f in (1760,2637,3520))/3
    return y*np.minimum(1,t/.01)*.35

S=SEG
# (time, sound, gain dB, pan -1..1)
EV=[
 (.02,thump(),-7,0),(wt('s1',4),tick(),-12,.2),
 (S['s2']['start']-.3,whoosh(.6),-10,0),
 (wt('s2',3)-.1,pop(430),-12,.4),(wt('s2',4)-.1,pop(480),-12,0),(wt('s2',7)-.1,pop(540),-12,-.4),
 (wt('s2',9)-.35,whoosh(.45,400,2200),-13,0),
 (wt('s3',0)-.05,thump(),-6,0),
 (wt('s3',4)-.55,whoosh(.7,300,4200),-8,0),(wt('s3',4)+.25,pop(660),-11,0),(wt('s3',5)+.2,chime(),-10,0),
 (S['s4']['start']-.3,whoosh(.6),-11,0),(wt('s4',6)+.1,tick(),-10,-.3),
 (wt('s4',8)-.3,whoosh(.45,400,2400),-13,.3),(wt('s4',11)+.3,chime((1046.5,1568)),-15,0),
 (S['s5']['start']+.02,whoosh(.4,400,2000),-14,0),(wt('s5',4)-.05,thump(),-9,0),
 (wt('s5',6)-.3,whoosh(.5,500,3000),-13,0),
 (wt('s5',8),tick(),-10,.3),(wt('s5',9),tick(),-10,.1),(wt('s5',10),tick(),-10,-.1),
 (wt('s5',12)-.2,whoosh(.35,500,2200),-15,0),(wt('s5',12)+.4,pop(700),-14,0),
 (wt('s5',17)-.2,whoosh(.35,500,2200),-15,0),(wt('s5',20)+.1,chime((1046.5,1568)),-14,0),
 (S['s6']['start'],whoosh(.5),-12,-.3),
 (wt('s6',4),tick(),-11,.3),(wt('s6',6),tick(),-11,.2),(wt('s6',7),tick(),-11,.1),
 (wt('s6',8)-.1,whoosh(.5,400,3200),-13,0),(wt('s6',8)+.62,pop(760),-10,-.2),
 (S['s7']['start'],whoosh(.5),-12,.3),(wt('s7',3),tick(),-11,0),
 (wt('s7',4)-.2,whoosh(.45,400,2400),-13,0),(wt('s7',5),tick(),-8,-.2),(wt('s7',5)+.45,chime((1046.5,1568)),-13,0),
 (wt('s7',12)-.2,whoosh(.45,400,2400),-13,0),(wt('s7',14),pop(700),-13,.3),
 (S['s8']['start']-1.2,riser(1.2),-13,0),(S['s8']['start'],thump(),-4,0),
 (wt('s8',6)-.15,whoosh(.6,300,4200),-8,0),(wt('s8',6)+1.25,chime((1318.5,1760,2093)),-8,0),
 (wt('s8',8)-.3,whoosh(.45,400,2400),-13,0),(wt('s8',12),tick(),-10,0),
 (S['s9']['start']-.1,whoosh(.7,300,3600),-9,0),(wt('s9',0)+.35,pop(660),-11,0),
 (wt('s9',2),tick(),-8,.4),(wt('s9',3),tick(),-8,0),(wt('s9',4),pop(820),-8,-.4),(wt('s9',4)+.05,shimmer(),-12,0),
 (wt('s9',5)-.4,whoosh(.5,400,3000),-11,0),(wt('s9',10)+.7,pop(600),-11,0),(wt('s9',10)+1.1,chime(),-9,0),
]
def render_sfx():
    n=int(DUR*SR);y=np.zeros((n,2),np.float32)
    for t,x,g,pan in EV:
        a=int(max(0,t)*SR);x=x[:max(0,n-a)]*10**(g/20);l=np.sqrt((1-pan)/2);r=np.sqrt((1+pan)/2)
        y[a:a+len(x),0]+=x*l*1.414;y[a:a+len(x),1]+=x*r*1.414
    with wave.open(str(B/'sfx.wav'),'wb') as w:w.setnchannels(2);w.setsampwidth(2);w.setframerate(SR);w.writeframes((np.clip(y,-1,1)*32767).astype(np.int16).tobytes())
def run(args):
    p=subprocess.run(['ffmpeg','-hide_banner','-nostdin','-y',*args],capture_output=True,text=True)
    if p.returncode:print(p.stderr[-3000:]);p.check_returncode()
    return p.stderr
def main():
    render_sfx()
    off=TL['music_offset'];delay=max(0,-off);start=max(0,off);fade=DUR-3.2
    # voice: gentle clean-up and level; music: ducked by the voice (sidechain), held lower through the louder chorus
    # (from scene s8), faded out under the end card; effects sit under the voice too
    filt=(f"[0:a]highpass=f=75,equalizer=f=220:t=q:w=1:g=-2,equalizer=f=4200:t=q:w=1.2:g=2.5,acompressor=threshold=-20dB:ratio=3:attack=8:release=140:makeup=3,"
          f"aformat=sample_rates=48000:channel_layouts=stereo,asplit=2[v][vk];"
          f"[1:a]atrim=start={start}:duration={DUR},asetpts=PTS-STARTPTS,adelay={int(delay*1000)}:all=1,aformat=sample_rates=48000:channel_layouts=stereo,"
          f"volume=volume='if(lt(t,{S['s8']['start']-.05}),0.33,0.125)':eval=frame,afade=t=in:st={delay}:d=1.2,afade=t=out:st={fade}:d=2.5[m];"
          f"[vk]asplit=2[vk1][vk2];[m][vk1]sidechaincompress=threshold=0.02:ratio=8:attack=20:release=380:makeup=1[md];"
          f"[2:a]volume=-6dB[fx0];[fx0][vk2]sidechaincompress=threshold=0.05:ratio=3:attack=10:release=200:makeup=1[fx];"
          f"[v][md][fx]amix=inputs=3:normalize=0:duration=first,loudnorm=I=-14:TP=-1.5:LRA=9,alimiter=limit=0.84:level=false[a]")
    run(['-i',str(B/'vo.wav'),'-i',str(MUSIC),'-i',str(B/'sfx.wav'),'-filter_complex',filt,'-map','[a]','-t',f'{DUR:.3f}','-ar','48000','-c:a','pcm_s16le',str(B/'mix.wav')])
    report(B/'mix.wav')
    # No-voiceover version (owner, 2026-11-13), for feeds that autoplay muted or where the voice is not wanted: the same
    # music and effects with nothing to duck under, the music at one steady level, the on-screen type carrying the message.
    # (single-pass loudnorm lands about 1 dB hot on music alone, hence the trim to -14 LUFS.)
    nv=(f"[0:a]atrim=start={start}:duration={DUR},asetpts=PTS-STARTPTS,adelay={int(delay*1000)}:all=1,aformat=sample_rates=48000:channel_layouts=stereo,"
        f"volume=0.5,afade=t=in:st={delay}:d=1.2,afade=t=out:st={fade}:d=2.5[m];[1:a]volume=-4dB[fx];"
        f"[m][fx]amix=inputs=2:normalize=0:duration=first,loudnorm=I=-14:TP=-1.5:LRA=9,volume=-1.1dB,alimiter=limit=0.84:level=false[a]")
    run(['-i',str(MUSIC),'-i',str(B/'sfx.wav'),'-filter_complex',nv,'-map','[a]','-t',f'{DUR:.3f}','-ar','48000','-c:a','pcm_s16le',str(B/'mix-novo.wav')])
    report(B/'mix-novo.wav')
def report(p):
    out=run(['-i',str(p),'-af','ebur128=peak=true','-f','null','-'])
    s=out[out.rfind('Summary:'):];print(p.name,re.search(r'I:\s*(-?[\d.]+) LUFS',s)[0],re.search(r'Peak:\s*(-?[\d.]+) dBFS',s)[0])
if __name__=='__main__':main()
