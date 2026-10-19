# Invalidate only v2 shots affected by the final phone / ledger reframing.
from paths import *
from build_v2 import build
import concurrent.futures
for tag in ('ar-v','en-v'):
 for i in (1,2,9,10,14):
  p=ROOT/'segments'/tag/f'{i:02}.mp4'
  if p.exists():p.unlink()
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(lambda lang:build(lang,True),['ar','en']))
