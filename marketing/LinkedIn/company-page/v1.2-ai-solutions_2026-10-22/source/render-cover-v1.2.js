const fs=require('fs'),path=require('path');
const {chromium}=require('/opt/node22/lib/node_modules/playwright');
const out=process.argv[2]||'out2';
const sym='data:image/png;base64,'+fs.readFileSync('/mnt/user-data/uploads/IronSystem/Branding/Identity-v3/logo/png/iron-system-symbol-metal-2048.png').toString('base64');
const hex=`url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='76.21' height='132' viewBox='0 0 76.21 132'%3E%3Cpath d='M38.1 0L76.21 22V66L38.1 88L0 66V22ZM38.1 88V132' fill='none' stroke='%23E2E8F0' stroke-opacity='.10'/%3E%3C/svg%3E")`;
const fonts='<link href="https://fonts.googleapis.com/css2?family=Archivo:wdth,wght@125,600;125,700;125,800&family=Inter:wght@500;600&family=Readex+Pro:wght@500;600;700&display=block" rel="stylesheet">';
function cover(ar){
 const T = ar ? {
  head:'حلول الذكاء الاصطناعي',
  sub:'نمكّن الأعمال بتقنيات ذكية.',
  svc:['مساعدون ذكيون','ذكاء المستندات','الأتمتة الذكية','التحليلات التنبؤية']
 } : {
  head:'AI SOLUTIONS',
  sub:'Powering Businesses with Intelligent Technologies.',
  svc:['AI Assistants','Document AI','AI Automation','Predictive Analytics']
 };
 const headS = ar? "font-family:'Readex Pro';font-weight:700;font-size:32px;line-height:1.2;white-space:nowrap" : "font-family:Archivo;font-stretch:125%;font-weight:800;font-size:34px;line-height:1;letter-spacing:-.005em;white-space:nowrap";
 const subS = ar? "font-family:'Readex Pro';font-weight:500;font-size:16px;color:#E2E8F0;white-space:nowrap" : "font-family:Inter;font-weight:500;font-size:14.5px;color:#E2E8F0;letter-spacing:-.005em;white-space:nowrap";
 const svcS = ar? "font-family:'Readex Pro';font-weight:500;font-size:11.5px" : "font-family:Inter;font-weight:500;font-size:10.5px;letter-spacing:.02em";
 const svc = T.svc.map(s=>`<span>${s}</span>`).join('<i style="display:inline-block;width:4px;height:4px;background:#F97316;transform:rotate(45deg);margin:0 10px 1px"></i>');
 // ticks on the hairlines
 let ticks=''; for(let x=370;x<=1100;x+=24){ticks+=`<div style="position:absolute;left:${x}px;top:22px;width:1px;height:${x%120===10?6:3}px;background:rgba(226,232,240,.18)"></div><div style="position:absolute;left:${x}px;bottom:22px;width:1px;height:${x%120===20?6:3}px;background:rgba(226,232,240,.18)"></div>`;}
 return `<html><head>${fonts}</head><body style="margin:0;width:1128px;height:191px;background:#0B0F17;overflow:hidden;position:relative">
<div style="position:absolute;inset:0;background:linear-gradient(180deg,#0B0F17 0,#0E131D 100%)"></div>
<!-- right panel, left edge at the brand's 30 deg -->
<div style="position:absolute;top:0;bottom:0;right:0;width:400px;background:#111827;clip-path:polygon(110px 0,100% 0,100% 100%,0 100%)"></div>
<div style="position:absolute;top:0;bottom:0;right:0;width:400px;background-image:${hex};background-size:30px 52px;clip-path:polygon(110px 0,100% 0,100% 100%,0 100%);-webkit-mask-image:radial-gradient(60% 90% at 62% 55%,#000 10%,transparent 90%)"></div>
<div style="position:absolute;top:0;bottom:0;right:399px;width:2px;"></div>
<svg style="position:absolute;right:0;top:0" width="400" height="191"><line x1="110" y1="0" x2="0" y2="191" stroke="#1E293B" stroke-width="1.5"/><line x1="122" y1="0" x2="12" y2="191" stroke="#F97316" stroke-width="2" stroke-opacity=".9" stroke-dasharray="0 150 41 0"/></svg>
<div style="position:absolute;right:20px;top:-40px;width:330px;height:300px;background:radial-gradient(closest-side at 50% 60%,rgba(249,115,22,.16),transparent 70%)"></div>
<img src="${sym}" style="position:absolute;right:108px;top:24px;height:143px">
<!-- hairlines -->
<div style="position:absolute;left:370px;right:0;top:22px;height:1px;background:linear-gradient(90deg,rgba(226,232,240,.18),rgba(226,232,240,.06) 55%,transparent 62%)"></div>
<div style="position:absolute;left:370px;right:0;bottom:22px;height:1px;background:linear-gradient(90deg,rgba(226,232,240,.18),rgba(226,232,240,.06) 55%,transparent 62%)"></div>
<div style="position:absolute;inset:0;-webkit-mask-image:linear-gradient(90deg,#000 0,#000 55%,transparent 62%)">${ticks}</div>
<!-- copy -->
<div dir="${ar?'rtl':'ltr'}" style="position:absolute;${ar?'right:430px;left:330px':'left:370px;right:330px'};top:23px;bottom:23px;display:flex;flex-direction:column;justify-content:center;gap:${ar?6:9}px;color:#E2E8F0">
 <div style="display:flex;align-items:center;gap:12px"><span style="width:22px;height:3px;background:#F97316;flex:none"></span><span style="${headS}">${T.head}</span></div>
 <div style="${subS}">${T.sub}</div>
 <div style="${svcS};color:#94A3B8;white-space:nowrap;margin-top:2px">${svc}</div>
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
