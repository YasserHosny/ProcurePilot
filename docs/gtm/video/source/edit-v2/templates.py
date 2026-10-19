import sys
from paths import *
sys.path.insert(0,str(ROOT/'deps'))
from PIL import Image,ImageDraw
jobs=[('s2b-photo-closeup-4', (800,108,946,216)),('s3-guardrail-draft-5',(1045,838,1280,863)),('s4-phone-approve-9',(30,230,305,253))]
for name,box in jobs:
 im=Image.open(ROOT/'analysis'/f'{name}.png');c=im.crop(box);c.resize((c.width*4,c.height*4)).save(ROOT/'analysis'/f'template-{name}.png')
