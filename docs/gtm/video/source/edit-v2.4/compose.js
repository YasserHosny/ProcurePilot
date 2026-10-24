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
    const e=T(text,{size:vertical?102:72,w:700,dir:rtl?'rtl':'ltr',color:C.ink,x:tx,y:vertical?650:745,ax:0,ay:0,z:52,t0:start+.65,t1:end});
    e.node.style.width=tw+'px';e.node.style.textAlign=align;
    e.k('iy',[[start+.65,110],[start+1.12,0,'out']]);
    if(beat===13){e.update=t=>{const u=EASE.out(Math.max(0,Math.min(1,(t-start-.7)/.8)));let n=String(Math.round((rtl?300:200)*u));if(rtl)n=n.replace(/\d/g,d=>'٠١٢٣٤٥٦٧٨٩'[d]);e.inner.textContent=rtl?n+' ج.م':'EGP '+n;};}
    const bar=R({w:vertical?620:420,h:12,x:rtl?tx+tw:tx,y:vertical?790:850,ax:rtl?1:0,ay:0,color:C.teal,z:51,t0:start+.8,t1:end});
    bar.k('sx',[[start+.8,0],[start+1.35,1,'out']]);
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
    caption(scene.copy[lang],st+.08,end);
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
        if(scene.beat===3){useCrop=a>=44?[rtl?900:350,150,680,650]:[550,180,840,760];centerY=1110;}
        if(scene.beat===5)useCrop=[240,290,1440,450];
        if(scene.beat===6){useCrop=a<12?[235,300,1450,170]:[rtl?250:970,220,710,390];if(a>=22){centerY=1255;width=900;}}
        if(scene.beat===7)useCrop=[230,60,1450,980];
        if(scene.beat===8){useCrop=[rtl?850:260,520,810,260];centerY=1040;}
        if(scene.beat===10){useCrop=[410,90,1100,800];centerY=1110;}
        if(scene.beat===12){useCrop=[rtl?600:340,60,980,900];centerY=1110;}
        if(scene.beat===13)useCrop=[240,60,1440,980];
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
      if(vertical&&scene.beat===8){
        const rows=PLATE(key,{w:960,crop:[rtl?1110:260,820,550,150],x:540,y:1350,z:11,depth:2,t0:sourceStart,t1:sourceStart+slot,map:t=>a});
        const ri=rows.node.querySelector('img');
        rows.update=t=>{const seconds=a+(b-a)*Math.min(1,Math.max(0,(t-sourceStart)/slot));
          const idx=Math.max(1,Math.min(m.frames,Math.floor(seconds*FPS+1e-6)+1));
          if(idx!==rows.cur){rows.cur=idx;ri.src=`plates/${key}/${String(idx).padStart(4,'0')}.jpg`;PENDING.push(ri);}};
      }
      if(phone)p.node.classList.add('phone');
      if(cursor===st)p.k('y',[[st,centerY+80],[st+.5,centerY,'out']]);
      cursor+=slot;
    }
    if([1,6,8,13,14].includes(scene.beat)){
      const money=lang==='ar'?{1:'٣٠٠ ج.م',6:'٢٤٬٦٤٠ ج.م',8:'٢٠٠ ج.م',13:'٣٠٠ ج.م',14:'١٬٥٦٠ ج.م'}:
        {1:'EGP 200',6:'EGP 24,440',8:'EGP 200',13:'EGP 200',14:'EGP 1,760'};
      number(money[scene.beat],st,end,scene.beat);
    }
    if([1,3,8,10,12].includes(scene.beat))PASS(st,{W,H,dur:.65});
  }
  const disclosure=rtl?'تشغيل حقيقي · بيانات تجريبية · دقيقتين':'Real run · demo data · 2 minutes';
  const pill=T(disclosure,{size:vertical?28:24,w:500,dir:rtl?'rtl':'ltr',color:C.ink,bg:C.mist,pad:'.25em .6em',x:vertical?540:60,y:vertical?1500:1028,ax:vertical?.5:0,ay:0,z:950,t0:vertical?3:4,t1:timeline.body});
  pill.node.style.borderRadius='40px';
  window.DURATION=timeline.body;
}
