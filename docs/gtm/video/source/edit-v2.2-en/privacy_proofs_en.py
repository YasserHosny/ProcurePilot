from inspect_en import *
import json
samples={'s2-quote-photo':[6.2,6.4,6.6,7,7.5,8,12,20,23.5,24,24.5,25,25.5,26,28.5,30.6,31,31.5,32,32.5,33.1], 's2b-photo-closeup':[0,.5,1.7,2,2.5,3,3.5,4,4.5,8,12,15.5,16,16.5], 's4-phone-approve':[3.9,4.1,4.5,5.5,6.5,6.8,7,7.2,7.5,8,12,15.5,16,16.4,16.6]}
for name,times in samples.items():
 for t in times:
  for kind,base in [('raw',SOURCE),('masked',ROOT/'masked-en')]:
   frame(base/(name+'.mp4'),t).save(ROOT/'qa-en/privacy'/f'{name}-{t:06.3f}-{kind}.png')
 # Masked overview samples, exact native proof PNGs retained separately.
 sheet(ROOT/'masked-en'/(name+'.mp4'),times,ROOT/'qa-en/privacy'/f'{name}-proof-sheet.jpg',tw=480,th=310 if 'phone' not in name else 1050)
(ROOT/'qa-en/privacy/proof-times.json').write_text(json.dumps(samples,indent=2))
