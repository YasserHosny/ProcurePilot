from paths import *
import subprocess
for name,times in {'s2-quote-photo':[8,23,26],'s2b-photo-closeup':[0,4,10,18],'s3-guardrail-draft':[5,10],'s4-phone-approve':[6,9],'s5-po-savings':[30,35,41],'s6-savings-close':[10]}.items():
 for t in times:
  subprocess.run([str(FF),'-y','-loglevel','error','-ss',str(t),'-i',str(RAW/f'{name}.mp4'),'-frames:v','1',str(ROOT/'analysis'/f'{name}-{t}.png')],check=True)
