// Beat 8: Smart Compare for oil × 8: per pack and landed, the recommended supplier and the margin.
// PP_DRY=1 screenshots the result without recording.
const L = require('./lib.cjs');
const DRY = process.env.PP_DRY === '1';
L.run(async () => {
  const { page } = await L.connect();
  await page.goto(L.BASE + '/offers/compare'); await page.waitForLoadState('networkidle').catch(() => {}); await L.sleep(2500);
  await L.hideNav(page); await L.ensureCursor(page);
  const rec = DRY ? null : await L.startRec('s3c-smart-compare', page); await L.sleep(2500);
  try {
    await L.click(page, page.locator('mat-select').first().locator('.mat-mdc-select-trigger'), 900);
    await L.click(page, page.getByRole('option', { name: 'زيت عباد الشمس (صفيحة 18 لتر)' }), 3000);
    await L.ensureCursor(page);
    const q = page.locator('input[type=number]').first();
    await L.click(page, q, 300, true); await q.press('Control+a'); await q.pressSequentially('8', { delay: 150 }); await L.sleep(3500);
    await L.moveTo(page, page.getByText(L.t('compare.recommendation.title')).first()); await L.sleep(3000);
    await L.moveTo(page, page.getByText(L.rx('compare.recommendation.winningMargin')).first()); await L.sleep(2000);
    if (DRY) { await page.screenshot({ path: process.argv[2] }); console.log('dry: compare shown'); return; }
    const amana = page.locator('tr.mat-mdc-row').filter({ hasText: 'الأمانة للتجارة' }).first();
    await L.scrollToEl(page, amana, 300, 1800); await L.sleep(800);
    await L.moveTo(page, amana); await L.sleep(2500);
    await L.moveTo(page, page.locator('tr.mat-mdc-row').filter({ hasText: 'النور للمواد الغذائية' }).first()); await L.sleep(3000);
  } finally { if (rec) await L.stopRec(rec); }
});
