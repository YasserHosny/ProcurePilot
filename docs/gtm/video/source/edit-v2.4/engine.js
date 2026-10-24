// Brand editorial motion engine (v2.4 fork of v2.3): deterministic, frame-addressed (renderAt(t)).
// Colours are the official ProcurePilot palette (docs/brand/README.md); see ../../motion-style.md.
const C = { paper:'#F4F6F9', card:'#FFFFFF', mist:'#C9D6E3', ink:'#0B2545', mid:'#5B6B80',
  teal:'#12A594', tealDark:'#19B8A4', tealText:'#0C7A6E' };
const FPS = 30;
const META = window.PLATE_META;
let BEATS = window.BEATS || [];

// cubic-bezier easing
function bez(x1,y1,x2,y2){ const cx=3*x1,bx=3*(x2-x1)-cx,ax=1-cx-bx,cy=3*y1,by=3*(y2-y1)-cy,ay=1-cy-by;
  const sx=t=>((ax*t+bx)*t+cx)*t, sy=t=>((ay*t+by)*t+cy)*t, dx=t=>(3*ax*t+2*bx)*t+cx;
  return x=>{ if(x<=0)return 0; if(x>=1)return 1; let t=x; for(let i=0;i<8;i++){const e=sx(t)-x; const d=dx(t); if(Math.abs(e)<1e-6||!d)break; t-=e/d;} return sy(t); }; }
const EASE = { sig:bez(.72,0,.12,1), out:bez(.16,1,.3,1), in:bez(.7,0,.84,0), io:bez(.45,0,.2,1), lin:x=>x, hold:x=>0 };

function nb(t){ if(!BEATS.length) return t; let b=BEATS[0]; for(const x of BEATS){ if(Math.abs(x-t)<Math.abs(b-t)) b=x; } return Math.abs(b-t)<0.3? b : t; }

const ELS=[];
const stage=document.getElementById('stage');
const defs=document.getElementById('defs');
let uid=0;
class El{
  constructor(node,o){ this.node=node; this.id='e'+(uid++); this.o=Object.assign({x:0,y:0,ax:.5,ay:.5,s:1,sx:1,sy:1,r:0,o:1,ct:0,cr:0,cb:0,cl:0,ix:0,iy:0,z:1,depth:0,mb:1},o);
    this.tr={}; this.win=[o.t0??-1e9, o.t1??1e9]; node.style.zIndex=this.o.z; node.classList.add('el'); stage.appendChild(node); ELS.push(this);
    const f=document.createElementNS('http://www.w3.org/2000/svg','filter'); f.setAttribute('id','mb'+this.id); f.setAttribute('x','-40%'); f.setAttribute('y','-40%'); f.setAttribute('width','180%'); f.setAttribute('height','180%');
    f.innerHTML='<feGaussianBlur stdDeviation="0 0"/>'; defs.appendChild(f); this.fb=f.firstChild;
    if(this.o.depth>0){ const d=this.o.depth; this.shadow=`${3*d}px ${5*d}px ${12*d}px rgba(11,37,69,${0.16+0.035*d}), 0 0 0 1px rgba(0,0,0,.04)`; }
    this.last={}; }
  k(p,keys){ this.tr[p]=keys; return this; }
  on(t0,t1){ this.win=[t0,t1]; return this; }
  val(p,t){ const k=this.tr[p]; if(!k) return this.o[p]; if(t<=k[0][0]) return k[0][1];
    for(let i=1;i<k.length;i++){ if(t<k[i][0]){ const [t0,v0]=k[i-1],[t1,v1,e]=k[i]; const u=(EASE[e||'sig'])((t-t0)/(t1-t0)); return v0+(v1-v0)*u; } }
    return k[k.length-1][1]; }
  apply(t){
    const vis = t>=this.win[0] && t<this.win[1];
    if(!vis){ if(this.last.vis!==false){ this.node.style.display='none'; this.last.vis=false;} return; }
    if(this.last.vis!==true){ this.node.style.display='block'; this.last.vis=true; }
    const g=p=>this.val(p,t);
    const x=g('x'),y=g('y'),s=g('s'),sx=g('sx'),sy=g('sy'),r=g('r'),ax=this.o.ax,ay=this.o.ay;
    const n=this.node.style;
    n.transformOrigin=`${ax*100}% ${ay*100}%`;
    n.transform=`translate(${x}px,${y}px) translate(${-ax*100}%,${-ay*100}%) rotate(${r}deg) scale(${s*sx},${s*sy})`;
    n.opacity=g('o');
    const ct=g('ct'),cr=g('cr'),cb=g('cb'),cl=g('cl');
    n.clipPath=(ct||cr||cb||cl)?`inset(${ct}% ${cr}% ${cb}% ${cl}%)`:'none';
    if(this.inner){ this.inner.style.transform=`translate(${g('ix')}%,${g('iy')}%)`; }
    // motion blur from velocity over half a frame
    const dt=0.5/FPS; const dx=(x-this.val('x',t-dt))*s, dy=(y-this.val('y',t-dt))*s;
    let bx=Math.min(Math.abs(dx)*0.55,70), by=Math.min(Math.abs(dy)*0.55,70);
    if(this.inner){ const h=this.node.offsetHeight||100, w=this.node.offsetWidth||100;
      by=Math.max(by, Math.min(Math.abs((g('iy')-this.val('iy',t-dt))*h/100)*0.55,70));
      bx=Math.max(bx, Math.min(Math.abs((g('ix')-this.val('ix',t-dt))*w/100)*0.55,70)); }
    bx*=this.o.mb; by*=this.o.mb;
    const blur = (bx>1.2||by>1.2);
    this.fb.setAttribute('stdDeviation', `${blur?bx.toFixed(1):0} ${blur?by.toFixed(1):0}`);
    n.filter = blur?`url(#mb${this.id})`:'none';
    if(this.shadow) n.boxShadow = this.shadow;
    if(this.update) this.update(t);
  }
}
function div(cls,html){ const d=document.createElement('div'); if(cls)d.className=cls; if(html!=null)d.innerHTML=html; return d; }

// Text: mask container + inner moving line
function T(str,o){ const d=div('txt'); const inn=div('in'); inn.textContent=str; d.appendChild(inn);
  const st=d.style; st.fontSize=(o.size||100)+'px'; st.fontWeight=o.w||700; st.color=o.color||C.ink; st.lineHeight=o.lh||1.3;
  if(o.font) st.fontFamily=o.font; if(o.dir) d.dir=o.dir; else d.dir='rtl'; if(o.ls!=null) st.letterSpacing=o.ls+'em';
  if(o.bg){ st.background=o.bg; st.padding=o.pad||'0 .25em'; }
  const e=new El(d,o); e.inner=inn; return e; }
function R(o){ const d=div('rect'); d.style.width=o.w+'px'; d.style.height=o.h+'px'; d.style.background=o.color||C.teal; if(o.radius)d.style.borderRadius=o.radius+'px'; return new El(d,o); }
function IMG(src,o){ const d=div('img'); d.style.width=o.w+'px'; d.style.height=o.h+'px'; const im=document.createElement('img'); im.src=src; if(o.fit)im.style.objectFit=o.fit; if(o.pos)im.style.objectPosition=o.pos; d.appendChild(im);
  if(o.paper){ d.style.background=C.card; } return new El(d,o); }
// Plate: app footage as a printed plate. map(t) -> seconds into the plate.
const PENDING=[];
function PLATE(name,o){ const m=META[name]; const sc=o.w/(o.crop?o.crop[2]:m.box[2]); const w=Math.round(m.box[2]*sc), h=Math.round(m.box[3]*sc);
  const crop=o.crop; // [x,y,w,h] in plate px
  const d=div('plate'); const cw=crop?crop[2]*sc:w, ch=crop?crop[3]*sc:h; d.style.width=cw+'px'; d.style.height=ch+'px';
  const im=document.createElement('img'); im.style.width=w+'px'; im.style.height=h+'px'; if(crop){ im.style.left=(-crop[0]*sc)+'px'; im.style.top=(-crop[1]*sc)+'px'; }
  d.appendChild(im); d.appendChild(div('platefx'));
  const e=new El(d,Object.assign({depth:2},o)); e.h=ch; e.cur=-1;
  e.update=(t)=>{ const p=o.map(t); const idx=Math.max(1,Math.min(m.frames,Math.floor(p*FPS+1e-6)+1)); if(idx!==e.cur){ e.cur=idx; im.src=`plates/${name}/${String(idx).padStart(4,'0')}.jpg`; PENDING.push(im); } };
  return e; }
// piecewise plate clock: segs [[t0,p0,speed,t1]] ; holds before/after
function PM(segs){ return t=>{ let p=segs[0][1]; for(const [t0,p0,sp,t1] of segs){ if(t>=t0){ p = p0 + (Math.min(t,t1)-t0)*sp; } } return p; }; }

// Brand transition: the Converge mark as a wipe. Three bars in the mark's order (navy, teal with
// the arrowhead, navy) cross the frame left to right, the arrow's "forward" (never mirrored, even
// in Arabic). The middle bar leads like the mark's longest bar; the frame is fully covered at tc,
// which is where the cut between scenes sits.
function PASS(tc,o={}){ const W=o.W||1920, H=o.H||1080, dur=o.dur||.9, z=o.z||800;
  const bh=Math.ceil(H/3)+2, len=W*1.7, dist=len+W, lead=[.055,0,.11];
  const cols=[o.c1||C.ink,o.c2||C.teal,o.c3||C.ink];
  [0,1,2].forEach(i=>{ const t0=tc-dur/2+lead[i], t1=t0+dur;
    const d=div('rect'); d.style.width=len+'px'; d.style.height=bh+'px'; d.style.background=cols[i]; d.style.borderRadius=`0 ${bh/2}px ${bh/2}px 0`;
    const e=new El(d,{x:0,y:i*(H/3)-1,ax:0,ay:0,z:z+(i==1?2:0),mb:.6,t0,t1});
    // left edge from -len to +W; covered while left<=0 and right>=W
    e.k('x',[[t0,-len],[t1,W,'io']]);
    if(i==1){ const ah=Math.min(bh*1.7,W*.55), aw=ah*.92; /* capped so portrait frames keep the bars dominant */ const a=div('rect'); a.style.width=aw+'px'; a.style.height=ah+'px';
      a.innerHTML=`<svg viewBox="0 0 92 100" width="100%" height="100%" preserveAspectRatio="none"><path d="M4 4 L88 50 L4 96 Z" fill="${cols[1]}" stroke="${cols[1]}" stroke-width="8" stroke-linejoin="round"/></svg>`;
      const ar=new El(a,{x:0,y:H/2,ax:0,ay:.5,z:z+3,mb:.6,t0,t1}); ar.k('x',[[t0,0],[t1,W+len,'io']]); }
  });
}

// Grain overlay
const grain=div('grain'); stage.appendChild(grain);
window.renderAt = async (t)=>{
  PENDING.length=0;
  for(const e of ELS) e.apply(t);
  const gi=Math.floor(t*FPS/2)%4; grain.style.backgroundImage=`url(tex/grain${gi}.png)`;
  await Promise.all(PENDING.map(im=>im.decode().catch(()=>{})));
  await Promise.all([...document.querySelectorAll('img')].filter(i=>!i.complete).map(i=>i.decode().catch(()=>{})));
  return true;
};
