// Structural timeline execution without Chrome. Does not certify typography or visual layout.
const fs=require('fs'),path=require('path'),vm=require('vm'),assert=require('assert');
class Node {
  constructor(tag){this.tag=tag;this.style={};this.children=[];this.classList={add(){}};this.complete=true;this.textContent='';}
  appendChild(n){this.children.push(n);return n;}
  setAttribute(){}
  set innerHTML(value){this._html=value;this.firstChild=new Node('filter-child');}
  get innerHTML(){return this._html;}
  querySelector(tag){return this.children.find(c=>c.tag===tag);}
  decode(){return Promise.resolve();}
}
(async()=>{
 for(const lang of ['en'])for(const fmt of ['h','v']){
  const stage=new Node('stage'),defs=new Node('defs');const nodes=[];
  const doc={getElementById:id=>id==='stage'?stage:defs,createElement:tag=>{const n=new Node(tag);nodes.push(n);return n;},createElementNS:(_,tag)=>new Node(tag),querySelectorAll:tag=>nodes.filter(n=>n.tag===tag)};
  const ctx={document:doc,console,Promise,Math,LANG:lang,FMT:fmt};ctx.window=ctx;vm.createContext(ctx);
  for(const file of ['data.js','engine.js','compose.js',`spec_${fmt}.js`])vm.runInContext(fs.readFileSync(path.join(__dirname,file),'utf8'),ctx,{filename:file});
  // Caption revision 2026-10-25: 16:9 body 103 s (3090 frames), 9:16 body 1529 frames.
  assert.equal(Math.round(ctx.DURATION*30),fmt==='h'?3090:1529);
  const timeline=ctx.TIMELINES[fmt];
  assert(timeline.body+timeline.outro<=(fmt==='v'?59.5:122));
  assert(fmt==='v'||Math.abs(timeline.body+timeline.outro-112.75)<.01);
  assert(timeline.scenes.every(s=>s.beat!==4&&s.beat!==9),'beats 4 and 9 are dropped');
  assert.equal(timeline.scenes.find(s=>s.beat===1).duration,fmt==='h'?8:4);
  // 16:9: pain/bridge card then fix on beats 1,3,5,8,10,13. 9:16: two cards only on beats 1 and 13.
  const twoCard=fmt==='h'?[1,3,5,8,10,13]:[1,13];
  for(const s of timeline.scenes){
    const cards=s.cards_by_language[lang];
    assert.equal(cards.length,twoCard.includes(s.beat)?2:1,`beat ${s.beat} card count`);
    if(cards.length===2)assert(cards[0].offset===0&&cards[0].duration===2.5&&cards[1].offset===2.5&&cards[1].role==='fix');
    assert(Math.abs(cards.reduce((n,c)=>n+c.duration,0)-s.duration)<.001);
    for(const c of cards)assert(!/وفر|وفورات/.test(c.text),`beat ${s.beat}: use «توفير»`);
  }
  const beat1=timeline.scenes.find(s=>s.beat===1).cards_by_language[lang][0].text;
  assert.equal(beat1,lang==='ar'?'ProcurePilot لمشتريات المطاعم':'ProcurePilot, for restaurant purchasing');
  for(const [beat,name] of [[7,'s2r-authorised'],[11,'s4r-approved']]){
    const spans=timeline.scenes.find(s=>s.beat===beat).spans_by_language[lang];
    const result=spans.at(-1);assert.equal(result[0],name);assert.equal(Math.round(result[3]*30),54);
    assert(result[1]>=0&&result[2]<ctx.PLATE_META[lang+'/'+name].frames/30);
  }
  const times=new Set([0,ctx.DURATION-1/30]);
  for(const s of timeline.scenes){times.add(s.start);times.add(s.start+.6);times.add(s.start+s.duration-.01);let at=s.start;for(const span of s.spans_by_language[lang]){times.add(at+.01);times.add(at+span[3]-.01);at+=span[3];}}
  let checks=0;
  for(const t of times){
   await ctx.renderAt(t);
   for(const n of nodes){
    if(n.style.display!=='none')assert(!String(n.style.transform).includes('NaN'));
    if(n.tag==='img'&&n.src&&n.src.startsWith('plates/')){assert(fs.existsSync(path.join(__dirname,n.src)),`Missing ${n.src}`);checks++;}
   }
  }
  console.log('TIMELINE_STRUCTURE',lang,fmt,'duration',ctx.DURATION,'sample_times',times.size,'plate_path_checks',checks);
 }
 console.log('PASS: all four timelines execute at scene boundaries; visual QA still requires Chrome');
})().catch(e=>{console.error(e);process.exit(1)});
