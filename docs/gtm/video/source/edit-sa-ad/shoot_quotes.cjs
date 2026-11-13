// Screenshot the real round-A demo quotes (HTML sources of the PDFs) as paper sheets.
const { chromium } = require('playwright');const path=require('path');
const [,,src,out]=process.argv;
(async()=>{const b=await chromium.launch();const p=await b.newPage({viewport:{width:794,height:1123},deviceScaleFactor:1.25});
for(const n of ['wafra','qassim','dhahabi']){await p.goto('file://'+path.resolve(src,n+'.html'));await p.waitForTimeout(300);await p.screenshot({path:path.join(out,n+'.png')});}
await b.close();})();
