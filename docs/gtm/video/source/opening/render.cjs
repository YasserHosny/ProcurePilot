const { chromium } = require('@playwright/test'); const fs = require('fs'); const path = require('path');
const [,, html, out, w, h, secs, hash, only] = process.argv; const FPS = 30;
(async () => {
  const b = await chromium.launch({ channel: 'chrome', headless: true });
  const p = await b.newPage({ viewport: { width: +w, height: +h } });
  await p.goto('file://' + path.resolve(html) + '#' + (hash || '')); await p.evaluate(() => document.fonts.ready); await p.waitForTimeout(1200);
  fs.rmSync(out, { recursive: true, force: true }); fs.mkdirSync(out, { recursive: true });
  const n = Math.round(+secs * FPS); const frames = only ? only.split(',').map(Number) : [...Array(n).keys()];
  for (const f of frames) { await p.evaluate((t) => { for (const a of document.getAnimations()) { a.pause(); a.currentTime = t; } }, f / FPS * 1000);
    await p.screenshot({ path: path.join(out, String(f).padStart(4, '0') + '.png') }); }
  await b.close(); console.log('frames', frames.length);
})();
