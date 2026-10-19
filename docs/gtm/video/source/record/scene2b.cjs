const L = require('./lib.cjs');
(async () => {
  const { page } = await L.connect();
  await page.goto(L.BASE + '/quotations/1552ad74-3b83-4afa-9255-8b9c309ca5af/review'); await L.sleep(3000);
  if (await page.locator('.mat-drawer-opened').count()) { await page.getByRole('button', { name: 'تبديل شريط التنقل' }).click(); await L.sleep(800); }
  await L.ensureCursor(page);
  const rec = L.startRec('s2b-photo-closeup'); await L.sleep(1500);
  try {
    await L.scrollToEl(page, page.getByText('أدلة المستند الأصلي').first(), 70, 2200);
    await L.sleep(1500);
    await L.moveTo(page, page.getByText('تفاصيل عرض السعر').first()); await L.sleep(2500);
    await L.moveTo(page, page.getByText('بنود عروض السعر المستخرجة').first().or(page.getByText(/بنود عرض السعر المستخرجة/)).first()); await L.sleep(3000);
    await L.scrollToEl(page, page.getByText(/بنود عرض السعر المستخرجة/).first(), 70, 2000);
    await L.sleep(4500);
  } finally { await L.stopRec(rec); }
})().then(() => process.exit(0)).catch((e) => { console.error('FAIL', e.message); process.exit(1); });
