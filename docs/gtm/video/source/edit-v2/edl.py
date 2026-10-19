# Rebuild EDL. Times in seconds. freeze adds a readable endpoint hold.
# Source masks are applied BEFORE all reframing, for the complete shot including holds.
from paths import *
def shot(src,a,b,d,cap,crop=None,freeze=0,mask=None):
 return dict(src=src,a=a,b=b,d=d,cap=cap,crop=crop,freeze=freeze,mask=mask)
QUOTE=[800,110,148,108,'white']
PHONE=[30,231,276,25,'0xfff7ff']
# Landscape stays below 3:00; condensed waits, retained evidence and deliberate holds.
FULL=[
 shot('stock',0,3,3,'open'),
 shot('s0-phone-lowstock',7.5,20.5,8,'low'),
 shot('s0-phone-lowstock',21,22.5,3,'low',freeze=1.5),
 shot('s1-rfq',2.5,5,2.5,'rfq'),
 shot('s1-rfq',6,37.5,13,'rfq',(400,100,1000,900)),
 shot('s1-rfq',40,43,4,'rfq',(400,100,1000,900),freeze=1),
 shot('s2-quote-photo',2.5,4.5,2,'photo'),
 shot('s2b-photo-closeup',4,8,5,'photo',(240,65,1450,1000),freeze=1,mask=QUOTE),
 shot('s2b-photo-closeup',10,12,4.5,'fields',(240,240,720,690),freeze=2.5,mask=QUOTE),
 shot('s2b-photo-closeup',18,21,4.5,'lines',(240,295,720,450),freeze=1.5),
 shot('s2-quote-photo',26,30,4,'authorise',(240,120,1450,900)),
 shot('s3c-smart-compare',5.5,11.5,5,'compare',(240,100,1450,950)),
 shot('s3c-smart-compare',12,15,5.5,'prices',(250,550,1420,480),freeze=2.5),
 shot('s3-guardrail-draft',9,11,4.5,'draft',(430,90,815,290),freeze=2.5),
 shot('s3-guardrail-draft',16,29.7,8,'submit',(425,90,825,920)),
 shot('s4-phone-approve',9,12,5.5,'approve',freeze=2.5,mask=PHONE),
 shot('s4-phone-approve',12.5,18.6,5,'approved',mask=PHONE),
 shot('s5-po-savings',7.5,19.5,7,'po',(350,100,1220,900)),
 shot('s5-po-savings',34,35.4,3.9,'po',(355,100,1220,850),freeze=2.5),
 shot('s5-po-savings',34,37.8,5,'sent',(355,80,1220,960),freeze=1.2),
 shot('s5-po-savings',40.5,47.5,6,'outcome',(770,120,1110,690)),
 shot('s5-po-savings',51,53,4.5,'outcome',(220,235,1370,760),freeze=2.5),
 shot('counter',0,1,5,None),
 shot('s6-savings-close',9,13,7,'ledger',(220,170,1230,800),freeze=3),
]
# Every web crop is a deliberate successive view; active content lies y=475..1515.
VERT=[
 shot('stock-v',.5,2,1.5,'open'),
 shot('s0-phone-lowstock',14,20.3,3.5,'low',(0,50,390,330)),
 shot('s0-phone-lowstock',21,22.5,2.5,'low',(0,335,390,240),freeze=1),
 shot('s1-rfq',34,37,3,'rfq',(420,190,815,820)),
 shot('s2b-photo-closeup',4,6,3,'photo',(995,245,660,500),freeze=1,mask=QUOTE),
 shot('s2b-photo-closeup',10,11,3,'fields',(250,250,700,385),freeze=2,mask=QUOTE),
 shot('s3c-smart-compare',12,14,4.5,'prices',(255,550,1405,480),freeze=2.5),
 shot('s3-guardrail-draft',9,10.5,3.5,'draft',(430,140,805,150),freeze=2),
 shot('s3-guardrail-draft',26,29,2,'submit',(435,760,795,220)),
 shot('s4-phone-approve',9,11,4,'approve',(0,65,390,295),freeze=2,mask=PHONE),
 shot('s4-phone-approve',13,18.6,3,'approved',(0,380,390,464),mask=PHONE),
 shot('s5-po-savings',34,36,3,'sent',(1100,95,470,605),freeze=1),
 shot('s5-po-savings',45.5,47.5,3,'outcome',(775,150,1100,630),freeze=1),
 shot('counter',0,1,4,None),
 shot('s6-savings-close',10,11,3,'ledger',(1030,295,410,105),freeze=2),
]
if __name__=='__main__':print('bodies',sum(x['d'] for x in FULL),sum(x['d'] for x in VERT))
