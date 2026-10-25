// node render_quotes_en.cjs <dir>: photo.png (phone-photo source) + the two supplier PDFs, named "<Supplier> quote <No>.pdf".
const { chromium } = require('@playwright/test'); const path = require('path'); const fs = require('fs');
(async () => {
  const D = path.resolve(process.argv[2]); const b = await chromium.launch({ channel: 'chrome', headless: true });
  const p = await b.newPage({ viewport: { width: 1240, height: 1754 } });
  await p.goto('file://' + path.join(D, 'photo.html')); await p.evaluate(() => document.fonts.ready); await p.waitForTimeout(500);
  await p.screenshot({ path: path.join(D, 'photo.png') });
  for (const f of ['pdf1.html', 'pdf2.html']) {
    const name = fs.readFileSync(path.join(D, f + '.name'), 'utf8').trim().replace(/\//g, '-');
    await p.goto('file://' + path.join(D, f)); await p.evaluate(() => document.fonts.ready); await p.waitForTimeout(400);
    await p.pdf({ path: path.join(D, name + '.pdf'), format: 'A4', printBackground: true });
  }
  await b.close();
})();
