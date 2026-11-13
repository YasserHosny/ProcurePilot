// ProcurePilot Saudi ad (marketing cut with voiceover). Deterministic: window.renderAt(seconds) draws one frame.
// Every scene is timed from the voiceover's word timings in build/data.js (prep_vo.py), so type lands on the word.
const FMT=(location.hash||'#h').slice(1),V=FMT==='v',W=V?1080:1920,H=V?1920:1080;
const st=document.getElementById('stage');st.style.width=W+'px';st.style.height=H+'px';
const C={navy:'#0B2545',teal:'#12A594',tealOn:'#19B8A4',mist:'#C9D6E3',paper:'#F4F6F9',white:'#fff',ink2:'#4A5D78'};
const SHOTS='../../../gcc/rounds/screens/ar/';
const cl=(x,a=0,b=1)=>Math.min(b,Math.max(a,x)),pr=(t,a,d)=>cl((t-a)/d),lerp=(a,b,p)=>a+(b-a)*p;
const E={out:x=>1-Math.pow(1-x,3),expo:x=>x>=1?1:1-Math.pow(2,-10*x),io:x=>x<.5?4*x*x*x:1-Math.pow(-2*x+2,3)/2,
  back:x=>{const c=1.6;return 1+(c+1)*Math.pow(x-1,3)+c*Math.pow(x-1,2)},in:x=>x*x*x};
const SEG=Object.fromEntries(AD.segments.map(s=>[s.id,s]));
const wt=(id,k)=>SEG[id].at-SEG[id].start+SEG[id].words[k][0];
const dur=id=>SEG[id].end-SEG[id].start;
const AR='٠١٢٣٤٥٦٧٨٩',arNum=n=>String(Math.round(n)).replace(/\d/g,d=>AR[d]);
const pending=[];
function mk(parent,cls,css,html){const e=document.createElement('div');if(cls)e.className=cls;if(css)Object.assign(e.style,css);if(html!=null)e.innerHTML=html;parent.appendChild(e);return e;}
function img(parent,src,css){const i=new Image();pending.push(new Promise((ok,no)=>{i.onload=ok;i.onerror=()=>no(new Error('missing '+src))}));i.src=src;if(css)Object.assign(i.style,css);parent.appendChild(i);return i;}
const box=(x,y,w,h)=>({left:x+'px',top:y+'px',width:w+'px',height:h==null?'auto':h+'px'});
const tf=(e,x=0,y=0,s=1,r=0)=>{e.style.transform=`translate(${x}px,${y}px) rotate(${r}deg) scale(${s})`};

// ---- kinetic type: words rise out of a mask, in reading order, on the spoken word ----
function KT(parent,text,css){
  const el=mk(parent,'kt abs',css);const words=[];
  for(const tok of text.split(' ')){
    const hot=tok[0]==='*';const w=document.createElement('span');w.className='w';const i=document.createElement('span');i.className='i';
    i.textContent=hot?tok.slice(1):tok;if(hot)i.style.color=css.hot||C.teal;w.appendChild(i);el.appendChild(w);words.push(i);
  }
  return {el,words,
    // times: number (start, staggered) or array per word; tOut: all words leave upward
    at(t,times,tOut,stagger=.07){
      words.forEach((w,k)=>{const t0=Array.isArray(times)?times[Math.min(k,times.length-1)]:times+k*stagger;
        const p=E.expo(pr(t,t0-.06,.5));let y=(1-p)*112;
        if(tOut!=null){const q=E.in(pr(t,tOut+k*.02,.26));y-=q*112;}
        w.style.transform=`translateY(${y}%)`;w.style.visibility=Math.abs(y)>=111.9?'hidden':'visible';});
    }};
}
function LN(parent,html,css){const el=mk(parent,'ln abs',css);const i=document.createElement('span');i.className='i';i.innerHTML=html;el.appendChild(i);
  return {el,i,at(t,t0,tOut){const p=E.expo(pr(t,t0,.5));let y=(1-p)*112;if(tOut!=null)y-=E.in(pr(t,tOut,.26))*112;i.style.transform=`translateY(${y}%)`;i.style.visibility=Math.abs(y)>=111.9?'hidden':'visible';}};}
// pop: chips, papers and other blocks arrive with a short travel and settle
function pop(e,t,t0,tOut,o={}){
  const p=E.expo(pr(t,t0,o.d||.5)),q=tOut==null?0:E.in(pr(t,tOut,.25));
  e.style.opacity=cl(pr(t,t0,.12)-q);
  tf(e,(o.dx||0)*(1-p)+(o.ox||0)*q,(o.dy==null?40:o.dy)*(1-p)+(o.oy||0)*q,lerp(o.s0||.92,1,p),(o.r||0)+(o.r0||0)*(1-p));
}

// ---- product plate: a real screenshot behind a frame, with a camera and highlight rings in screenshot pixels ----
function Plate(parent,frame,srcs,o={}){
  const sw=o.sw||1920,sh=o.sh||1080;
  const root=mk(parent,'plate'+(o.phone?' phone':''),box(frame.x,frame.y,frame.w,frame.h));
  const world=mk(root,'world',{width:sw+'px',height:sh+'px'});
  const imgs=srcs.map((s,k)=>s instanceof HTMLElement?(world.appendChild(s),s):img(world,s,{width:sw+'px',height:sh+'px',opacity:k?0:1}));
  const P={root,world,imgs,frame,
    cam(cx,cy,fw){const s=frame.w/fw,fh=frame.h/s;cx=cl(cx,fw/2,Math.max(fw/2,sw-fw/2));cy=cl(cy,fh/2,Math.max(fh/2,sh-fh/2));
      world.style.transform=`translate(${-(cx-fw/2)*s}px,${-(cy-fh/2)*s}px) scale(${s})`;},
    // keys: [[t,cx,cy,w],...] eased between neighbours
    camKeys(t,keys){let a=keys[0],b=keys[0];for(const k of keys){if(k[0]<=t)a=k;}b=keys[keys.indexOf(a)+1]||a;
      const p=a===b?0:E.io(pr(t,a[0],b[0]-a[0]));P.cam(lerp(a[1],b[1],p),lerp(a[2],b[2],p),lerp(a[3],b[3],p));},
    show(t,cuts){// cuts: [t0 of image 1, t0 of image 2, ...] quick dissolves
      imgs.forEach((im,k)=>{im.style.opacity=k===0?1:pr(t,cuts[k-1],.16);});},
    ring(x,y,w,h,color){const r=mk(world,'ring',box(x,y,w,h));if(color){r.style.borderColor=color;r.style.background='transparent';}
      return {el:r,at(t,t0,tOut){const p=E.back(pr(t,t0,.4));r.style.opacity=cl(pr(t,t0,.1)-(tOut==null?0:pr(t,tOut,.2)));r.style.transform=`scale(${lerp(1.12,1,p)})`;}};},
    enter(t,t0,tOut,o2={}){const p=E.expo(pr(t,t0,.6)),q=tOut==null?0:E.in(pr(t,tOut,.28));
      root.style.opacity=cl(pr(t,t0,.14)-q);
      tf(root,(o2.dx==null?0:o2.dx)*(1-p)+(o2.ox==null?-90:o2.ox)*q,(o2.dy==null?70:o2.dy)*(1-p),lerp(.95,1,p)*(1-.03*q),(o2.r||0)*(1-p));
      root.style.filter=p<.98?`blur(${(1-p)*7}px)`:'none';}};
  P.cam(sw/2,sh/2,sw);return P;
}
function Phone(parent,frame,srcs){return Plate(parent,frame,srcs.map(s=>SHOTS+s),{phone:true,sw:390,sh:844});}
const Web=(parent,frame,srcs)=>Plate(parent,frame,srcs.map(s=>SHOTS+s));

// ---- the official logo, built in motion from its own SVG geometry (never redrawn) ----
let logoN=0;
function Logo(parent,variant,x,y,width){
  const el=mk(parent,'abs',{left:x+'px',top:y+'px',width:width+'px',transformOrigin:'50% 50%'},LOGOS[variant]);
  const svg=el.querySelector('svg');svg.setAttribute('width',width);svg.setAttribute('height',width*220/956.7);svg.style.display='block';
  const g=svg.querySelector('g'),[top,mid,bot]=g.querySelectorAll('rect'),arrow=g.querySelector('path');
  const wm=[...svg.children].filter(n=>n.tagName==='path');const id='lc'+(logoN++);const NS='http://www.w3.org/2000/svg';
  const cp=document.createElementNS(NS,'clipPath');cp.id=id;const cr=document.createElementNS(NS,'rect');cr.setAttribute('x',215);cr.setAttribute('y',0);cr.setAttribute('height',220);cr.setAttribute('width',0);cp.appendChild(cr);svg.appendChild(cp);
  const wg=document.createElementNS(NS,'g');wg.setAttribute('clip-path',`url(#${id})`);wm.forEach(p=>wg.appendChild(p));svg.appendChild(wg);
  for(const r of [top,mid,bot,arrow]){r.style.transformBox='fill-box';r.style.transformOrigin='0% 50%';}
  return {el,set(p){
    top.style.transform=`scaleX(${E.expo(pr(p,0,.22))})`;bot.style.transform=`scaleX(${E.expo(pr(p,.07,.22))})`;
    mid.style.transform=`scaleX(${E.expo(pr(p,.18,.26))})`;
    const a=pr(p,.38,.2);arrow.style.opacity=a>0?1:0;arrow.style.transform=`scale(${a>0?E.back(a):0})`;
    cr.setAttribute('width',E.io(pr(p,.48,.5))*745);}};
}

// ---- layout ----
const L=V?{
  plate:{x:50,y:700,w:980,h:760},phone:{x:365,y:700,w:350,h:757},cap:{x:70,y:340,w:940},
  big:104,mid:74,small:42,steps:{y:1505},bug:{x:440,y:262,w:200}
}:{
  plate:{x:80,y:160,w:1090,h:760},phone:{x:445,y:130,w:360,h:779},cap:{x:1330,y:250,w:510},
  big:96,mid:66,small:38,steps:{y:992},bug:{x:80,y:52,w:210}
};
const capCss=(o={})=>({...box(o.x==null?L.cap.x:o.x,o.y==null?L.cap.y:o.y,o.w||L.cap.w),fontSize:(o.size||L.big)+'px',color:o.color||C.navy,
  justifyContent:V||o.center?'center':'flex-start',textAlign:V||o.center?'center':'right',fontWeight:o.weight||700,hot:o.hot});
const lnCss=(o={})=>({...box(o.x==null?L.cap.x:o.x,o.y==null?L.cap.y:o.y,o.w||L.cap.w),fontSize:(o.size||L.small)+'px',color:o.color||C.ink2,
  textAlign:V||o.center?'center':'right',fontWeight:o.weight||500});

const scenes=[];const overlays=[];
function scene(id,bg,build){const root=mk(st,'scene',{background:bg,display:'none'});const s={id,root,start:SEG[id].start,end:SEG[id].end};s.update=build(root,s);scenes.push(s);}

// ---- persistent: logo bug + five-step tracker on the product chapters ----
const STEPS=['اطلب','اقرأ','قارن','اعتمد','وفّر'];
function chrome(root,active){
  const bug=mk(root,'abs',box(L.bug.x,L.bug.y,L.bug.w),LOGOS.light);const svg=bug.querySelector('svg');svg.setAttribute('width',L.bug.w);svg.setAttribute('height',L.bug.w*220/956.7);
  const gap=V?188:170,total=gap*4,x0=(V?W/2:625)+total/2,y=L.steps.y;const items=[];
  mk(root,'abs',{left:(x0-total)+'px',top:(y+8)+'px',width:total+'px',height:'3px',background:C.mist});
  const fill=mk(root,'abs',{left:(x0-total)+'px',top:(y+8)+'px',width:total+'px',height:'3px',background:C.navy,transformOrigin:'100% 50%'});
  STEPS.forEach((s,k)=>{const x=x0-k*gap;
    const dot=mk(root,'abs',{left:(x-10)+'px',top:y+'px',width:'20px',height:'20px',borderRadius:'50%',background:k<active?C.navy:C.mist,border:'3px solid '+C.paper});
    const lab=mk(root,'abs',{left:(x-80)+'px',top:(y+28)+'px',width:'160px',textAlign:'center',direction:'rtl',fontSize:(V?30:26)+'px',fontWeight:k===active?700:500,color:k===active?C.navy:k<active?C.ink2:'#9AA9BC'},s);
    items.push({dot,lab});});
  return t=>{const p=E.expo(pr(t,.15,.6));fill.style.transform=`scaleX(${Math.max(0,(active-1+p)/4)})`;
    const d=items[active].dot;d.style.background=p>.5?C.teal:C.mist;d.style.transform=`scale(${1+.5*E.back(p)})`;};
}

// ================= S1 hook: «كم مرة اشتريت بسعر أغلى، وأنت ما تدري؟» =================
scene('s1',C.navy,(root)=>{
  const bars=[[.10,.56,.34],[.36,.80,.5],[.66,.44,.22]].map(([y,w,o],k)=>mk(root,'abs',{left:0,top:H*y+'px',width:W*w+'px',height:(V?150:120)+'px',borderRadius:'0 999px 999px 0',background:C.mist,opacity:.075}));
  const q=mk(root,'abs',{left:(V?40:90)+'px',top:(V?980:120)+'px',fontSize:(V?900:900)+'px',fontWeight:700,color:'transparent',WebkitTextStroke:'3px rgba(201,214,227,.13)',lineHeight:1},'؟');
  const x=V?70:170,w=V?940:1580,y=V?560:210,s1=V?112:150,s2=V?168:226,s3=V?84:104;
  const a=KT(root,'كم مرة اشتريت',{...box(x,y,w),fontSize:s1+'px',color:C.white,justifyContent:V?'center':'flex-start'});
  const b=KT(root,'بسعر أغلى',{...box(x,y+s1*1.3,w),fontSize:s2+'px',color:C.white,justifyContent:V?'center':'flex-start'});
  const ul=mk(root,'abs',{left:(V?150:x+w-780)+'px',top:(y+s1*1.3+s2*1.32)+'px',width:(V?780:780)+'px',height:(V?16:20)+'px',borderRadius:'99px',background:C.mist,transformOrigin:'100% 50%'});
  const c=KT(root,'…وأنت ما تدري؟',{...box(x,y+s1*1.3+s2*1.62,w),fontSize:s3+'px',color:C.mist,fontWeight:500,justifyContent:V?'center':'flex-start'});
  const T=k=>wt('s1',k);
  return t=>{
    bars.forEach((e,k)=>tf(e,-W*.5*(1-E.expo(pr(t,k*.08,.9)))+t*(14+k*9),0));tf(q,-t*18,t*6);
    a.at(t,[T(0),T(1),T(2)]);b.at(t,[T(3),T(4)]);ul.style.transform=`scaleX(${E.expo(pr(t,T(4)+.1,.5))})`;c.at(t,[T(5),T(6),T(7)]);
    const k=1+.035*E.out(pr(t,0,3.8));[a.el,b.el,c.el,ul].forEach(e=>e.style.scale=k);
  };
});

// ================= S2 problem: quotes in every format, retyped by hand, packs that don't match =================
scene('s2',C.paper,(root)=>{
  const T=k=>wt('s2',k),tb=T(9)-.2,tc=T(15)-.12,D=dur('s2');
  const title=KT(root,'عروض الموردين تجيك…',V?{...box(70,330,940),fontSize:'82px',justifyContent:'center'}:{...box(900,96,900),fontSize:'88px'});
  const defs=V?[['photo.jpg','واتساب',640,560,340,453,6],['wafra.png','PDF',370,640,340,481,-4],['qassim.png','ورق مصوّر',90,580,340,481,5]]
              :[['photo.jpg','واتساب',1260,300,420,560,5],['wafra.png','PDF',760,340,400,566,-4],['qassim.png','ورق مصوّر',270,290,400,566,4]];
  const papers=defs.map(([f,label,x,y,w,h,r],k)=>{const p=mk(root,'paper',box(x,y,w,h));img(p,'build/tex/'+f);
    const chip=mk(root,'chip',{left:(x+w/2-110)+'px',top:(y+h-36)+'px',width:'220px',textAlign:'center',fontSize:(V?38:40)+'px'},label);return {p,chip,r};});
  const cv=document.createElement('canvas');cv.width=V?1080:1920;cv.height=V?1920:1080;const cx=cv.getContext('2d');
  const frames=[];for(let k=1;k<=OPEN_FRAMES[FMT];k++){const i=new Image();pending.push(new Promise(ok=>{i.onload=ok}));i.src=`build/open-${FMT}/${String(k).padStart(3,'0')}.jpg`;frames.push(i);}
  const pf=V?{x:300,y:700,w:480,h:853}:{x:110,y:300,w:1080,h:608};
  const plate=Plate(root,pf,[cv],{sw:cv.width,sh:cv.height});
  const capB=KT(root,'وأنت تنقل الأسعار بيدك في الإكسل',V?capCss({size:84,y:350}):capCss({x:1250,w:590,y:380,size:84}));
  const capC=KT(root,'وتقارن كراتين مو نفس الحجم!',V?capCss({size:84,y:350}):capCss({x:1250,w:590,y:380,size:84}));
  let last=-1;
  return t=>{
    title.at(t,[T(0),T(1),T(2)],tb-.1);
    [[T(3)],[T(4)],[T(7)]].forEach(([t0],k)=>{const {p,chip,r}=papers[k];
      pop(p,t,t0-.12,tb-.12+k*.04,{dy:260,r:r,r0:r*3,s0:.8,ox:-W*.5,d:.6});pop(chip,t,t0+.1,tb-.16+k*.04,{dy:30,ox:-W*.5});});
    plate.enter(t,tb,D-.2,{dy:120,ox:0});plate.cam(cv.width/2,cv.height/2,cv.width/lerp(1,1.07,pr(t,tb,D-tb)));
    const f=Math.min(frames.length-1,Math.round(pr(t,tb+.25,D-tb-.9)*(frames.length-1)));if(f!==last){cx.drawImage(frames[f],0,0);last=f;}
    capB.at(t,[T(9),T(10),T(11),T(12),T(13),T(14)],tc-.12);capC.at(t,[T(15),T(16),T(17),T(18),T(19)],D-.22);
  };
});

// ================= S3 turn: «خلاص» → the logo builds → the promise =================
scene('s3',C.paper,(root)=>{
  const T=k=>wt('s3',k),tw=T(4)-.42,D=dur('s3');
  const big=mk(root,'abs',{...box(0,V?560:150,W),textAlign:'center',direction:'rtl',fontSize:(V?330:400)+'px',fontWeight:700,lineHeight:1.2,color:C.navy},'خلاص.');
  const sub=KT(root,'ارتاح من هالدوخة',{...box(0,V?1030:690,W),fontSize:(V?92:104)+'px',justifyContent:'center',color:C.ink2,fontWeight:600});
  const teal=mk(root,'abs',{...box(0,0,W,H),background:C.tealOn}),navy=mk(root,'abs',{...box(0,0,W,H),background:C.navy});
  const lw=V?860:1000,logo=Logo(navy,'dark',(W-lw)/2,V?600:250,lw);
  const l1=KT(navy,'مشتريات مطعمك كلها',{...box(0,V?900:560,W),fontSize:(V?88:100)+'px',justifyContent:'center',color:C.white});
  const l2=KT(navy,'في مكان واحد.',{...box(0,V?1030:700,W),fontSize:(V?112:128)+'px',justifyContent:'center',color:C.tealOn});
  const bar=mk(navy,'abs',{left:(W/2-(V?330:380))+'px',top:(V?1200:880)+'px',width:(V?660:760)+'px',height:'16px',borderRadius:'99px',background:C.tealOn,transformOrigin:'100% 50%'});
  return t=>{
    const p=E.expo(pr(t,T(0)-.05,.4));big.style.opacity=pr(t,T(0)-.05,.08);big.style.transform=`scale(${lerp(1.6,1,p)*(1+.02*pr(t,0,tw))})`;big.style.filter=p<.95?`blur(${(1-p)*14}px)`:'none';
    sub.at(t,[T(1),T(2),T(3)]);
    tf(teal,W*(1-E.io(pr(t,tw,.5))),0);tf(navy,W*(1-E.io(pr(t,tw+.12,.5))),0);
    logo.set(pr(t,tw+.35,1.5));logo.el.style.transform=`scale(${lerp(.94,1,E.out(pr(t,tw+.3,D-tw)))})`;
    l1.at(t,[T(6),T(7),T(8)]);l2.at(t,[T(9),T(10),T(11)]);bar.style.transform=`scaleX(${E.expo(pr(t,T(11),.6))})`;
  };
});

// caption groups: a column beside the plate (above it in 9:16); lines stack, so a wrapped line never collides
function Group(root){return mk(root,'abs',V?{left:'60px',top:'312px',width:'960px',height:'376px',display:'flex',flexDirection:'column',justifyContent:'center',alignItems:'center',gap:'10px'}
  :{left:'1225px',top:'150px',width:'620px',height:'780px',display:'flex',flexDirection:'column',justifyContent:'center',alignItems:'flex-end',gap:'16px'});}
const REL={position:'relative',left:'auto',top:'auto',width:'100%'};
const gKT=(g,text,size,o={})=>KT(g,text,{...REL,fontSize:size+'px',color:o.color||C.navy,justifyContent:V?'center':'flex-start',fontWeight:o.weight||700,hot:o.hot});
const gLN=(g,html,size,o={})=>LN(g,html,{...REL,fontSize:size+'px',color:o.color||C.ink2,textAlign:V?'center':'right',fontWeight:o.weight||500});
const gRow=g=>mk(g,'',V?{display:'flex',flexDirection:'row-reverse',gap:'16px',justifyContent:'center',marginTop:'8px'}:{display:'flex',flexDirection:'column',gap:'16px',alignItems:'flex-end',marginTop:'10px'});
const gChip=(g,text,cls,size)=>mk(g,'chip '+(cls||''),{position:'relative',fontSize:(size||(V?38:42))+'px',alignSelf:V?'center':'flex-end'},text);

// ================= S4 ask: the branch reports from the phone → one RFQ to every supplier =================
scene('s4',C.paper,(root)=>{
  const T=k=>wt('s4',k),tb=T(8)-.3,tc=T(11)-.15,D=dur('s4');const ch=chrome(root,0);
  const ph=Phone(root,L.phone,['02-phone-lowstock-filled.jpg','03-phone-lowstock-sent.jpg']);
  const g1=Group(root),k1=gLN(g1,'الفرع يبلّغك من الجوال',V?46:44),c1=gKT(g1,'الزيت قرّب يخلص',V?108:112);
  const web=Web(root,L.plate,['5-rfq-suppliers.jpg','6-rfq-sent.jpg']);
  const ring=web.ring(352,222,1216,46);
  const g2=Group(root),c2=gKT(g2,'طلب واحد',V?124:136),c3=gKT(g2,'لكل *مورّدينك',V?104:108);
  return t=>{ch(t);
    ph.enter(t,.05,tb,{dy:140});ph.show(t,[T(6)+.1]);
    k1.at(t,T(0),tb-.05);c1.at(t,[T(5),T(6),T(7)],tb);
    web.enter(t,tb+.08,D-.25,{dx:160,dy:0});web.show(t,[tc]);
    web.camKeys(t,V?[[tb,960,470,900],[tc-.15,960,490,800],[tc,960,260,1300],[tc+.8,960,250,1240]]:[[tb,960,470,1000],[tc-.15,960,480,840],[tc,960,300,1380],[tc+.8,960,250,1270]]);
    ring.at(t,tc+.45);
    c2.at(t,[T(8),T(9)],D-.22);c3.at(t,[T(11),T(12)],D-.2);
  };
});

// ================= S5 read: a WhatsApp photo, read by the system; you review and authorise =================
scene('s5',C.paper,(root)=>{
  const T=k=>wt('s5',k),tb=T(6)-.3,tc=T(12)-.2,td=T(17)-.2,D=dur('s5');const ch=chrome(root,1);
  const pp=V?{x:300,y:740,w:480,h:640}:{x:375,y:205,w:500,h:667};
  const paper=mk(root,'paper',box(pp.x,pp.y,pp.w,pp.h));img(paper,'build/tex/photo.jpg');
  const chip=mk(root,'chip',{left:(pp.x+pp.w/2-150)+'px',top:(pp.y+pp.h-40)+'px',width:'300px',textAlign:'center',fontSize:'40px'},'صورة واتساب');
  const g1=Group(root),c1=gKT(g1,'جاك الرد صورة واتساب؟',V?76:72,{color:C.ink2,weight:600});
  const c2=mk(g1,'',{position:'relative',width:'100%',textAlign:V?'center':'right',direction:'rtl',fontSize:(V?150:136)+'px',fontWeight:700,lineHeight:1.25,whiteSpace:'nowrap',transformOrigin:V?'50% 50%':'100% 50%'},'ولا يهمّك.');
  const web=Web(root,L.plate,['09-quote-lines-photo.jpg','08-quote-review.jpg','10-quote-authorised.jpg']);
  const scan=mk(web.world,'abs',{left:'997px',top:'56px',width:'660px',height:'6px',background:C.teal,boxShadow:'0 0 0 2px rgba(18,165,148,.25), 0 -40px 60px 10px rgba(18,165,148,.18)'});
  const r1=web.ring(748,274,170,318),r2=web.ring(604,274,112,318),r3=web.ring(600,384,162,56),r4=web.ring(1296,390,376,58),r5=web.ring(1086,156,196,46);
  const g2=Group(root),k2=gLN(g2,'النظام يقرأ العرض لحاله',V?52:50,{weight:600,color:C.navy}),row=gRow(g2);
  const chips=['الأصناف','الأسعار','الضريبة'].map(s=>gChip(row,s,'teal',V?44:50));
  const g3=Group(root),c3=gKT(g3,'بدون ما تكتب ولا رقم',V?88:116),ok=gChip(g3,'الإجمالي مطابق <span style="color:#12A594">✓</span>','light',V?40:40);
  const g4=Group(root),c4=gKT(g4,'وأنت بس تراجع *وتعتمد',V?112:116);
  return t=>{ch(t);
    pop(paper,t,.02,tb-.05,{dy:200,r:-5,r0:-10,s0:.85,ox:-200});pop(chip,t,T(2),tb-.1,{dy:30,ox:-200});
    c1.at(t,[T(0),T(1),T(2),T(3)],tb-.1);
    const p=E.expo(pr(t,T(4)-.05,.4));c2.style.opacity=cl(pr(t,T(4)-.05,.08)-pr(t,tb-.12,.2));c2.style.transform=`scale(${lerp(1.5,1,p)})`;
    web.enter(t,tb+.05,D-.26,{dy:90});web.show(t,[tc,td]);
    web.camKeys(t,V?[[tb,1300,300,860],[T(8)-.55,1300,300,820],[T(8)-.05,620,370,780],[tc-.2,620,400,760],[tc,1300,420,1000],[tc+.6,1300,400,840],[td-.15,1300,400,820],[td,1330,330,900],[td+.8,1380,250,720]]
                   :[[tb,1300,300,960],[T(8)-.55,1300,300,900],[T(8)-.05,640,360,900],[tc-.2,640,380,860],[tc,1250,420,1100],[tc+.6,1250,400,920],[td-.15,1250,400,900],[td,1300,330,1000],[td+.8,1330,260,820]]);
    const sp=pr(t,tb+.4,T(8)-tb-.95);scan.style.opacity=t<tc&&sp>0&&sp<1?1:0;scan.style.top=(56+sp*352)+'px';
    r1.at(t,T(8),tc-.1);r2.at(t,T(9),tc-.1);r3.at(t,T(10),tc-.1);r4.at(t,tc+.45,td-.1);r5.at(t,td+.7);
    k2.at(t,T(6),tc-.12);chips.forEach((c,k)=>pop(c,t,T(8+k)-.05,tc-.14+k*.03,{dy:0,dx:V?0:120,oy:-30}));
    c3.at(t,[T(12),T(13),T(14),T(15),T(16)],td-.12);pop(ok,t,tc+.6,td-.14,{dy:30,oy:-30});
    c4.at(t,[T(17),T(18),T(19),T(20)],D-.22);
  };
});

// ================= S6 compare: per pack, VAT and delivery included → who is cheaper, in numbers =================
scene('s6',C.paper,(root)=>{
  const T=k=>wt('s6',k),tb=T(8)-.25,D=dur('s6');const ch=chrome(root,2);
  const web=Web(root,L.plate,['11-smart-compare.jpg']);
  const rr=web.ring(256,518,1408,264),ra=web.ring(1208,874,108,40),rb=web.ring(1208,928,108,40,C.navy);
  const g1=Group(root),c1=gKT(g1,'يقارن لك العروض *صح',V?100:104),row=gRow(g1);
  const chips=['بالكرتون','شامل الضريبة','والتوصيل'].map(s=>gChip(row,s,'',V?40:44));
  const g2=Group(root),k2=V?{at(){}}:gLN(g2,'مين الأوفر لك؟',52,{weight:600,color:C.navy});
  // Converge motif: the compared bar stops, the better one carries on as the arrow
  const bw=V?860:620,bb=mk(g2,'',{position:'relative',width:bw+'px',height:'170px',flex:'none'});
  const b1=mk(bb,'abs',{left:bw*.2+'px',top:'0',width:bw*.8+'px',height:'68px',borderRadius:'99px',background:C.mist,transformOrigin:'100% 50%'});
  const t1=mk(bb,'abs',{...box(0,10,bw-30),textAlign:'right',direction:'rtl',fontSize:'34px',fontWeight:600,color:C.navy},'الوفرة · ١٬٥٦٠ ر.س');
  const b2=mk(bb,'abs',{left:bw*.1+'px',top:'90px',width:bw*.9+'px',height:'68px',borderRadius:'99px',background:C.teal,transformOrigin:'100% 50%'});
  const ah=mk(bb,'abs',{left:(bw*.1-58)+'px',top:(90-24)+'px',width:'84px',height:'116px',background:C.teal,clipPath:'polygon(100% 0,0 50%,100% 100%)',transformOrigin:'100% 50%'});
  const t2=mk(bb,'abs',{...box(0,100,bw-30),textAlign:'right',direction:'rtl',fontSize:'34px',fontWeight:700,color:C.white},'الذهبي · ١٬٥٢٠ ر.س');
  const big=gKT(g2,'أوفر *بـ٤٠ *ر.س',V?116:104),note=V?{at(){}}:gLN(g2,'على ١٠ تنكات زيت · شامل الضريبة والتوصيل',30);
  return t=>{ch(t);
    web.enter(t,.05,D-.26,{dx:160,dy:0});
    web.camKeys(t,V?[[0,960,330,1450],[T(4)-.3,960,650,1420],[tb,960,650,1420],[tb+.7,1250,890,860]]:[[0,960,420,1560],[T(4)-.3,960,650,1440],[tb,960,650,1440],[tb+.7,1180,890,1000]]);
    rr.at(t,T(4)-.1,tb);ra.at(t,tb+.8);rb.at(t,tb+1.0);
    c1.at(t,[T(0),T(1),T(2),T(3)],tb-.1);chips.forEach((c,k)=>pop(c,t,T([4,6,7][k])-.05,tb-.14+k*.03,{dy:0,dx:V?0:120,oy:-30}));
    k2.at(t,T(8)-.1,D-.22);
    const o=1-pr(t,D-.25,.2);
    b1.style.transform=`scaleX(${E.expo(pr(t,T(8),.5))})`;b2.style.transform=`scaleX(${E.expo(pr(t,T(8)+.18,.6))})`;
    const a=pr(t,T(8)+.62,.3);ah.style.transform=`scale(${a>0?E.back(a):0})`;
    t1.style.opacity=pr(t,T(8)+.2,.2)*o;t2.style.opacity=pr(t,T(8)+.4,.2)*o;[b1,b2,ah].forEach(e=>e.style.opacity=o);
    big.at(t,T(10)-.05,D-.22,.1);note.at(t,T(11)+.2,D-.22);
  };
});

// ================= S7 approve: the draft is prepared → the manager approves on the phone → the PO goes out =================
scene('s7',C.paper,(root)=>{
  const T=k=>wt('s7',k),tb=T(4)-.3,tc=T(12)-.3,D=dur('s7');const ch=chrome(root,3);
  const web=Web(root,L.plate,['12-guardrail-draft.jpg']);const r1=web.ring(556,126,808,96);
  const g1=Group(root),c1=gKT(g1,'الطلب يتجهّز لك',V?112:116),dchip=gChip(g1,'مسودة، مو شراء','light',V?42:44);
  const ph=Phone(root,L.phone,['3-phone-approval-detail.jpg','14-phone-approved.jpg']);
  const tap=mk(ph.world,'abs',{left:'72px',top:'652px',width:'60px',height:'60px',borderRadius:'50%',background:'rgba(18,165,148,.35)',border:'3px solid #12A594'});
  const g2=Group(root),c2=gKT(g2,'المدير يعتمد *من *جواله',V?108:112),k2=gLN(g2,'وهو في أي مكان',V?58:60,{weight:600});
  const po=Web(root,L.plate,['17-po-submitted.jpg']);const r2=po.ring(1390,136,190,50),r3=po.ring(360,112,72,40);
  const g3=Group(root),c3=gKT(g3,'وأمر الشراء للمورد *على *طول',V?104:108);
  return t=>{ch(t);
    web.enter(t,.05,tb,{dx:160,dy:0});web.camKeys(t,V?[[0,960,400,1000],[1.2,960,300,840]]:[[0,960,400,1150],[1.2,960,330,900]]);r1.at(t,.9,tb);
    c1.at(t,[T(0),T(1),T(2)],tb-.05);pop(dchip,t,T(3)-.05,tb-.1,{dy:30,oy:-30});
    ph.enter(t,tb+.1,tc,{dy:160});ph.show(t,[T(5)+.45]);
    const a=pr(t,T(5),.45);tap.style.opacity=a>0&&a<1?1-a*.6:0;tap.style.transform=`scale(${lerp(.4,1.8,E.out(a))})`;
    c2.at(t,[T(4),T(5),T(6),T(7)],tc-.05);k2.at(t,T(8),tc-.08);
    po.enter(t,tc+.1,D-.26,{dx:160,dy:0});po.camKeys(t,V?[[tc,968,320,1340],[tc+1.2,968,290,1250]]:[[tc,968,340,1420],[tc+1.2,968,300,1280]]);r2.at(t,tc+1.1);r3.at(t,T(14));
    c3.at(t,[T(12),T(13),T(15),T(16),T(17)],D-.22);
  };
});

// ================= S8 save: «كم وفّرنا؟» → the number → the verified ledger =================
scene('s8',C.navy,(root)=>{
  const T=k=>wt('s8',k),tb=T(6)-.05,tc=T(8)-.3,D=dur('s8');
  const k1=LN(root,'وإذا سألك صاحب المطعم:',{...box(0,V?590:170,W),textAlign:'center',fontSize:(V?56:60)+'px',color:C.mist,fontWeight:500});
  const q=KT(root,'كم وفّرنا؟',{...box(0,V?790:370,W),fontSize:(V?230:300)+'px',justifyContent:'center',color:C.white});
  const teal=mk(root,'abs',{...box(0,0,W,H),background:C.teal});
  const blk=mk(teal,'abs',{...box(0,0,W,H),transformOrigin:V?'50% 28%':'50% 50%'});
  const l1=LN(blk,'توفير على هذا الطلب',{...box(0,V?640:250,W),textAlign:'center',fontSize:(V?64:66)+'px',color:C.white,fontWeight:600});
  const num=mk(blk,'abs',{...box(0,V?740:330,W),textAlign:'center',direction:'rtl',fontSize:(V?290:360)+'px',fontWeight:700,color:C.white,lineHeight:1.25,whiteSpace:'nowrap'});
  const l2=LN(blk,'مقابل آخر سعر شراء',{...box(0,V?1110:790,W),textAlign:'center',fontSize:(V?50:52)+'px',color:C.navy,fontWeight:600});
  const web=Web(teal,V?{x:50,y:760,w:980,h:740}:{x:90,y:170,w:1150,h:740},['20-ledger-verified.jpg']);
  const r1=web.ring(1042,280,398,98,C.navy),r2=web.ring(544,542,100,292,C.navy);
  const c3=KT(teal,'كل ريال مسجّل *ومراجَع',V?{...box(70,1530,940),fontSize:'70px',justifyContent:'center',color:C.white,hot:C.navy}:{...box(1310,650,530),fontSize:'76px',color:C.white,hot:C.navy});
  return t=>{
    k1.at(t,T(0),tb-.1);q.at(t,[T(4)-.3,T(5)-.3],tb-.05);q.el.style.scale=1+.04*pr(t,T(4),tb-T(4));
    tf(teal,0,H*(1-E.expo(pr(t,tb,.55))));
    l1.at(t,tb+.25);l2.at(t,tb+.9);
    const n=190*E.out(pr(t,tb+.3,1.0));num.innerHTML=arNum(n)+' <span style="font-size:.42em;font-weight:600">ر.س</span>';
    num.style.opacity=pr(t,tb+.25,.15);num.style.transform=`scale(${lerp(.8,1,E.back(pr(t,tb+.25,.5)))})`;
    const m=E.io(pr(t,tc,.6));blk.style.transform=V?`translateY(${-360*m}px) scale(${lerp(1,.62,m)})`:`translateX(${575*m}px) translateY(${-170*m}px) scale(${lerp(1,.44,m)})`;
    web.enter(t,tc+.15,D-.3,{dy:140,ox:0});web.camKeys(t,V?[[tc,990,430,1200],[tc+1.4,990,430,1000]]:[[tc,850,440,1480],[tc+1.6,830,400,1260]]);
    r1.at(t,tc+.9);r2.at(t,T(12)-.1);
    c3.at(t,[T(8),T(9),T(11),T(12)],D-.28);
    const o=1-pr(t,D-.3,.25);blk.style.opacity=o;
  };
});

// ================= S9 brand + CTA =================
scene('s9',C.teal,(root)=>{
  const T=k=>wt('s9',k),tb=T(5)-.35,tc=T(11)-.3,D=dur('s9');
  const navy=mk(root,'abs',{...box(0,0,W,H),background:C.navy});
  const bars=[[.14,.5],[.74,.36]].map(([y,w])=>mk(navy,'abs',{left:0,top:H*y+'px',width:W*w+'px',height:(V?130:110)+'px',borderRadius:'0 999px 999px 0',background:C.mist,opacity:.05}));
  const lw=V?800:900,ly=V?560:230,logo=Logo(navy,'dark',(W-lw)/2,ly,lw);
  const ty=V?860:560,fs=V?104:124,gap=V?330:420;
  const tag=['قارن.','اختار.','وفّر.'].map((s,k)=>LN(navy,s,{...box(W/2+gap*(1-k)-200,ty,400),textAlign:'center',fontSize:fs+'px',fontWeight:700,color:k===2?C.tealOn:C.white}));
  const tbar=tag.map((_,k)=>mk(navy,'abs',{left:(W/2+gap*(1-k)-(V?120:150))+'px',top:(ty+fs*1.42)+'px',width:(V?240:300)+'px',height:'12px',borderRadius:'99px',background:k===2?C.tealOn:C.mist,transformOrigin:'100% 50%'}));
  const offer=KT(navy,'جرّبه أسبوعين *مجانًا',{...box(V?40:0,V?640:330,V?1000:W),fontSize:(V?132:164)+'px',justifyContent:'center',color:C.white,hot:C.tealOn});
  const sub=LN(navy,'وحنّا نجهّزه معك',{...box(0,V?990:560,W),textAlign:'center',fontSize:(V?66:72)+'px',color:C.mist,fontWeight:500});
  const pw=V?860:1180,pill=mk(navy,'abs',{...box((W-pw)/2,V?1160:700,pw,V?210:150),borderRadius:'32px',background:C.tealOn,display:'flex',flexDirection:V?'column':'row-reverse',alignItems:'center',justifyContent:'center',gap:V?'6px':'36px',direction:'ltr'},
    `<span style="direction:rtl;white-space:nowrap;font-size:${V?46:48}px;font-weight:600;color:#0B2545">راسلنا واتساب</span><span class="ltr" style="white-space:nowrap;font-size:${V?78:76}px;font-weight:700;color:#fff;letter-spacing:.01em">+20 102 735 4140</span>`);
  const foot=LN(navy,'<span class="ltr">www.iron-sys.com &nbsp;·&nbsp; hello@iron-sys.com</span>',{...box(0,V?1420:900,W),textAlign:'center',fontSize:(V?36:36)+'px',color:C.mist,fontWeight:400});
  return t=>{
    tf(navy,W*(1-E.io(pr(t,0,.55))),0);bars.forEach((e,k)=>tf(e,-W*.4*(1-E.expo(pr(t,.2+k*.1,.9)))+t*(8+k*6),0));
    logo.set(pr(t,T(0)-.1,1.5));
    const m=E.io(pr(t,tb,.6));logo.el.style.transform=`translateY(${(V?-270:-150)*m}px) scale(${lerp(1,V?.5:.42,m)})`;
    tag.forEach((l,k)=>{l.at(t,T(2+k)-.05,tb-.05+k*.03);tbar[k].style.transform=`scaleX(${E.expo(pr(t,T(2+k)+.1,.45))*(1-E.in(pr(t,tb-.05,.25)))})`;});
    offer.at(t,[T(5),T(6),T(7)]);sub.at(t,T(8));
    pop(pill,t,tc,null,{dy:70,s0:.9});foot.at(t,tc+.55);
    const k=1+.02*pr(t,tb,D-tb);offer.el.style.scale=k;
  };
});

// ---- transitions that sit above scenes: the Converge bars sweep, and a rising plane ----
function barsWipe(at,colors,dir=1){const half=.34,lag=.07;const bands=colors.map((c,k)=>mk(st,'abs',{left:0,top:Math.floor(H*k/colors.length)+'px',width:W+'px',height:Math.ceil(H/colors.length)+1+'px',background:c,zIndex:500,display:'none'}));
  overlays.push(T=>{bands.forEach((b,k)=>{const n=colors.length-1,t0=at-half-(n-k)*lag,t1=at+k*lag;const on=T>=t0&&T<=t1+half;b.style.display=on?'block':'none';if(!on)return;
    const x=dir*W*(1-E.io(pr(T,t0,half)))-dir*W*E.io(pr(T,t1,half));b.style.transform=`translateX(${x}px)`;});});}
function planeWipe(at,color){const p=mk(st,'abs',{...box(0,0,W,H),background:color,zIndex:500,display:'none'});
  overlays.push(T=>{const on=T>=at-.42&&T<at;p.style.display=on?'block':'none';if(on)p.style.transform=`translateY(${H*(1-E.io(pr(T,at-.42,.4)))}px)`;});}
barsWipe(SEG.s2.start,[C.mist,'#E3EAF1',C.mist],1);
barsWipe(SEG.s4.start,[C.mist,C.tealOn,C.mist],-1);
planeWipe(SEG.s8.start,C.navy);
mk(st,'grain');

window.DURATION=AD.duration;
window.READY=Promise.all(pending).then(()=>document.fonts.ready);
window.renderAt=T=>{
  for(const s of scenes){const on=T>=s.start&&T<s.end;s.root.style.display=on?'block':'none';if(on)s.update(T-s.start);}
  overlays.forEach(f=>f(T));
};
