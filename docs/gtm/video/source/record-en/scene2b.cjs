const L = require('./lib.cjs');
(async () => {
  const { page } = await L.connect();
  await page.goto(L.BASE + '/quotations/1544467f-8260-47a1-80e8-b5f180f9c243/review'); await L.sleep(3000);
  if (await page.locator('.mat-drawer-opened').count()) { await page.getByRole('button', { name: 'Toggle navigation' }).click(); await L.sleep(800); }
  await L.ensureCursor(page);
  const rec = await L.startRec('s2b-photo-closeup', page); await L.sleep(1500);
  try {
    await L.scrollToEl(page, page.getByText('Source Document Evidence').first(), 70, 2200);
    await L.sleep(1500);
    await L.moveTo(page, page.getByText('Quotation Details').first()); await L.sleep(2500);
    await L.moveTo(page, page.getByText(/Extracted Line Items/).first()); await L.sleep(3000);
    await L.scrollToEl(page, page.getByText(/Extracted Line Items/).first(), 70, 2000);
    await L.sleep(4500);
  } finally { await L.stopRec(rec); }
})().then(() => process.exit(0)).catch((e) => { console.error('FAIL', e.message); process.exit(1); });
