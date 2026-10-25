// node render_quotes.cjs <dir>: dhahabi.png (photo source) + the two supplier PDFs named after their quote numbers.
const { chromium } = require('@playwright/test'); const path = require('path'); const fs = require('fs');
(async () => {
  const D = process.argv[2]; const b = await chromium.launch({ channel: 'chrome', headless: true });
  const p = await b.newPage({ viewport: { width: 1240, height: 1754 } });
  await p.goto('file://' + path.join(D, 'dhahabi.html')); await p.evaluate(() => document.fonts.ready); await p.waitForTimeout(500);
  await p.screenshot({ path: path.join(D, 'dhahabi.png') });
  for (const [f, label] of [['wafra.html', 'عرض سعر الوفرة'], ['qassim.html', 'عرض سعر خضار القصيم']]) {
    const no = fs.readFileSync(path.join(D, f), 'utf8').match(/رقم: ([^<]+)</)[1].replace(/\//g, '-');
    await p.goto('file://' + path.join(D, f)); await p.evaluate(() => document.fonts.ready); await p.waitForTimeout(400);
    await p.pdf({ path: path.join(D, `${label} ${no}.pdf`), format: 'A4', printBackground: true });
  }
  await b.close();
})();
