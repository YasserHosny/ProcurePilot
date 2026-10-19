const L = require('./lib.cjs');
const AMANA = '1552ad74-3b83-4afa-9255-8b9c309ca5af';
(async () => {
  const { page } = await L.connect();
  await page.goto(L.BASE + '/quotations'); await page.waitForLoadState('networkidle').catch(() => {}); await L.sleep(1500);
  // sidebar hidden for this scene
  const nav = page.getByRole('button', { name: 'تبديل شريط التنقل' });
  if (await page.locator('mat-sidenav.mat-drawer-opened, .mat-drawer-opened').count()) { await nav.click(); await L.sleep(800); }
  await L.ensureCursor(page);
  const rec = L.startRec('s2-quote-photo'); await L.sleep(3000);
  try {
    const row = page.locator('tr, mat-row, .mat-mdc-row').filter({ hasText: 'الأمانة للتجارة' }).first();
    await L.click(page, row.getByRole('button', { name: /مراجعة واعتماد/ }).or(row.getByRole('link', { name: /مراجعة واعتماد/ })).first(), 3000);
    await L.ensureCursor(page);
    if (await page.locator('.mat-drawer-opened').count()) { await nav.click(); await L.sleep(800); }
    // show the photo beside the fields
    const evidence = page.getByText('أدلة المستند الأصلي').first();
    await L.moveTo(page, evidence); await page.mouse.wheel(0, 0); await L.sleep(4000);
    await page.evaluate(() => window.scrollBy({ top: 420, behavior: 'smooth' })); await L.sleep(4500);
    await page.evaluate(() => window.scrollBy({ top: 380, behavior: 'smooth' })); await L.sleep(3500);
    // confirm flagged values as read
    const confirms = page.getByRole('button', { name: 'تأكيد القيمة كما هي' });
    const n = await confirms.count();
    for (let i = 0; i < n; i++) { await L.click(page, confirms.first(), 1200); }
    const auth = page.getByRole('button', { name: 'تأكيد واعتماد عرض السعر' });
    await L.click(page, auth, 1500);
    await L.click(page, page.getByRole('button', { name: 'تأكيد واعتماد', exact: true }), 3500);
    await L.ensureCursor(page); await L.sleep(1500);
  } finally { await L.stopRec(rec); }
  console.log('done', page.url());
})().then(() => process.exit(0)).catch((e) => { console.error('FAIL', e.message); process.exit(1); });
