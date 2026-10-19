const L = require('./lib.cjs');
(async () => { const { b } = await L.connect(); const pg = b.contexts()[0].pages().find((p) => p.url().includes('procurepilot.iron-sys.com')); await pg.bringToFront(); pg.setDefaultTimeout(15000);
  await pg.goto(L.BASE + '/offers/compare'); await L.sleep(4000);
  if (await pg.locator('.mat-drawer-opened').count()) { await pg.getByRole('button', { name: 'تبديل شريط التنقل' }).click(); await L.sleep(900); }
  await L.ensureCursor(pg);
  const rec = L.startRec('s3c-smart-compare'); await L.sleep(2500);
  try {
    await L.click(pg, pg.locator('mat-select').first().locator('.mat-mdc-select-trigger'), 900);
    await L.click(pg, pg.getByRole('option', { name: 'زيت عباد الشمس (صفيحة 18 لتر)' }), 3000);
    await L.ensureCursor(pg);
    const q = pg.locator('input[type=number]').first();
    await L.click(pg, q, 300, true); await q.press('Control+a'); await q.pressSequentially('8', { delay: 150 }); await L.sleep(3500);
    await L.moveTo(pg, pg.getByText('العرض الموصى به').first()); await L.sleep(3000);
    await L.moveTo(pg, pg.getByText('هامش التوفير').first()); await L.sleep(2000);
    await L.scrollToEl(pg, pg.getByText('المورد', { exact: true }).first(), 200, 1800); await L.sleep(1000);
    await L.moveTo(pg, pg.locator('tr, .mat-mdc-row').filter({ hasText: 'الأمانة للتجارة' }).first()); await L.sleep(2500);
    await L.moveTo(pg, pg.locator('tr, .mat-mdc-row').filter({ hasText: 'النور للمواد الغذائية' }).first()); await L.sleep(3000);
  } finally { await L.stopRec(rec); }
  await pg.screenshot({ path: process.argv[2] });
})().then(() => process.exit(0)).catch((e) => { console.error('FAIL', e.message); process.exit(1); });
