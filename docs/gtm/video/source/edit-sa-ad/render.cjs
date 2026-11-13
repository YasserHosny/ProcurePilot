// node render.cjs <h|v> <outDir> <f0> <f1> [comma-separated seconds for stills]
const { chromium } = require('playwright');const fs=require('fs'),path=require('path');
const [,,fmt,out,f0,f1,only]=process.argv;const W=fmt==='v'?1080:1920,H=fmt==='v'?1920:1080;
(async()=>{
  const b=await chromium.launch({args:['--allow-file-access-from-files','--disable-web-security','--font-render-hinting=none']});
  const p=await b.newPage({viewport:{width:W,height:H}});
  let fatal;p.on('pageerror',e=>{fatal=e;console.error('PAGEERR',e.message)});p.on('console',m=>{if(m.type()==='error')console.error('CONSOLE',m.text())});
  await p.goto('file://'+path.resolve(__dirname,'index.html')+'#'+fmt);await p.evaluate(()=>window.READY);
  fs.mkdirSync(out,{recursive:true});
  const jobs=only?only.split(',').map(s=>[+s,`t${(+s).toFixed(2).padStart(6,'0')}.jpg`]):Array.from({length:(+f1)-(+f0)},(_,i)=>[(+f0+i)/30,String(+f0+i).padStart(5,'0')+'.jpg']);
  for(const [t,name] of jobs){await p.evaluate(t=>window.renderAt(t),t);if(fatal)throw fatal;await p.screenshot({path:path.join(out,name),type:'jpeg',quality:only?85:95});}
  await b.close();
})().catch(e=>{console.error(e);process.exit(1)});
