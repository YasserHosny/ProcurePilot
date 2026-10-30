// node render_quotes_review.cjs <dir>: the two supplier PDFs from gen_quotes_review.py, named after their quote numbers.
const { chromium } = require('@playwright/test'); const path = require('path'); const fs = require('fs');
(async () => {
  const D = process.argv[2]; const b = await chromium.launch({ channel: 'chrome', headless: true });
  const p = await b.newPage();
  for (const [f, label] of [['dhahabi.html', 'عرض سعر الذهبي'], ['wafra.html', 'عرض سعر الوفرة']]) {
    if (!fs.existsSync(path.join(D, f))) continue; // gen_quote_pps129.py writes only dhahabi.html
    const no = fs.readFileSync(path.join(D, f), 'utf8').match(/رقم: ([^<]+)</)[1].replace(/\//g, '-');
    await p.goto('file://' + path.join(D, f)); await p.evaluate(() => document.fonts.ready); await p.waitForTimeout(400);
    await p.pdf({ path: path.join(D, `${label} ${no}.pdf`), format: 'A4', printBackground: true });
  }
  await b.close();
})();
