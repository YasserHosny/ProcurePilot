const { chromium } = require('@playwright/test');
const fs = require('fs'); const path = require('path');
const B = process.argv[2], OUT = process.argv[3]; const FPS = 30;
const jobs = [
  ...[0,1,2,3,4,5,6].map(i => ({ name: 'en_card' + i, file: 'SceneCardsEn16x9.html', start: i * 3.2, seconds: 3.2 })),
  { name: 'en_notify', file: 'NotificationCardEn16x9.html', start: 0, seconds: 4.5 },
  { name: 'en_counter', file: 'SavingsCounterEn16x9.html', start: 0, seconds: 3.6 },
];
(async () => {
  const browser = await chromium.launch({ channel: 'chrome', headless: true });
  for (const job of jobs) {
    const dir = path.join(OUT, job.name); fs.rmSync(dir, { recursive: true, force: true }); fs.mkdirSync(dir, { recursive: true });
    const page = await browser.newPage({ viewport: { width: 1920, height: 1080 } });
    await page.goto('file://' + path.join(B, job.file)); await page.evaluate(() => document.fonts.ready); await page.waitForTimeout(800);
    const n = Math.max(1, Math.round(job.seconds * FPS));
    for (let f = 0; f < n; f++) {
      const t = (job.start + f / FPS) * 1000;
      await page.evaluate((t) => { for (const a of document.getAnimations()) { a.pause(); a.currentTime = t; } }, t);
      await page.screenshot({ path: path.join(dir, String(f).padStart(4, '0') + '.png') });
    }
    await page.close(); console.log(job.name, n);
  }
  await browser.close();
})();
