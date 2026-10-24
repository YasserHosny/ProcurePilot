// Beat 3: build one RFQ (oil 8, rice 12, onions 80) to three suppliers and send it.
// PP_DRY=1 fills the form without recording and stops before saving (rehearsal; nothing is created).
const L = require('./lib.cjs');
const DRY = process.env.PP_DRY === '1';
const NEEDED = process.env.PP_NEEDED || '28/10/2026';
const TERMS = L.LANG === 'ar' ? 'التوريد لفرع المعادي. الدفع خلال 30 يومًا من الاستلام.' : 'Delivery to the Maadi branch. Payment within 30 days of receipt.';
L.run(async () => {
  const { page } = await L.connect();
  await page.goto(L.BASE + '/rfq/history'); await page.waitForLoadState('networkidle').catch(() => {}); await L.sleep(1500);
  await L.hideNav(page); await L.ensureCursor(page);
  const rec = DRY ? null : await L.startRec('s1-rfq', page); await L.sleep(2000);
  try {
    await L.click(page, page.getByRole('link', { name: L.rx('rfq.history.createRfq') }).or(page.getByRole('button', { name: L.rx('rfq.history.createRfq') })).first(), 1500);
    await L.hideNav(page); await L.ensureCursor(page);
    const selects = () => page.locator('mat-select[formcontrolname="workspace_product_id"]');
    const qtys = () => page.locator('input[formcontrolname="quantity"]');
    const lines = [['زيت عباد الشمس (صفيحة 18 لتر)', '8'], ['أرز مصري (شيكارة 25 كجم)', '12'], ['بصل أبيض', '80']];
    for (let i = 0; i < lines.length; i++) {
      if (i > 0) await L.click(page, page.getByRole('button', { name: L.rx('rfq.create.addLineButton') }), 600);
      await L.click(page, selects().nth(i).locator('.mat-mdc-select-trigger'), 700);
      await L.click(page, page.getByRole('option', { name: lines[i][0], exact: true }), 500);
      await L.type(page, qtys().nth(i), lines[i][1], 120);
    }
    await L.click(page, page.locator('mat-select[formcontrolname="supplierIds"] .mat-mdc-select-trigger'), 700);
    for (const s of ['النور للمواد الغذائية', 'الأمانة للتجارة', 'الحاج سيد للخضار']) await L.click(page, page.getByRole('option', { name: s }), 300);
    await page.keyboard.press('Escape'); await L.sleep(600);
    await L.type(page, page.locator('input[formcontrolname="neededByDate"]'), NEEDED, 110);
    await L.type(page, page.locator('textarea[formcontrolname="tenantTerms"]'), TERMS, 45);
    await L.sleep(800);
    if (DRY) { await page.screenshot({ path: process.argv[2] || '/dev/null' }); console.log('dry run filled; not saved'); return; }
    await L.click(page, page.getByRole('button', { name: L.rx('rfq.create.saveDraftButton') }), 2500);
    await L.ensureCursor(page);
    const send = page.getByRole('button', { name: L.rx('rfq.create.sendButton') });
    await send.waitFor({ timeout: 15000 });
    await L.click(page, send, 3500);
    await L.ensureCursor(page); await L.sleep(3000);
  } finally { if (rec) await L.stopRec(rec); }
  console.log('url', page.url());
});
