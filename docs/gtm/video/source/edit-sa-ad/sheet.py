import sys,glob
from PIL import Image
d,out,cols=sys.argv[1],sys.argv[2],int(sys.argv[3]);tw=int(sys.argv[4])
fs=sorted(glob.glob(d+'/*.jpg'));im=[Image.open(f) for f in fs];th=tw*im[0].height//im[0].width
rows=(len(im)+cols-1)//cols;sh=Image.new('RGB',(tw*cols,th*rows))
for i,x in enumerate(im):sh.paste(x.resize((tw,th)),((i%cols)*tw,(i//cols)*th))
sh.save(out,quality=88)
