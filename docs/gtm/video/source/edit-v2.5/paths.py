"""Shared paths for the v2.5 build. Plates are each v1 fork's masked plates (plates-<market> links)."""
from pathlib import Path
ROOT=Path(__file__).resolve().parent
FF='/home/yasserhosny/Work/pp-video-env/lib/python3.12/site-packages/imageio_ffmpeg/binaries/ffmpeg-linux-x86_64-v7.0.2'

def jobs(timeline,only=None):
    """(market, lang, fmt) for every cut, optionally filtered by 'eg-ar-h,ie-en-v'."""
    out=[(m,l,f) for m,t in timeline.items() for f in 'hv' for l in t[f]['langs']]
    return [j for j in out if not only or '-'.join(j) in only.split(',')]
