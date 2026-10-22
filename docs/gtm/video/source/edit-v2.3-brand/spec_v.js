// 9:16 Arabic, v2.3 brand editorial (../../motion-style.md): the v2.2-editorial vertical timeline in the
// brand system; copy, order and timing unchanged. Opening + body + fast outro. Total 53.4 s. Safe area: key text y 250..1570.
const W=1080,H=1920;
const io=(e,p,tin,tout,from,to,din=.4,dout=.3)=>{ const k=[[tin,from],[tin+din,0,'sig']]; if(tout!=null){ k.push([tout,0,'lin']); k.push([tout+dout,to,'in']); } return e.k(p,k); };
const up=(e,tin,tout)=>io(e,'iy',tin,tout,118,-118);
const fromR=(e,tin,tout)=>io(e,'ix',tin,tout,105,-105);
const K=(e,p,...keys)=>e.k(p,keys);
const BOFF=120; // body music starts at track 2:00 in the vertical cut
BEATS=BEATS.map(b=>b-BOFF).filter(b=>b>0);
const ST=[0,3.1,8.0,11.0,17.5,22.0,28.0,34.0,39.0,42.0,44.9].map((t,i)=>(i==0||i==10)?t:nb(t));
const END=53.4;
const sc=(i)=>{ const st=ST[i], D=(ST[i+1]??END)-st; return [x=>st+x, D, st]; };
T('بيانات تجريبية · واجهة عربية',{size:26,w:400,color:C.mid,bg:'rgba(244,246,249,.88)',pad:'0 .5em',x:1020,y:1560,ax:1,ay:.5,z:900,t0:ST[1]+.3,t1:ST[8]});
T('بيانات تجريبية · واجهة عربية',{size:26,w:400,color:C.mid,bg:'rgba(244,246,249,.88)',pad:'0 .5em',x:1020,y:1560,ax:1,ay:.5,z:900,t0:ST[9]+.3,t1:ST[10]-.5});

// ---------- S0 OPENING ----------
{ const [a,D]=sc(0);
  const nour=IMG('tex/nour.png',{w:800,h:493,x:520,y:840,r:-3,depth:2,z:3,paper:true,t0:0,t1:a(D)});
  K(nour,'x',[a(.1),-700],[a(.55),520]); K(nour,'r',[a(.1),-12],[a(.55),-3]);
  const sayed=IMG('tex/sayed.png',{w:760,h:468,x:600,y:1500,r:2.5,depth:2,z:4,paper:true,t0:0,t1:a(D)}); K(sayed,'y',[a(.2),2300],[a(.65),1500]);
  const wa11=IMG('tex/wa11.jpg',{w:470,h:700,x:790,y:1180,r:5,depth:3,z:5,t0:0,t1:a(D)}); K(wa11,'x',[a(0),1700],[a(.45),790]); K(wa11,'r',[a(0),16],[a(.45),5]);
  const wa7=IMG('tex/wa7.jpg',{w:420,h:625,x:290,y:1280,r:-6,depth:3,z:6,t0:0,t1:a(D)}); K(wa7,'y',[a(.3),2400],[a(.8),1280]); K(wa7,'r',[a(.3),-18],[a(.8),-6]);
  const t1=T('عروض واتساب…',{size:118,x:1030,y:390,ax:1,z:10,t0:a(.4),t1:a(D)}); up(t1,a(.45));
  const ul=R({w:730,h:18,x:1030,y:485,ax:1,ay:.5,z:9,color:C.ink,t0:a(.75),t1:a(D)}); K(ul,'sx',[a(.8),0],[a(1.15),1]);
  const t2=T('ونسخ يدوي؟',{size:118,x:960,y:620,ax:1,z:11,r:-1.5,bg:C.card,pad:'0 .3em .05em',depth:2,t0:a(1.0),t1:a(D)});
  K(t2,'x',[a(1.05),1900],[a(1.5),960]); K(t2,'r',[a(1.05),-6],[a(1.5),-1.5]);
}
// ---------- S1 LOW STOCK ----------
{ const [a,D]=sc(1);
  const pl=R({w:W,h:H,x:0,y:0,ax:0,ay:0,z:2,color:C.mist,t0:a(0),t1:a(D)}); K(pl,'cb',[a(.05),0],[a(.55),64]);
  const w1=T('نقص',{size:230,x:1030,y:350,ax:1,z:12,t0:a(.3),t1:a(D)}); up(w1,a(.35),a(D-.45));
  const w2=T('المخزون',{size:130,x:1030,y:545,ax:1,z:12,t0:a(.45),t1:a(D)}); up(w2,a(.5),a(D-.42));
  const k=IMG('tex/kitchen.jpg',{w:420,h:346,x:250,y:420,r:-3,depth:1,z:4,t0:a(.3),t1:a(D)}); K(k,'x',[a(.35),-400],[a(.8),250]);
  const ph=PLATE('low',{w:560,x:540,y:1240,z:8,depth:3,t0:a(.1),t1:a(D),map:PM([[a(.6),3.0,1.6,a(4.3)]])}); K(ph,'y',[a(.15),2700],[a(.6),1240]);
  const cap=T('بلاغ نقص المخزون من الموبايل',{size:34,w:500,x:1030,y:1640,ax:1,z:12,bg:C.card,pad:'0 .3em',t0:a(.8),t1:a(D)}); up(cap,a(.9),a(D-.4));
  const ink=R({w:W,h:H,x:0,y:H,ax:0,ay:0,z:60,color:C.ink,t0:a(D-.5),t1:a(D)+.01}); K(ink,'y',[a(D-.45),H],[a(D),0,'sig']);
}
// ---------- S2 RFQ ----------
{ const [a,D]=sc(2);
  const col=R({w:W,h:H,x:0,y:0,ax:0,ay:0,z:2,color:C.ink,t0:a(0),t1:a(D)}); K(col,'cb',[a(.6),0],[a(1.1),64],[a(D-.45),64,'lin'],[a(D),100,'in']);
  const one=T('واحد',{size:300,color:C.card,x:540,y:960,z:12,t0:a(0),t1:a(D)}); up(one,a(.03));
  K(one,'y',[a(.6),960],[a(1.1),330,'sig'],[a(D-.45),330,'lin'],[a(D),-400,'in']); K(one,'s',[a(.6),1],[a(1.1),.7]);
  const l1=T('طلب عرض سعر',{size:58,color:C.card,x:540,y:500,z:12,t0:a(.9),t1:a(D)}); up(l1,a(1.0),a(D-.45));
  const l2=T('لكل الموردين',{size:58,color:C.tealDark,x:540,y:580,z:12,t0:a(1.0),t1:a(D)}); up(l2,a(1.1),a(D-.45));
  const form=PLATE('rfqform',{w:1000,crop:[20,40,950,780],x:540,y:1110,z:7,depth:3,t0:a(.7),t1:a(D),map:PM([[a(1.2),9.0,2.6,a(D)]])});
  K(form,'y',[a(.75),2700],[a(1.2),1110],[a(D-.45),1110,'lin'],[a(D),2900,'in']);
}
// ---------- S3 PHOTO / FIELDS ----------
{ const [a,D]=sc(3);
  const ph=IMG('tex/wa11.jpg',{w:600,h:893,x:250,y:560,r:-4,depth:3,z:8,t0:a(-.45),t1:a(3.6)});
  K(ph,'x',[a(-.45),-600],[a(.1),250,'sig'],[a(3.0),250,'lin'],[a(3.45),-700,'in']); K(ph,'r',[a(-.45),-16],[a(.1),-4]); K(ph,'s',[a(-.45),1.2],[a(.1),.5]);
  const w1=T('صورة',{size:220,x:1030,y:380,ax:1,z:4,t0:a(.1),t1:a(3.6)}); K(w1,'cl',[a(.12),100],[a(.5),0]); up(w1,a(-1),a(3.0));
  const w2=T('عرض سعر',{size:90,x:1030,y:560,ax:1,z:4,t0:a(.3),t1:a(3.6)}); up(w2,a(.35),a(3.0));
  const pp=PLATE('photo',{w:900,crop:[660,0,630,620],x:560,y:1140,z:7,depth:3,t0:a(.4),t1:a(3.6),map:PM([[a(.9),.5,1,a(3.2)]])});
  K(pp,'y',[a(.45),2700],[a(.9),1140],[a(3.0),1140,'lin'],[a(3.45),2900,'in']);
  const ex=T('استخراج',{size:110,x:1000,y:1500,ax:1,z:14,bg:C.mist,pad:'0 .25em .04em',t0:a(1.3),t1:a(3.6)}); K(ex,'cl',[a(1.35),100],[a(1.75),0]); up(ex,a(-1),a(3.0));
  const ex2=T('ثم مراجعة بشرية',{size:46,x:1000,y:1600,ax:1,z:14,bg:C.card,pad:'0 .3em',t0:a(1.5),t1:a(3.6)}); up(ex2,a(1.6),a(3.0));
  const num=T('٢٥٬١٤٠',{size:240,x:540,y:420,z:12,t0:a(3.25),t1:a(D)}); K(num,'x',[a(3.3),-700],[a(3.75),540]); K(num,'s',[a(3.3),1.7],[a(3.75),1]); K(num,'y',[a(D-.45),420],[a(D),-300,'in']);
  const ul=R({w:600,h:18,x:840,y:540,ax:1,ay:.5,z:11,color:C.ink,t0:a(3.7),t1:a(D)}); K(ul,'sx',[a(3.8),0],[a(4.15),1],[a(D-.45),1,'lin'],[a(D-.2),0,'in']);
  const egp=T('ج.م',{size:80,x:840,y:630,ax:1,z:12,t0:a(3.6),t1:a(D)}); up(egp,a(3.7),a(D-.45));
  const fl=T('الإجمالي مطابق للبنود',{size:50,x:840,y:730,ax:1,z:12,t0:a(3.9),t1:a(D)}); up(fl,a(4.0),a(D-.45));
  const fp=PLATE('fields',{w:1040,crop:[0,0,928,620],x:540,y:1180,z:7,depth:3,t0:a(3.3),t1:a(D),map:PM([[a(3.8),0,1.3,a(D)]])});
  K(fp,'y',[a(3.35),-500],[a(3.8),1180],[a(D-.45),1180,'lin'],[a(D),2600,'in']);
  const grow=R({w:W,h:H,x:0,y:0,ax:0,ay:0,z:70,color:C.mist,t0:a(D-.45),t1:a(D)+.01}); K(grow,'ct',[a(D-.45),100],[a(D),0]);
}
// ---------- S4 COMPARE / PRICES ----------
{ const [a,D]=sc(4);
  const band=R({w:W,h:H,x:0,y:0,ax:0,ay:0,z:2,color:C.mist,t0:a(0),t1:a(D)}); K(band,'cb',[a(.6),0],[a(1.1),65],[a(D-.45),65,'lin'],[a(D),100,'in']);
  const m=T('مقارنة',{size:250,x:540,y:960,z:12,t0:a(0),t1:a(2.0)}); up(m,a(.03),a(1.55)); K(m,'y',[a(.6),960],[a(1.1),330]); K(m,'s',[a(.6),1],[a(1.1),.75]);
  const m2=T('عروض الزيت × ٨ عبوات',{size:50,x:540,y:520,z:12,t0:a(.9),t1:a(2.0)}); up(m2,a(1.0),a(1.55));
  const pp=PLATE('prices',{w:1320,crop:[700,30,1100,360],x:540,y:1060,z:8,depth:3,t0:a(.8),t1:a(D),map:PM([[a(1.25),0,1,a(D)]])});
  K(pp,'x',[a(.85),2300],[a(1.25),540]); K(pp,'y',[a(D-.45),1060],[a(D),2700,'in']);
  const n1=T('١٢٬٨٨٠',{size:190,x:1030,y:330,ax:1,z:13,t0:a(1.7),t1:a(D)}); up(n1,a(1.8)); K(n1,'s',[a(D-.45),1],[a(D),5,'in']); K(n1,'o',[a(D-.15),1],[a(D),0,'lin']);
  const ub=R({w:620,h:18,x:1030,y:435,ax:1,ay:.5,z:13,color:C.teal,radius:9,t0:a(2.0),t1:a(D-.35)}); K(ub,'sx',[a(2.1),0],[a(2.45),1]);
  const vs=T('مقابل',{size:50,x:1030,y:510,ax:1,z:13,t0:a(1.9),t1:a(D-.35)}); up(vs,a(2.0),a(D-.5));
  const n2=T('١٣٬٠٨٠',{size:90,color:C.mid,x:860,y:505,ax:1,z:13,t0:a(2.0),t1:a(D-.35)}); up(n2,a(2.1),a(D-.5));
  const eg=T('ج.م',{size:50,x:500,y:510,ax:1,z:13,t0:a(2.1),t1:a(D-.35)}); up(eg,a(2.2),a(D-.5));
  const ox=T('الزيت × ٨',{size:42,x:1030,y:595,ax:1,z:13,t0:a(2.2),t1:a(D-.35)}); up(ox,a(2.3),a(D-.5));
}
// ---------- S5 GUARDRAILS / SUBMIT ----------
{ const [a,D]=sc(5);
  const dp=PLATE('draft',{w:1260,crop:[780,30,1020,300],x:540,y:1020,z:7,depth:3,t0:a(0),t1:a(3.3),map:PM([[a(.5),0,1,a(3.0)]])});
  K(dp,'x',[a(.05),-700],[a(.5),540]); K(dp,'y',[a(2.8),1020],[a(3.25),2600,'in']);
  const g1=T('الضوابط',{size:210,x:1030,y:360,ax:1,z:12,t0:a(.15),t1:a(3.3)}); up(g1,a(.2)); K(g1,'x',[a(2.8),1030],[a(3.25),-300,'in']);
  const g2=T('تجهّز المسودة',{size:80,x:1030,y:560,ax:1,z:12,t0:a(.35),t1:a(3.3)}); up(g2,a(.4)); K(g2,'x',[a(2.8),1030],[a(3.25),-300,'in']);
  const g3=T('والقرار للمدير',{size:80,color:C.teal,x:1030,y:665,ax:1,z:12,t0:a(.55),t1:a(3.3)}); up(g3,a(.6)); K(g3,'x',[a(2.85),1030],[a(3.3),-300,'in']);
  const sp=PLATE('submit',{w:700,x:540,y:1150,z:7,depth:3,t0:a(2.8),t1:a(D),map:PM([[a(3.25),3.0,1.4,a(D)]])});
  K(sp,'y',[a(2.85),2700],[a(3.25),1150],[a(D-.45),1150,'lin'],[a(D),2700,'in']);
  const r1=T('راجع المسودة',{size:150,x:1030,y:400,ax:1,z:12,t0:a(3.0),t1:a(D)}); up(r1,a(3.1),a(D-.45));
  const r3=T('ثم أرسلها للاعتماد',{size:56,x:1030,y:580,ax:1,z:12,t0:a(3.25),t1:a(D)}); up(r3,a(3.35),a(D-.45));
  const ink=R({w:W,h:680,x:0,y:0,ax:0,ay:0,z:40,color:C.ink,t0:a(D-.45),t1:a(D)+.01}); K(ink,'cb',[a(D-.45),100],[a(D),0]);
}
// ---------- S6 APPROVE ----------
{ const [a,D]=sc(6);
  const panel=R({w:W,h:680,x:0,y:0,ax:0,ay:0,z:2,color:C.ink,t0:a(0),t1:a(D)}); K(panel,'y',[a(D-.45),0],[a(D),-950,'in']);
  const m1=T('المدير',{size:220,color:C.card,x:1030,y:290,ax:1,z:6,t0:a(.05),t1:a(4.0)}); up(m1,a(.1));
  const m2=T('يراجع ويعتمد',{size:76,color:C.card,x:1030,y:465,ax:1,z:6,t0:a(.25),t1:a(4.0)}); up(m2,a(.3));
  const m3=T('من الموبايل',{size:76,color:C.mist,x:1030,y:560,ax:1,z:6,t0:a(.4),t1:a(4.0)}); up(m3,a(.45));
  const m4=T('اعتماد الطلب',{size:48,color:C.card,x:1030,y:650,ax:1,z:6,t0:a(2.5),t1:a(4.0)}); up(m4,a(2.6));
  const ph=PLATE('approve',{w:480,x:540,y:1220,z:8,depth:3,t0:a(.1),t1:a(D),map:PM([[a(.55),2.0,1.6,a(3.6)],[a(3.6),9.9,1,a(4.2)]])});
  K(ph,'y',[a(.15),2700],[a(.55),1220],[a(D-.45),1220,'lin'],[a(D),2800,'in']);
  const op=R({w:W,h:680,x:0,y:0,ax:0,ay:0,z:10,t0:a(3.55),t1:a(D)}); K(op,'cl',[a(3.6),100],[a(3.9),0]); K(op,'y',[a(D-.45),0],[a(D),-950,'in']);
  const d1=T('تم اعتماد',{size:190,x:1030,y:290,ax:1,z:12,t0:a(3.7),t1:a(D)}); up(d1,a(3.75)); K(d1,'y',[a(D-.45),290],[a(D),-660,'in']);
  const d2=T('الطلب',{size:190,x:1030,y:510,ax:1,z:12,t0:a(3.85),t1:a(D)}); up(d2,a(3.9)); K(d2,'y',[a(D-.45),510],[a(D),-440,'in']);
}
// ---------- S7 SENT / OUTCOME ----------
{ const [a,D]=sc(7);
  const id=T('PO-000006',{size:130,dir:'ltr',x:60,y:380,ax:0,z:13,t0:a(0),t1:a(2.8)}); K(id,'x',[a(.05),-900],[a(.45),60],[a(2.3),60,'lin'],[a(2.75),-1000,'in']); K(id,'s',[a(.05),1.4],[a(.45),1]);
  const iu=R({w:760,h:16,x:66,y:470,ax:0,ay:.5,z:12,color:C.ink,t0:a(.5),t1:a(2.8)}); K(iu,'sx',[a(.55),0],[a(.9),1],[a(2.3),1,'lin'],[a(2.55),0,'in']);
  const sn=T('تم إرسال أمر الشراء',{size:60,x:1030,y:560,ax:1,z:13,t0:a(.5),t1:a(2.8)}); up(sn,a(.55),a(2.3));
  const sp=PLATE('sent',{w:1000,crop:[300,0,830,600],x:540,y:1110,z:8,depth:3,t0:a(.1),t1:a(2.9),map:PM([[a(.5),1.0,1.4,a(2.8)]])});
  K(sp,'y',[a(.1),-500],[a(.5),1110],[a(2.3),1110,'lin'],[a(2.75),2800,'in']);
  const o1=T('تسجيل النتيجة',{size:140,x:1030,y:380,ax:1,z:13,t0:a(2.4),t1:a(D)}); up(o1,a(2.5));
  const o2=T('من أمر الشراء',{size:60,x:1030,y:540,ax:1,z:13,t0:a(2.55),t1:a(D)}); up(o2,a(2.65));
  const rp=PLATE('result',{w:1000,crop:[500,0,1104,700],x:540,y:1080,z:9,depth:3,t0:a(2.3),t1:a(D),map:PM([[a(2.75),1.0,1,a(D)]])}); K(rp,'x',[a(2.35),2100],[a(2.75),540]);
  const grow=R({w:W,h:H,x:0,y:0,ax:0,ay:0,z:70,t0:a(D-.45),t1:a(D)+.01}); for(const p of ['ct','cb','cl','cr']) K(grow,p,[a(D-.45),48],[a(D),0]);
}
// ---------- S8 COUNTER ----------
{ const [a,D]=sc(8);
  const blk=R({w:W,h:H,x:0,y:0,ax:0,ay:0,z:2,t0:a(0),t1:a(D)});
  K(blk,'ct',[a(.05),0],[a(.5),37]); K(blk,'cb',[a(.05),0],[a(.5),37]); K(blk,'cl',[a(.05),0],[a(.5),11]); K(blk,'cr',[a(.05),0],[a(.5),11]); K(blk,'y',[a(D-.4),0],[a(D),-2000,'in']);
  const h1=T('وفّر الطلب ده',{size:72,x:540,y:600,z:12,t0:a(.25),t1:a(D)}); up(h1,a(.3),a(D-.35));
  const n=T('٠',{size:330,x:540,y:950,z:12,t0:a(.3),t1:a(D)}); up(n,a(.35)); K(n,'y',[a(D-.4),950],[a(D),-1000,'in']);
  const t0=a(.45),t1=a(1.25); const AR='٠١٢٣٤٥٦٧٨٩';
  n.update=(t)=>{ const u=EASE.out(Math.max(0,Math.min(1,(t-t0)/(t1-t0)))); const v=String(Math.round(460*u)).replace(/\d/g,d=>AR[d]); if(n.inner.textContent!==v) n.inner.textContent=v; };
  const eg=T('ج.م',{size:80,x:540,y:1290,z:12,t0:a(.9),t1:a(D)}); up(eg,a(1.0),a(D-.35));
  const l1=T('مقابل أسعار آخر أوامر شراء',{size:44,x:540,y:1400,z:12,t0:a(1.0),t1:a(D)}); up(l1,a(1.1),a(D-.35));
  const l2=T('بيانات تجريبية · زيت +٢٤٠ · أرز +١٨٠ · بصل +٤٠',{size:30,w:400,color:C.mid,x:540,y:1470,z:12,t0:a(1.1),t1:a(D)}); up(l2,a(1.2),a(D-.35));
}
// ---------- S9 LEDGER ----------
{ const [a,D]=sc(9);
  const lp=PLATE('ledger',{w:900,crop:[560,40,808,640],x:540,y:1180,z:7,depth:3,t0:a(0),t1:a(D),map:PM([[a(.4),4.5,1,a(D)]])});
  K(lp,'y',[a(0),2700],[a(.4),1180],[a(D-.5),1180,'lin'],[a(D-.1),2800,'in']);
  const n=T('١٬٠٦٠',{size:200,x:1000,y:400,ax:1,z:12,t0:a(.2),t1:a(D)}); up(n,a(.25),a(D-.45));
  const u=R({w:560,h:16,x:1000,y:520,ax:1,ay:.5,z:12,t0:a(.4),t1:a(D)}); K(u,'sx',[a(.45),0],[a(.8),1],[a(D-.5),1,'lin'],[a(D-.3),0,'in']);
  const e=T('ج.م',{size:70,x:1000,y:605,ax:1,z:12,t0:a(.4),t1:a(D)}); up(e,a(.45),a(D-.45));
  const c=T('سجل تجريبي يشمل تجربة سابقة',{size:42,x:1000,y:700,ax:1,z:12,t0:a(.5),t1:a(D)}); up(c,a(.55),a(D-.45));
}
// ---------- BRAND BAR WIPES (Converge mark: navy / teal + arrow / navy, left to right) ----------
for(const i of [1,5,7]) PASS(ST[i],{W,H,dur:.75});

// ---------- OUTRO (fast sting, 2/3 timing, beat-locked to the approved vertical outro audio) ----------
// The mark builds from its own geometry and colours, then the official stacked lockup is revealed
// over it; the end card uses the official on-dark lockup. The logo itself is never redrawn.
{ const st=ST[10]; const a=x=>st+x; const D=END-st; const LOGO='../../../../brand/logo/';
  const sc=1.52, LW=631.6*sc, LH=404.2*sc, Lx=(W-LW)/2, Ly=380;        // stacked lockup, px per viewBox unit
  const u=4.0625*sc, mx=Lx+185.8*sc, my=Ly+20*sc;
  const bar=(x,y,w,h,color,t,dur)=>{ const e=R({w:w*u,h:h*u,x:mx+x*u,y:my+y*u,ax:0,ay:0,z:10,color,radius:h*u/2,t0:t-.01,t1:a(3.1)}); K(e,'sx',[t,0],[t+dur,1,'out']); return e; };
  bar(6,14,22,8,C.ink,a(.356),.22); bar(6,42,16,8,C.ink,a(.534),.22); bar(6,28,34,8,C.teal,a(.534),.36);
  const arrow=div('rect'); arrow.style.width=(26*u)+'px'; arrow.style.height=(30*u)+'px';
  arrow.innerHTML=`<svg viewBox="34 17 26 30" width="100%" height="100%"><path d="M36 20 L58 32 L36 44 Z" fill="${C.teal}" stroke="${C.teal}" stroke-width="3" stroke-linejoin="round"/></svg>`;
  const ar=new El(arrow,{x:mx+34*u,y:my+32*u,ax:0,ay:.5,z:11,t0:a(1.0),t1:a(3.1)});
  K(ar,'x',[a(1.0),mx+20*u],[a(1.17),mx+34*u,'out']); K(ar,'s',[a(1.0),.3],[a(1.17),1,'out']);
  const lock=IMG(LOGO+'procurepilot-stacked.svg',{w:LW,h:LH,x:Lx,y:Ly,ax:0,ay:0,z:12,fit:'contain',t0:a(1.23),t1:a(3.1)});
  K(lock,'cr',[a(1.247),100],[a(1.781),0,'io']);
  const tg=[['قارن.',C.ink,.356,820],['اختار.',C.ink,.67,560],['وفّر.',C.teal,1.068,300]];
  tg.forEach(([s,col,t,x])=>{ const e=T(s,{size:84,color:col,x:x,y:Ly+LH+130,z:10,t0:a(t)-.01,t1:a(3.1)}); up(e,a(t)); });
  // end card: navy band with the official on-dark lockup; contact on paper
  const pl=R({w:W,h:H,x:0,y:0,ax:0,ay:0,z:40,color:C.ink,t0:a(2.8),t1:a(D)+.1}); K(pl,'cl',[a(2.8),100],[a(3.05),0]); K(pl,'cb',[a(3.1),0],[a(3.5),64]);
  const dk=IMG(LOGO+'procurepilot-horizontal-dark.svg',{w:800,h:184,x:540,y:420,z:42,fit:'contain',t0:a(3.25),t1:a(D)+.1});
  K(dk,'y',[a(3.25),560],[a(3.6),420,'out']); K(dk,'o',[a(3.25),0],[a(3.45),1,'lin']);
  const L=[['جرّبه أسبوعين مجانًا',{size:92,y:840}],['وإحنا اللي هنجهّزه معاك.',{size:48,w:500,y:950}],['واتساب',{size:30,w:500,color:C.mid,y:1060}],
    ['+20 102 735 4140',{size:86,w:600,dir:'ltr',color:C.tealText,y:1130}],['د. ياسر حسني — المؤسس',{size:38,w:500,y:1290}],['yasser.hosny@iron-sys.com',{size:32,w:400,dir:'ltr',y:1350}],['أحد منتجات Iron Systems',{size:28,w:400,color:C.mid,y:1450}]];
  const step=[1,2,3,3,4,4,5];
  L.forEach(([s,o],i)=>{ const e=T(s,Object.assign({x:1000,ax:1,z:41,t0:a(3.0),t1:a(D)+.1},o)); up(e,a(3.0+.2*step[i])); });
  const wu=R({w:680,h:12,x:1000,y:1192,ax:1,ay:.5,z:41,color:C.mist,t0:a(3.55),t1:a(D)+.1}); K(wu,'sx',[a(3.6),0],[a(3.95),1]);
}
window.DURATION=END;
