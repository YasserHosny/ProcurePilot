const L = require('./lib.cjs');
(async () => {
  const { page } = await L.connect();
  for (const id of process.argv.slice(2)) {
    await page.goto(L.BASE + '/quotations/' + id + '/review'); await L.sleep(3000);
    const confirms = page.getByRole('button', { name: 'Confirm as-is' });
    while (await confirms.count()) { await confirms.first().click({ force: true }); await L.sleep(900); }
    await page.getByRole('button', { name: 'Confirm & Authorize Quotation' }).click({ force: true }); await L.sleep(1200);
    await page.getByRole('button', { name: 'Confirm & Authorize', exact: true }).click(); await L.sleep(3500);
    console.log('authorised', id);
  }
})().then(() => process.exit(0)).catch((e) => { console.error('FAIL', e.message); process.exit(1); });
