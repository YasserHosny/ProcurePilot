from paths import *
import json,subprocess,hashlib
summary=[]
for lang,sz in [('ar','16x9'),('en','16x9'),('ar','9x16-60s'),('en','9x16-60s')]:
 tag=f'{lang}-{sz}';path=ROOT/f'procurepilot-demo-{tag}.mp4'
 r=subprocess.run([str(FF),'-hide_banner','-i',str(path)],capture_output=True,text=True)
 (ROOT/'analysis'/f'ffmpeg-info-{tag}.log').write_text(r.stderr)
 assert 'Video: h264' in r.stderr and 'yuv420p' in r.stderr and '30 fps' in r.stderr and 'Audio: aac' in r.stderr,tag
 q=json.loads((ROOT/'analysis'/f'qa-{tag}.json').read_text());m=json.loads((ROOT/'analysis'/f'output-mask-check-{tag}.json').read_text());assert m['passed'],tag
 assert float(q['loudnorm']['input_tp'])<=-1,tag
 assert abs(float(q['loudnorm']['input_i'])+14)<.5,tag
 assert q['duration']<=60 if '9x16' in sz else q['duration']<=180
 summary.append({'file':path.name,'duration':q['duration'],'integrated_lufs':q['loudnorm']['input_i'],'true_peak_dbtp':q['loudnorm']['input_tp'],'proof_frames':len(q['proof_frames']),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
coverage=json.loads((ROOT/'analysis/mask-coverage.json').read_text());assert not coverage['errors']
for copy in (ROOT/'reference').iterdir():
 original=REF/'source/edit'/copy.name
 assert hashlib.sha256(copy.read_bytes()).digest()==hashlib.sha256(original.read_bytes()).digest(),copy.name
(ROOT/'MEASUREMENTS.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary,indent=2))
