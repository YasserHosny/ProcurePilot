// Beat 14: the savings ledger with the sidebar on: the verified total, then this round's three lines.
const L = require('./lib.cjs');
L.run(async () => {
  const { page } = await L.connect();
  await page.goto(L.BASE + '/savings'); await page.getByText('زيت عباد الشمس').first().waitFor(); await L.sleep(1500);
  await L.showNav(page); await L.ensureCursor(page);
  const rec = await L.startRec('s6-savings-close', page); await L.sleep(2000);
  try {
    await L.moveTo(page, page.getByText(L.t('savings.ledger.title')).first()); await L.sleep(1500);
    await L.moveTo(page, page.getByText(L.t('savings.ledger.stats.totalVerified')).first()); await L.sleep(3500);
    for (const p of ['زيت عباد الشمس', 'أرز مصري', 'بصل أبيض']) { await L.moveTo(page, page.locator('tr.mat-mdc-row').filter({ hasText: p }).first()); await L.sleep(2500); }
    await L.sleep(1500);
  } finally { await L.stopRec(rec); }
  await page.screenshot({ path: process.argv[2] });
});
