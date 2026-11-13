"""Split the one-take ElevenLabs voiceover (vo/elevenlabs-full.mp3) into the nine lines and estimate word timings.
The engine returns no timings, so phrase boundaries come from the measured pauses in the take (PHRASES below,
seconds in the full file, checked against the script's punctuation), and words inside a phrase are spread by
their relative lengths in REF (word durations from the earlier neural take of the same text)."""
import json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parent
SOURCE={'s7':'vo/elevenlabs-line7.mp3'}  # every other line is cut from vo/elevenlabs-full.mp3
# line -> [(phrase start, phrase end, number of words)]
PHRASES={
 's1':[(0.04,1.78,5),(2.14,2.88,3)],
 's2':[(3.42,5.38,4),(5.64,6.32,3),(6.56,7.46,2),(8.08,10.12,6),(10.38,12.24,5)],
 's3':[(12.76,13.42,1),(13.58,14.72,3),(15.30,16.24,2),(16.60,17.54,3),(17.70,19.00,3)],
 's4':[(19.40,22.62,8),(22.92,23.88,2),(24.02,25.36,3)],
 's5':[(25.90,27.34,4),(27.72,28.48,2),(28.88,32.06,6),(32.30,33.00,3),(33.16,33.86,2),(34.40,36.04,4)],
 's6':[(36.54,37.96,4),(38.22,38.94,1),(39.12,40.60,3),(41.08,42.86,5)],
 # line 7 was regenerated on its own with vowel marks on «الطلب يتجهّز لك مسودة» (owner: mispronounced in the full take)
 's7':[(0.14,2.14,4),(2.54,6.18,8),(6.80,7.66,2),(7.82,9.76,4)],
 's8':[(52.98,54.78,4),(55.22,55.96,2),(56.36,57.54,2),(58.00,59.26,3),(59.60,60.94,2)],
 's9':[(61.26,62.30,2),(62.68,63.08,1),(63.42,63.98,1),(64.24,64.72,1),(65.18,66.68,3),(67.02,68.12,3)],  # «راسلنا واتساب اليوم» (68.68-69.76) dropped at the owner's request
}
def main():
    ref={r['id']:r['words'] for r in json.loads((ROOT/'vo/reference-word-lengths.json').read_text())}
    out=[]
    for sid,phr in PHRASES.items():
        words=ref[sid][:sum(p[2] for p in phr)] if sid=='s9' else ref[sid];assert sum(p[2] for p in phr)==len(words),sid
        t0=max(0,phr[0][0]-.08);t1=phr[-1][1]+.22;res=[];k=0
        for a,b,n in phr:
            ws=words[k:k+n];tot=sum(w[1] for w in ws);t=a
            for w in ws:
                d=(b-a)*w[1]/tot;res.append([round(t-t0,3),round(d,3),w[2]]);t+=d
            k+=n
        subprocess.run(['ffmpeg','-v','error','-y','-ss',f'{t0:.3f}','-to',f'{t1:.3f}','-i',str(ROOT/SOURCE.get(sid,'vo/elevenlabs-full.mp3')),
                        '-af','afade=t=in:d=0.03,areverse,afade=t=in:d=0.08,areverse','-c:a','libmp3lame','-b:a','192k',str(ROOT/'vo'/(sid+'.mp3'))],check=True)
        out.append({'id':sid,'dur':round(t1-t0,3),'words':res})
    (ROOT/'vo/raw-timing.json').write_text(json.dumps(out,ensure_ascii=False,indent=1)+'\n')
    for o in out:print(o['id'],o['dur'],len(o['words']))
if __name__=='__main__':main()
