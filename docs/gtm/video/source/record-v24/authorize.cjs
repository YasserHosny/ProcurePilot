// Off-camera: authorise the given quotations (ids) the same way the review screen does.
const L = require('./lib.cjs');
L.run(async () => {
  const { page } = await L.connect();
  for (const id of process.argv.slice(2)) {
    await page.goto(L.BASE + '/quotations/' + id + '/review'); await page.waitForLoadState('networkidle').catch(() => {}); await L.sleep(3000);
    const confirms = page.getByRole('button', { name: L.t('quotations.review.flagged.confirmAsIs') });
    while (await confirms.count()) { await confirms.first().click({ force: true }); await L.sleep(900); }
    await page.getByRole('button', { name: L.t('quotations.review.actions.confirmButton') }).click({ force: true }); await L.sleep(1200);
    await page.getByRole('button', { name: L.t('quotations.review.actions.confirmDialogProceed'), exact: true }).click(); await L.sleep(3500);
    console.log('authorised', id);
  }
});
