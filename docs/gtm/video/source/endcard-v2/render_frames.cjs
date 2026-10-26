// Render the v2 end card boards frame by frame (pause every CSS animation, seek it, screenshot), like
// ../render_frames.js did for v1. Usage: node render_frames.cjs <outDir> [stillSeconds]
// With stillSeconds, writes one PNG per board at that time instead of the full frame run.
// NODE_PATH must point at a node_modules with playwright; PP_CHROME may name a Chrome binary.
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const FPS = 30;
const jobs = [
  { name: 'EndCard16x9', w: 1920, h: 1080, seconds: 157 / 30 },
  { name: 'EndCard9x16', w: 1080, h: 1920, seconds: 5.5 },
  { name: 'EndCardEn16x9', w: 1920, h: 1080, seconds: 157 / 30 },
  { name: 'EndCardEn9x16', w: 1080, h: 1920, seconds: 5.5 },
];

(async () => {
  const out = path.resolve(process.argv[2] || 'frames');
  const still = process.argv[3] !== undefined ? Number(process.argv[3]) : null;
  const browser = await chromium.launch(process.env.PP_CHROME ? { executablePath: process.env.PP_CHROME } : { channel: 'chrome' });
  for (const job of jobs) {
    const page = await browser.newPage({ viewport: { width: job.w, height: job.h } });
    await page.goto('file://' + path.join(__dirname, `${job.name}.html`));
    await page.evaluate(() => document.fonts.ready);
    await page.waitForTimeout(500);
    const seek = (ms) => page.evaluate((t) => { for (const a of document.getAnimations()) { a.pause(); a.currentTime = t; } }, ms);
    if (still !== null) {
      fs.mkdirSync(out, { recursive: true });
      await seek(still * 1000);
      await page.screenshot({ path: path.join(out, `${job.name}.png`) });
    } else {
      const dir = path.join(out, job.name);
      fs.rmSync(dir, { recursive: true, force: true });
      fs.mkdirSync(dir, { recursive: true });
      const total = Math.round(job.seconds * FPS);
      for (let i = 0; i < total; i++) {
        await seek((i * 1000) / FPS);
        await page.screenshot({ path: path.join(dir, `f${String(i).padStart(4, '0')}.png`) });
      }
      console.log(`${job.name}: ${total} frames`);
    }
    await page.close();
  }
  await browser.close();
})();
