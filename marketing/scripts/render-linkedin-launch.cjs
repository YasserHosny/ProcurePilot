#!/usr/bin/env node
/**
 * Renders the LinkedIn launch images (decision MD-13: bilingual, Arabic first) in each identity:
 *   company posts CP-01..CP-04  -> Iron Systems v3.3 (Iron Dark, one Power Orange accent)
 *   ProcurePilot posts A-01..A-04 -> ProcurePilot sub-brand (Navy / Teal / Paper, Converge logo)
 * A-05 and A-06 wait for real Egypt screens (visual-plan.md). Run from marketting/:
 *   node scripts/render-linkedin-launch.cjs
 * Output: <campaign>/assets/drafts/images/*.png (+ A-01 carousel PDF). Nothing is uploaded or posted.
 */
const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

const ROOT = path.resolve(__dirname, '..');
const BRAND = path.join(ROOT, 'brand/iron-systems');
const uri = (p, mime) => `data:${mime};base64,${fs.readFileSync(p).toString('base64')}`;
const en = (s) => `<span dir="ltr" style="unicode-bidi:isolate">${s}</span>`;
const img = (p) => uri(p, p.endsWith('.svg') ? 'image/svg+xml' : p.endsWith('.png') ? 'image/png' : 'image/jpeg');

const FONTS = '<link href="https://fonts.googleapis.com/css2?family=Archivo:wdth,wght@125,800&family=Inter:wght@400;500;600&family=Readex+Pro:wght@400;500;700&family=Noto+Kufi+Arabic:wght@500;700&display=block" rel="stylesheet">';

// ---------- Iron Systems (company) ----------
const IS = {
  dark: '#0B0F17', iron2: '#111827', iron3: '#1E293B', steel: '#94A3B8', light: '#E2E8F0', orange: '#F97316',
  logo: img(path.join(BRAND, 'iron-system-logo-primary-dark-1024.png')),
  mark: img(path.join(BRAND, 'iron-system-symbol-metal-1024.png')),
  hero: img(path.join(BRAND, 'hero-bg.jpg')),
};
const isBase = `*{box-sizing:border-box;margin:0}body{width:1080px;height:1350px;background:${IS.dark};color:${IS.light};overflow:hidden;position:relative;font-family:Inter}
.ar{font-family:'Readex Pro';direction:rtl;text-align:right}.disp{font-family:Archivo;font-stretch:125%;font-weight:800;text-transform:uppercase;letter-spacing:-.01em}
.rule{width:64px;height:3px;background:${IS.orange}}.foot{position:absolute;left:80px;right:80px;bottom:64px;display:flex;justify-content:space-between;align-items:center;color:${IS.steel};font-size:22px}
.foot img{height:64px}.slashes{position:absolute;font-family:Archivo;font-weight:800;font-size:220px;color:${IS.iron3};letter-spacing:-.05em}`;
const isFoot = `<div class="foot"><img src="${IS.logo}"><span>www.iron-sys.com</span></div>`;

const company = {
  'CP-01-1080x1350': `<style>${isBase}</style>
<div style="position:absolute;inset:0;background:url(${IS.hero}) center/cover"></div>
<div style="position:absolute;inset:0;background:linear-gradient(180deg,rgba(11,15,23,.25) 0%,rgba(11,15,23,.55) 45%,${IS.dark} 78%)"></div>
<img src="${IS.mark}" style="position:absolute;top:120px;left:50%;transform:translateX(-50%);width:300px">
<div style="position:absolute;left:80px;right:80px;top:640px">
  <div class="ar" style="font-weight:700;font-size:54px;line-height:1.45;white-space:nowrap">ذكاء اصطناعي يعمل في بيئة الإنتاج،<br>لا في العرض التجريبي فقط.</div>
  <div class="rule" style="margin:40px 0 36px"></div>
  <div class="disp" style="font-size:46px;line-height:1.12">AI that works in production,<br>not just in a demo.</div>
  <div style="margin-top:28px;font-size:26px;color:${IS.steel}">Powering Businesses with Intelligent Technologies.</div>
</div>${isFoot}`,

  'CP-02-1080x1350': `<style>${isBase}</style>
<div class="slashes" style="top:40px;right:60px">////</div>
<div style="position:absolute;left:80px;top:150px;font-size:24px;color:${IS.steel};letter-spacing:.12em">OUR PRINCIPLES · مبادئنا</div>
<div style="position:absolute;left:80px;right:80px;top:380px">
  <div class="ar" style="font-weight:700;font-size:80px;line-height:1.3">الذكاء الاصطناعي<br>حيث يفيد.</div>
  <div class="ar" style="margin-top:28px;font-size:34px;color:${IS.steel}">نختبر القيمة قبل الإطلاق.</div>
  <div class="rule" style="margin:64px 0 48px"></div>
  <div class="disp" style="font-size:64px;line-height:1.05">AI where it <span style="color:${IS.orange}">helps.</span></div>
  <div style="margin-top:24px;font-size:30px;color:${IS.steel}">We test the value before we ship.</div>
</div>${isFoot}`,

  'CP-03-thumbnail-1920x1080': `<style>${isBase}body{width:1920px;height:1080px}</style>
<div class="slashes" style="top:10px;left:70px">////</div>
<div style="position:absolute;left:110px;top:330px;width:700px">
  <div class="ar" style="font-weight:700;font-size:88px;text-align:left;direction:rtl">من صنعنا.</div>
  <div class="disp" style="font-size:92px;margin-top:20px">Built by <span style="color:${IS.orange}">us.</span></div>
  <div style="margin-top:34px;font-size:32px;color:${IS.steel}">ProcurePilot · real screens, demo data</div>
</div>
<div style="position:absolute;right:110px;top:150px;width:900px;border:2px solid ${IS.iron3};background:${IS.iron2};padding:16px">
  <img src="${img(path.join(ROOT, '../docs/gtm/gcc/rounds/screens/sa-en/11-smart-compare.jpg'))}" style="width:100%;display:block">
  <div style="position:absolute;top:30px;right:30px;background:${IS.dark};color:${IS.light};font-size:22px;padding:8px 16px;border:1px solid ${IS.steel}">Demo data · بيانات تجريبية</div>
</div>
<div class="foot" style="left:110px;right:110px;bottom:60px"><img src="${IS.logo}"><span>www.iron-sys.com</span></div>`,

  'CP-04-1080x1350': `<style>${isBase}.row{height:30px;margin:10px 0;background:#2A3344;border:1px solid #3A4458}.row.dup{background:#323B4E;opacity:.75}
.blk{height:64px;border:2px solid ${IS.steel};margin:22px 0;display:flex;align-items:center;padding:0 18px;font-size:22px;color:${IS.light};background:${IS.iron2}}</style>
<div style="position:absolute;left:80px;right:80px;top:110px">
  <div class="ar" style="font-weight:700;font-size:54px;line-height:1.35">بيانات تُكتب مرتين ← أنظمة مترابطة</div>
  <div class="disp" style="font-size:34px;margin-top:22px;line-height:1.1">Re-typed data → connected systems</div>
</div>
<div style="position:absolute;left:80px;top:420px;width:340px">
  ${Array.from({ length: 13 }, (_, i) => `<div class="row ${i % 3 === 1 ? 'dup' : ''}" style="width:${70 + ((i * 37) % 30)}%"></div>`).join('')}
  <div style="margin-top:22px;color:${IS.steel};font-size:22px">ERP · CRM · Excel · ERP…</div>
</div>
<div style="position:absolute;left:553px;top:470px;width:14px;height:450px;background:${IS.orange};transform:skewX(-30deg)"></div>
<div style="position:absolute;right:80px;top:430px;width:300px">
  <div class="blk">ERP</div><div class="blk">CRM</div><div class="blk">Accounting</div><div class="blk">Spreadsheets</div>
  <div style="margin-top:22px;color:${IS.steel};font-size:22px">One flow, data entered once.</div>
</div>${isFoot}`,
};

// ---------- ProcurePilot (product sub-brand) ----------
const PP = {
  navy: '#0B2545', teal: '#12A594', tealText: '#0C7A6E', tealDark: '#19B8A4', mist: '#C9D6E3', paper: '#F4F6F9',
  logoDark: img(path.join(ROOT, 'ProcurePilot/design-system/logo/procurepilot-horizontal-dark.svg')),
  logoArDark: img(path.join(ROOT, 'ProcurePilot/design-system/logo/procurepilot-arabic-horizontal-dark.svg')),
  logo: img(path.join(ROOT, 'ProcurePilot/design-system/logo/procurepilot-horizontal.svg')),
};
const ppBase = `*{box-sizing:border-box;margin:0}body{width:1080px;height:1350px;overflow:hidden;position:relative;font-family:'Readex Pro'}
.ar{direction:rtl;text-align:right}.num{font-family:'Noto Kufi Arabic';font-variant-numeric:tabular-nums}
.navy{background:${PP.navy};color:#fff}.paper{background:${PP.paper};color:${PP.navy}}
.note{position:absolute;left:72px;right:72px;bottom:56px;display:flex;justify-content:space-between;align-items:center;font-size:22px}
.chip{border:1.5px solid currentColor;padding:6px 14px;font-size:20px;border-radius:999px}`;
const navyFoot = (extra = 'أرقام للتوضيح · Example numbers') => `<div class="note" style="color:${PP.mist}"><img src="${PP.logoDark}" style="height:52px"><span class="chip" dir="rtl">${extra}</span></div>`;
const paperFoot = (extra = 'أرقام للتوضيح · Example numbers') => `<div class="note" style="color:${PP.tealText}"><img src="${PP.logo}" style="height:52px"><span class="chip" dir="rtl">${extra}</span></div>`;
const card = (title, enTitle, lines, win) => `<div style="background:#fff;border:2px solid ${win ? PP.teal : PP.mist};padding:34px 36px;${win ? `box-shadow:inset 0 -8px 0 ${PP.teal}` : ''}">
  <div class="ar" style="font-size:34px;font-weight:700">${title} <span style="font-size:22px;color:#5A6B82;font-weight:400">· ${en(enTitle)}</span></div>
  ${lines.map(([ar, enL, v, strong]) => `<div style="display:flex;justify-content:space-between;align-items:baseline;margin-top:18px;direction:rtl">
    <div class="ar" style="font-size:28px">${ar} <span style="font-size:19px;color:#5A6B82">${en(enL)}</span></div>
    <div class="num" style="font-size:${strong ? 40 : 30}px;font-weight:700;color:${strong && win ? PP.tealText : PP.navy};direction:ltr">${v}</div></div>`).join('')}
</div>`;

const carousel = [
  `<body class="navy"><style>${ppBase}</style>
<div style="position:absolute;left:72px;right:72px;top:250px">
  <div class="ar" style="font-size:84px;font-weight:700;line-height:1.3">أرخص عرض سعر<br>مش دايماً<br>أرخص طلبية.</div>
  <div style="width:120px;height:8px;background:${PP.teal};margin:56px 0 46px auto"></div>
  <div style="font-size:42px;line-height:1.3;color:${PP.mist}">The cheapest quote isn't always<br>the cheapest order.</div>
  <div class="ar" style="margin-top:70px;font-size:28px;color:${PP.tealDark}">اسحب ← · Swipe</div>
</div>${navyFoot()}</body>`,
  `<body class="paper"><style>${ppBase}</style>
<div style="position:absolute;left:72px;right:72px;top:110px">
  <div class="ar" style="font-size:52px;font-weight:700">موردين بعتولك أسعار رز</div>
  <div style="font-size:28px;color:#5A6B82;margin-top:10px">Two suppliers quote you rice</div>
  <div style="margin-top:56px;display:grid;gap:34px">
    ${card('المورد (أ)', 'Supplier A', [['شوال 25 كيلو', '25 kg sack', 'EGP 900'], ['سعر الكيلو', 'per kilo', 'EGP 36', true]], false)}
    ${card('المورد (ب)', 'Supplier B', [['كيس 10 كيلو', '10 kg bag', 'EGP 420'], ['سعر الكيلو', 'per kilo', 'EGP 42', true]], false)}
  </div>
  <div class="ar" style="margin-top:50px;font-size:40px;font-weight:700">(أ) شكله أرخص. <span style="font-size:28px;font-weight:400;color:#5A6B82">${en('A looks cheaper.')}</span></div>
</div>${paperFoot()}</body>`,
  `<body class="paper"><style>${ppBase}</style>
<div style="position:absolute;left:72px;right:72px;top:110px">
  <div class="ar" style="font-size:52px;font-weight:700">طيب اطلب 50 كيلو</div>
  <div style="font-size:28px;color:#5A6B82;margin-top:10px">Now order 50 kg</div>
  <div style="margin-top:56px;display:grid;gap:34px">
    ${card('المورد (أ)', 'Supplier A', [['2 شوال', '2 sacks', 'EGP 1,800'], ['توصيل', 'delivery', 'EGP 400'], ['الإجمالي', 'total', 'EGP 2,200', true], ['الكيلو', 'per kilo', 'EGP 44']], false)}
    ${card('المورد (ب)', 'Supplier B', [['5 أكياس', '5 bags', 'EGP 2,100'], ['توصيل', 'delivery', 'EGP 0'], ['الإجمالي', 'total', 'EGP 2,100', true], ['الكيلو', 'per kilo', 'EGP 42']], true)}
  </div>
</div>${paperFoot()}</body>`,
  `<body class="navy"><style>${ppBase}</style>
<div style="position:absolute;left:72px;right:72px;top:330px">
  <div class="ar" style="font-size:76px;font-weight:700;line-height:1.35">المورد "الغالي"<br>كسب بـ <span class="num" style="color:${PP.tealDark}">100</span> جنيه<br>في طلبية واحدة.</div>
  <div style="width:120px;height:8px;background:${PP.teal};margin:56px 0 46px auto"></div>
  <div style="font-size:40px;line-height:1.35;color:${PP.mist}">The "expensive" supplier wins<br>by EGP 100 on a single order.</div>
</div>${navyFoot()}</body>`,
  `<body class="navy"><style>${ppBase}</style>
<div style="position:absolute;left:72px;right:72px;top:200px">
  <img src="${PP.logoArDark}" style="height:96px;display:block;margin-left:auto">
  <div class="ar" style="margin-top:80px;font-size:50px;font-weight:700;line-height:1.45">بيقارن كل عرض عبوة بعبوة،<br>شامل رسوم توصيل كل مورد،<br>ويوريك أسباب الترشيح.</div>
  <div style="margin-top:40px;font-size:32px;line-height:1.4;color:${PP.mist}">Compares every offer pack for pack, with each supplier's delivery fee included, and shows the scoring.</div>
  <div class="ar" style="margin-top:80px;font-size:34px;color:${PP.tealDark}">بتقارن عروض الأسعار إزاي النهارده؟<br><span style="font-size:26px;color:${PP.mist}">${en('How do you compare quotes today?')}</span></div>
</div>${navyFoot()}</body>`,
];

const product = {
  'A-02-1080x1350': `<body class="paper"><style>${ppBase}.r{display:flex;justify-content:space-between;align-items:baseline;padding:22px 0;border-bottom:1px solid ${PP.mist};direction:rtl}</style>
<div style="position:absolute;left:72px;right:72px;top:130px">
  <div class="ar" style="font-size:66px;font-weight:700;line-height:1.35">وفّرت فعلاً..<br>ولا فاكر إنك وفّرت؟</div>
  <div style="font-size:34px;color:#5A6B82;margin-top:18px">Did you really save, or do you just think you did?</div>
  <div style="margin-top:70px;background:#fff;border:2px solid ${PP.mist};padding:20px 40px 30px">
    <div class="r"><span class="ar" style="font-size:28px">آخر سعر معروض <span style="font-size:19px;color:#5A6B82">${en('Last quoted price')}</span></span><span class="num" style="font-size:32px;direction:ltr">EGP 2,600.00</span></div>
    <div class="r"><span class="ar" style="font-size:28px">المدفوع <span style="font-size:19px;color:#5A6B82">${en('Paid')}</span></span><span class="num" style="font-size:32px;direction:ltr">EGP 2,040.00</span></div>
    <div class="r" style="border:2px dashed ${PP.mist};padding:22px 18px;margin-top:16px"><span class="ar" style="font-size:28px">توفير محسوب <span style="font-size:19px;color:#5A6B82">${en('Calculated · not yet verified')}</span></span><span class="num" style="font-size:32px;direction:ltr">EGP 560.00</span></div>
    <div class="r" style="border-bottom:6px double ${PP.teal};padding-top:30px"><span class="ar" style="font-size:30px;font-weight:700;color:${PP.tealText}">توفير معتمد ✓ <span style="font-size:19px;color:#5A6B82;font-weight:400">${en('Verified saving')}</span></span><span class="num" style="font-size:40px;font-weight:700;color:${PP.tealText};direction:ltr">EGP 560.00</span></div>
  </div>
  <div class="ar" style="margin-top:46px;font-size:30px">التوفير مابيتحسبش غير لما حد يتأكد منه.</div><div dir="ltr" style="text-align:right;font-size:24px;color:#5A6B82;margin-top:8px">A saving counts only once someone verifies it.</div>
</div>${paperFoot('بيانات تجريبية · Demo data')}</body>`,

  'A-03-1080x1350': `<body class="navy"><style>${ppBase}.li{display:flex;gap:22px;align-items:flex-start;margin:30px 0;direction:rtl}.dot{width:18px;height:18px;background:${PP.teal};margin-top:18px;flex:none}</style>
<div style="position:absolute;left:72px;right:72px;top:140px">
  <img src="${PP.logoArDark}" style="height:92px;display:block;margin-left:auto">
  <div class="ar" style="margin-top:60px;font-size:36px;color:${PP.mist}">لمجموعات المطاعم اللي عندها أكتر من فرع<br><span style="font-size:24px">For restaurant groups with several branches</span></div>
  <div style="margin-top:40px">
    ${[['بيقرا عروض الأسعار، PDF وصور', 'Reads your suppliers\' quotes, PDFs and photos'], ['بيقارن عبوة بعبوة شامل التوصيل', 'Compares pack for pack, delivery included'], ['حد من فريقك بيعتمد كل شراء', 'A person approves every purchase'], ['التوفير بيتحسب لما حد يتأكد منه', 'A saving counts once someone verifies it']]
      .map(([a, e]) => `<div class="li"><span class="dot"></span><div class="ar" style="font-size:38px;font-weight:700">${a}<br><span style="font-size:24px;font-weight:400;color:${PP.mist}">${e}</span></div></div>`).join('')}
  </div>
</div>
<div class="note" style="color:${PP.mist}"><span style="display:flex;align-items:center;gap:16px;font-size:22px"><img src="${PP.logoDark}" style="height:48px"> by Iron Systems</span><span class="chip" dir="rtl">تجربة بالدعوة · Invitation-only pilot</span></div></body>`,

  'A-04-thumbnail-1920x1080': `<body class="navy" style="width:1920px;height:1080px"><style>${ppBase}body{width:1920px;height:1080px}</style>
<div style="position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:40px">
  <img src="${PP.logoArDark}" style="height:130px">
  <div class="ar" style="text-align:center;font-size:72px;font-weight:700">في حوالي دقيقتين</div>
  <div style="font-size:44px;color:${PP.mist}">ProcurePilot in about two minutes</div>
  <div style="width:140px;height:8px;background:${PP.teal}"></div>
  <div class="chip" dir="rtl" style="color:${PP.mist};font-size:26px">شاشات حقيقية ببيانات تجريبية · Real screens, demo data</div>
</div></body>`,
};

async function main() {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1080, height: 1350 } });
  const shoot = async (html, file, w = 1080, h = 1350) => {
    await page.setViewportSize({ width: w, height: h });
    await page.setContent(`<!doctype html><html><head><meta charset="utf-8">${FONTS}</head>${html.startsWith('<body') ? html : `<body>${html}</body>`}</html>`, { waitUntil: 'networkidle' });
    await page.evaluate(() => document.fonts.ready);
    fs.mkdirSync(path.dirname(file), { recursive: true });
    await page.screenshot({ path: file });
    console.log('wrote', path.relative(ROOT, file));
  };
  const cOut = path.join(ROOT, 'campaigns/2026-11-company-ai-in-production/assets/drafts/images');
  for (const [name, html] of Object.entries(company)) {
    const [w, h] = name.includes('1920x1080') ? [1920, 1080] : [1080, 1350];
    await shoot(html, path.join(cOut, `${name}.png`), w, h);
  }
  const pOut = path.join(ROOT, 'ProcurePilot/campaigns/2026-11-procurepilot-founder-linkedin/assets/drafts/images');
  for (const [name, html] of Object.entries(product)) {
    const [w, h] = name.includes('1920x1080') ? [1920, 1080] : [1080, 1350];
    await shoot(html, path.join(pOut, `${name}.png`), w, h);
  }
  for (const [i, html] of carousel.entries()) await shoot(html, path.join(pOut, `A-01-carousel-p${i + 1}-1080x1350.png`));
  // Carousel as one PDF (LinkedIn document post), built from the checked PNG pages so both match exactly.
  const pages = carousel.map((_, i) => `<img src="${img(path.join(pOut, `A-01-carousel-p${i + 1}-1080x1350.png`))}" style="display:block;width:1080px;height:1350px;page-break-after:always">`).join('');
  await page.setContent(`<!doctype html><html><head><style>@page{size:1080px 1350px;margin:0}body{margin:0}</style></head><body>${pages}</body></html>`);
  await page.pdf({ path: path.join(pOut, 'A-01-carousel-1080x1350.pdf'), width: '1080px', height: '1350px', printBackground: true });
  console.log('wrote A-01-carousel-1080x1350.pdf');
  await browser.close();
}
main().catch((e) => { console.error(e); process.exit(1); });
