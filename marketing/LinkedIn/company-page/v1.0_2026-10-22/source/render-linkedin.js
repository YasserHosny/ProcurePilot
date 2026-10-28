const fs=require('fs'),path=require('path');
const {chromium}=require('/opt/node22/lib/node_modules/playwright');
const B='/mnt/user-data/uploads/IronSystem/Branding/Identity-v3/logo/';
const out=process.argv[2];
const du=s=>'data:image/svg+xml;base64,'+Buffer.from(s).toString('base64');
const metalIcon=fs.readFileSync(B+'iron-system-app-icon-metal.svg','utf8').replace(/<rect width="80" height="80" rx="[\d.]+"/,'<rect width="80" height="80" rx="0"');
const flatIcon=fs.readFileSync(B+'iron-system-app-icon-dark.svg','utf8').replace(/<rect width="80" height="80" rx="[\d.]+"/,'<rect width="80" height="80" rx="0"');
const hex=`url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='76.21' height='132' viewBox='0 0 76.21 132'%3E%3Cpath d='M38.1 0L76.21 22V66L38.1 88L0 66V22ZM38.1 88V132' fill='none' stroke='%23E2E8F0' stroke-opacity='.07'/%3E%3C/svg%3E")`;
const fonts='<link href="https://fonts.googleapis.com/css2?family=Archivo:wdth,wght@125,600;125,700&family=Inter:wght@500;600&family=Readex+Pro:wght@500;600&display=block" rel="stylesheet">';
function cover(ar){
 const tag= ar? 'نمكّن الأعمال بتقنيات ذكية.' : 'Powering Businesses with<br>Intelligent Technologies.';
 const eyebrow= ar? 'حلول الذكاء الاصطناعي &nbsp;·&nbsp; برمجيات مخصّصة &nbsp;·&nbsp; الأتمتة &nbsp;·&nbsp; تكامل الأنظمة' : 'AI SOLUTIONS &nbsp;·&nbsp; CUSTOM SOFTWARE &nbsp;·&nbsp; AUTOMATION &nbsp;·&nbsp; INTEGRATION';
 const ebStyle= ar? "font-family:'Readex Pro';font-weight:500;font-size:13px;color:#94A3B8" : "font-family:Inter;font-weight:600;font-size:10.5px;letter-spacing:.16em;color:#94A3B8";
 const tagStyle= ar? "font-family:'Readex Pro';font-weight:600;font-size:30px;line-height:1.35" : "font-family:Inter;font-weight:600;font-size:27px;line-height:1.15;letter-spacing:-.01em";
 const sign= ar? `<div style="font-family:'Readex Pro';font-weight:600;font-size:14px;color:#E2E8F0">ذكاءٌ بهندسةٍ دقيقة.</div>` : `<div style="font-family:Archivo;font-stretch:125%;font-weight:700;font-size:11px;letter-spacing:.14em;color:#E2E8F0">INTELLIGENCE, ENGINEERED.</div>`;
 return `<html><head>${fonts}</head><body style="margin:0;width:1128px;height:191px;background:#0B0F17;overflow:hidden;position:relative">
<div style="position:absolute;inset:0;background-image:${hex};background-size:38px 66px;-webkit-mask-image:linear-gradient(90deg,transparent 0,transparent 25%,#000 70%,#000 100%)"></div>
<div style="position:absolute;right:-6%;bottom:-120%;width:46%;height:260%;background:radial-gradient(closest-side,rgba(249,115,22,.20),transparent)"></div>
<div dir="${ar?'rtl':'ltr'}" style="position:absolute;left:400px;right:56px;top:0;bottom:0;display:flex;flex-direction:column;justify-content:center;gap:${ar?6:10}px">
 <div style="${ebStyle}">${eyebrow}</div>
 <div style="color:#E2E8F0;${tagStyle}">${tag}</div>
 <div style="display:flex;align-items:center;gap:12px"><div style="width:36px;height:3px;background:#F97316"></div>${sign}</div>
</div></body></html>`;
}
(async()=>{
 const b=await chromium.launch({executablePath:'/opt/pw-browsers/chromium'});
 for(const [name,svg] of [['iron-systems-linkedin-logo-metal',metalIcon],['iron-systems-linkedin-logo-flat',flatIcon]]){
  for(const s of [400,300]){
   const p=await b.newPage({viewport:{width:s,height:s}});
   await p.setContent(`<body style="margin:0;background:#0B0F17"><img id=i src="${du(svg)}" style="display:block;width:${s}px;height:${s}px"></body>`);
   await p.waitForFunction(()=>document.getElementById('i').complete);
   await p.screenshot({path:path.join(out,`${name}-${s}.png`)}); await p.close();
  }
 }
 for(const [name,ar] of [['iron-systems-linkedin-cover',false],['iron-systems-linkedin-cover-ar',true]]){
  for(const sc of [1,2]){
   const p=await b.newPage({viewport:{width:1128,height:191},deviceScaleFactor:sc});
   await p.setContent(cover(ar)); await p.evaluate(()=>document.fonts.ready); await p.waitForTimeout(400);
   await p.screenshot({path:path.join(out,`${name}-${1128*sc}x${191*sc}.png`)}); await p.close();
  }
 }
 await b.close();
})();
