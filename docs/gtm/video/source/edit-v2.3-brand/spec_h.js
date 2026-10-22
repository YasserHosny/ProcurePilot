// 16:9 Arabic, v2.3 brand editorial: the v2.2-editorial timeline re-art-directed in the brand system
// (../../motion-style.md). Copy, order and timing are unchanged. Total 118.95 s.
const W=1920,H=1080;
const io=(e,p,tin,tout,from,to,din=.45,dout=.35)=>{ const k=[[tin,from],[tin+din,0,'sig']]; if(tout!=null){ k.push([tout,0,'lin']); k.push([tout+dout,to,'in']); } return e.k(p,k); };
const up=(e,tin,tout)=>io(e,'iy',tin,tout,118,-118);
const fromR=(e,tin,tout)=>io(e,'ix',tin,tout,105,-105);
const K=(e,p,...keys)=>e.k(p,keys);

const ST=[0,5.0,14.0,26.0,42.0,54.0,64.5,75.5,92.3,98.0,109.2].map((t,i)=>(i==0||i==10)?t:nb(t));
const END=118.95;
const sc=(i)=>{ const st=ST[i], D=(ST[i+1]??END)-st; return [x=>st+x, D, st]; };

// global disclosure marker
T('بيانات تجريبية · واجهة عربية',{size:24,w:400,color:C.mid,bg:'rgba(244,246,249,.88)',pad:'0 .5em',x:60,y:1042,ax:0,ay:.5,z:900,t0:ST[1]+.3,t1:ST[8]});
T('بيانات تجريبية · واجهة عربية',{size:24,w:400,color:C.mid,bg:'rgba(244,246,249,.88)',pad:'0 .5em',x:60,y:1042,ax:0,ay:.5,z:900,t0:ST[9]+.3,t1:ST[10]-1.2});

// ---------- S0 OPENING ----------
{ const [a,D]=sc(0);
  const nour=IMG('tex/nour.png',{w:760,h:468,x:600,y:300,r:-3,depth:2,z:3,paper:true,t0:0,t1:a(D)});
  K(nour,'x',[a(.15),-700],[a(.7),600]); K(nour,'r',[a(.15),-12],[a(.7),-3]); K(nour,'y',[a(.7),300],[a(4.2),288,'io'],[a(4.9),300]);
  const sayed=IMG('tex/sayed.png',{w:700,h:431,x:1080,y:790,r:2.5,depth:2,z:4,paper:true,t0:0,t1:a(D)});
  K(sayed,'y',[a(.3),1500],[a(.85),790]); K(sayed,'r',[a(.3),10],[a(.85),2.5]);
  const wa11=IMG('tex/wa11.jpg',{w:470,h:700,x:1510,y:640,r:5,depth:3,z:5,t0:0,t1:a(D)});
  K(wa11,'x',[a(0),2500],[a(.55),1510]); K(wa11,'r',[a(0),16],[a(.55),5]); K(wa11,'y',[a(.55),640],[a(4.2),628,'io']);
  const wa7=IMG('tex/wa7.jpg',{w:420,h:625,x:330,y:760,r:-6,depth:3,z:6,t0:0,t1:a(D)});
  K(wa7,'y',[a(.45),1700],[a(1.0),760]); K(wa7,'r',[a(.45),-18],[a(1.0),-6]); K(wa7,'x',[a(1.0),330],[a(4.2),342,'io']);
  const t1=T('عروض واتساب…',{size:200,x:1850,y:250,ax:1,z:10,t0:a(.6),t1:a(D)}); up(t1,a(.7));
  const ul=R({w:1030,h:22,x:1850,y:385,ax:1,ay:.5,z:9,color:C.ink,t0:a(1.0),t1:a(D)}); K(ul,'sx',[a(1.1),0],[a(1.55),1]);
  const t2=T('ونسخ يدوي؟',{size:150,x:1600,y:560,ax:1,z:11,r:-1.5,bg:C.card,pad:'0 .3em .05em',depth:2,t0:a(1.5),t1:a(D)});
  K(t2,'x',[a(1.6),2700],[a(2.15),1600]); K(t2,'r',[a(1.6),-6],[a(2.15),-1.5]);
  // exit: layers pushed left under the brand bar wipe (PASS at ST[1])
  for(const e of [nour,sayed,wa11,wa7,t1,t2,ul]){ const k=e.tr.x||[[0,e.o.x]]; e.k('x',[...k,[a(D-.6),k[k.length-1][1],'lin'],[a(D),k[k.length-1][1]-260,'in']]); }
}
// ---------- S1 LOW STOCK ----------
{ const [a,D]=sc(1);
  const pl=R({w:W,h:H,x:W,y:0,ax:1,ay:0,z:2,color:C.mist,t0:a(0),t1:a(D)}); K(pl,'sx',[a(.05),1],[a(.65),620/W]);
  const w1=T('نقص',{size:260,x:1860,y:290,ax:1,z:12,t0:a(.4),t1:a(D)}); up(w1,a(.45),a(D-.5));
  const w2=T('المخزون',{size:150,x:1860,y:520,ax:1,z:12,t0:a(.55),t1:a(D)}); up(w2,a(.6),a(D-.45));
  const k=IMG('tex/kitchen.jpg',{w:560,h:462,x:390,y:330,r:-2,depth:1,z:4,t0:a(.3),t1:a(D)}); K(k,'x',[a(.5),-500],[a(1.05),390]); K(k,'y',[a(1.05),330],[a(D-.5),318,'io']);
  const ph=PLATE('low',{w:430,x:930,y:540,z:8,depth:3,t0:a(.2),t1:a(D),map:PM([[a(.85),0,1.2,a(8.2)]])});
  K(ph,'y',[a(.3),1700],[a(.85),540]);
  const cap=T('بلاغ نقص المخزون من الموبايل',{size:40,w:500,x:660,y:640,ax:1,z:6,t0:a(1.0),t1:a(D)}); up(cap,a(1.1),a(D-.5));
  const bar=R({w:10,h:150,x:672,y:600,ax:0,ay:0,z:6,color:C.ink,t0:a(1.1),t1:a(D)}); K(bar,'sy',[a(1.15),0],[a(1.5),1]);
  // exit: ink plane rises from bottom
  const ink=R({w:W,h:H,x:0,y:H,ax:0,ay:0,z:60,color:C.ink,t0:a(D-.6),t1:a(D)+.01}); K(ink,'y',[a(D-.55),H],[a(D),0,'sig']);
}
// ---------- S2 RFQ ----------
{ const [a,D,st]=sc(2);
  const col=R({w:W,h:H,x:0,y:0,ax:0,ay:0,z:2,color:C.ink,t0:a(0),t1:a(D)}); K(col,'sx',[a(1.0),1],[a(1.6),600/W]); K(col,'x',[a(D-.5),0],[a(D),-700,'in']);
  const one=T('واحد',{size:360,color:C.card,x:960,y:520,z:12,t0:a(0),t1:a(D)}); up(one,a(.05));
  K(one,'x',[a(1.0),960],[a(1.6),300],[a(D-.5),300,'lin'],[a(D),-500,'in']); K(one,'y',[a(1.0),520],[a(1.6),330]); K(one,'s',[a(1.0),1],[a(1.6),.62]);
  const l1=T('طلب عرض سعر',{size:64,color:C.card,x:300,y:560,z:12,t0:a(1.4),t1:a(D)}); up(l1,a(1.5)); K(l1,'x',[a(D-.5),300],[a(D),-500,'in']);
  const l2=T('لكل الموردين',{size:64,color:C.tealDark,x:300,y:650,z:12,t0:a(1.55),t1:a(D)}); up(l2,a(1.65)); K(l2,'x',[a(D-.5),300],[a(D),-500,'in']);
  const list=PLATE('rfqlist',{w:1150,x:1250,y:360,z:5,t0:a(1.2),t1:a(D),map:PM([[a(1.85),0,1,a(4.35)]])});
  K(list,'x',[a(1.3),2700],[a(1.85),1250],[a(3.6),1250,'lin'],[a(4.2),1180],[a(D-.55),1180,'lin'],[a(D),3000,'in']); K(list,'y',[a(3.6),360],[a(4.2),300]); K(list,'s',[a(3.6),1],[a(4.2),.92]);
  const form=PLATE('rfqform',{w:930,x:1260,y:570,z:7,depth:3,t0:a(3.5),t1:a(D),map:PM([[a(4.15),0,2.15,a(10.9)]])});
  K(form,'y',[a(3.6),1750],[a(4.15),570]); K(form,'x',[a(D-.55),1260],[a(D),3200,'in']);
}
// ---------- S3 PHOTO / FIELDS / LINES / AUTH ----------
{ const [a,D,st]=sc(3);
  // quote photo crosses the frame as the transition
  const ph=IMG('tex/wa11.jpg',{w:600,h:893,x:390,y:560,r:-4,depth:3,z:8,t0:a(-.55),t1:a(7)});
  K(ph,'x',[a(-.55),-700],[a(.12),390,'sig'],[a(6.3),390,'lin'],[a(6.8),-800,'in']); K(ph,'r',[a(-.55),-16],[a(.12),-4]); K(ph,'s',[a(-.55),1.35],[a(.12),.78]);
  const w1=T('صورة',{size:300,x:1840,y:230,ax:1,z:4,t0:a(.1),t1:a(7)}); K(w1,'cl',[a(.15),100],[a(.6),0]); up(w1,a(-1),a(2.35));
  const w2=T('عرض سعر',{size:110,x:1840,y:440,ax:1,z:4,t0:a(.35),t1:a(7)}); up(w2,a(.4),a(2.3));
  const inbox=PLATE('inbox',{w:1000,x:1260,y:740,z:6,t0:a(.8),t1:a(3),map:PM([[a(1.35),0,1,a(2.45)]])}); K(inbox,'x',[a(.9),2700],[a(1.35),1260]);
  const pp=PLATE('photo',{w:1180,x:1240,y:575,z:7,depth:3,t0:a(2.0),t1:a(7),map:PM([[a(2.6),0,1.3,a(6.4)]])});
  K(pp,'y',[a(2.1),1750],[a(2.6),575]); K(pp,'x',[a(6.3),1240],[a(6.8),3000,'in']);
  const ex=T('استخراج',{size:150,x:1010,y:900,ax:1,z:14,bg:C.mist,pad:'0 .25em .04em',t0:a(2.9),t1:a(7)}); K(ex,'cl',[a(3.0),100],[a(3.45),0]); up(ex,a(-1),a(6.3));
  const ex2=T('ثم مراجعة بشرية',{size:54,x:1010,y:1012,ax:1,z:14,bg:C.card,pad:'0 .3em',t0:a(3.2),t1:a(7)}); up(ex2,a(3.3),a(6.3));
  // FIELDS
  const num=T('٢٥٬١٤٠',{size:320,x:560,y:400,z:12,t0:a(6.25),t1:a(10.6)});
  K(num,'x',[a(6.3),-900],[a(6.85),560],[a(10.0),560,'lin'],[a(10.45),-900,'in']); K(num,'s',[a(6.3),1.8],[a(6.85),1]);
  const egp=T('ج.م',{size:100,x:900,y:640,ax:1,z:12,t0:a(6.6),t1:a(10.6)}); up(egp,a(6.7),a(10.0));
  const ul=R({w:740,h:20,x:930,y:590,ax:1,ay:.5,z:11,color:C.ink,t0:a(6.8),t1:a(10.6)}); K(ul,'sx',[a(6.9),0],[a(7.3),1],[a(10.0),1,'lin'],[a(10.3),0,'in']);
  const fl=T('الإجمالي مطابق للبنود',{size:56,x:900,y:760,ax:1,z:12,t0:a(7.0),t1:a(10.6)}); up(fl,a(7.1),a(10.0));
  const fp=PLATE('fields',{w:760,x:1440,y:540,z:7,depth:3,t0:a(6.4),t1:a(10.6),map:PM([[a(7.0),0,1.25,a(10.6)]])});
  K(fp,'y',[a(6.5),-700],[a(7.0),540],[a(10.0),540,'lin'],[a(10.45),-800,'in']);
  // LINES
  const words=['زيت','أرز','بصل'];
  words.forEach((s,i)=>{ const e=T(s,{size:190,x:580,y:230+i*215,ax:1,z:12,t0:a(10.1),t1:a(14.2)}); fromR(e,a(10.15+i*.14),a(13.6+i*.06)); });
  const lc=T('راجع البنود قبل الاعتماد',{size:48,x:580,y:880,ax:1,z:12,t0:a(10.6),t1:a(14.2)}); up(lc,a(10.7),a(13.7));
  const vb=R({w:10,h:640,x:640,y:200,ax:0,ay:0,z:11,color:C.ink,t0:a(10.3),t1:a(14.2)}); K(vb,'sy',[a(10.4),0],[a(10.9),1],[a(13.6),1,'lin'],[a(14.0),0,'in']);
  const lp=PLATE('lines',{w:1180,x:1270,y:540,z:7,depth:3,t0:a(10.1),t1:a(14.4),map:PM([[a(10.7),0,1.25,a(14.3)]])}); K(lp,'cb',[a(10.2),100],[a(10.7),0]);
  // AUTH
  const ap=PLATE('auth',{w:1150,x:1250,y:600,z:9,depth:4,t0:a(13.6),t1:a(D),map:PM([[a(14.2),0,.5,a(15.4)]])}); K(ap,'x',[a(13.7),3000],[a(14.2),1250]);
  const al=T('مراجعة بشرية',{size:130,color:C.card,x:1860,y:150,ax:1,z:15,bg:C.ink,pad:'0 .25em .04em',t0:a(14.0),t1:a(D)}); K(al,'cl',[a(14.1),100],[a(14.55),0]);
  const a2=T('ثم اعتماد عرض السعر',{size:58,x:340,y:560,z:15,t0:a(14.3),t1:a(D)}); up(a2,a(14.4),a(D-.55));
  const grow=R({w:W,h:H,x:0,y:0,ax:0,ay:0,z:14,color:C.mist,t0:a(D-.5),t1:a(D)+.01});
  K(grow,'ct',[a(D-.5),5],[a(D),0]); K(grow,'cb',[a(D-.5),76],[a(D),0]); K(grow,'cl',[a(D-.5),46],[a(D),0]); K(grow,'cr',[a(D-.5),3],[a(D),0]);
}
// ---------- S4 COMPARE / PRICES ----------
{ const [a,D]=sc(4);
  const band=R({w:W,h:H,x:0,y:0,ax:0,ay:0,z:2,color:C.mist,t0:a(0),t1:a(D)}); K(band,'cb',[a(1.0),0],[a(1.6),62.5],[a(D-.5),62.5,'lin'],[a(D),100,'in']);
  const m=T('مقارنة',{size:340,x:960,y:520,z:12,t0:a(0),t1:a(6.2)}); up(m,a(.05),a(5.7));
  K(m,'x',[a(1.0),960],[a(1.6),1480]); K(m,'y',[a(1.0),520],[a(1.6),200]); K(m,'s',[a(1.0),1],[a(1.6),.5]);
  const m2=T('عروض الزيت × ٨ عبوات',{size:64,x:1110,y:215,ax:1,z:12,t0:a(1.4),t1:a(6.2)}); up(m2,a(1.5),a(5.75));
  const cp=PLATE('compare',{w:1120,x:960,y:680,z:7,depth:3,t0:a(1.0),t1:a(6.3),map:PM([[a(1.65),0,1.2,a(5.8)]])});
  K(cp,'y',[a(1.1),1800],[a(1.65),680]); K(cp,'x',[a(5.7),960],[a(6.2),-1000,'in']);
  const pp=PLATE('prices',{w:1700,x:960,y:720,z:8,depth:3,t0:a(5.6),t1:a(D),map:PM([[a(6.25),0,1,a(11.75)]])});
  K(pp,'x',[a(5.75),3000],[a(6.25),960]); K(pp,'y',[a(D-.5),720],[a(D),1800,'in']);
  const n1=T('١٢٬٨٨٠',{size:220,x:1840,y:190,ax:1,z:13,t0:a(6.0),t1:a(D)}); up(n1,a(6.1));
  K(n1,'s',[a(D-.55),1],[a(D),6,'in']); K(n1,'x',[a(D-.55),1840],[a(D),2400,'in']); K(n1,'o',[a(D-.2),1],[a(D),0,'lin']);
  const vs=T('مقابل',{size:60,x:1060,y:200,ax:1,z:13,t0:a(6.2),t1:a(D-.4)}); up(vs,a(6.3),a(D-.6));
  const n2=T('١٣٬٠٨٠',{size:120,color:C.mid,x:880,y:195,ax:1,z:13,t0:a(6.3),t1:a(D-.4)}); up(n2,a(6.4),a(D-.6));
  const eg=T('ج.م',{size:60,x:450,y:200,ax:1,z:13,t0:a(6.45),t1:a(D-.4)}); up(eg,a(6.55),a(D-.6));
  const ox=T('الزيت × ٨',{size:46,x:1840,y:350,ax:1,z:13,t0:a(6.5),t1:a(D-.4)}); up(ox,a(6.6),a(D-.6));
  const ub=R({w:730,h:22,x:1840,y:310,ax:1,ay:.5,z:13,color:C.teal,radius:11,t0:a(6.5),t1:a(D-.4)}); K(ub,'sx',[a(6.6),0],[a(7.0),1],[a(D-.6),1,'lin'],[a(D-.4),0,'in']);
}
// ---------- S5 GUARDRAILS / SUBMIT ----------
{ const [a,D]=sc(5);
  const dp=PLATE('draft',{w:1620,x:960,y:730,z:7,depth:3,t0:a(0),t1:a(5.6),map:PM([[a(.6),0,1,a(5.1)]])});
  K(dp,'x',[a(.1),-1000],[a(.6),960]); K(dp,'y',[a(5.0),730],[a(5.5),1900,'in']);
  const g1=T('الضوابط',{size:250,x:1840,y:220,ax:1,z:12,t0:a(.2),t1:a(5.6)}); up(g1,a(.25)); K(g1,'x',[a(5.0),1840],[a(5.5),-300,'in']);
  const g2=T('تجهّز المسودة',{size:96,x:830,y:200,ax:1,z:12,t0:a(.45),t1:a(5.6)}); up(g2,a(.5)); K(g2,'x',[a(5.0),830],[a(5.5),-700,'in']);
  const g3=T('والقرار للمدير',{size:96,color:C.teal,x:830,y:330,ax:1,z:12,t0:a(.75),t1:a(5.6)}); up(g3,a(.8)); K(g3,'x',[a(5.05),830],[a(5.55),-700,'in']);
  const sp=PLATE('submit',{w:760,x:1390,y:560,z:7,depth:3,t0:a(5.0),t1:a(D),map:PM([[a(5.6),0,1.35,a(10.5)]])});
  K(sp,'y',[a(5.1),1900],[a(5.6),560]); K(sp,'x',[a(D-.5),1390],[a(D),2600,'in']);
  const r1=T('راجع',{size:300,x:930,y:330,ax:1,z:12,t0:a(5.2),t1:a(D)}); up(r1,a(5.3));
  const r2=T('المسودة',{size:170,x:930,y:600,ax:1,z:12,t0:a(5.35),t1:a(D)}); up(r2,a(5.45));
  const r3=T('ثم أرسلها للاعتماد',{size:60,x:930,y:790,ax:1,z:12,t0:a(5.6),t1:a(D)}); up(r3,a(5.7));
  const rb=R({w:600,h:16,x:930,y:860,ax:1,ay:.5,z:12,color:C.ink,t0:a(5.8),t1:a(D)}); K(rb,'sx',[a(5.9),0],[a(6.3),1]);
  const ink=R({w:900,h:H,x:0,y:0,ax:0,ay:0,z:40,color:C.ink,t0:a(D-.55),t1:a(D)+.01}); K(ink,'cr',[a(D-.5),100],[a(D),0]);
}
// ---------- S6 APPROVE ----------
{ const [a,D]=sc(6);
  const panel=R({w:900,h:H,x:0,y:0,ax:0,ay:0,z:2,color:C.ink,t0:a(0),t1:a(D)}); K(panel,'x',[a(D-.5),0],[a(D),-950,'in']);
  const m1=T('المدير',{size:260,color:C.card,x:840,y:300,ax:1,z:6,t0:a(.05),t1:a(7.8)}); up(m1,a(.1));
  const m2=T('يراجع ويعتمد',{size:90,color:C.card,x:840,y:520,ax:1,z:6,t0:a(.3),t1:a(7.8)}); up(m2,a(.35));
  const m3=T('من الموبايل',{size:90,color:C.mist,x:840,y:640,ax:1,z:6,t0:a(.45),t1:a(7.8)}); up(m3,a(.5));
  const m4=T('اعتماد الطلب',{size:70,color:C.card,x:840,y:860,ax:1,z:6,t0:a(5.9),t1:a(7.8)}); up(m4,a(6.0));
  const mb=R({w:430,h:12,x:840,y:930,ax:1,ay:.5,z:6,color:C.mist,t0:a(6.1),t1:a(7.8)}); K(mb,'sx',[a(6.15),0],[a(6.5),1]);
  const ph=PLATE('approve',{w:440,x:1110,y:540,z:8,depth:3,t0:a(.15),t1:a(D),map:PM([[a(.7),.3,1,a(7.4)],[a(7.4),9.9,1,a(8.0)]])});
  K(ph,'x',[a(.2),2500],[a(.7),1110],[a(D-.5),1110,'lin'],[a(D),2600,'in']);
  const op=R({w:900,h:H,x:0,y:0,ax:0,ay:0,z:10,t0:a(7.35),t1:a(D)}); K(op,'cl',[a(7.4),100],[a(7.7),0]); K(op,'x',[a(D-.5),0],[a(D),-950,'in']);
  const d1=T('تم اعتماد',{size:200,x:840,y:410,ax:1,z:12,t0:a(7.5),t1:a(D)}); up(d1,a(7.6)); K(d1,'x',[a(D-.5),840],[a(D),-110,'in']);
  const d2=T('الطلب',{size:200,x:840,y:640,ax:1,z:12,t0:a(7.65),t1:a(D)}); up(d2,a(7.75)); K(d2,'x',[a(D-.5),840],[a(D),-110,'in']);
}
// ---------- S7 PO / SENT / OUTCOME ----------
{ const [a,D]=sc(7);
  const p1=T('أمر الشراء',{size:280,x:1720,y:540,ax:1,z:12,t0:a(0),t1:a(6.1)}); up(p1,a(.1),a(5.6));
  K(p1,'x',[a(1.0),1720],[a(1.6),720]); K(p1,'y',[a(1.0),540],[a(1.6),410]); K(p1,'s',[a(1.0),1],[a(1.6),.5]);
  const p0=T('من الطلب المعتمد إلى',{size:64,x:1720,y:330,ax:1,z:12,t0:a(.2),t1:a(6.1)}); up(p0,a(.3),a(5.6));
  K(p0,'x',[a(1.0),1720],[a(1.6),720]); K(p0,'y',[a(1.0),330],[a(1.6),235]);
  const po=PLATE('po',{w:1080,x:1300,y:560,z:7,depth:3,t0:a(1.0),t1:a(6.2),map:PM([[a(1.6),0,1.25,a(5.6)]])});
  K(po,'y',[a(1.1),1800],[a(1.6),560],[a(5.6),560,'lin'],[a(6.1),-500,'in']);
  const id=T('PO-000006',{size:155,dir:'ltr',x:80,y:330,ax:0,z:13,t0:a(5.55),t1:a(10.7)});
  K(id,'x',[a(5.6),-1100],[a(6.05),80],[a(10.2),80,'lin'],[a(10.65),-1300,'in']); K(id,'s',[a(5.6),1.4],[a(6.05),1]);
  const iu=R({w:830,h:18,x:90,y:445,ax:0,ay:.5,z:12,color:C.ink,t0:a(6.1),t1:a(10.7)}); K(iu,'sx',[a(6.2),0],[a(6.6),1],[a(10.2),1,'lin'],[a(10.5),0,'in']);
  const sn=T('تم إرسال أمر الشراء',{size:72,x:940,y:540,ax:1,z:13,t0:a(6.1),t1:a(10.7)}); up(sn,a(6.2),a(10.2));
  const sp=PLATE('sent',{w:860,x:1470,y:600,z:8,depth:3,t0:a(5.7),t1:a(10.8),map:PM([[a(6.05),0,1.2,a(10.2)]])});
  K(sp,'y',[a(5.75),-700],[a(6.15),600],[a(10.2),600,'lin'],[a(10.7),1900,'in']);
  const o1=T('تسجيل النتيجة',{size:200,x:1850,y:200,ax:1,z:13,t0:a(10.2),t1:a(D)}); up(o1,a(10.3));
  const o2=T('من أمر الشراء',{size:72,x:1850,y:370,ax:1,z:13,t0:a(10.4),t1:a(D)}); up(o2,a(10.5));
  const op=PLATE('outcome',{w:1100,x:760,y:660,z:7,depth:3,t0:a(10.1),t1:a(D),map:PM([[a(10.7),0,1.4,a(13.85)]])});
  K(op,'x',[a(10.2),-800],[a(10.7),760],[a(13.6),760,'lin'],[a(14.1),640]);
  const rp=PLATE('result',{w:1150,x:1250,y:690,z:9,depth:4,t0:a(13.5),t1:a(D),map:PM([[a(14.1),0,1,a(D)]])}); K(rp,'x',[a(13.6),3000],[a(14.1),1250]);
  const grow=R({w:W,h:H,x:0,y:0,ax:0,ay:0,z:70,t0:a(D-.5),t1:a(D)+.01});
  for(const p of ['ct','cb','cl','cr']) K(grow,p,[a(D-.5),48],[a(D),0]);
}
// ---------- S8 COUNTER ----------
{ const [a,D]=sc(8);
  const blk=R({w:W,h:H,x:0,y:0,ax:0,ay:0,z:2,t0:a(0),t1:a(D)});
  K(blk,'ct',[a(.05),0],[a(.6),22]); K(blk,'cb',[a(.05),0],[a(.6),26]); K(blk,'cl',[a(.05),0],[a(.6),27]); K(blk,'cr',[a(.05),0],[a(.6),27]);
  K(blk,'y',[a(D-.5),0],[a(D),-1200,'in']);
  const h1=T('وفّر الطلب ده',{size:80,x:960,y:150,z:12,t0:a(.3),t1:a(D)}); up(h1,a(.4),a(D-.45));
  const n=T('٠',{size:380,x:960,y:520,z:12,t0:a(.4),t1:a(D)}); up(n,a(.45)); K(n,'y',[a(D-.5),520],[a(D),-700,'in']);
  const t0=a(.6),t1=a(1.6); const AR='٠١٢٣٤٥٦٧٨٩';
  n.update=(t)=>{ const u=EASE.out(Math.max(0,Math.min(1,(t-t0)/(t1-t0)))); const v=String(Math.round(460*u)).replace(/\d/g,d=>AR[d]); if(n.inner.textContent!==v) n.inner.textContent=v; };
  const eg=T('ج.م',{size:90,x:960,y:740,z:12,t0:a(1.2),t1:a(D)}); up(eg,a(1.3)); K(eg,'y',[a(D-.5),740],[a(D),-500,'in']);
  const l1=T('مقابل أسعار آخر أوامر شراء',{size:46,x:960,y:900,z:12,t0:a(1.4),t1:a(D)}); up(l1,a(1.5),a(D-.45));
  const l2=T('بيانات تجريبية · زيت +٢٤٠ · أرز +١٨٠ · بصل +٤٠',{size:30,w:400,color:C.mid,x:960,y:968,z:12,t0:a(1.6),t1:a(D)}); up(l2,a(1.7),a(D-.45));
}
// ---------- S9 LEDGER ----------
{ const [a,D]=sc(9);
  const lp=PLATE('ledger',{w:1080,x:1330,y:560,z:7,depth:3,t0:a(0),t1:a(D),map:PM([[a(.5),0,1,a(7.5)]])});
  K(lp,'y',[a(0),1800],[a(.5),560],[a(4.6),560,'lin'],[a(5.4),640,'io'],[a(D-.9),640,'lin'],[a(D-.3),1900,'in']); K(lp,'x',[a(4.6),1330],[a(5.4),1300,'io'],[a(D-.9),1300,'lin'],[a(D-.3),1600,'in']); K(lp,'s',[a(4.6),1],[a(5.4),1.1,'io']);
  const n=T('١٬٠٦٠',{size:220,x:740,y:330,ax:1,z:12,t0:a(.3),t1:a(D)}); up(n,a(.4)); K(n,'x',[a(D-.9),740],[a(D-.35),-700,'in']);
  const u=R({w:600,h:18,x:740,y:490,ax:1,ay:.5,z:12,t0:a(.6),t1:a(D)}); K(u,'sx',[a(.7),0],[a(1.1),1],[a(D-1.0),1,'lin'],[a(D-.7),0,'in']);
  const e=T('ج.م',{size:90,x:740,y:590,ax:1,z:12,t0:a(.6),t1:a(D)}); up(e,a(.7),a(D-.9));
  const c=T('سجل تجريبي يشمل تجربة سابقة',{size:46,x:740,y:710,ax:1,z:12,t0:a(.8),t1:a(D)}); up(c,a(.9),a(D-.85));
}
// ---------- BRAND BAR WIPES (Converge mark: navy / teal + arrow / navy, left to right) ----------
for(const i of [1,5,7]) PASS(ST[i]);

// ---------- OUTRO (beat-locked to the approved outro audio) ----------
// The mark builds from its own geometry and colours (docs/brand/logo/procurepilot-mark.svg), then
// the official horizontal lockup is revealed over it; the logo itself is never redrawn or recoloured.
{ const st=ST[10]; const a=x=>st+x; const D=END-st; const LOGO='../../../../brand/logo/';
  const sc=1.4933, LW=956.7*sc, LH=220*sc, Lx=(W-LW)/2, Ly=230;          // lockup px per viewBox unit
  const u=2.8125*sc, mx=Lx+20*sc, my=Ly+20*sc;                           // mark units inside the lockup
  const bar=(x,y,w,h,color,t,dur)=>{ const e=R({w:w*u,h:h*u,x:mx+x*u,y:my+y*u,ax:0,ay:0,z:10,color,radius:h*u/2,t0:t-.01,t1:a(4.6)}); K(e,'sx',[t,0],[t+dur,1,'out']); return e; };
  bar(6,14,22,8,C.ink,a(.534),.3); bar(6,42,16,8,C.ink,a(.801),.3); bar(6,28,34,8,C.teal,a(.80),.54);
  const arrow=div('rect'); arrow.style.width=(26*u)+'px'; arrow.style.height=(30*u)+'px';
  arrow.innerHTML=`<svg viewBox="34 17 26 30" width="100%" height="100%"><path d="M36 20 L58 32 L36 44 Z" fill="${C.teal}" stroke="${C.teal}" stroke-width="3" stroke-linejoin="round"/></svg>`;
  const ar=new El(arrow,{x:mx+34*u,y:my+32*u,ax:0,ay:.5,z:11,t0:a(1.5),t1:a(4.6)});
  K(ar,'x',[a(1.5),mx+20*u],[a(1.75),mx+34*u,'out']); K(ar,'s',[a(1.5),.3],[a(1.75),1,'out']);
  const lock=IMG(LOGO+'procurepilot-horizontal.svg',{w:LW,h:LH,x:Lx,y:Ly,ax:0,ay:0,z:12,fit:'contain',t0:a(1.85),t1:a(4.6)});
  K(lock,'cr',[a(1.87),79.1],[a(2.67),0,'io']);
  const tg=[['قارن.',C.ink,.534],['اختار.',C.ink,1.0],['وفّر.',C.teal,1.602]];
  let x=W/2+420; tg.forEach(([s,col,t],i)=>{ const e=T(s,{size:96,color:col,x:x,y:Ly+LH+150,ax:1,z:10,t0:a(t)-.01,t1:a(4.6)}); up(e,a(t)); x-=[300,330,0][i]; });
  // end card: navy panel with the official on-dark lockup; contact on paper
  const pl=R({w:W,h:H,x:0,y:0,ax:0,ay:0,z:40,color:C.ink,t0:a(4.2),t1:a(D)+.1}); K(pl,'cl',[a(4.2),100],[a(4.5),0]); K(pl,'sx',[a(4.55),1],[a(5.0),600/W]);
  const dk=IMG(LOGO+'procurepilot-horizontal-dark.svg',{w:500,h:115,x:300,y:540,z:42,fit:'contain',t0:a(4.75),t1:a(D)+.1});
  K(dk,'y',[a(4.75),700],[a(5.15),540,'out']); K(dk,'o',[a(4.75),0],[a(5.0),1,'lin']);
  const L=[['جرّبه أسبوعين مجانًا',{size:120,y:300}],['وإحنا اللي هنجهّزه معاك.',{size:56,w:500,y:430}],['واتساب',{size:34,w:500,color:C.mid,y:565}],
    ['+20 102 735 4140',{size:110,w:600,dir:'ltr',color:C.tealText,y:650}],['د. ياسر حسني — المؤسس',{size:42,w:500,y:810}],['yasser.hosny@iron-sys.com',{size:36,w:400,dir:'ltr',y:870}],['أحد منتجات Iron Systems',{size:32,w:400,color:C.mid,y:975}]];
  const step=[1,2,3,3,4,4,5];
  L.forEach(([s,o],i)=>{ const e=T(s,Object.assign({x:1800,ax:1,z:41,t0:a(4.5),t1:a(D)+.1},o)); up(e,a(4.5+.27*step[i])); });
  const wu=R({w:860,h:14,x:1800,y:722,ax:1,ay:.5,z:41,color:C.mist,t0:a(5.3),t1:a(D)+.1}); K(wu,'sx',[a(5.35),0],[a(5.75),1]);
}
window.DURATION=END;
