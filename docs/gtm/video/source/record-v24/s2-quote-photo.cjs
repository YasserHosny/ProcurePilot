// Beats 5–7: the quotation inbox with the three replies, then الأمانة's photo quote: the photo beside the
// extracted lines, a hold on the reconciled total, flagged values confirmed, Authorise.
// PP_DRY=1 opens the review and screenshots it without recording or authorising.
const L = require('./lib.cjs');
const DRY = process.env.PP_DRY === '1';
L.run(async () => {
  const { page } = await L.connect();
  await page.goto(L.BASE + '/quotations'); await page.waitForLoadState('networkidle').catch(() => {}); await L.sleep(1500);
  await L.hideNav(page); await L.ensureCursor(page);
  const rec = DRY ? null : await L.startRec('s2-quote-photo', page); await L.sleep(3000);
  try {
    const row = page.locator('tr.mat-mdc-row').filter({ hasText: 'الأمانة للتجارة' }).first();
    await L.moveTo(page, row); await L.sleep(1200);
    const review = row.getByRole('button', { name: L.rx('quotations.queue.actions.review') }).or(row.getByRole('link', { name: L.rx('quotations.queue.actions.review') })).first();
    await L.click(page, review, 3000);
    await L.hideNav(page); await L.ensureCursor(page);
    await L.moveTo(page, page.getByText(L.t('quotations.review.panels.document')).first()); await L.sleep(3500);
    if (DRY) { await page.screenshot({ path: process.argv[2] }); console.log('dry: review open', page.url()); return; }
    await page.evaluate(() => window.scrollBy({ top: 420, behavior: 'smooth' })); await L.sleep(4000);
    await page.evaluate(() => window.scrollBy({ top: 380, behavior: 'smooth' })); await L.sleep(3500);
    const confirms = page.getByRole('button', { name: L.t('quotations.review.flagged.confirmAsIs') });
    const n = await confirms.count();
    for (let i = 0; i < n; i++) await L.click(page, confirms.first(), 1200);
    await L.click(page, page.getByRole('button', { name: L.t('quotations.review.actions.confirmButton') }), 1500);
    await L.click(page, page.getByRole('button', { name: L.t('quotations.review.actions.confirmDialogProceed'), exact: true }), 3500);
    await L.ensureCursor(page); await L.sleep(1500);
  } finally { if (rec) await L.stopRec(rec); }
  console.log('done', page.url());
});
