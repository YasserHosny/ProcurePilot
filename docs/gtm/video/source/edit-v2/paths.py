"""Where the v2 build finds its inputs. Override any of these with environment variables."""
from pathlib import Path
import os

ROOT = Path(__file__).resolve().parent
# Holds the vid/ virtualenv with imageio-ffmpeg (PP_FFMPEG overrides the binary itself).
S = Path(os.environ.get('PP_VIDEO_WORK', ROOT))
# ffmpeg 7 with libx264 (imageio-ffmpeg's static build has no drawtext, which v2 does not need).
FF = Path(os.environ.get('PP_FFMPEG', S / 'vid/lib/python3.12/site-packages/imageio_ffmpeg/binaries/ffmpeg-linux-x86_64-v7.0.2'))
# The raw screen recordings (not in git until the owner's email is masked at source).
RAW = Path(os.environ.get('PP_RAW', Path.home() / 'Videos/pp-recording'))
# docs/gtm/video in a checkout: music/ and source/stock/ come from fetch-assets.sh.
ASSETS = Path(os.environ.get('PP_VIDEO_DOCS', ROOT.parent.parent))
REF = Path(os.environ.get('PP_VIDEO_REF', ASSETS))
