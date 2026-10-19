# Rebuild EDL. Times in seconds. freeze adds a readable endpoint hold.
# Source masks are applied BEFORE all reframing, for the complete shot including holds.
from paths import *
def shot(src,a,b,d,cap,crop=None,freeze=0,mask=None):
 return dict(src=src,a=a,b=b,d=d,cap=cap,crop=crop,freeze=freeze,mask=mask)
QUOTE=[800,110,148,108,'white']
PHONE=[30,231,276,25,'0xfff7ff']
# Landscape: condensed waits, repaired crops, unified PO, enlarged phone evidence and readable holds.
FULL=[
 shot('stock',0,3,3,'open'),
 shot('s0-phone-lowstock-v3',1.5,19.4,7.5,'low'),
 shot('s0-phone-lowstock-v3',21.3,22.8,3,'low',freeze=1.5),
 shot('s1-rfq',2.5,5,2.5,'rfq'),
 shot('s1-rfq',6,37.5,12,'rfq',(400,100,1000,900)),
 shot('s1-rfq',40.5,41.65,2.2,'rfq',(400,180,1000,900)),
 shot('s2-quote-photo',2.5,3.95,1.5,'photo'),
 shot('s2b-photo-closeup',4,8,4.5,'photo',(240,65,1450,1000),freeze=1,mask=QUOTE),
 shot('s2b-photo-closeup',10,12,4,'fields',(240,240,720,690),freeze=2,mask=QUOTE),
 shot('s2b-photo-closeup',18,21,4,'lines',(240,295,720,450),freeze=1.5),
 shot('s2-quote-photo',25.2,26.7,2.2,'authorise',(240,120,1450,900)),
 shot('s3c-smart-compare',5.5,11.5,5,'compare',(240,100,1450,950)),
 shot('s3c-smart-compare',12,15,5,'prices',(250,550,1420,480),freeze=2),
 shot('s3-guardrail-draft',9,11,4,'draft',(430,90,815,290),freeze=2),
 shot('s3-guardrail-draft',16,27.2,6,'submit',(425,90,825,920)),
 shot('s4-phone-approve',9,12.5,4,'approve',(0,65,390,500),mask=PHONE),
 shot('s4-phone-approve',12.5,14.0,2.5,'approve_action',(0,380,390,464)),
 shot('s4-phone-approve',17.1,18.6,3.5,'approved',(0,380,390,464),freeze=2.0),
 shot('s5-po-savings',7.5,17.5,5,'po',(350,100,1220,900)),
 shot('s5-po-savings',17.5,18.5,1.8,'po',(350,160,1220,900)),
 shot('s5-po-savings',34,37.8,4.5,'sent',(355,80,1220,960),freeze=1.5),
 shot('s5-po-savings',40.5,46.3,4,'outcome',(770,120,1110,690)),
 shot('s5-po-savings',50.5,53,4,'outcome',(220,235,1370,760),freeze=2),
 shot('counter',0,1,5,None),
 shot('s6-savings-close',9,13,6.5,'ledger',(220,170,1230,800),freeze=2.5),
]
# Vertical: under 60 s, vertical continuity for low-stock form, enlarged outcome, no busy freezes.
VERT=[
 shot('stock-v',.5,2,1.5,'open'),
 shot('s0-phone-lowstock-v3',2,11,3.0,'low',(0,0,390,420)),
 shot('s0-phone-lowstock-v3',18.0,19.4,1.8,'low',(0,65,390,360)),
 shot('s0-phone-lowstock-v3',21.3,22.8,2.0,'low',(0,335,390,240),freeze=1.0),
 shot('s1-rfq',34,37,2.5,'rfq',(420,190,815,820)),
 shot('s2b-photo-closeup',4,6,2.5,'photo',(995,245,660,500),freeze=1.0,mask=QUOTE),
 shot('s2b-photo-closeup',10,11,2.5,'fields',(250,250,700,385),freeze=1.5,mask=QUOTE),
 shot('s3c-smart-compare',12,14,3.5,'prices',(880,590,790,470),freeze=2.0),
 shot('s3-guardrail-draft',9,10.5,3.0,'draft',(435,90,800,820),freeze=1.5),
 shot('s3-guardrail-draft',26.2,27.2,1.5,'submit',(435,480,800,520)),
 shot('s4-phone-approve',9,11,2.5,'approve',(0,65,390,295),freeze=1.0,mask=PHONE),
 shot('s4-phone-approve',13.0,14.0,1.5,'approve_action',(0,380,390,464)),
 shot('s4-phone-approve',17.1,18.6,2.5,'approved',(0,380,390,464),freeze=1.5),
 shot('s5-po-savings',34,36,2.5,'sent',(1100,95,470,605),freeze=1.0),
 shot('s5-po-savings',45.5,46.3,1.5,'outcome',(770,450,600,400)),
 shot('s5-po-savings',50.5,52.5,2.5,'outcome',(350,235,950,700),freeze=1.5),
 shot('counter',0,1,3.5,None),
 shot('s6-savings-close',10,11,3.0,'ledger',(630,290,800,620),freeze=2.0),
]
if __name__=='__main__':print('bodies',sum(x['d'] for x in FULL),sum(x['d'] for x in VERT))
