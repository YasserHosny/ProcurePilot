from paths import *
import subprocess,re,json
results={}
for src in sorted(RAW.glob('*.mp4')):
 if src.stem.startswith('old'):continue
 r=subprocess.run([str(FF),'-hide_banner','-i',str(src),'-vf','showinfo','-fps_mode','passthrough','-f','null','-'],capture_output=True,text=True,check=True)
 (ROOT/'analysis'/(src.stem+'-pts.log')).write_text(r.stderr)
 pts=[float(x) for x in re.findall(r'pts_time:([0-9.]+)',r.stderr)]
 results[src.stem]=pts
(ROOT/'analysis'/'source-pts.json').write_text(json.dumps(results))
print({k:len(v) for k,v in results.items()})
