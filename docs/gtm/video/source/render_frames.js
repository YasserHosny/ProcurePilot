// Render canvas boards frame-by-frame: pause every CSS animation and seek it with the Web Animations API.
const { chromium } = require("/media/yasserhosny/My Passport/Work/Projects/ProcurePilot/apps/web/node_modules/playwright");
const fs = require("fs");
const path = require("path");

const SCRATCH = "/tmp/claude-1000/-media-yasserhosny-My-Passport-Work-Projects-ProcurePilot/1c3520f5-a777-4834-b5ef-0684f2157c72/scratchpad";
const BOARDS = path.join(SCRATCH, "logo/project");
const OUT = path.join(SCRATCH, "render/frames");
const FPS = 30;

const jobs = [
  { name: "Anim16x9", w: 1920, h: 1080, seconds: 4.5 },
  { name: "EndCard16x9", w: 1920, h: 1080, seconds: 157 / 30 }, // 157 frames: the outro ends at 3:00
  { name: "Anim9x16Fast", w: 1080, h: 1920, seconds: 3.0 },
  { name: "EndCard9x16", w: 1080, h: 1920, seconds: 5.5 },
  // English versions: same timing, English text
  { name: "AnimEn16x9", w: 1920, h: 1080, seconds: 4.5 },
  { name: "EndCardEn16x9", w: 1920, h: 1080, seconds: 157 / 30 },
  { name: "AnimEn9x16Fast", w: 1080, h: 1920, seconds: 3.0 },
  { name: "EndCardEn9x16", w: 1080, h: 1920, seconds: 5.5 },
];

function standalone(src) {
  const helmet = src.match(/<helmet>([\s\S]*?)<\/helmet>/)[1];
  const body = src.match(/<\/helmet>([\s\S]*?)<\/x-dc>/)[1];
  return `<!doctype html><html><head><meta charset="utf-8">${helmet}</head><body>${body}</body></html>`;
}

(async () => {
  const browser = await chromium.launch({ channel: "chrome", headless: true });
  for (const job of jobs) {
    const dir = path.join(OUT, job.name);
    fs.rmSync(dir, { recursive: true, force: true }); // no stale frames from a longer earlier render
    fs.mkdirSync(dir, { recursive: true });
    const html = path.join(dir, "board.html");
    fs.writeFileSync(html, standalone(fs.readFileSync(path.join(BOARDS, `${job.name}.dc.html`), "utf8")));
    const page = await browser.newPage({ viewport: { width: job.w, height: job.h } });
    await page.goto("file://" + html);
    await page.evaluate(() => document.fonts.ready);
    await page.waitForTimeout(500);
    const total = Math.round(job.seconds * FPS);
    for (let i = 0; i < total; i++) {
      const ms = (i * 1000) / FPS;
      await page.evaluate((t) => {
        for (const a of document.getAnimations()) { a.pause(); a.currentTime = t; }
      }, ms);
      await page.screenshot({ path: path.join(dir, `f${String(i).padStart(4, "0")}.png`) });
    }
    console.log(`${job.name}: ${total} frames`);
    await page.close();
  }
  await browser.close();
})();
