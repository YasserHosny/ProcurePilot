// Source crops exclude the recommendation validity line (y=663..681) and both validity columns.
function compareCrops(vertical,rtl){return {
  main:vertical?[rtl?850:260,520,810,135]:[260,520,1400,135],
  rows:rtl?[1110,826,550,142]:[260,826,450,142]
};}
// v2.4 compositions built on the forked v2.3 frame-addressed motion engine.
// Full-colour white-framed plates, asymmetric type and the original Converge wipes.
function buildTimeline(fmt,lang){
  const vertical=fmt==='v',rtl=lang==='ar',W=vertical?1080:1920,H=vertical?1920:1080;
  const timeline=window.TIMELINES[fmt];
  const tx=vertical?80:rtl?1400:60, tw=vertical?920:470;
  const align=rtl?'right':'left';
  function caption(copy,start,end){
    const e=T(copy,{size:vertical?58:53,w:700,dir:rtl?'rtl':'ltr',x:tx,y:vertical?290:240,ax:0,ay:0,z:50,t0:start,t1:end,lh:1.48});
    e.node.classList.add('caption');e.node.style.width=tw+'px';e.node.style.textAlign=align;
    e.k('iy',[[start,110],[start+.48,0,'out']]);
    return e;
  }
  function number(text,start,end,beat){
    const fast=beat===13,delay=fast||beat===1?0:.65,enter=fast?.15:.47;
    const e=T(text,{size:vertical?102:72,w:700,dir:rtl?'rtl':'ltr',color:C.ink,x:tx,y:vertical?650:745,ax:0,ay:0,z:52,t0:start+delay,t1:end});
    e.node.style.width=tw+'px';e.node.style.textAlign=align;
    e.k('iy',[[start+delay,beat===1?0:110],[start+delay+enter,0,'out']]);
    if(beat===13){e.update=t=>{const u=EASE.out(Math.max(0,Math.min(1,(t-start-.1)/.3)));e.inner.textContent=MONEY.prefix+amount(MONEY.saving*u)+MONEY.suffix;};}
    const bar=R({w:vertical?620:420,h:12,x:rtl?tx+tw:tx,y:vertical?790:850,ax:rtl?1:0,ay:0,color:C.teal,z:51,t0:start+(fast?.1:.8),t1:end});
    bar.k('sx',[[start+(fast?.1:.8),0],[start+(fast?.4:1.35),1,'out']]);
    if(beat===8){
      for(const [dy,width,color] of [[30,vertical?570:370,C.ink],[60,vertical?520:320,C.mist]]){
        const other=R({w:width,h:12,x:rtl?tx+tw:tx,y:(vertical?790:850)+dy,ax:rtl?1:0,ay:0,color,z:51,t0:start+.4,t1:end});
        other.k('sx',[[start+.4,0],[start+.8,1,'out']]);
      }
    }
  }

  const MARKET=window.MARKET||'eg', V25=timeline.v25[lang], MONEY=timeline.money[lang], K=(e,p,...keys)=>e.k(p,keys);
  const digits=n=>rtl?String(n).replace(/\d/g,d=>'٠١٢٣٤٥٦٧٨٩'[d]):String(n);
  const amount=v=>digits(MONEY.decimals?v.toFixed(MONEY.decimals):String(Math.round(v)));
  function problemPapers(st,D,copy){
    // v2.3 brand opening (paper quotes and WhatsApp photos from this market's own rounds), 2.5 s, with the v2.5 line.
    const a=x=>st+x, end=st+D, tex='tex/'+MARKET+'/';
    const L=vertical?{p1:[760,468,540,760,-3],p2:[700,431,560,1180,2.5],f1:[400,596,830,1530,5],f2:[360,536,250,1500,-6],tx:rtl?1010:50,ty:250,ts:70}
                    :{p1:[760,468,600,300,-3],p2:[700,431,1080,790,2.5],f1:[470,700,1510,640,5],f2:[420,625,330,760,-6],tx:rtl?1850:70,ty:250,ts:150};
    const put=(src,[w,h,x,y,r],z,depth,paper)=>IMG(tex+src,{w,h,x,y,r,depth,z,paper,t0:st,t1:end});
    const nour=put('paper1.png',L.p1,3,2,true); K(nour,'x',[a(.05),-700],[a(.5),L.p1[2]]); K(nour,'r',[a(.05),-12],[a(.5),L.p1[4]]);
    const sayed=put('paper2.png',L.p2,4,2,true); K(sayed,'y',[a(.15),H+500],[a(.6),L.p2[3]]); K(sayed,'r',[a(.15),10],[a(.6),L.p2[4]]);
    const wa11=put('photo1.jpg',L.f1,5,3,false); K(wa11,'x',[a(0),W+600],[a(.4),L.f1[2]]); K(wa11,'r',[a(0),16],[a(.4),L.f1[4]]);
    const wa7=put('photo2.jpg',L.f2,6,3,false); K(wa7,'y',[a(.25),H+600],[a(.7),L.f2[3]]); K(wa7,'r',[a(.25),-18],[a(.7),L.f2[4]]);
    // Card and text arrive together (owner, 2026-10-26: no blank card before the text).
    const t1=T(copy,{size:L.ts,x:L.tx,y:L.ty,ax:rtl?1:0,z:10,dir:rtl?'rtl':'ltr',bg:C.card,pad:'0 .3em .08em',depth:2,t0:st,t1:end});
    t1.k('x',[[st,rtl?W+800:-900],[a(.4),L.tx,'out']]);
    for(const e of [nour,sayed,wa11,wa7,t1]){ const k=e.tr.x||[[st,e.o.x]]; e.k('x',[...k,[a(D-.45),k[k.length-1][1],'lin'],[a(D),k[k.length-1][1]-260,'in']]); }
  }
  function painList(st,D,lines){
    const end=st+D;
    lines.forEach((line,i)=>{
      const t0=st+.15+i*(vertical?.8:.95), y=vertical?470+i*360:250+i*190, size=vertical?68:96;
      const e=T(line,{size,w:700,dir:rtl?'rtl':'ltr',x:vertical?(rtl?990:110):(rtl?1820:100),y,ax:rtl?1:0,ay:0,z:20,t0,t1:end,lh:1.3});
      // Portrait: a long line wraps to two inside the 880-px column instead of running off the frame.
      if(vertical){e.node.classList.add('caption');e.node.style.width='880px';e.node.style.textAlign=rtl?'right':'left';}
      e.k('iy',[[t0,118],[t0+.45,0,'sig']]);
      const rule=R({w:14,h:size*1.25,x:vertical?(rtl?1030:70):(rtl?1860:60),y:y+12,ax:rtl?1:0,ay:0,z:20,color:C.ink,t0,t1:end}); rule.k('sy',[[t0,0],[t0+.35,1,'out']]);
    });
  }
  function turnCard(st,D,copy){
    // The brand's first appearance: the Converge mark builds from its official geometry (brand/logo, 64-unit
    // grid), the wordmark is revealed beside it, then the category line and the promise. Always LTR lockup.
    const end=st+D, a=x=>st+x;
    PASS(st,{W,H,dur:.65});
    R({w:W,h:H,x:0,y:0,ax:0,ay:0,z:600,color:C.ink,t0:st,t1:end});
    const LW=vertical?900:1100, sc=LW/957, left=W/2-LW/2, top=(vertical?700:360)-220*sc/2, u=2.8125*sc, ox=left+20*sc, oy=top+20*sc;
    [[14,22,C.mist,.3],[42,16,C.mist,.38],[28,34,C.tealDark,.48]].forEach(([y,w,color,t0])=>{
      const bar=R({w:w*u,h:8*u,radius:4*u,x:ox+6*u,y:oy+y*u,ax:0,ay:0,z:612,color,t0:a(t0),t1:end});
      K(bar,'sx',[a(t0),0],[a(t0+.38),1,'out']);
    });
    const head=div('rect'); head.style.background='none';
    head.innerHTML='<svg viewBox="34 18 26 28" width="100%" height="100%"><path d="M36 20 L58 32 L36 44 Z" fill="#19B8A4" stroke="#19B8A4" stroke-width="3" stroke-linejoin="round"/></svg>';
    head.style.width=26*u+'px'; head.style.height=28*u+'px';
    const arrow=new El(head,{x:ox+34*u,y:oy+32*u,ax:0,ay:.5,z:613,t0:a(.78),t1:end});
    K(arrow,'x',[a(.78),ox+20*u],[a(1.02),ox+34*u,'out']); K(arrow,'s',[a(.78),.5],[a(1.05),1,'out']); K(arrow,'o',[a(.78),0],[a(.9),1,'out']);
    const markEnd=(229/957)*100;
    const word=IMG('../../../../brand/logo/procurepilot-horizontal-dark.svg',{w:LW,h:220*sc,x:left,y:top,ax:0,ay:0,z:611,fit:'contain',cl:markEnd,t0:a(.95),t1:end});
    K(word,'cr',[a(.95),100-markEnd],[a(1.55),0,'out']); K(word,'x',[a(.95),left-40],[a(1.55),left,'out']);
    const Y=vertical?[960,1110,1205]:[590,740,835];
    const sub=T(copy[0],{size:60,w:500,dir:rtl?'rtl':'ltr',color:C.mist,x:W/2,y:Y[0],z:612,t0:a(1.5),t1:end});
    sub.k('iy',[[a(1.5),118],[a(1.95),0,'sig']]);
    const line=T(copy[1],{size:96,w:700,dir:rtl?'rtl':'ltr',color:'#FFFFFF',x:W/2,y:Y[1],z:612,t0:a(1.85),t1:end});
    line.k('iy',[[a(1.85),118],[a(2.3),0,'sig']]);
    const bar=R({w:560,h:12,x:W/2,y:Y[2],z:611,color:C.tealDark,t0:a(2.15),t1:end}); bar.k('sx',[[a(2.15),0],[a(2.6),1,'out']]);
  }
  function savingPage(st,D,text){
    // Full-page saving (v2.3 style), counter rolls from 0.
    const end=st+D, Y=vertical?{title:420,block:[900,640,960],num:900,cur:1140,sub:1420}:{title:150,block:[900,540,560],num:520,cur:745,sub:930};
    const bg=R({w:W,h:H,x:0,y:0,ax:0,ay:0,z:700,color:C.paper,t0:st,t1:end}); bg.k('o',[[st,0],[st+.2,1,'out']]);
    const title=T(text[0],{size:vertical?84:96,w:700,dir:rtl?'rtl':'ltr',x:W/2,y:Y.title,z:710,t0:st+.1,t1:end}); title.k('iy',[[st+.1,118],[st+.55,0,'sig']]);
    const block=R({w:Y.block[0],h:Y.block[1],x:W/2,y:Y.block[2],z:705,color:C.teal,t0:st+.2,t1:end}); block.k('sy',[[st+.2,0],[st+.6,1,'out']]);
    const big=MONEY.label?'':MONEY.prefix;  // no currency line (euro): the sign stays on the number
    const num=T('0',{size:MONEY.decimals?250:330,w:700,dir:'ltr',x:W/2,y:Y.num,z:711,t0:st+.45,t1:end});
    num.update=t=>{const u=EASE.out(Math.max(0,Math.min(1,(t-st-.5)/.9)));num.inner.textContent=big+amount(MONEY.saving*u);};
    if(MONEY.label){const cur=T(MONEY.label,{size:96,w:700,dir:rtl?'rtl':'ltr',x:W/2,y:Y.cur,z:711,t0:st+.6,t1:end}); cur.k('iy',[[st+.6,118],[st+1,0,'sig']]);}
    const sub=T(text[1],{size:58,w:500,dir:rtl?'rtl':'ltr',color:C.ink,x:W/2,y:Y.sub,z:710,t0:st+.9,t1:end}); sub.k('iy',[[st+.9,118],[st+1.3,0,'sig']]);
  }
  function recapCard(st,D,data){
    const end=st+D;
    PASS(st,{W,H,dur:.65});
    R({w:W,h:H,x:0,y:0,ax:0,ay:0,z:2,color:C.paper,t0:st,t1:end});
    if(vertical)return recapPortrait(st,D,data);
    const title=T(data.title,{size:84,w:700,dir:rtl?'rtl':'ltr',x:rtl?1820:100,y:110,ax:rtl?1:0,ay:0,z:20,t0:st+.3,t1:end}); title.k('iy',[[st+.3,118],[st+.75,0,'sig']]);
    const colPain=rtl?1820:100, colFix=rtl?1060:860;
    data.rows.forEach(([pain,fix],i)=>{
      const t0=st+.8+i*.55, y=300+i*140;
      const pe=T(pain,{size:48,w:500,dir:rtl?'rtl':'ltr',color:C.mid,x:colPain,y,ax:rtl?1:0,ay:0,z:20,t0,t1:end}); pe.k('iy',[[t0,118],[t0+.4,0,'sig']]);
      pe.inner.style.textDecorationColor=C.mid; pe.inner.style.textDecorationThickness='3px';
      const peUpdate=pe.update; pe.update=t=>{ if(peUpdate)peUpdate(t); pe.inner.style.textDecorationLine=t>=t0+.45?'line-through':'none'; };
      const arrow=T(rtl?'←':'→',{size:48,w:500,color:C.teal,dir:'ltr',x:rtl?1180:740,y,ax:.5,ay:0,z:20,t0:t0+.25,t1:end});
      const fe=T(fix,{size:50,w:700,dir:rtl?'rtl':'ltr',color:C.ink,x:colFix,y,ax:rtl?1:0,ay:0,z:20,t0:t0+.3,t1:end}); fe.k('iy',[[t0+.3,118],[t0+.7,0,'sig']]);
      const tick=R({w:12,h:56,x:rtl?colFix+30:colFix-30,y:y+8,ax:.5,ay:0,z:20,color:C.teal,t0:t0+.3,t1:end}); tick.k('sy',[[t0+.3,0],[t0+.6,1,'out']]);
    });
  }
  function recapPortrait(st,D,data){
    const end=st+D, x=rtl?1000:80, ax=rtl?1:0, dir=rtl?'rtl':'ltr';
    const title=T(data.title,{size:76,w:700,dir,x,y:230,ax,ay:0,z:20,t0:st+.3,t1:end}); title.k('iy',[[st+.3,118],[st+.75,0,'sig']]);
    data.rows.forEach(([pain,fix],i)=>{
      const t0=st+.7+i*.45, y=470+i*260;
      const pe=T(pain,{size:44,w:500,dir,color:C.mid,x,y,ax,ay:0,z:20,t0,t1:end}); pe.k('iy',[[t0,118],[t0+.4,0,'sig']]);
      pe.inner.style.textDecorationColor=C.mid; pe.inner.style.textDecorationThickness='3px';
      const peUpdate=pe.update; pe.update=t=>{ if(peUpdate)peUpdate(t); pe.inner.style.textDecorationLine=t>=t0+.45?'line-through':'none'; };
      const fe=T(fix,{size:50,w:700,dir,color:C.ink,x:rtl?x-34:x+34,y:y+76,ax,ay:0,z:20,t0:t0+.3,t1:end}); fe.k('iy',[[t0+.3,118],[t0+.7,0,'sig']]);
      const tick=R({w:12,h:56,x:rtl?x-6:x+6,y:y+84,ax:.5,ay:0,z:20,color:C.teal,t0:t0+.3,t1:end}); tick.k('sy',[[t0+.3,0],[t0+.6,1,'out']]);
    });
  }
  for(const scene of timeline.scenes){
    const st=scene.start,end=st+scene.duration;
    if(scene.beat==='p1'){problemPapers(st,scene.duration,V25.p1);continue;}
    if(scene.beat==='p3'){painList(st,scene.duration,V25.p3);continue;}
    if(scene.beat==='turn'){turnCard(st,scene.duration,V25.turn);continue;}
    if(scene.beat==='recap'){recapCard(st,scene.duration,V25.recap);continue;}
    if(scene.beat===0){
      // v2.5: the opening animation as a framed plate beside the caption panel, so no copy covers the sheet.
      R({w:vertical?W:520,h:vertical?650:H,x:rtl?W:0,y:0,ax:rtl?1:0,ay:0,z:1,color:C.mist,t0:st,t1:end});
      if(vertical){const op=PLATE('opening-v',{w:960,x:540,y:1250,z:10,depth:2,t0:st,t1:end,map:t=>t-st}); op.k('y',[[st,1330],[st+.45,1250,'out']]);}
      else{const op=PLATE('opening-h',{w:1260,x:rtl?670:1250,y:H/2,z:10,depth:2,t0:st,t1:end,map:t=>t-st}); op.k('x',[[st,rtl?470:1450],[st+.45,rtl?670:1250,'out']]);}
      caption(scene.cards_by_language[lang][0].text,st+.12,end);
      continue;
    }
    for(const card of scene.cards_by_language[lang])caption(card.text,st+card.offset+(card.offset===0?.08:0),st+card.offset+card.duration);
    const panel=R({w:vertical?W:520,h:vertical?650:H,x:rtl?W:0,y:0,ax:rtl?1:0,ay:0,z:1,color:C.mist,t0:st,t1:end});
    panel.k('sx',[[st,.96],[st+.5,1,'out']]);
    let cursor=st;
    for(const [name,a,b,slot] of scene.spans_by_language[lang]){
      const key=lang+'/'+name,phone=name.includes('phone'),base=name.replace(/^r-/,'');  // r-<clip>: PPS-84 Arabic re-shoot
      const crop=phone?null:(scene.crop||(!vertical&&[1,14].includes(scene.beat)?[0,0,1920,1080]:[220,60,1480,980]));
      let width=vertical?(phone?450:960):(phone?390:1260);
      let centerX=vertical?540:(rtl?670:1250),centerY=vertical?(phone?1020:1160):535;
      // Portrait focuses the important section while preserving the complete horizontal target region.
      let useCrop=crop;
      if(vertical&&!phone){
        if(scene.beat===3){useCrop=(MARKET==='eg'?a>=44:a===b)?[rtl?900:350,150,680,650]:[550,180,840,760];centerY=1110;}
        if(scene.beat===5)useCrop=[240,290,1440,450];
        if(scene.beat===6){useCrop=a<12?[235,300,1450,170]:[rtl?250:970,220,710,390];if(a>=22){centerY=1255;width=900;}}
        if(scene.beat===7)useCrop=[230,60,1450,980];
        if(scene.beat===8){useCrop=compareCrops(true,rtl).main;centerY=1040;}
        if(scene.beat===10){useCrop=[410,90,1100,800];centerY=1110;}
        if(scene.beat===12){useCrop=[rtl?600:340,60,980,900];centerY=1110;}
        if(scene.beat===13)useCrop=[240,60,1440,980];
      }
      // PPS-63: the re-shot Arabic outcome form (s5 34–42 s) sits further right, nav hidden; keep its title in frame.
      if(MARKET==='eg'&&rtl&&scene.beat===13&&name==='s5-po-savings'&&a>=34&&a<42)useCrop=vertical?[460,60,1440,980]:[420,60,1480,980];
      // Saudi/Irish outcome form (s5 32–41 s): nav hidden, so the form hugs the reading edge; keep its title in frame.
      // Re-shot outcome form (nav hidden): same reading-edge crop as the originals.
      if(name==='r-s5r-outcome-form'&&a>=7)useCrop=rtl?(vertical?[460,60,1440,980]:[420,60,1480,980]):(vertical?[20,60,1440,980]:[20,60,1480,980]);
      if(MARKET!=='eg'&&scene.beat===13&&name==='s5-po-savings'&&a<41)useCrop=rtl?(vertical?[460,60,1440,980]:[420,60,1480,980]):(vertical?[20,60,1440,980]:[20,60,1480,980]);
      if(scene.beat===8){useCrop=compareCrops(vertical,rtl).main;centerY=vertical?1040:360;}
      // Real end-state inserts: source coordinates never include quotation identity fields.
      if(base==='s2r-authorised'){
        useCrop=vertical?[rtl?1070:220,140,rtl?640:790,330]:[rtl?1070:220,60,rtl?640:790,410];
        width=vertical?960:1260;centerY=vertical?1120:535;
      }
      if(base==='s4r-approved'){
        useCrop=vertical?[rtl?1070:570,775,rtl?280:370,120]:[570,775,780,120];
        width=vertical?960:1260;centerY=vertical?1120:535;
      }
      const p=PLATE(key,{w:width,crop:useCrop,x:centerX,y:centerY,z:10,depth:2,t0:cursor,t1:cursor+slot,map:t=>{
        const travel=slot; // Explicit a===b subslots supply the decision-result holds.
        return a+(b-a)*Math.min(1,Math.max(0,(t-cursor)/travel));
      }});
      // Capture source clock per subslot: closures must not follow the next slot's cursor.
      const sourceStart=cursor;
      // PLATE's map callback retains this local start rather than the mutable edit cursor.
      const m=META[key]; const im=p.node.querySelector('img');
      p.update=t=>{const travel=slot;const seconds=a+(b-a)*Math.min(1,Math.max(0,(t-sourceStart)/travel));
        const idx=Math.max(1,Math.min(m.frames,Math.floor(seconds*FPS+1e-6)+1));
        if(idx!==p.cur){p.cur=idx;im.src=`${PLATES}/${key}/${String(idx).padStart(4,'0')}.jpg`;PENDING.push(im);}};
      if(vertical&&scene.beat===6&&a>=22){
        const photo=PLATE(key,{w:960,crop:[rtl?995:240,60,675,130],x:540,y:900,z:11,depth:2,t0:sourceStart,t1:sourceStart+slot,map:t=>a});
        const pi=photo.node.querySelector('img');
        photo.update=t=>{const seconds=a+(b-a)*Math.min(1,Math.max(0,(t-sourceStart)/slot));
          const idx=Math.max(1,Math.min(m.frames,Math.floor(seconds*FPS+1e-6)+1));
          if(idx!==photo.cur){photo.cur=idx;pi.src=`${PLATES}/${key}/${String(idx).padStart(4,'0')}.jpg`;PENDING.push(pi);}};
      }
      if(scene.beat===8){
        const rows=PLATE(key,{w:vertical?960:1260,crop:compareCrops(vertical,rtl).rows,x:centerX,y:vertical?1320:690,z:11,depth:2,t0:sourceStart,t1:sourceStart+slot,map:t=>a});
        const ri=rows.node.querySelector('img');
        rows.update=t=>{const seconds=a+(b-a)*Math.min(1,Math.max(0,(t-sourceStart)/slot));
          const idx=Math.max(1,Math.min(m.frames,Math.floor(seconds*FPS+1e-6)+1));
          if(idx!==rows.cur){rows.cur=idx;ri.src=`${PLATES}/${key}/${String(idx).padStart(4,'0')}.jpg`;PENDING.push(ri);}};
      }
      if(base==='s2r-authorised'||base==='s4r-approved'){
        const sc=width/useCrop[2];
        const status=base==='s2r-authorised'?[rtl?1100:790,202,rtl?168:190]:[rtl?1280:592,831,rtl?55:65];
        const hit=R({w:status[2]*sc,h:4*sc,x:centerX-width/2+(status[0]-useCrop[0])*sc,
          y:centerY-useCrop[3]*sc/2+(status[1]-useCrop[1])*sc,ax:0,ay:0,z:15,color:C.teal,t0:sourceStart,t1:sourceStart+slot});
        hit.k('sx',[[sourceStart,0],[sourceStart+.2,1,'out']]);
      }
      if(phone)p.node.classList.add('phone');
      if(cursor===st)p.k('y',[[st,centerY+80],[st+.5,centerY,'out']]);
      cursor+=slot;
    }
    if([1,6,8,13,14].includes(scene.beat)){
      const money=MONEY.cards;
      const cards=scene.cards_by_language[lang];
      const reveal=scene.beat===1?st+scene.spans_by_language[lang][0][3]:st+cards.at(-1).offset;
      number(money[scene.beat],reveal,end,scene.beat);
    }
    if(scene.beat===13)savingPage(st+timeline.saving_at[0],timeline.saving_at[1],V25.saving);
    if([3,8,10,12].includes(scene.beat))PASS(st,{W,H,dur:.65});
  }
  // v2.5: the 'Real run · demo data' pill is removed (owner, 2026-10-26); the description carries the disclosure.
  window.DURATION=timeline.body;
}
