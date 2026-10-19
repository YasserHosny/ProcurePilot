const { chromium } = require(process.env.PP_PLAYWRIGHT||'playwright');
const fs=require('fs'),path=require('path');
const [,,fmt,out,f0,f1,only]=process.argv; const W=fmt==='v'?1080:1920,H=fmt==='v'?1920:1080;
(async()=>{
  const b=await chromium.launch({executablePath:process.env.PP_CHROME||undefined,args:['--allow-file-access-from-files','--disable-web-security']});
  const p=await b.newPage({viewport:{width:W,height:H}});
  p.on('pageerror',e=>console.error('PAGEERR',e.message)); p.on('console',m=>{ if(m.type()==='error') console.error('CONSOLE',m.text()); });
  await p.goto('file://'+path.resolve(__dirname,'index.html')+'#'+fmt); await p.evaluate(()=>document.fonts.ready); await p.waitForTimeout(500);
  fs.mkdirSync(out,{recursive:true});
  const frames = only? only.split(',').map(Number) : Array.from({length:(+f1)-(+f0)},(_,i)=>+f0+i);
  for(const f of frames){ await p.evaluate(t=>window.renderAt(t), f/30); await p.screenshot({path:path.join(out,String(f).padStart(5,'0')+'.jpg'),type:'jpeg',quality:94}); }
  await b.close();
})();
