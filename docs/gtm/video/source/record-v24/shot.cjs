// node shot.cjs <path> <out.png> — open a page in the kiosk tab and screenshot it (no clicks).
const L = require('./lib.cjs');
L.run(async () => { const { page } = await L.connect(); await page.goto(L.BASE + process.argv[2]); await page.waitForLoadState('networkidle').catch(() => {}); await L.sleep(2500); await page.screenshot({ path: process.argv[3] }); });
