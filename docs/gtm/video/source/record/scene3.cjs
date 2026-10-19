const L = require('./lib.cjs');
const REQ = 'd1f10ff7-1c14-46e0-980e-bb8ba3b12526';
(async () => {
  const { page } = await L.connect();
  await page.goto(L.BASE + '/requests'); await L.sleep(3000);
  if (await page.locator('.mat-drawer-opened').count()) { await page.getByRole('button', { name: 'تبديل شريط التنقل' }).click(); await L.sleep(800); }
  await L.ensureCursor(page);
  const rec = L.startRec('s3-guardrail-draft'); await L.sleep(3000);
  try {
    const row = page.locator('tr, mat-row, .mat-mdc-row, mat-card, li').filter({ hasText: /٢٥٬١٤٠|25,140/ }).first();
    if (await row.count()) { await L.click(page, row, 3000); } else { await page.goto(L.BASE + '/requests/' + REQ); await L.sleep(3000); }
    if (!page.url().includes(REQ)) { await page.goto(L.BASE + '/requests/' + REQ); await L.sleep(3000); }
    await L.ensureCursor(page);
    await L.moveTo(page, page.getByText('أعدّته الضوابط تلقائيًا').first()); await L.sleep(4000);
    await L.moveTo(page, page.getByText('المطبخ — المعادي').first()); await L.sleep(2500);
    await L.scrollToEl(page, page.getByText('الإجمالي المقدر').first(), 380, 1800); await L.sleep(3500);
    await L.click(page, page.getByRole('button', { name: 'إرسال الطلب' }), 4000);
    await L.ensureCursor(page); await L.sleep(1500);
  } finally { await L.stopRec(rec); }
  console.log('done', page.url());
})().then(() => process.exit(0)).catch((e) => { console.error('FAIL', e.message); process.exit(1); });
