#!/usr/bin/env node
/**
 * Iron Systems company post images CP-05 to CP-07 (2026-11-19). English only (MD-23), same Iron Systems v3.3 look
 * as the CP-01..CP-04 v2 images (dark iron ground, one orange accent, Archivo display + Inter).
 * Run from marketing/:  node scripts/render-linkedin-v3-company.cjs
 * Output: campaigns/2026-11-company-ai-in-production/assets/drafts/images/v3/. Nothing is uploaded or posted.
 */
const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

const ROOT = path.resolve(__dirname, '..');
const BRAND = path.join(ROOT, 'brand/iron-systems');
const OUT = path.join(ROOT, 'campaigns/2026-11-company-ai-in-production/assets/drafts/images/v3');
const mime = (p) => (p.endsWith('.svg') ? 'image/svg+xml' : p.endsWith('.png') ? 'image/png' : 'image/jpeg');
const img = (p) => `data:${mime(p)};base64,${fs.readFileSync(p).toString('base64')}`;

const FONTS = '<link href="https://fonts.googleapis.com/css2?family=Archivo:wdth,wght@125,800&family=Inter:wght@400;500;600&family=Readex+Pro:wght@400;500;600;700&display=block" rel="stylesheet">';
const GRAIN = `url("data:image/svg+xml;utf8,${encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" width="300" height="300"><filter id="n"><feTurbulence type="fractalNoise" baseFrequency=".85" numOctaves="2" stitchTiles="stitch"/><feColorMatrix values="0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 .55 0"/></filter><rect width="100%" height="100%" filter="url(#n)"/></svg>')}")`;

const I = { dark: '#0B0F17', iron2: '#111827', iron3: '#1E293B', line: '#2A3448', steel: '#94A3B8', light: '#E2E8F0', orange: '#F97316' };
const IL = { logo: img(path.join(BRAND, 'iron-system-logo-primary-dark-1024.png')) };
const css = `*{box-sizing:border-box;margin:0}html,body{width:1080px;height:1350px}
body{position:relative;overflow:hidden;background:${I.dark};color:${I.light};font-family:Inter}
body:after{content:"";position:absolute;inset:0;background:${GRAIN};opacity:.06;mix-blend-mode:screen;pointer-events:none}
.disp{font-family:Archivo;font-stretch:125%;font-weight:800;text-transform:uppercase;letter-spacing:-.01em}
.rule{width:64px;height:3px;background:${I.orange}}.lbl{font-size:20px;letter-spacing:.14em;color:${I.steel};text-transform:uppercase}
.foot{position:absolute;left:80px;right:80px;bottom:64px;display:flex;justify-content:space-between;align-items:center;color:${I.steel};font-size:22px}
.dots{position:absolute;background-image:radial-gradient(${I.iron3} 2px,transparent 2px);background-size:26px 26px}
.ar{font-family:'Readex Pro';direction:rtl;text-align:right}`;
const foot = `<div class="foot"><img src="${IL.logo}" style="height:60px"><span>www.iron-sys.com</span></div>`;

const STAGES = ['Understand', 'Architect', 'Build', 'Validate', 'Launch', 'Improve'];

const co = {
  'CP-05': `<body>
  <div class="dots" style="top:0;right:0;width:380px;height:380px"></div>
  <div class="lbl" style="position:absolute;top:80px;left:80px">How we build</div>
  <div style="position:absolute;left:80px;right:80px;top:150px">
    <div class="disp" style="font-size:76px;line-height:1.04">Six stages.<br>A named<br>deliverable<br>at <span style="color:${I.orange}">each.</span></div>
  </div>
  <div style="position:absolute;left:80px;right:80px;top:640px">
    ${STAGES.map((s, i) => `<div style="display:flex;align-items:center;height:84px;border-top:1px solid ${I.line};${i === 5 ? `border-bottom:1px solid ${I.line};` : ''}">
      <div class="disp" style="width:120px;font-size:30px;color:${I.orange}">0${i + 1}</div>
      <div style="font-size:38px;font-weight:500">${s}</div>
      <div style="margin-left:auto;width:${60 + i * 36}px;height:8px;background:${i === 5 ? I.orange : I.iron3};border-radius:4px"></div>
    </div>`).join('')}
    <div style="margin-top:26px;font-size:24px;color:${I.steel}">We start with the problem, before any code.</div>
  </div>${foot}</body>`,

  'CP-06': `<body>
  <div class="dots" style="top:0;right:0;width:380px;height:380px"></div>
  <div class="lbl" style="position:absolute;top:80px;left:80px">What we do</div>
  <div style="position:absolute;left:80px;right:80px;top:150px">
    <div class="disp" style="font-size:80px;line-height:1.04">Four<br>disciplines.<br>One <span style="color:${I.orange}">team.</span></div>
  </div>
  <div style="position:absolute;left:80px;right:80px;top:560px;display:grid;grid-template-columns:1fr 1fr;gap:24px">
    ${[['01', 'AI solutions', 'Built on your own data'], ['02', 'Custom software', 'Manages the work, your way'], ['03', 'Automation', 'Moves routine work along'], ['04', 'System integration', 'Connects the systems you use']].map(([n, a, b], i) => `<div style="background:${I.iron2};border:1px solid ${I.line};padding:34px 32px;height:250px;position:relative">
      <div class="disp" style="font-size:26px;color:${I.orange}">${n}</div>
      <div style="font-size:36px;font-weight:600;margin-top:20px">${a}</div>
      <div style="font-size:22px;color:${I.steel};margin-top:14px;line-height:1.4">${b}</div>
    </div>`).join('')}
  </div>
  <div style="position:absolute;left:80px;top:1130px;font-size:24px;color:${I.steel}">From the first idea to a system running in production.</div>
  ${foot}</body>`,

  'CP-07': `<body>
  <div class="dots" style="top:0;right:0;width:380px;height:380px"></div>
  <div class="lbl" style="position:absolute;top:80px;left:80px">AI in production</div>
  <div style="position:absolute;left:80px;right:80px;top:150px">
    <div class="disp" style="font-size:74px;line-height:1.05">AI that keeps<br>working after<br><span style="color:${I.orange}">launch.</span></div>
  </div>
  <div style="position:absolute;left:80px;right:80px;top:620px">
    ${[['Built', 'on your own data'], ['Evaluated', 'before launch'], ['Monitored', 'after it goes live']].map(([a, b], i) => `<div style="display:flex;align-items:baseline;gap:22px;padding:30px 0;border-top:1px solid ${I.line};${i === 2 ? `border-bottom:1px solid ${I.line};` : ''}">
      <div class="disp" style="font-size:40px;width:330px">${a}</div><div style="font-size:32px;color:${I.steel}">${b}</div></div>`).join('')}
    <div style="margin-top:40px;font-size:24px;color:${I.light}">Problem first <span style="color:${I.orange}">·</span> AI where it helps <span style="color:${I.orange}">·</span> Built to last</div>
  </div>${foot}</body>`,
  'CP-08': `<body>
  <div class="dots" style="top:0;right:0;width:380px;height:380px"></div>
  <div class="lbl" style="position:absolute;top:80px;left:80px">AI solutions</div>
  <div style="position:absolute;left:80px;right:80px;top:150px">
    <div class="disp" style="font-size:70px;line-height:1.05">AI that reads<br>the documents<br>your team<br><span style="color:${I.orange}">re-types.</span></div>
  </div>
  <div style="position:absolute;left:80px;right:80px;top:640px;display:flex;align-items:center;gap:30px">
    <div style="flex:1;display:flex;flex-direction:column;gap:14px">
      ${['Quote', 'Invoice', 'Delivery note'].map((d, i) => `<div style="background:${I.iron2};border:1px solid ${I.line};padding:22px 26px;transform:translateX(${i * 18}px)">
        <div style="font-size:26px;font-weight:600">${d}</div>
        ${[78, 62, 70].map((w) => `<div style="height:8px;width:${w}%;background:${I.iron3};border-radius:4px;margin-top:12px"></div>`).join('')}
      </div>`).join('')}
    </div>
    <div style="width:70px;height:4px;background:${I.orange}"></div>
    <div style="flex:1;background:${I.iron2};border:1px solid ${I.line};padding:26px">
      <div class="lbl" style="font-size:16px">Read and linked</div>
      ${['Item', 'Quantity', 'Unit price', 'Total'].map((f) => `<div style="display:flex;justify-content:space-between;align-items:center;padding:16px 0;border-bottom:1px solid ${I.line};font-size:22px"><span>${f}</span><span style="width:90px;height:8px;background:${I.steel};border-radius:4px;opacity:.5"></span></div>`).join('')}
      <div style="margin-top:16px;font-size:18px;color:${I.steel}">Each value linked to its place in the source</div>
    </div>
  </div>
  <div style="position:absolute;left:80px;top:1130px;font-size:24px;color:${I.steel}">The same engine reads supplier quotes in ProcurePilot.</div>
  ${foot}</body>`,
};

async function main() {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1080, height: 1350 } });
  fs.mkdirSync(OUT, { recursive: true });
  const only = process.argv.slice(2);
  for (const [n, h] of Object.entries(co)) {
    if (only.length && !only.includes(n)) continue;
    await page.setContent(`<!doctype html><html><head><meta charset="utf-8">${FONTS}<style>${css}</style></head>${h}</html>`, { waitUntil: 'networkidle' });
    await page.evaluate(() => document.fonts.ready);
    const file = path.join(OUT, `${n}-1080x1350.png`);
    await page.screenshot({ path: file });
    console.log('wrote', path.relative(ROOT, file));
  }
  await browser.close();
}
main().catch((e) => { console.error(e); process.exit(1); });
