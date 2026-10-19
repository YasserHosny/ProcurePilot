"""Last editorial fixes: stronger vertical phone crops and a PO evidence hold.
Only v2 segment caches are invalidated. Bodies/outros then mux without video re-encode.
"""
from paths import *
from build_v2 import build
import concurrent.futures
for tag,indices in [('ar',(18,)),('en',(18,)),('ar-v',(1,2,9,10,14)),('en-v',(1,2,9,10,14))]:
 for i in indices:
  p=ROOT/'segments'/tag/f'{i:02}.mp4'
  if p.exists():p.unlink()
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(lambda x:build(*x),[('ar',False),('en',False),('ar',True),('en',True)]))
