import sys
B=sys.argv[1]
pairs=[('عروض الأسعار على الواتساب…','Quotes on WhatsApp…'),('ونسخ يدوي في إكسل.','copied into Excel by hand.'),
('إنت بتشتري كده كده —','You’re buying anyway —'),('إحنا بنوريك بتوفّر قد إيه.','we show you what you save.'),
('طلب عرض سعر واحد…','One request for quotes…'),('لكل الموردين مرة واحدة.','to every supplier at once.'),
('العروض توصل وتتقري لوحدها','Quotes arrive and read themselves'),('بالجنيه المصري.','in Egyptian pounds.'),
('مقارنة بند بند…','Line-by-line comparison…'),('والوفر قدامك.','and the saving in front of you.'),
('المدير يوافق','The manager approves'),('من موبايله.','from their phone.'),
('وأمر الشراء','And the purchase order'),('يطلع جاهز.','comes out ready.')]
def ltr(s):
    s=s.replace('lang="ar" dir="rtl"','lang="en" dir="ltr"').replace('dir="rtl"','dir="ltr"').replace('transform-origin:100% 50%','transform-origin:0% 50%')
    return s
for size in ['16x9','9x16']:
    s=open(f'{B}/SceneCards{size}.html').read()
    for a,b in pairs:
        assert a in s,(size,a); s=s.replace(a,b)
    open(f'{B}/SceneCardsEn{size}.html','w').write(ltr(s))
    n=open(f'{B}/NotificationCard{size}.html').read()
    for a,b in [('طلب شراء محتاج موافقتك','A purchase request needs your approval'),('فرع المعادي · زيت، أرز، بصل · ٢٥٬١٤٠ ج.م','Maadi branch · oil, rice, onions · EGP 25,140'),('<span>الآن</span>','<span>now</span>'),('وصل إشعار <span style="color:#19B8A4">للمدير</span>','The <span style="color:#19B8A4">manager</span> is notified')]:
        assert a in n,(size,a); n=n.replace(a,b)
    open(f'{B}/NotificationCardEn{size}.html','w').write(ltr(n))
    c=open(f'{B}/SavingsCounter{size}.html').read()
    for a,b in [('وفّرت في الطلب ده','You saved on this order'),('من تقرير التوفير — بالأرقام الحقيقية','From the savings report — real numbers'),('>ج.م<','>EGP<'),('.sv-num.sv-small::before{content:counter(r,arabic-indic)}','.sv-num.sv-small::before{content:counter(r)}')]:
        assert a in c,(size,a); c=c.replace(a,b)
    open(f'{B}/SavingsCounterEn{size}.html','w').write(ltr(c))
print('ok')
