const { chromium } = require('@playwright/test');
(async () => { const b = await chromium.connectOverCDP('http://127.0.0.1:9333'); const ctx = b.contexts()[0];
  const page = ctx.pages().find((p) => p.url().includes('iron-sys'));
  await page.goto('https://procurepilot.iron-sys.com/quotations'); await page.waitForLoadState('networkidle').catch(() => {}); await page.waitForTimeout(2000);
  const out = [];
  for (const name of ['النور للمواد الغذائية', 'الحاج سيد للخضار']) {
    await page.locator('.mat-mdc-row, tr').filter({ hasText: name }).first().getByText(/Review & Authorize/).first().click();
    await page.waitForURL(/review/); out.push(page.url().split('/')[4]); await page.goBack(); await page.waitForTimeout(2000);
  }
  console.log(out.join(' ')); process.exit(0); })();
