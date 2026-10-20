const L = require('./lib.cjs');
(async () => {
  const { b } = await L.connect(); const pg = b.contexts()[0].pages().find((p) => p.url().includes('procurepilot.iron-sys.com')); await pg.bringToFront(); pg.setDefaultTimeout(15000);
  await pg.goto(L.BASE + '/savings'); await pg.getByText('زيت عباد الشمس').first().waitFor(); await L.sleep(1500);
  if (!(await pg.locator('.mat-drawer-opened').count())) { await pg.getByRole('button', { name: 'Toggle navigation' }).click(); await L.sleep(1000); }
  await L.ensureCursor(pg);
  const rec = await L.startRec('s6-savings-close', pg); await L.sleep(2000);
  try {
    await L.moveTo(pg, pg.getByText('Savings Ledger').first()); await L.sleep(1500); await L.moveTo(pg, pg.getByText('Total Verified Savings').first()); await L.sleep(3500);
    await L.moveTo(pg, pg.locator('tr, .mat-mdc-row').filter({ hasText: 'زيت عباد الشمس' }).first()); await L.sleep(3500);
    await L.moveTo(pg, pg.locator('tr, .mat-mdc-row').filter({ hasText: 'أرز مصري' }).first()); await L.sleep(2500);
    await L.moveTo(pg, pg.locator('tr, .mat-mdc-row').filter({ hasText: 'بصل أبيض' }).first()); await L.sleep(4000);
  } finally { await L.stopRec(rec); }
  await pg.screenshot({ path: process.argv[2] });
})().then(() => process.exit(0)).catch((e) => { console.error('FAIL', e.message); process.exit(1); });
