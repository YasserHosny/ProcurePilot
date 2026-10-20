# Wait only for the initial render/QA readers, then replace outputs with final refinements.
from paths import *
import sys,time,subprocess
py=S/'vid/bin/python'
while True:
 b=(ROOT/'build.log').read_text()
 qs=[(ROOT/f'qa-{l}.log').read_text() for l in ('ar','en')]
 if b.count('FINISHED ')==4 and all('16x9' in q for q in qs):break
 time.sleep(5)
for script,log in [('final_refinements.py','refine.log'),('qa.py','qa-final.log'),('verify_output_masks.py','output-mask-check.log'),('verify_masks.py','mask-coverage.log'),('report.py','report.log')]:
 print('RUN',script,flush=True)
 with open(ROOT/log,'w') as f:subprocess.run([str(py),str(ROOT/script)],stdout=f,stderr=subprocess.STDOUT,check=True)
 print('DONE',script,flush=True)
