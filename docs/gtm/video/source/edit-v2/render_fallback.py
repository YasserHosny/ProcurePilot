# Pillow/Raqm fallback: sandbox denies Chrome socket shutdown on startup.
# The requested Playwright implementation is retained in render_cards_v2.cjs.
import sys,re,json
from paths import *
sys.path.insert(0,str(ROOT/'deps'))
from PIL import Image,ImageDraw,ImageFont
FONT='/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
BOLD='/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
content=(ROOT/'render_cards_v2.cjs').read_text();block=content.split('const text={')[1].split('\n};')[0]
texts={m[0]:[m[1],m[2]] for m in re.findall(r"(\w+):\['([^']*)','([^']*)'\]",block)}
def font(n,b=False):return ImageFont.truetype(BOLD if b else FONT,n)
def wrap(d,text,size,width,bold=False):
 words=text.split();out=[];line=''
 for w in words:
  s=(line+' '+w).strip()
  if d.textlength(s,font=font(size,bold))>width and line:out.append(line);line=w
  else:line=s
 if line:out.append(line)
 return out
for vertical in (False,True):
 W,H=(1080,1920) if vertical else (1920,1080)
 for lang in ('ar','en'):
  folder=ROOT/'graphics'/(lang+('-v' if vertical else ''));folder.mkdir(parents=True,exist_ok=True)
  for key,strings in texts.items():
   if len(sys.argv)>1 and (not vertical or key!='prices'):continue
   im=Image.new('RGBA',(W,H));d=ImageDraw.Draw(im);sz=42 if vertical else 38;pad=28 if vertical else 32;x=54 if vertical else 80;maxw=W-2*x-2*pad
   lines=wrap(d,strings[lang=='en'],sz,maxw,True);lineh=60 if lang=='ar' else 53;h=max(150 if vertical else 118,len(lines)*lineh+65);y=275 if vertical else H-28-h
   d.rounded_rectangle((x,y,W-x,y+h),radius=18,fill='#0b2545');d.rectangle((W-x-8 if lang=='ar' else x,y+18,W-x if lang=='ar' else x+8,y+h-18),fill='#19b8a4')
   ty=y+15
   for line in lines:
    d.text((W-x-pad if lang=='ar' else x+pad,ty),line,font=font(sz,True),fill='white',anchor='rt' if lang=='ar' else 'lt',direction='rtl' if lang=='ar' else 'ltr');ty+=lineh
   d.text((W-x-pad if lang=='ar' else x+pad,ty+3),'بيانات تجريبية · واجهة عربية' if lang=='ar' else 'Demo data · Arabic interface',font=font(24 if vertical else 22),fill='#9ce2d7',anchor='rt' if lang=='ar' else 'lt',direction='rtl' if lang=='ar' else 'ltr')
   im.save(folder/(key+'.png'))
  for f in range(0 if len(sys.argv)>1 else 31):
   im=Image.new('RGB',(W,H),'#0b2545');d=ImageDraw.Draw(im);cy=600 if vertical else 220
   d.text((W/2,cy),'وفّر الطلب ده' if lang=='ar' else 'This order saved',font=font(50,True),fill='white',anchor='mt',direction='rtl' if lang=='ar' else 'ltr')
   num=str(round(460*f/30));num=num.translate(str.maketrans('0123456789','٠١٢٣٤٥٦٧٨٩')) if lang=='ar' else num
   d.text((W/2,cy+130),num,font=font(170,True),fill='#28c6b2',anchor='mt')
   d.text((W/2,cy+330),'ج.م' if lang=='ar' else 'EGP',font=font(48,True),fill='white',anchor='mt')
   label='مقابل أسعار آخر أوامر شراء' if lang=='ar' else 'Compared with last purchase-order prices'
   ty=cy+430
   for line in wrap(d,label,38,W-120):
    d.text((W/2,ty),line,font=font(38),fill='white',anchor='mt',direction='rtl' if lang=='ar' else 'ltr');ty+=65
   sub='بيانات تجريبية · زيت +٢٤٠ · أرز +١٨٠ · بصل +٤٠' if lang=='ar' else 'Demo data · oil +240 · rice +180 · onions +40'
   for line in wrap(d,sub,26,W-120):
    d.text((W/2,ty+25),line,font=font(26),fill='#9ce2d7',anchor='mt',direction='rtl' if lang=='ar' else 'ltr');ty+=42
   im.save(folder/f'counter-{f:02}.png')
print('fallback graphics rendered',len(texts))
