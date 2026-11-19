#!/usr/bin/env node
/**
 * ProcurePilot post images, v3 (2026-11-19). English only (MD-23), general business (MD-22). Same ProcurePilot look
 * as the v2 images (Paper ground, Navy dominant, one Teal hit, Converge bars, light grain).
 * Run from marketing/:  node scripts/render-linkedin-v3-procurepilot.cjs [A-10 ...]
 * Output: ProcurePilot/campaigns/2026-11-procurepilot-founder-linkedin/assets/drafts/images/v3/. Nothing is posted.
 */
const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

const ROOT = path.resolve(__dirname, '..');
const OUT = path.join(ROOT, 'ProcurePilot/campaigns/2026-11-procurepilot-founder-linkedin/assets/drafts/images/v3');
const img = (p) => `data:${p.endsWith('.svg') ? 'image/svg+xml' : 'image/png'};base64,${fs.readFileSync(p).toString('base64')}`;
const FONTS = '<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=block" rel="stylesheet">';
const GRAIN = `url("data:image/svg+xml;utf8,${encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" width="300" height="300"><filter id="n"><feTurbulence type="fractalNoise" baseFrequency=".85" numOctaves="2" stitchTiles="stitch"/><feColorMatrix values="0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 .55 0"/></filter><rect width="100%" height="100%" filter="url(#n)"/></svg>')}")`;
const P = { navy: '#0B2545', teal: '#12A594', tealText: '#0C7A6E', mist: '#C9D6E3', paper: '#F4F6F9', ink2: '#4A5D77' };
const LOGO = img(path.join(ROOT, 'ProcurePilot/design-system/logo/procurepilot-horizontal.svg'));
const css = `*{box-sizing:border-box;margin:0}html,body{width:1080px;height:1350px}
body{position:relative;overflow:hidden;font-family:Inter;color:${P.navy};background:${P.paper}}
body:after{content:"";position:absolute;inset:0;background:${GRAIN};opacity:.07;pointer-events:none;mix-blend-mode:multiply}
.card{background:#fff;box-shadow:0 2px 4px rgba(11,37,69,.06),0 24px 60px -18px rgba(11,37,69,.28)}
.kick{font-size:22px;letter-spacing:.02em;color:${P.ink2}}
.foot{position:absolute;left:72px;right:72px;bottom:60px;display:flex;justify-content:space-between;align-items:center}
.bars{display:flex;flex-direction:column;gap:7px;align-items:flex-end}.bars i{display:block;height:9px;border-radius:5px}`;
const bars = `<div class="bars"><i style="width:64px;background:${P.navy}"></i><i style="width:46px;background:${P.mist}"></i><i style="width:92px;background:${P.teal}"></i></div>`;
const foot = `<div class="foot"><img src="${LOGO}" style="height:44px"><span style="font-size:22px;color:${P.ink2}">procurepilot.iron-sys.com</span></div>`;

const pp = {
  'A-10': `<body>
  <div style="position:absolute;top:72px;right:72px">${bars}</div>
  <div class="kick" style="position:absolute;top:80px;left:72px">Your data</div>
  <div style="position:absolute;left:72px;right:72px;top:170px">
    <div style="font-size:84px;font-weight:700;line-height:1.1;letter-spacing:-.02em">We don't use<br>your data to train<br><span style="color:${P.tealText}">AI models.</span></div>
    <div style="font-size:32px;color:${P.ink2};margin-top:34px;line-height:1.45">ProcurePilot reads the quotes your<br>suppliers send so you can compare them.</div>
  </div>
  <div class="card" style="position:absolute;left:72px;right:72px;top:760px;padding:40px 44px">
    <div class="kick" style="font-size:18px;text-transform:uppercase;letter-spacing:.12em">Privacy policy · Artificial intelligence</div>
    <div style="display:flex;align-items:center;gap:22px;margin-top:26px">
      <div style="width:56px;height:56px;border-radius:50%;background:${P.teal};display:flex;align-items:center;justify-content:center;flex:none">
        <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12l5 5L20 7"/></svg></div>
      <div style="font-size:34px;font-weight:600">Not used to train AI models</div>
    </div>
    <div style="height:1px;background:${P.mist};margin:30px 0"></div>
    <div style="font-size:24px;color:${P.ink2};line-height:1.5">Written in our privacy policy, under "Artificial intelligence".</div>
  </div>
  ${foot}</body>`,
};

async function main() {
  const only = process.argv.slice(2);
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1080, height: 1350 } });
  fs.mkdirSync(OUT, { recursive: true });
  for (const [n, h] of Object.entries(pp)) {
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
