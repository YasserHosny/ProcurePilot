"""English recordings, newly derived LTR crops and source spans. Zero-based slots.
Source b is exclusive. Durations include endpoint freeze; source masks baked first.
"""
from edl import shot
FULL=[
 shot('open-anim-16x9',0,5,5,'open'),
 shot('s0-phone-lowstock',3.2,21.3,7.5,'low',(0,0,390,410)),
 shot('s0-phone-lowstock',22.3,24,3,'low',(0,335,390,285),freeze=1.3),
 shot('s1-rfq',4.5,6,2.5,'rfq',(670,90,820,660)),
 shot('s1-rfq',6,37.8,12,'rfq',(670,90,820,920)),
 shot('s1-rfq',41.2,42.066667,2.2,'rfq',(670,170,820,900)),
 shot('s2-quote-photo',2.5,4.1,1.5,'photo',(230,110,1440,700)),
 shot('s2b-photo-closeup',4.5,8,4.5,'photo',(230,64,1450,1000),freeze=1),
 shot('s2b-photo-closeup',8,10,4,'fields',(960,180,720,425),freeze=2),
 shot('s2b-photo-closeup',11,14,4,'lines',(960,615,720,440),freeze=1),
 shot('s2-quote-photo',25.3,26.2,1,'authorise',(230,400,1450,680)),
 shot('s2-quote-photo',27.6,28.35,1.2,'authorise',(230,400,1450,680)),
 shot('s3c-smart-compare',10.5,13.5,5,'compare',(250,100,1420,950),freeze=2),
 shot('s3c-smart-compare',14,17,5,'prices',(250,560,1420,480),freeze=2),
 shot('s3-guardrail-draft',20,22,4,'draft',(680,90,820,300),freeze=2),
 shot('s3-guardrail-draft',28,35.366667,6,'submit',(680,90,820,920)),
 shot('s4-phone-approve',7.6,11.8,4,'approve',(0,65,390,520)),
 shot('s4-phone-approve',11.8,12.4,2.5,'approve_action',(0,580,390,264)),
 shot('s4-phone-approve',16.4,18,3.5,'approved',(0,380,390,464),freeze=1.9),
 shot('s5-po-savings',7.5,19.9,5,'po',(350,90,1220,950)),
 shot('s5-po-savings',19.9,20.566667,1.8,'po',(350,160,1220,920)),
 shot('s5-po-savings',24.7,25.066667,1,'po',(350,90,1220,950)),
 shot('s5-po-savings',28.8,30.8,4,'sent',(350,90,1220,950),freeze=2),
 shot('s5-po-savings',33.3,39.8,4,'outcome',(30,150,1120,650)),
 shot('s5-po-savings',39.8,40.566667,1,'outcome',(30,150,1120,650)),
 shot('s6-savings-close',.4,2,3,'outcome',(475,280,800,620),freeze=1.4),
 shot('counter',0,1,5,None),
 shot('s6-savings-close',7,11,6.5,'ledger',(475,280,1000,740),freeze=2.5),
]
VERT=[
 shot('open-anim-9x16',0,3.1,3.1,'open'),
 shot('s0-phone-lowstock',3.2,18,3,'low',(0,0,390,410)),
 shot('s0-phone-lowstock',19,21.3,1.8,'low',(0,65,390,315)),
 shot('s0-phone-lowstock',22.3,23.3,2,'low',(0,335,390,285),freeze=1),
 shot('s1-rfq',33,36.5,2.5,'rfq',(680,170,800,860)),
 shot('s2b-photo-closeup',4.5,6,2.5,'photo',(240,150,690,610),freeze=1),
 shot('s2b-photo-closeup',8,9,2.5,'fields',(965,180,710,425),freeze=1.5),
 shot('s3c-smart-compare',14,16,3.5,'prices',(250,860,720,185),freeze=1.5),
 shot('s3-guardrail-draft',20,21.5,3,'draft',(680,90,820,880),freeze=1.5),
 shot('s3-guardrail-draft',34.4,35.366667,1.5,'submit',(680,720,820,270)),
 shot('s4-phone-approve',8,9.5,2.5,'approve',(0,65,390,295),freeze=1),
 shot('s4-phone-approve',11.8,12.4,1.5,'approve_action',(0,580,390,264)),
 shot('s4-phone-approve',16.4,17.4,2.5,'approved',(0,380,390,464),freeze=1.5),
 shot('s5-po-savings',28.8,30.3,2.5,'sent',(350,120,1210,195),freeze=1),
 shot('s5-po-savings',39.8,40.566667,1.5,'outcome',(700,600,450,200)),
 shot('s6-savings-close',.4,1.4,2.5,'outcome',(490,355,780,285),freeze=1.5),
 shot('counter',0,1,3.5,None),
 shot('s6-savings-close',7,8,3,'ledger',(490,350,780,290),freeze=2),
]
def plan(vertical=False,variant='anim'):
 import copy
 p=copy.deepcopy(VERT if vertical else FULL);p[0]['src']=f'open-{variant}-'+('9x16' if vertical else '16x9');return p
