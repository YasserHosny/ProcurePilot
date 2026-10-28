#!/usr/bin/env node
/**
 * LinkedIn launch images, v2 (2026-10-29). Owner asked for a more professional, human, non-AI look.
 * ProcurePilot images follow the product repo's binding motion/visual direction
 * (docs/gtm/video/motion-style.md): Paper ground, Navy dominant, one Teal hit per image meaning "the better choice",
 * real material only (app screens from the approved v2.5 cut, the round-6 WhatsApp quote photo), layered paper with
 * soft navy shadows, light grain, Converge bars as the motif. Company images follow Iron Systems v3.3.
 * Run from marketting/:  node scripts/render-linkedin-v2.cjs
 * Output: <campaign>/assets/drafts/images/v2/. Nothing is uploaded or posted.
 */
const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

const ROOT = path.resolve(__dirname, '..');
const BRAND = path.join(ROOT, 'brand/iron-systems');
const PPC = path.join(ROOT, 'ProcurePilot/campaigns/2026-11-procurepilot-founder-linkedin/assets/drafts');
const COC = path.join(ROOT, 'campaigns/2026-11-company-ai-in-production/assets/drafts');
const mime = (p) => (p.endsWith('.svg') ? 'image/svg+xml' : p.endsWith('.png') ? 'image/png' : 'image/jpeg');
const img = (p) => `data:${mime(p)};base64,${fs.readFileSync(p).toString('base64')}`;
const en = (s) => `<span dir="ltr" style="unicode-bidi:isolate">${s}</span>`;
const SRC = (f) => img(path.join(PPC, '..', 'approved', 'source', f)); // approved sources (2026-10-29); new renders go to drafts/

const FONTS = '<link href="https://fonts.googleapis.com/css2?family=Archivo:wdth,wght@125,800&family=Inter:wght@400;500;600&family=Readex+Pro:wght@300;400;500;600;700&display=block" rel="stylesheet">';
const GRAIN = `url("data:image/svg+xml;utf8,${encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" width="300" height="300"><filter id="n"><feTurbulence type="fractalNoise" baseFrequency=".85" numOctaves="2" stitchTiles="stitch"/><feColorMatrix values="0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 .55 0"/></filter><rect width="100%" height="100%" filter="url(#n)"/></svg>')}")`;

/** A crop of a 1920x1080 frame shown at width w. */
const crop = (src, x, y, cw, ch, w, extra = '') => {
  const s = w / cw;
  return `<div style="width:${w}px;height:${Math.round(ch * s)}px;background:url(${src}) ${-x * s}px ${-y * s}px / ${1920 * s}px ${1080 * s}px no-repeat;${extra}"></div>`;
};

// ---------------- ProcurePilot ----------------
const P = { navy: '#0B2545', teal: '#12A594', tealText: '#0C7A6E', tealDark: '#19B8A4', mist: '#C9D6E3', paper: '#F4F6F9', ink2: '#4A5D77' };
const L = {
  ar: img(path.join(ROOT, 'ProcurePilot/design-system/logo/procurepilot-arabic-horizontal.svg')),
  arDark: img(path.join(ROOT, 'ProcurePilot/design-system/logo/procurepilot-arabic-horizontal-dark.svg')),
  en: img(path.join(ROOT, 'ProcurePilot/design-system/logo/procurepilot-horizontal.svg')),
  enDark: img(path.join(ROOT, 'ProcurePilot/design-system/logo/procurepilot-horizontal-dark.svg')),
};
const ppCss = `*{box-sizing:border-box;margin:0}html,body{width:1080px;height:1350px}
body{position:relative;overflow:hidden;font-family:'Readex Pro';color:${P.navy};background:${P.paper}}
body:after{content:"";position:absolute;inset:0;background:${GRAIN};opacity:.07;pointer-events:none;mix-blend-mode:multiply}
.ar{direction:rtl;text-align:right}.en{direction:ltr;text-align:left}
.card{background:#fff;box-shadow:0 2px 4px rgba(11,37,69,.06),0 24px 60px -18px rgba(11,37,69,.28)}
.kick{font-size:22px;letter-spacing:.02em;color:${P.ink2}}
.chip{display:inline-block;border:1.5px solid currentColor;border-radius:999px;padding:6px 16px;font-size:19px}
.foot{position:absolute;left:72px;right:72px;bottom:60px;display:flex;justify-content:space-between;align-items:center}
.bars{display:flex;flex-direction:column;gap:7px;align-items:flex-end}.bars i{display:block;height:9px;border-radius:5px}
.navyBg{background:${P.navy};color:#fff}.navyBg:after{mix-blend-mode:screen;opacity:.05}`;
const bars = (w = 1) => `<div class="bars"><i style="width:${64 * w}px;background:${P.navy}"></i><i style="width:${46 * w}px;background:${P.mist}"></i><i style="width:${92 * w}px;background:${P.teal}"></i></div>`;
const foot = (chip, dark) => `<div class="foot"><img src="${dark ? L.enDark : L.en}" style="height:44px"><span class="chip" dir="rtl" style="color:${dark ? P.mist : P.tealText}">${chip}</span></div>`;
const counter = (n, dark) => `<div style="position:absolute;top:72px;left:72px;font-size:22px;color:${dark ? P.mist : P.ink2}">${en(`${n} / 5`)}</div>`;
const EX = 'أرقام للتوضيح · Example numbers';
const DEMO = 'شاشة حقيقية · بيانات تجريبية · Real screen, demo data';

const slip = (name, enName, pack, enPack, price, perKg, rot) => `<div class="card ar" style="padding:34px 38px;transform:rotate(${rot}deg)">
  <div style="display:flex;justify-content:space-between;align-items:baseline"><div style="font-size:32px;font-weight:600">${name}</div><div class="kick">${en(enName)}</div></div>
  <div style="height:1px;background:${P.mist};margin:20px 0"></div>
  <div style="display:flex;justify-content:space-between;align-items:baseline"><div style="font-size:28px">${pack} <span class="kick">${en(enPack)}</span></div><div style="font-size:30px;font-weight:500">${en(price)}</div></div>
  <div style="display:flex;justify-content:space-between;align-items:baseline;margin-top:22px"><div style="font-size:26px;color:${P.ink2}">سعر الكيلو <span class="kick">${en('per kilo')}</span></div><div style="font-size:64px;font-weight:700;line-height:1">${en(perKg)}</div></div>
</div>`;

const pp = {
  'A-01-p1': `<body>${counter(1)}
  <div style="position:absolute;top:72px;right:72px">${bars()}</div>
  <div class="ar" style="position:absolute;top:150px;right:72px;left:72px">
    <div class="kick">مشتريات المطاعم · ${en('Restaurant purchasing')}</div>
    <div style="font-size:96px;font-weight:700;line-height:1.18;margin-top:26px;letter-spacing:-.01em">أرخص عرض سعر<br>مش دايماً<br>أرخص طلبية.</div>
    <div class="en" style="font-size:32px;font-weight:400;color:${P.ink2};margin-top:30px;text-align:right">The cheapest quote isn't always the cheapest order.</div>
  </div>
  <div class="card" style="position:absolute;left:84px;bottom:150px;width:430px;padding:12px;transform:rotate(-5deg)"><img src="${SRC('round6-whatsapp-quote-photo.jpg')}" style="width:100%;display:block"></div>
  <div class="ar" style="position:absolute;right:72px;bottom:190px;width:420px;font-size:26px;line-height:1.5;color:${P.ink2}">عرض سعر جالك صورة على الواتساب.<br>شوف بنقارنه إزاي ←<br><span style="font-size:20px">${en('A quote that came in as a WhatsApp photo. Swipe →')}</span></div>
  ${foot(EX)}</body>`,

  'A-01-p2': `<body>${counter(2)}
  <div class="ar" style="position:absolute;top:150px;right:72px;left:72px">
    <div style="font-size:60px;font-weight:700">موردين بعتولك أسعار رز</div>
    <div class="en" style="font-size:28px;color:${P.ink2};margin-top:10px;text-align:right">Two suppliers quote you rice</div>
  </div>
  <div style="position:absolute;top:400px;right:110px;width:640px">${slip('المورد (أ)', 'Supplier A', 'شوال 25 كيلو', '25 kg sack', 'EGP 900', 'EGP 36', 1.2)}</div>
  <div style="position:absolute;top:740px;left:110px;width:640px">${slip('المورد (ب)', 'Supplier B', 'كيس 10 كيلو', '10 kg bag', 'EGP 420', 'EGP 42', -1.4)}</div>
  <div class="ar" style="position:absolute;right:72px;bottom:150px;font-size:44px;font-weight:600">(أ) شكله أرخص. <span style="font-size:26px;font-weight:400;color:${P.ink2}">${en('A looks cheaper.')}</span></div>
  ${foot(EX)}</body>`,

  'A-01-p3': (() => {
    const row = (lbl, enL, parts, total, perKg, w, win) => `<div class="ar" style="margin-top:58px">
      <div style="display:flex;justify-content:space-between;align-items:baseline"><div style="font-size:34px;font-weight:600">${lbl} <span class="kick">${en(enL)}</span></div><div style="font-size:24px;color:${P.ink2}">${parts}</div></div>
      <div style="display:flex;align-items:center;gap:0;margin-top:18px;direction:rtl">
        <div style="height:46px;width:${w}px;background:${win ? P.teal : P.mist};border-radius:6px 0 0 6px"></div>
        ${win ? `<div style="width:0;height:0;border-top:34px solid transparent;border-bottom:34px solid transparent;border-right:40px solid ${P.teal}"></div>` : ''}
      </div>
      <div style="display:flex;justify-content:space-between;align-items:baseline;margin-top:16px"><div style="font-size:56px;font-weight:700;color:${win ? P.tealText : P.navy}">${en(total)}</div><div style="font-size:26px;color:${P.ink2}">${en(perKg)}</div></div>
    </div>`;
    return `<body>${counter(3)}
    <div class="ar" style="position:absolute;top:150px;right:72px;left:72px">
      <div style="font-size:60px;font-weight:700">طيب اطلب 50 كيلو</div>
      <div class="en" style="font-size:28px;color:${P.ink2};margin-top:10px;text-align:right">Now order 50 kg</div>
      <div style="margin-top:40px">
      ${row('المورد (أ)', 'Supplier A', 'شوالين 1,800 جنيه، والتوصيل 400', 'EGP 2,200', 'EGP 44 / kg', 880, false)}
      ${row('المورد (ب)', 'Supplier B', '5 أكياس 2,100 جنيه، والتوصيل مجاني', 'EGP 2,100', 'EGP 42 / kg', 800, true)}
      </div>
    </div>${foot(EX)}</body>`;
  })(),

  'A-01-p4': `<body class="navyBg">${counter(4, true)}
  <div style="position:absolute;top:72px;right:72px">${bars()}</div>
  <div class="ar" style="position:absolute;top:330px;right:72px;left:72px">
    <div style="font-size:88px;font-weight:700;line-height:1.25">المورد "الغالي"<br>كسب بـ <span style="color:${P.tealDark}">100 جنيه</span><br>في طلبية واحدة.</div>
    <div class="en" style="font-size:30px;color:${P.mist};margin-top:44px;text-align:right">The "expensive" supplier wins by EGP 100 on one order.</div>
  </div>${foot(EX, true)}</body>`,

  'A-01-p5': `<body>${counter(5)}
  <div class="ar" style="position:absolute;top:150px;right:72px;left:72px">
    <img src="${L.ar}" style="height:70px;display:block;margin-right:0;margin-left:auto">
    <div style="font-size:54px;font-weight:700;line-height:1.3;margin-top:46px">بيقارن كل عرض عبوة بعبوة،<br>شامل توصيل كل مورد.</div>
    <div class="en" style="font-size:28px;color:${P.ink2};margin-top:16px;text-align:right">Every offer compared pack for pack, delivery included.</div>
  </div>
  <div class="card" style="position:absolute;top:610px;left:60px;right:60px;padding:14px">${crop(SRC('frame-v25-ar-72s-smart-compare.jpg'), 30, 285, 1285, 580, 932)}</div>
  <div class="ar" style="position:absolute;right:72px;bottom:150px;font-size:30px;font-weight:600">بتقارن عروض الأسعار إزاي النهارده؟ <span style="font-size:22px;font-weight:400;color:${P.ink2}">${en('How do you compare quotes today?')}</span></div>
  ${foot(DEMO)}</body>`,

  'A-02': `<body>
  <div style="position:absolute;top:72px;right:72px">${bars()}</div>
  <div class="ar" style="position:absolute;top:150px;right:72px;left:72px">
    <div style="font-size:84px;font-weight:700;line-height:1.2">وفّرت فعلاً..<br>ولا فاكر إنك وفّرت؟</div>
    <div class="en" style="font-size:30px;color:${P.ink2};margin-top:22px;text-align:right">Did you really save, or do you just think you did?</div>
  </div>
  <div class="card ar" style="position:absolute;top:620px;left:110px;right:110px;padding:40px 48px 46px;transform:rotate(-1deg)">
    <div class="kick">سجل التوفير · ${en('Savings ledger')}</div>
    ${[['آخر سعر معروض', 'Last quoted price', 'EGP 2,600'], ['المدفوع', 'Paid', 'EGP 2,040']].map(([a, e, v]) => `<div style="display:flex;justify-content:space-between;align-items:baseline;padding:20px 0;border-bottom:1px solid ${P.mist}"><div style="font-size:28px">${a} <span class="kick">${en(e)}</span></div><div style="font-size:32px">${en(v)}</div></div>`).join('')}
    <div style="display:flex;justify-content:space-between;align-items:baseline;padding:22px 20px;margin-top:18px;border:2px dashed ${P.mist};color:${P.ink2}"><div style="font-size:28px">محسوب <span style="font-size:20px">${en('Calculated, not yet verified')}</span></div><div style="font-size:32px">${en('EGP 560')}</div></div>
    <div style="display:flex;justify-content:space-between;align-items:baseline;padding:26px 0 14px;border-bottom:7px double ${P.teal}"><div style="font-size:32px;font-weight:700;color:${P.tealText}">معتمد ✓ <span style="font-size:20px;font-weight:400;color:${P.ink2}">${en('Verified')}</span></div><div style="font-size:48px;font-weight:700;color:${P.tealText}">${en('EGP 560')}</div></div>
  </div>
  ${foot('بيانات تجريبية · Demo data')}</body>`,

  'A-03': `<body>
  <div class="ar" style="position:absolute;top:96px;right:72px;left:72px">
    <img src="${L.ar}" style="height:78px;display:block;margin-left:auto">
    <div class="kick" style="margin-top:36px">لمجموعات المطاعم اللي عندها أكتر من فرع · ${en('For restaurant groups with several branches')}</div>
  </div>
  <div class="ar" style="position:absolute;top:330px;right:72px;left:72px">
    ${[['01', 'بيقرا عروض الأسعار', 'PDF وصور، بالعربي والإنجليزي', 'Reads supplier quotes, PDFs and photos'], ['02', 'بيقارن عبوة بعبوة', 'شامل التوصيل، بالجنيه', 'Compares pack for pack, delivery included'], ['03', 'حد من فريقك بيعتمد', 'كل عملية شراء، في حدود الميزانية', 'A person approves every purchase'], ['04', 'التوفير بيتأكد قبل ما يتحسب', 'محسوب ومعتمد، كل واحد لوحده', 'A saving counts once someone verifies it']]
      .map(([n, a, b, e], i) => `<div style="display:flex;gap:28px;align-items:flex-start;padding:30px 0;border-top:1px solid ${P.mist}"><div style="font-size:30px;font-weight:300;color:${i === 3 ? P.tealText : P.ink2};width:56px">${en(n)}</div><div style="flex:1"><div style="font-size:44px;font-weight:700;color:${i === 3 ? P.tealText : P.navy}">${a}</div><div style="font-size:26px;color:${P.ink2};margin-top:6px">${b}</div><div dir="ltr" style="font-size:22px;color:${P.ink2};margin-top:4px;text-align:right">${e}</div></div></div>`).join('')}
  </div>
  <div class="foot"><span style="font-size:22px;color:${P.ink2}">${en('ProcurePilot · by Iron Systems')}</span><span class="chip" dir="rtl" style="color:${P.tealText}">تجربة بالدعوة · Invitation-only pilot</span></div></body>`,

  'A-05': `<body>
  <div style="position:absolute;top:72px;right:72px">${bars()}</div>
  <div class="ar" style="position:absolute;top:150px;right:72px;left:72px">
    <div style="font-size:92px;font-weight:700;line-height:1.15">خليها واتساب.</div>
    <div style="font-size:34px;margin-top:20px;line-height:1.45">احفظ الصورة وارفعها، أو حوّلها بالإيميل.<br>كل سطر بيفضل مربوط بمكانه في العرض الأصلي.</div>
    <div class="en" style="font-size:26px;color:${P.ink2};margin-top:14px;text-align:right">Keep WhatsApp. Upload the photo or forward it by email; every line stays linked to the original quote.</div>
  </div>
  <div class="card" style="position:absolute;top:640px;left:60px;width:640px;padding:12px">${crop(SRC('frame-v25-ar-62s-total-check.jpg'), 40, 200, 1260, 640, 616)}</div>
  <div class="card" style="position:absolute;top:600px;right:60px;width:330px;padding:10px;transform:rotate(4deg)"><img src="${SRC('round6-whatsapp-quote-photo.jpg')}" style="width:100%;display:block"></div>
  ${foot(DEMO)}</body>`,

  'A-06': `<body>
  <div style="position:absolute;top:72px;right:72px">${bars()}</div>
  <div class="ar" style="position:absolute;top:150px;right:72px;width:500px">
    <div style="font-size:84px;font-weight:700;line-height:1.2">القرار<br>لحد<br>من فريقك.</div>
    <div style="font-size:32px;margin-top:30px;line-height:1.5">البرنامج بيجهّز الطلب.<br>المدير بيعتمده من موبايله،<br>والميزانية المتبقية قدامه.</div>
    <div class="en" style="font-size:24px;color:${P.ink2};margin-top:18px;text-align:right">The software prepares the request. A manager approves it from the phone, with the remaining budget in view.</div>
  </div>
  <div class="card" style="position:absolute;top:140px;left:70px;width:420px;padding:10px;border-radius:32px">${crop(SRC('frame-v25-ar-88s-phone-approval.jpg'), 440, 80, 460, 920, 400, 'border-radius:24px')}</div>
  ${foot(DEMO)}</body>`,

  'A-04-thumb': `<body class="navyBg" style="width:1920px;height:1080px">
  <div class="card" style="position:absolute;left:90px;top:230px;width:1000px;padding:14px">${crop(SRC('frame-v25-ar-04s-opening.jpg'), 30, 170, 1280, 740, 972)}</div>
  <div class="ar" style="position:absolute;right:100px;top:250px;width:700px">
    <img src="${L.arDark}" style="height:90px;display:block;margin-left:auto">
    <div style="font-size:84px;font-weight:700;line-height:1.2;margin-top:50px">من عرض السعر<br>لأمر الشراء</div>
    <div style="font-size:40px;color:${P.tealDark};margin-top:24px">في حوالي دقيقتين</div>
    <div class="en" style="font-size:30px;color:${P.mist};margin-top:20px;text-align:right">ProcurePilot in about two minutes</div>
  </div></body>`,
};

// ---------------- Iron Systems ----------------
const I = { dark: '#0B0F17', iron2: '#111827', iron3: '#1E293B', steel: '#94A3B8', light: '#E2E8F0', orange: '#F97316' };
const IL = { logo: img(path.join(BRAND, 'iron-system-logo-primary-dark-1024.png')), mark: img(path.join(BRAND, 'iron-system-symbol-metal-1024.png')), hero: img(path.join(BRAND, 'hero-bg.jpg')) };
const isCss = `*{box-sizing:border-box;margin:0}html,body{width:1080px;height:1350px}
body{position:relative;overflow:hidden;background:${I.dark};color:${I.light};font-family:Inter}
body:after{content:"";position:absolute;inset:0;background:${GRAIN};opacity:.06;mix-blend-mode:screen;pointer-events:none}
.ar{font-family:'Readex Pro';direction:rtl;text-align:right}.disp{font-family:Archivo;font-stretch:125%;font-weight:800;text-transform:uppercase;letter-spacing:-.01em}
.rule{width:64px;height:3px;background:${I.orange}}.lbl{font-size:20px;letter-spacing:.14em;color:${I.steel};text-transform:uppercase}
.foot{position:absolute;left:80px;right:80px;bottom:64px;display:flex;justify-content:space-between;align-items:center;color:${I.steel};font-size:22px}
.dots{position:absolute;background-image:radial-gradient(${I.iron3} 2px,transparent 2px);background-size:26px 26px}`;
const isFoot = `<div class="foot"><img src="${IL.logo}" style="height:60px"><span>www.iron-sys.com</span></div>`;

const co = {
  'CP-01': `<body>
  <div style="position:absolute;inset:0;background:url(${IL.hero}) center/cover"></div>
  <div style="position:absolute;inset:0;background:linear-gradient(180deg,rgba(11,15,23,.2) 0%,rgba(11,15,23,.5) 42%,${I.dark} 74%)"></div>
  <div class="lbl" style="position:absolute;top:80px;left:80px">Iron Systems · AI solutions</div>
  <img src="${IL.mark}" style="position:absolute;top:150px;right:90px;width:260px">
  <div style="position:absolute;left:80px;right:80px;top:700px">
    <div class="ar" style="font-weight:700;font-size:62px;line-height:1.35">ذكاء اصطناعي يعمل<br>في بيئة الإنتاج.</div>
    <div class="rule" style="margin:42px 0 36px"></div>
    <div class="disp" style="font-size:52px;line-height:1.08">AI that works<br>in production.</div>
    <div style="margin-top:26px;font-size:24px;color:${I.steel}">Powering Businesses with Intelligent Technologies.</div>
  </div>${isFoot}</body>`,

  'CP-02': `<body>
  <div class="dots" style="top:0;right:0;width:420px;height:420px"></div>
  <div class="disp" style="position:absolute;top:110px;left:70px;font-size:300px;line-height:1;color:transparent;-webkit-text-stroke:2px ${I.iron3}">02</div>
  <div class="lbl" style="position:absolute;top:110px;right:80px">Our principles · مبادئنا</div>
  <div style="position:absolute;left:80px;right:80px;top:470px">
    <div class="ar" style="font-weight:700;font-size:84px;line-height:1.25">الذكاء الاصطناعي<br>حيث يفيد.</div>
    <div class="ar" style="margin-top:24px;font-size:32px;color:${I.steel}">نختبر القيمة قبل ما نطلق أي نموذج.</div>
    <div class="rule" style="margin:60px 0 44px"></div>
    <div class="disp" style="font-size:64px;line-height:1.05">AI where it <span style="color:${I.orange}">helps.</span></div>
    <div style="margin-top:22px;font-size:28px;color:${I.steel}">We test the value before we ship a model.</div>
  </div>${isFoot}</body>`,

  'CP-04': `<body>
  <div class="lbl" style="position:absolute;top:80px;left:80px">Automation · Integration</div>
  <div style="position:absolute;left:80px;right:80px;top:150px">
    <div class="ar" style="font-weight:700;font-size:58px;line-height:1.35">بيانات بتتكتب مرتين<br>← أنظمة مترابطة</div>
    <div class="disp" style="font-size:34px;margin-top:22px">Re-typed data → connected systems</div>
  </div>
  <div style="position:absolute;left:80px;top:500px;width:360px">
    ${Array.from({ length: 12 }, (_, i) => `<div style="height:28px;margin:10px 0;background:${i % 3 === 1 ? '#323B4E' : '#262F40'};border:1px solid #3A4458;width:${68 + ((i * 37) % 30)}%"></div>`).join('')}
    <div style="margin-top:20px;color:${I.steel};font-size:20px">ERP · Excel · CRM · Excel…</div>
  </div>
  <div style="position:absolute;left:555px;top:540px;width:14px;height:430px;background:${I.orange};transform:skewX(-30deg)"></div>
  <div style="position:absolute;right:80px;top:520px;width:300px">
    ${['ERP', 'CRM', 'Accounting', 'Spreadsheets'].map((t, i) => `<div style="height:62px;border:1.5px solid ${I.steel};margin-bottom:${i < 3 ? 0 : 22}px;display:flex;align-items:center;padding:0 18px;font-size:22px;background:${I.iron2}">${t}</div>${i < 3 ? `<div style="width:1.5px;height:22px;background:${I.steel};margin-left:28px"></div>` : ''}`).join('')}
    <div style="color:${I.steel};font-size:20px">Entered once. Moves on its own.</div>
  </div>${isFoot}</body>`,

  'CP-03-thumb': `<body style="width:1920px;height:1080px">
  <div class="dots" style="top:0;left:0;width:520px;height:1080px"></div>
  <div style="position:absolute;left:120px;top:300px;width:620px">
    <div class="lbl">Iron Systems · ProcurePilot</div>
    <div class="ar" style="font-weight:700;font-size:96px;margin-top:36px;text-align:left">من صنعنا.</div>
    <div class="disp" style="font-size:96px;margin-top:10px">Built by <span style="color:${I.orange}">us.</span></div>
    <div style="margin-top:30px;font-size:28px;color:${I.steel}">Real screens, demo data</div>
  </div>
  <div style="position:absolute;right:100px;top:190px;width:1000px;background:#fff;padding:14px;box-shadow:0 40px 80px -30px rgba(0,0,0,.7)">${crop(SRC('frame-v25-ar-72s-smart-compare.jpg'), 30, 285, 1285, 580, 972)}</div>
  <div class="foot" style="left:120px;right:100px;bottom:70px"><img src="${IL.logo}" style="height:60px"><span>www.iron-sys.com</span></div></body>`,
};

async function main() {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  const shoot = async (html, css, file, w, h) => {
    await page.setViewportSize({ width: w, height: h });
    await page.setContent(`<!doctype html><html><head><meta charset="utf-8">${FONTS}<style>${css}</style></head>${html}</html>`, { waitUntil: 'networkidle' });
    await page.evaluate(() => document.fonts.ready);
    fs.mkdirSync(path.dirname(file), { recursive: true });
    await page.screenshot({ path: file });
    console.log('wrote', path.relative(ROOT, file));
  };
  const ppOut = path.join(PPC, 'images/v2');
  for (const [n, h] of Object.entries(pp)) {
    const thumb = n.endsWith('thumb');
    await shoot(h, ppCss + (thumb ? 'html,body{width:1920px;height:1080px}' : ''), path.join(ppOut, `${n}-${thumb ? '1920x1080' : '1080x1350'}.png`), thumb ? 1920 : 1080, thumb ? 1080 : 1350);
  }
  const coOut = path.join(COC, 'images/v2');
  for (const [n, h] of Object.entries(co)) {
    const thumb = n.endsWith('thumb');
    await shoot(h, isCss + (thumb ? 'html,body{width:1920px;height:1080px}' : ''), path.join(coOut, `${n}-${thumb ? '1920x1080' : '1080x1350'}.png`), thumb ? 1920 : 1080, thumb ? 1080 : 1350);
  }
  // A-01 carousel PDF from the checked PNG pages
  const pages = [1, 2, 3, 4, 5].map((i) => `<img src="${img(path.join(ppOut, `A-01-p${i}-1080x1350.png`))}" style="display:block;width:1080px;height:1350px">`).join('');
  await page.setContent(`<!doctype html><html><head><style>@page{size:1080px 1350px;margin:0}body{margin:0}</style></head><body>${pages}</body></html>`);
  await page.pdf({ path: path.join(ppOut, 'A-01-carousel-1080x1350.pdf'), width: '1080px', height: '1350px', printBackground: true });
  console.log('wrote A-01 carousel PDF');
  await browser.close();
}
main().catch((e) => { console.error(e); process.exit(1); });
