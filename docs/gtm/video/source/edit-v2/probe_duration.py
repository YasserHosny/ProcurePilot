"""Exact MP4 movie-header duration fallback; ffprobe is not installed in this sandbox."""
import struct
from pathlib import Path
def atoms(f,start,end):
 pos=start
 while pos+8<=end:
  f.seek(pos);size,typ=struct.unpack('>I4s',f.read(8));hdr=8
  if size==1:size=struct.unpack('>Q',f.read(8))[0];hdr=16
  if size==0:size=end-pos
  yield typ,pos+hdr,pos+size
  pos+=size

def duration(path):
 with open(path,'rb') as f:
  for typ,a,b in atoms(f,0,Path(path).stat().st_size):
   if typ!=b'moov':continue
   for typ2,c,d in atoms(f,a,b):
    if typ2==b'mvhd':
     f.seek(c);v=f.read(1)[0];f.seek(c+(20 if v else 12));ts=struct.unpack('>I',f.read(4))[0];n=struct.unpack('>Q' if v else '>I',f.read(8 if v else 4))[0];return n/ts
if __name__=='__main__':
 import sys
 for p in sys.argv[1:]:print(p,duration(p))
