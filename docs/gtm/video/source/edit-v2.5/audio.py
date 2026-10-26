"""Offline body music + original outro audio, gain matched and limited before encoding."""
from paths import ROOT,FF,jobs
import subprocess,json,re,wave

def run(cmd,log):
    p=subprocess.run([FF,'-hide_banner','-nostdin','-y',*cmd],capture_output=True,text=True)
    (ROOT/'proof'/log).write_text(p.stderr);p.check_returncode();return p.stderr

def measure(p):
    text=run(['-i',str(p),'-af','ebur128=peak=true','-f','null','-'],p.name+'-ebur128.log')
    summary=text[text.rfind('Summary:'):].split('[out#')[0].strip()
    print(p.name,summary.strip(),flush=True)
    i=re.search(r'I:\s*(-?[\d.]+) LUFS',summary);tp=re.search(r'Peak:\s*(-?[\d.]+) dBFS',summary)
    duration=re.search(r'Duration: ([^,\n]+)',text)
    return {'integrated_lufs':float(i[1]),'true_peak_dbfs':float(tp[1]),'container_duration':duration[1] if duration else None,'summary':summary.strip()}

def main():
    (ROOT/'proof').mkdir(exist_ok=True);(ROOT/'audio').mkdir(exist_ok=True)
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--only');args=parser.parse_args()
    report=json.loads((ROOT/'proof/audio.json').read_text()) if args.only and (ROOT/'proof/audio.json').exists() else {}
    markets=json.loads((ROOT/'timeline.json').read_text())
    for market,lang,fmt in jobs(markets,args.only):
            key=f'{market}-{lang}-{fmt}';offset=0 if fmt=='h' else 120
            body=markets[market][fmt]['body'];total=body+markets[market][fmt]['outro']
            suffix='' if lang=='ar' else '-en';aspect='16x9' if fmt=='h' else '9x16'
            outro=ROOT/'../../renders'/('outro-'+aspect+suffix+'.mp4')
            dst=ROOT/'audio'/f'{key}.wav'
            # v2.5 (owner, 2026-10-27): crossfade the body music into the outro instead of a hard cut.
            # The body music runs XF seconds longer and overlaps the outro's start, so the total stays body+outro.
            XF=1.5
            filt=(f'[0:a]atrim=start={offset}:duration={body+XF},asetpts=PTS-STARTPTS,volume=-6.6dB,afade=t=in:st=0:d=0.5,aformat=sample_rates=48000:channel_layouts=stereo[m];'
                  '[1:a]asetpts=PTS-STARTPTS,aformat=sample_rates=48000:channel_layouts=stereo[o];'
                  f'[m][o]acrossfade=d={XF}:c1=qsin:c2=qsin,alimiter=limit=0.707945784:level=false:latency=true[a]')
            run(['-i',str(ROOT/'../../music/dayfox-antalya-beaches-119047.mp3'),'-i',str(outro),'-filter_complex',filt,'-map','[a]','-c:a','pcm_s24le',str(dst)],f'audio-{key}-build.log')
            report[key]={'pcm':measure(dst),'nominal_total_seconds':total}
            with wave.open(str(dst)) as w:report[key]['pcm']['duration_seconds']=w.getnframes()/w.getframerate()
            aac=dst.with_suffix('.m4a')
            run(['-i',str(dst),'-c:a','aac','-b:a','256k',str(aac)],f'audio-{key}-aac.log')
            report[key]['aac']=measure(aac)
            assert report[key]['aac']['true_peak_dbfs']<=-2
            assert abs(report[key]['aac']['integrated_lufs']+14)<=1
    (ROOT/'proof/audio.json').write_text(json.dumps(report,indent=2)+'\n')
if __name__=='__main__':main()
