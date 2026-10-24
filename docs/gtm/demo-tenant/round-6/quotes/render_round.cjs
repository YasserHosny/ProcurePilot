// node render_round.cjs <dir> <nour quote no> <sayed quote no>: amana.png + the two supplier PDFs.
const { chromium } = require('@playwright/test'); const path = require('path');
(async () => {
  const [D, nourNo, sayedNo] = process.argv.slice(2);
  const b = await chromium.launch({ channel: 'chrome', headless: true });
  const p = await b.newPage({ viewport: { width: 1240, height: 1754 } });
  await p.goto('file://' + path.join(D, 'amana.html')); await p.evaluate(() => document.fonts.ready); await p.waitForTimeout(500);
  await p.screenshot({ path: path.join(D, 'amana.png') });
  for (const [f, out] of [['nour.html', `عرض سعر النور ${nourNo.replace('/', '-')}.pdf`], ['sayed.html', `عرض سعر الحاج سيد ${sayedNo}.pdf`]]) {
    await p.goto('file://' + path.join(D, f)); await p.evaluate(() => document.fonts.ready); await p.waitForTimeout(400);
    await p.pdf({ path: path.join(D, out), format: 'A4', printBackground: true });
  }
  await b.close();
})();
