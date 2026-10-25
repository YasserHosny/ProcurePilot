// Source crops exclude the recommendation validity line (y=663..681) and both validity columns.
function compareCrops(vertical,rtl){return {
  main:vertical?[rtl?850:260,520,810,135]:[260,520,1400,135],
  rows:rtl?[1110,826,550,142]:[260,826,450,142]
};}
// Saudi demo (PPS-39), forked from edit-v2.4. v2.4 compositions built on the forked v2.3 frame-addressed motion engine.
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
    if(beat===13){e.update=t=>{const u=EASE.out(Math.max(0,Math.min(1,(t-start-.1)/.3)));let n=String(Math.round((rtl?190:310)*u));if(rtl)n=n.replace(/\d/g,d=>'٠١٢٣٤٥٦٧٨٩'[d]);e.inner.textContent=rtl?n+' ر.س':'SAR '+n;};}
    const bar=R({w:vertical?620:420,h:12,x:rtl?tx+tw:tx,y:vertical?790:850,ax:rtl?1:0,ay:0,color:C.teal,z:51,t0:start+(fast?.1:.8),t1:end});
    bar.k('sx',[[start+(fast?.1:.8),0],[start+(fast?.4:1.35),1,'out']]);
    if(beat===8){
      for(const [dy,width,color] of [[30,vertical?570:370,C.ink],[60,vertical?520:320,C.mist]]){
        const other=R({w:width,h:12,x:rtl?tx+tw:tx,y:(vertical?790:850)+dy,ax:rtl?1:0,ay:0,color,z:51,t0:start+.4,t1:end});
        other.k('sx',[[start+.4,0],[start+.8,1,'out']]);
      }
    }
  }
  for(const scene of timeline.scenes){
    const st=scene.start,end=st+scene.duration;
    if(scene.beat===0){
      const key='opening-'+fmt;
      const openingPlate=PLATE(key,{w:W,x:W/2,y:H/2,z:5,depth:0,t0:st,t1:end,map:t=>t});
      openingPlate.node.style.border='0';openingPlate.node.style.borderRadius='0';
      caption(scene.copy[lang],st+.12,end);
      // Opening copy on paper protects legibility over the pre-approved animation.
      const e=ELS[ELS.length-1];e.node.style.background=C.paper;e.node.style.padding='.15em .25em';
      continue;
    }
    for(const card of scene.cards_by_language[lang])caption(card.text,st+card.offset+(card.offset===0?.08:0),st+card.offset+card.duration);
    const panel=R({w:vertical?W:520,h:vertical?650:H,x:rtl?W:0,y:0,ax:rtl?1:0,ay:0,z:1,color:C.mist,t0:st,t1:end});
    panel.k('sx',[[st,.96],[st+.5,1,'out']]);
    let cursor=st;
    for(const [name,a,b,slot] of scene.spans_by_language[lang]){
      const key=lang+'/'+name,phone=name.includes('phone');
      const crop=phone?null:(scene.crop||(!vertical&&[1,14].includes(scene.beat)?[0,0,1920,1080]:[220,60,1480,980]));
      let width=vertical?(phone?450:960):(phone?390:1260);
      let centerX=vertical?540:(rtl?670:1250),centerY=vertical?(phone?1020:1160):535;
      // Portrait focuses the important section while preserving the complete horizontal target region.
      let useCrop=crop;
      if(vertical&&!phone){
        if(scene.beat===3){useCrop=a===b?[rtl?900:350,150,680,650]:[550,180,840,760];centerY=1110;}
        if(scene.beat===5)useCrop=[240,290,1440,450];
        if(scene.beat===6){useCrop=a<12?[235,300,1450,170]:[rtl?250:970,220,710,390];if(a>=22){centerY=1255;width=900;}}
        if(scene.beat===7)useCrop=[230,60,1450,980];
        if(scene.beat===8){useCrop=compareCrops(true,rtl).main;centerY=1040;}
        if(scene.beat===10){useCrop=[410,90,1100,800];centerY=1110;}
        if(scene.beat===12){useCrop=[rtl?600:340,60,980,900];centerY=1110;}
        if(scene.beat===13)useCrop=[240,60,1440,980];
      }
      // Saudi outcome form (s5 32–41 s): nav hidden, so the form hugs the reading edge; keep its title in frame.
      if(scene.beat===13&&name==='s5-po-savings'&&a<41)useCrop=rtl?(vertical?[460,60,1440,980]:[420,60,1480,980]):(vertical?[20,60,1440,980]:[20,60,1480,980]);
      // PPS-63: the re-shot Arabic outcome form (s5 34–42 s) sits further right, nav hidden; keep its title in frame.
      if(rtl&&scene.beat===13&&name==='s5-po-savings'&&a>=34&&a<42)useCrop=vertical?[460,60,1440,980]:[420,60,1480,980];
      if(scene.beat===8){useCrop=compareCrops(vertical,rtl).main;centerY=vertical?1040:360;}
      // Real end-state inserts: source coordinates never include quotation identity fields.
      if(name==='s2r-authorised'){
        useCrop=vertical?[rtl?1070:220,140,rtl?640:790,330]:[rtl?1070:220,60,rtl?640:790,410];
        width=vertical?960:1260;centerY=vertical?1120:535;
      }
      if(name==='s4r-approved'){
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
        if(idx!==p.cur){p.cur=idx;im.src=`plates/${key}/${String(idx).padStart(4,'0')}.jpg`;PENDING.push(im);}};
      if(vertical&&scene.beat===6&&a>=22){
        const photo=PLATE(key,{w:960,crop:[rtl?995:240,60,675,130],x:540,y:900,z:11,depth:2,t0:sourceStart,t1:sourceStart+slot,map:t=>a});
        const pi=photo.node.querySelector('img');
        photo.update=t=>{const seconds=a+(b-a)*Math.min(1,Math.max(0,(t-sourceStart)/slot));
          const idx=Math.max(1,Math.min(m.frames,Math.floor(seconds*FPS+1e-6)+1));
          if(idx!==photo.cur){photo.cur=idx;pi.src=`plates/${key}/${String(idx).padStart(4,'0')}.jpg`;PENDING.push(pi);}};
      }
      if(scene.beat===8){
        const rows=PLATE(key,{w:vertical?960:1260,crop:compareCrops(vertical,rtl).rows,x:centerX,y:vertical?1320:690,z:11,depth:2,t0:sourceStart,t1:sourceStart+slot,map:t=>a});
        const ri=rows.node.querySelector('img');
        rows.update=t=>{const seconds=a+(b-a)*Math.min(1,Math.max(0,(t-sourceStart)/slot));
          const idx=Math.max(1,Math.min(m.frames,Math.floor(seconds*FPS+1e-6)+1));
          if(idx!==rows.cur){rows.cur=idx;ri.src=`plates/${key}/${String(idx).padStart(4,'0')}.jpg`;PENDING.push(ri);}};
      }
      if(name==='s2r-authorised'||name==='s4r-approved'){
        const sc=width/useCrop[2];
        const status=name==='s2r-authorised'?[rtl?1100:790,202,rtl?168:190]:[rtl?1280:592,831,rtl?55:65];
        const hit=R({w:status[2]*sc,h:4*sc,x:centerX-width/2+(status[0]-useCrop[0])*sc,
          y:centerY-useCrop[3]*sc/2+(status[1]-useCrop[1])*sc,ax:0,ay:0,z:15,color:C.teal,t0:sourceStart,t1:sourceStart+slot});
        hit.k('sx',[[sourceStart,0],[sourceStart+.2,1,'out']]);
      }
      if(phone)p.node.classList.add('phone');
      if(cursor===st)p.k('y',[[st,centerY+80],[st+.5,centerY,'out']]);
      cursor+=slot;
    }
    if([1,6,8,13,14].includes(scene.beat)){
      // Saudi rounds (docs/gtm/gcc/rounds/README.md): Arabic UI = round A, English UI = round E; ledger as filmed.
      const money=lang==='ar'?{1:'١٩٠ ر.س',6:'٤٬٩١٠ ر.س',8:'٤٠ ر.س',13:'١٩٠ ر.س',14:'١٩٠ ر.س'}:
        {1:'SAR 310',6:'SAR 4,790',8:'SAR 40',13:'SAR 310',14:'SAR 310'};
      const cards=scene.cards_by_language[lang];
      const reveal=scene.beat===1?st+scene.spans_by_language[lang][0][3]:st+cards.at(-1).offset;
      number(money[scene.beat],reveal,end,scene.beat);
    }
    if([1,3,8,10,12].includes(scene.beat))PASS(st,{W,H,dur:.65});
  }
  const disclosure=rtl?'تشغيل حقيقي · بيانات تجريبية · دقيقتين':'Real run · demo data · 2 minutes';
  const pill=T(disclosure,{size:vertical?28:24,w:500,dir:rtl?'rtl':'ltr',color:C.ink,bg:C.mist,pad:'.25em .6em',x:vertical?540:60,y:vertical?1500:1028,ax:vertical?.5:0,ay:0,z:950,t0:vertical?3:4,t1:timeline.body});
  pill.node.style.borderRadius='40px';
  window.DURATION=timeline.body;
}
