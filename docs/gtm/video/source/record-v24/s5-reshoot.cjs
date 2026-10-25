// PPS-63: re-shoot the outcome-form and ledger shots after the «توفير» wording change (#263). Nothing is saved.
// usage: node s5-reshoot.cjs form <order id> <clip name>   — the order's record-outcome form, opened from the order
//        node s5-reshoot.cjs ledger <clip name> [rows]      — the ledger as it is now, nav hidden; hovers rows (0-based, e.g. 3,4,5)
const L = require('./lib.cjs');
L.run(async () => {
  const { page } = await L.connect();
  const [mode] = process.argv.slice(2);
  if (mode === 'form') {
    const [, order, name] = process.argv.slice(2);
    await page.goto(L.BASE + '/orders/' + order); await page.waitForLoadState('networkidle').catch(() => {}); await L.sleep(2500);
    await L.hideNav(page); await L.ensureCursor(page);
    const outcome = page.getByRole('link', { name: L.t('orders.detail.recordOutcome') }).or(page.getByRole('button', { name: L.t('orders.detail.recordOutcome') })).first();
    const rec = await L.startRec(name, page); await L.sleep(2000);
    try {
      await L.scrollToEl(page, outcome, 500, 1500);
      await L.click(page, outcome, 3500); await L.ensureCursor(page); await L.hideNav(page); await L.sleep(1500);
      await L.moveTo(page, page.getByText(L.rx('savings.fromOrder.baselineNote')).first()).catch(() => {}); await L.sleep(3000);
      await L.moveTo(page, page.getByRole('button', { name: L.rx('savings.fromOrder.submit') })); await L.sleep(3000);
    } finally { await L.stopRec(rec); }
  } else if (mode === 'ledger') {
    const [, name, rows = ''] = process.argv.slice(2);
    await page.goto(L.BASE + '/savings'); await page.locator('tr.mat-mdc-row').first().waitFor(); await L.sleep(1500);
    await L.hideNav(page); await L.ensureCursor(page);
    const rec = await L.startRec(name, page); await L.sleep(2000);
    try {
      await L.moveTo(page, page.getByText(L.t('savings.ledger.stats.totalVerified')).first()); await L.sleep(3000);
      for (const i of rows.split(',').filter(Boolean)) { await L.moveTo(page, page.locator('tr.mat-mdc-row').nth(Number(i))); await L.sleep(2000); }
      await L.sleep(1500);
    } finally { await L.stopRec(rec); }
  } else throw new Error('mode: form | ledger');
  console.log('done', page.url());
});
