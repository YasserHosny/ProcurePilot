"""Build-time assets (all under build/, not committed): real demo quotes as paper cutouts, the Saudi opening
animation as frames, a grain tile, and the official logo SVGs inlined for the logo build."""
import subprocess,json
from pathlib import Path
import numpy as np
from PIL import Image
ROOT=Path(__file__).resolve().parent;B=ROOT/'build';Q=ROOT/'../../../gcc/setup/quotes/round-A';R=ROOT/'../../renders/sa'
(B/'tex').mkdir(parents=True,exist_ok=True)
Image.open(Q/'IMG-20261025-WA0035.jpg').convert('RGB').resize((900,1200)).save(B/'tex/photo.jpg',quality=90)
subprocess.run(['node',str(ROOT/'shoot_quotes.cjs'),str(Q),str(B/'tex')],check=True)
for fmt,name in (('h','16x9'),('v','9x16')):
    d=B/('open-'+fmt);d.mkdir(exist_ok=True)
    subprocess.run(['ffmpeg','-v','error','-y','-i',str(R/f'opening-anim-sa-{name}.mp4'),'-q:v','3',str(d/'%03d.jpg')],check=True)
    print(fmt,len(list(d.glob('*.jpg'))),'opening frames')
rng=np.random.default_rng(7);n=rng.normal(128,26,(512,512)).clip(0,255).astype(np.uint8)
Image.fromarray(n,'L').save(B/'tex/grain.png')
L=ROOT/'../../../../brand/logo'
logos={'dark':(L/'procurepilot-horizontal-dark.svg').read_text(),'light':(L/'procurepilot-horizontal.svg').read_text()}
counts={f:len(list((B/('open-'+f)).glob('*.jpg'))) for f in 'hv'}
(B/'assets.js').write_text('window.LOGOS='+json.dumps(logos)+';\nwindow.OPEN_FRAMES='+json.dumps(counts)+';\n')
