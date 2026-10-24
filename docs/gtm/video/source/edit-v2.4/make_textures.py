"""Paper grain only. v2.4 retains native full colour; no duotone photo assets."""
from privacy import ROOT
import numpy as np
from PIL import Image,ImageFilter
folder=ROOT/'tex';folder.mkdir(exist_ok=True);rng=np.random.default_rng(7)
for i in range(4):
    a=rng.normal(128,12,(1920,1920)).clip(0,255).astype(np.uint8)
    Image.fromarray(a).filter(ImageFilter.GaussianBlur(.6)).save(folder/f'grain{i}.png')
print('TEXTURES 4 deterministic paper-grain layers')
