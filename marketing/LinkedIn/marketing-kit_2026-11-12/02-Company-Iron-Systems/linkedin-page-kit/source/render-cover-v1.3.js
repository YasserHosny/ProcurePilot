const fs=require('fs'),path=require('path');
const {chromium}=require('/opt/node22/lib/node_modules/playwright');
const out=process.argv[2]||'out4', Y=+(process.argv[3]||320);
const bg='data:image/png;base64,'+fs.readFileSync(path.join(__dirname,'shards-bg.png')).toString('base64');
const fonts='<link href="https://fonts.googleapis.com/css2?family=Archivo:wdth,wght@125,800&family=Inter:wght@500&family=Readex+Pro:wght@500;700&display=block" rel="stylesheet">';
function cover(ar){
 const T = ar ? {head:'حلول الذكاء الاصطناعي', sub:'نمكّن الأعمال بتقنيات ذكية.', svc:['مساعدون ذكيون','ذكاء المستندات','الأتمتة الذكية','التحليلات التنبؤية']}
              : {head:'AI SOLUTIONS', sub:'Powering Businesses with Intelligent Technologies.', svc:['AI Assistants','Document AI','AI Automation','Predictive Analytics']};
 const headS = ar? "font-family:'Readex Pro';font-weight:700;font-size:32px;line-height:1.2" : "font-family:Archivo;font-stretch:125%;font-weight:800;font-size:34px;line-height:1;letter-spacing:-.005em";
 const subS = ar? "font-family:'Readex Pro';font-weight:500;font-size:16px" : "font-family:Inter;font-weight:500;font-size:14.5px;letter-spacing:-.005em";
 const svcS = ar? "font-family:'Readex Pro';font-weight:500;font-size:11.5px" : "font-family:Inter;font-weight:500;font-size:10.5px;letter-spacing:.02em";
 const svc = T.svc.map(s=>`<span>${s}</span>`).join('<i style="display:inline-block;width:4px;height:4px;background:#F97316;transform:rotate(45deg);margin:0 10px 1px"></i>');
 // background: the website's shard photo, band starting at source y=Y (1881 px wide source, 319 px tall band)
 const scale=1128/1881;
 return `<html><head>${fonts}</head><body style="margin:0;width:1128px;height:191px;background:#05070B;overflow:hidden;position:relative">
<div style="position:absolute;left:0;top:${-Y*scale}px;width:1128px;height:${836*scale}px;background:url(${bg}) 0 0/100% 100% no-repeat"></div>
<div style="position:absolute;inset:0;background:radial-gradient(60% 120% at ${ar?'52%':'47%'} 40%,rgba(5,7,11,.55),transparent 70%)"></div>
<div dir="${ar?'rtl':'ltr'}" style="position:absolute;${ar?'right:430px;left:300px':'left:370px;right:330px'};top:18px;height:132px;display:flex;flex-direction:column;justify-content:center;gap:${ar?6:9}px;color:#E2E8F0;text-shadow:0 1px 12px rgba(0,0,0,.6)">
 <div style="display:flex;align-items:center;gap:12px"><span style="width:22px;height:3px;background:#F97316;flex:none;box-shadow:0 0 8px rgba(249,115,22,.6)"></span><span style="${headS};white-space:nowrap">${T.head}</span></div>
 <div style="${subS};white-space:nowrap">${T.sub}</div>
 <div style="${svcS};color:#A8B3C4;white-space:nowrap;margin-top:2px">${svc}</div>
</div>
</body></html>`;
}
(async()=>{
 fs.mkdirSync(out,{recursive:true});
 const b=await chromium.launch({executablePath:'/opt/pw-browsers/chromium'});
 for(const [name,ar] of [['iron-systems-linkedin-cover',false],['iron-systems-linkedin-cover-ar',true]]){
  for(const sc of [1,2]){
   const p=await b.newPage({viewport:{width:1128,height:191},deviceScaleFactor:sc});
   await p.setContent(cover(ar)); await p.evaluate(()=>document.fonts.ready); await p.waitForTimeout(500);
   await p.screenshot({path:path.join(out,`${name}-${1128*sc}x${191*sc}.png`)}); await p.close();
  }
 }
 await b.close();
})();
