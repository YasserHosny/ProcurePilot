const L = require('./lib.cjs');
(async () => {
  const { b, page } = await L.connect();
  await page.goto(L.BASE + '/rfq/history'); await page.waitForLoadState('networkidle'); await L.sleep(1500);
  await L.ensureCursor(page);
  const rec = L.startRec('s1-rfq'); await L.sleep(2500);
  try {
  await L.click(page, page.getByRole('link', { name: /إنشاء طلب عرض أسعار/ }), 1500);
  await L.ensureCursor(page);
  const selects = () => page.locator('mat-select[formcontrolname="workspace_product_id"]');
  const qtys = () => page.locator('input[formcontrolname="quantity"]');
  const lines = [['زيت عباد الشمس (صفيحة 18 لتر)', '8'], ['أرز مصري (شيكارة 25 كجم)', '12'], ['بصل أبيض', '80']];
  for (let i = 0; i < lines.length; i++) {
    if (i > 0) await L.click(page, page.getByRole('button', { name: /إضافة سطر/ }), 600);
    await L.click(page, selects().nth(i).locator('.mat-mdc-select-trigger'), 700);
    const opt = page.getByRole('option', { name: lines[i][0], exact: true });
    await L.click(page, opt, 500);
    await L.type(page, qtys().nth(i), lines[i][1], 120);
  }
  await L.click(page, page.locator('mat-select[formcontrolname="supplierIds"] .mat-mdc-select-trigger'), 700);
  for (const s of ['النور للمواد الغذائية', 'الأمانة للتجارة', 'الحاج سيد للخضار']) await L.click(page, page.getByRole('option', { name: s }), 300);
  await page.keyboard.press('Escape'); await L.sleep(600);
  await L.type(page, page.locator('input[formcontrolname="neededByDate"]'), '22/10/2026', 110);
  await L.type(page, page.locator('textarea[formcontrolname="tenantTerms"]'), 'التوريد إلى فرع المعادي. الدفع خلال 30 يومًا من الاستلام.', 45);
  await L.sleep(800);
  await L.click(page, page.getByRole('button', { name: /حفظ كمسودة/ }), 2500);
  await L.ensureCursor(page);
  const send = page.getByRole('button', { name: /إرسال الطلب/ });
  await send.waitFor({ timeout: 15000 });
  await L.click(page, send, 3500);
  await L.ensureCursor(page);
  await L.sleep(3000);
  } finally { await L.stopRec(rec); }
  console.log('url', page.url());
})().then(() => process.exit(0)).catch((e) => { console.error('FAIL', e.message); process.exit(1); });
