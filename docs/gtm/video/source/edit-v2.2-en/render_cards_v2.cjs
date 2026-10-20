// All renderer writes, including Chrome's profile, stay under v2.
const fs=require('fs'), path=require('path');
const ROOT=__dirname;
const {chromium}=require(path.join(ROOT,'../../wt44/node_modules/.pnpm/playwright@1.63.0/node_modules/playwright'));
const text={
open:['عروض واتساب… ونسخ يدوي؟','Quotes on WhatsApp. Still copying by hand?'],
low:['بلاغ نقص المخزون من الموبايل','Report low stock from the phone'],
rfq:['طلب عرض سعر واحد لكل الموردين','One RFQ for all suppliers'],
photo:['صورة عرض سعر ← استخراج ثم مراجعة بشرية','A quote photo → extraction, then human review'],
fields:['٢٥٬١٤٠ ج.م · الإجمالي مطابق للبنود','EGP 25,140 · extracted total reconciles'],
lines:['زيت · أرز · بصل — راجع البنود قبل الاعتماد','Oil, rice, onions · review before authorising'],
authorise:['مراجعة بشرية ثم اعتماد عرض السعر','Human review → authorise quote'],
compare:['مقارنة عروض الزيت × ٨ عبوات','Compare oil offers · 8 tins'],
prices:['الزيت × ٨ · ١٢٬٨٨٠ مقابل ١٣٬٠٨٠ ج.م','Oil ×8 · EGP 12,880 vs 13,080'],
draft:['الضوابط تجهّز المسودة — والقرار للمدير','Guardrails draft the request · manager decides'],
submit:['راجع المسودة ثم أرسلها للاعتماد','Review the draft, then submit for approval'],
approve:['المدير يراجع ويعتمد من الموبايل','Manager reviews and approves on the phone'],
approve_action:['اعتماد الطلب','Approve the request'],
approved:['تم اعتماد الطلب','Request approved'],
po:['من الطلب المعتمد إلى أمر الشراء','Approved request → purchase order'],
sent:['PO-000006 · تم إرسال أمر الشراء','PO-000006 · purchase order sent'],
outcome:['تسجيل النتيجة من أمر الشراء','Record the outcome from the purchase order'],
ledger:['١٬٠٦٠ ج.م · سجل تجريبي يشمل تجربة سابقة','EGP 1,060 · demo ledger, including a dry run'],
};
(async()=>{
 const browser=await chromium.launchPersistentContext(path.join(ROOT,'tmp/chrome-render'),{executablePath:'/opt/google/chrome/chrome',headless:true,args:['--no-sandbox','--disable-dev-shm-usage','--disable-crashpad-for-testing','--no-zygote','--single-process'], viewport:{width:1920,height:1080}});
 for(const vertical of [false,true])for(const lang of ['ar','en']){
  const W=vertical?1080:1920,H=vertical?1920:1080;
  const page=await browser.newPage(); await page.setViewportSize({width:W,height:H});
  const dir=path.join(ROOT,'graphics',lang+(vertical?'-v':''));fs.mkdirSync(dir,{recursive:true});
  for(const [key,strings] of Object.entries(text)){
   const label=strings[lang==='ar'?0:1];
   await page.setContent(`<html lang="${lang}" dir="${lang==='ar'?'rtl':'ltr'}"><style>*{box-sizing:border-box}html,body{margin:0;width:${W}px;height:${H}px;background:transparent;font-family:Arial,'Noto Sans Arabic',sans-serif}.cap{position:absolute;${vertical?'top:275px;left:54px;right:54px;min-height:150px':'bottom:28px;left:80px;right:80px;min-height:110px'};background:#0b2545; border-${lang==='ar'?'right':'left'}:8px solid #19b8a4;border-radius:18px;padding:${vertical?'24px 28px':'18px 32px'};color:white;display:flex;flex-direction:column;justify-content:center;gap:9px}.main{font-size:${vertical?42:38}px;font-weight:700;line-height:1.25}.sub{color:#9ce2d7;font-size:${vertical?24:22}px;line-height:1.3}</style><div class="cap"><div class="main">${label}</div><div class="sub">${lang==='ar'?'بيانات تجريبية · واجهة عربية':'Demo data · Arabic interface'}</div></div></html>`);
   await page.evaluate(()=>document.fonts.ready);await page.screenshot({path:path.join(dir,key+'.png'),omitBackground:true});
  }
  for(let f=0;f<31;f++){
   const value=Math.round(460*Math.min(f/30,1));const num=lang==='ar'?new Intl.NumberFormat('ar-EG').format(value):String(value);
   await page.setContent(`<html lang="${lang}" dir="${lang==='ar'?'rtl':'ltr'}"><style>html,body{margin:0;width:${W}px;height:${H}px;background:#0b2545;color:white;font-family:Arial,'Noto Sans Arabic',sans-serif}main{position:absolute;left:${vertical?60:180}px;right:${vertical?60:180}px;top:${vertical?600:220}px;text-align:center}h1{font-size:${vertical?48:52}px;line-height:1.5;margin:0 0 28px}strong{font-size:${vertical?160:180}px;color:#28c6b2}p{font-size:${vertical?36:36}px;line-height:1.6;margin:30px 0}small{font-size:26px;color:#9ce2d7}</style><main><h1>${lang==='ar'?'وفّر الطلب ده':'This order saved'}</h1><strong>${num}</strong><span style="font-size:48px"> ${lang==='ar'?'ج.م':'EGP'}</span><p>${lang==='ar'?'مقابل أسعار آخر أوامر شراء':'Compared with last purchase-order prices'}</p><small>${lang==='ar'?'بيانات تجريبية · زيت +٢٤٠ · أرز +١٨٠ · بصل +٤٠':'Demo data · oil +240 · rice +180 · onions +40'}</small></main></html>`);
   await page.evaluate(()=>document.fonts.ready);await page.screenshot({path:path.join(dir,`counter-${String(f).padStart(2,'0')}.png`)});
  }
  await page.close();console.log('graphics',dir);
 }
 await browser.close();
})();
