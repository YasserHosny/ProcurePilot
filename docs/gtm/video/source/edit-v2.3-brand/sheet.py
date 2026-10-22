import sys,glob
from PIL import Image, ImageDraw
fs=sorted(glob.glob(sys.argv[1]+'/*.jpg')); cols=int(sys.argv[3]) if len(sys.argv)>3 else 3
ims=[Image.open(f) for f in fs]; w,h=ims[0].size; tw=640 if w>h else 360; th=int(h*tw/w)
rows=(len(ims)+cols-1)//cols; c=Image.new('RGB',(cols*tw,rows*th),'red')
for i,(f,im) in enumerate(zip(fs,ims)):
    im=im.resize((tw,th)); d=ImageDraw.Draw(im); d.text((6,4),f.split('/')[-1],fill='red'); c.paste(im,((i%cols)*tw,(i//cols)*th))
c.save(sys.argv[2],quality=88)
