# v2.5 (from v2.3): builds tex/ (grain) and tex/<market>/ for the opening problem scene: paper grain, navy-duotone halftone photos (round-4 quote photos, one kitchen still) and the paper quotes.
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
def photo_rel(src,dst,frac=(.125,.0875,.9,.95)):
    w,h=Image.open(src).size; photo(src,dst,(int(frac[0]*w),int(frac[1]*h),int(frac[2]*w),int(frac[3]*h)))
def paper(pdf,dst):
    subprocess.run(['pdftoppm','-r','110','-png','-f','1','-l','1',pdf,f'{dst}-raw'],check=True)
    a=np.asarray(Image.open(f'{dst}-raw-1.png').convert('L').crop((0,0,909,560))).astype(float)/255
    Image.fromarray(duo(a)).save(f'{dst}.png'); os.remove(f'{dst}-raw-1.png')
# Each market's problem scene uses its own recorded rounds' quotes: two PDFs and two WhatsApp photos.
G=os.path.join(H,'../../../gcc/setup/quotes')
MARKETS={
 'eg':([f'{Q}/عرض سعر النور NR-26-0419.pdf',f'{Q}/عرض سعر الحاج سيد QS-2026-1073.pdf'],[f'{Q}/IMG-20261019-WA0011.jpg',f'{Q}/IMG-20261019-WA0007.jpg']),
 'sa':([f'{G}/round-A/عرض سعر الوفرة WF-2026-0731.pdf',f'{G}/round-A/عرض سعر خضار القصيم QS-5540.pdf'],[f'{G}/round-A/IMG-20261025-WA0035.jpg',f'{G}/round-D/IMG-20261025-WA0031.jpg']),
 'sa-en':([f'{G}/sa-en-round-E/Red Sea Food Trading quote RS-2026-0342.pdf',f'{G}/sa-en-round-E/Qassim Fresh Produce quote QF-7756.pdf'],[f'{G}/sa-en-round-E/IMG-20261025-WA0071.jpg',f'{G}/sa-en-round-D/IMG-20261025-WA0062.jpg']),
 'ie':([f'{G}/ie-round-E/Atlantic Fresh Foods Ltd quote AFF-2026-0748.pdf',f'{G}/ie-round-E/Kerrigan Farm Produce quote KFP-5557.pdf'],[f'{G}/ie-round-E/IMG-20261025-WA0081.jpg',f'{G}/ie-round-D/IMG-20261025-WA0061.jpg']),
}
for m,(pdfs,photos) in MARKETS.items():
    d=os.path.join(T,m); os.makedirs(d,exist_ok=True)
    for i,pdf in enumerate(pdfs,1): paper(pdf,f'{d}/paper{i}')
    for i,src in enumerate(photos,1): photo_rel(src,f'{d}/photo{i}.jpg')
