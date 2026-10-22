# Builds tex/: paper grain, navy-duotone halftone photos (round-4 quote photos, one kitchen still) and the paper quotes.
# Inputs: ../../../demo-tenant/round-4/quotes (photos + PDFs rendered with pdftoppm) and plates/kitchen from extract.py.
import os, subprocess, numpy as np
from PIL import Image, ImageFilter, ImageOps, ImageEnhance
H=os.path.dirname(os.path.abspath(__file__)); Q=os.path.join(H,'../../../demo-tenant/round-4/quotes'); T=os.path.join(H,'tex'); os.makedirs(T,exist_ok=True)
rng=np.random.default_rng(7)
for i in range(4):
    n=rng.normal(0,14,(1920,1920))
    m=np.asarray(Image.fromarray((rng.normal(128,40,(120,120))).clip(0,255).astype(np.uint8)).resize((1920,1920),Image.BICUBIC)).astype(float)-128
    Image.fromarray((128+n+m*0.12).clip(0,255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(0.6)).save(f'{T}/grain{i}.png')
def halftone(img,period,mix):
    g=np.asarray(img).astype(float)/255; Hh,W=g.shape; yy,xx=np.mgrid[0:Hh,0:W]; a=np.deg2rad(45)
    u=(xx*np.cos(a)+yy*np.sin(a))/period; v=(-xx*np.sin(a)+yy*np.cos(a))/period
    d=np.sqrt((u-np.round(u))**2+(v-np.round(v))**2)/0.7071
    small=np.asarray(img.resize((W//period+1,Hh//period+1),Image.BILINEAR).resize((W,Hh),Image.BILINEAR)).astype(float)/255
    dots=(d>np.sqrt(1-small)).astype(float); return Image.fromarray(((g*(1-mix)+dots*mix*np.clip(g*1.2,0,1)).clip(0,1)*255).astype(np.uint8))
NAVY=np.array([11,37,69])/255
def duo(a,lo=1.0):
    # brand duotone: black -> navy, white -> white (lo<1 lightens the darks for paper quotes)
    a=a[...,None]; n=1-(1-NAVY)*lo
    return ((n+(1-n)*a).clip(0,1)*255).astype(np.uint8)
def photo(src,dst,crop,contrast=1.15,bright=1.0,period=6,mix=0.22):
    im=Image.open(src).convert('RGB').crop(crop); im.thumbnail((1600,1600))
    g=ImageEnhance.Brightness(ImageEnhance.Contrast(ImageOps.grayscale(im)).enhance(contrast)).enhance(bright)
    a=np.asarray(halftone(g,period,mix)).astype(float)/255
    Image.fromarray(duo(a)).save(dst,quality=93)
photo(f'{Q}/IMG-20261019-WA0011.jpg',f'{T}/wa11.jpg',(150,140,1080,1520))
photo(f'{Q}/IMG-20261019-WA0007.jpg',f'{T}/wa7.jpg',(150,140,1080,1520))
photo(os.path.join(H,'plates/kitchen/0040.jpg'),f'{T}/kitchen.jpg',(560,170,1420,880),1.25,1.15,5)
for n,pdf in [('nour','عرض سعر النور NR-26-0419.pdf'),('sayed','عرض سعر الحاج سيد QS-2026-1073.pdf')]:
    subprocess.run(['pdftoppm','-r','110','-png','-f','1','-l','1',f'{Q}/{pdf}',f'{T}/{n}-raw'],check=True)
    a=np.asarray(Image.open(f'{T}/{n}-raw-1.png').convert('L').crop((0,0,909,560))).astype(float)/255
    Image.fromarray(duo(a)).save(f'{T}/{n}.png'); os.remove(f'{T}/{n}-raw-1.png')
