"""Offline body music + original outro audio, gain matched and limited before encoding."""
from privacy import ROOT,FF
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
    timeline=json.loads((ROOT/'timeline.json').read_text())
    for lang in ['en']:
        for fmt,offset in [('h',0),('v',120)]:
            body=timeline[fmt]['body'];total=body+timeline[fmt]['outro']
            if args.only and f'{lang}-{fmt}' not in args.only.split(','):continue
            suffix='' if lang=='ar' else '-en';aspect='16x9' if fmt=='h' else '9x16'
            outro=ROOT/'../../renders'/('outro-'+aspect+suffix+'.mp4')
            dst=ROOT/'audio'/f'{lang}-{fmt}.wav'
            filt=(f'[0:a]atrim=start={offset}:duration={body},asetpts=PTS-STARTPTS,volume=-6.6dB,afade=t=in:st=0:d=0.5,aformat=sample_rates=48000:channel_layouts=stereo[m];'
                  '[1:a]asetpts=PTS-STARTPTS,aformat=sample_rates=48000:channel_layouts=stereo[o];'
                  '[m][o]concat=n=2:v=0:a=1,alimiter=limit=0.707945784:level=false:latency=true[a]')
            run(['-i',str(ROOT/'../../music/dayfox-antalya-beaches-119047.mp3'),'-i',str(outro),'-filter_complex',filt,'-map','[a]','-c:a','pcm_s24le',str(dst)],f'audio-{lang}-{fmt}-build.log')
            report[f'{lang}-{fmt}']={'pcm':measure(dst),'nominal_total_seconds':total}
            with wave.open(str(dst)) as w:report[f'{lang}-{fmt}']['pcm']['duration_seconds']=w.getnframes()/w.getframerate()
            aac=dst.with_suffix('.m4a')
            run(['-i',str(dst),'-c:a','aac','-b:a','256k',str(aac)],f'audio-{lang}-{fmt}-aac.log')
            report[f'{lang}-{fmt}']['aac']=measure(aac)
            assert report[f'{lang}-{fmt}']['aac']['true_peak_dbfs']<=-2
            assert abs(report[f'{lang}-{fmt}']['aac']['integrated_lufs']+14)<=1
    (ROOT/'proof/audio.json').write_text(json.dumps(report,indent=2)+'\n')
if __name__=='__main__':main()
