const L = require('./lib.cjs');
(async () => { const { b } = await L.connect(); const pg = b.contexts()[0].pages().find((p) => p.url().includes('procurepilot.iron-sys.com')); await pg.bringToFront(); pg.setDefaultTimeout(15000);
  await pg.goto(L.BASE + '/rfq/compare/4503cd3c-69ac-4d39-9942-0c62b80f6811'); await L.sleep(4000);
  if (await pg.locator('.mat-drawer-opened').count()) { await pg.getByRole('button', { name: 'تبديل شريط التنقل' }).click(); await L.sleep(900); }
  await pg.screenshot({ path: process.argv[2] });
  await L.ensureCursor(pg);
  const rec = await L.startRec('s3b-compare', page); await L.sleep(3500);
  try {
    for (const t of ['الأمانة للتجارة', 'النور للمواد الغذائية', 'الحاج سيد للخضار']) { const el = pg.getByText(t).first(); if (await el.count()) { await L.moveTo(pg, el); await L.sleep(2500); } }
    const main = pg.locator('mat-sidenav-content, .mat-drawer-content').first();
    await pg.evaluate(() => { const sc = document.querySelector('mat-sidenav-content, .mat-drawer-content'); if (sc) sc.scrollBy({ top: 450, behavior: 'smooth' }); }); await L.sleep(4000);
    await pg.evaluate(() => { const sc = document.querySelector('mat-sidenav-content, .mat-drawer-content'); if (sc) sc.scrollBy({ top: 450, behavior: 'smooth' }); }); await L.sleep(4000);
  } finally { await L.stopRec(rec); }
  await pg.screenshot({ path: process.argv[2].replace('.png', '-end.png') });
})().then(() => process.exit(0)).catch((e) => { console.error('FAIL', e.message); process.exit(1); });
