// Beats 12–13: PO from the approved request → submit → record outcome from the PO → save outcomes.
// usage: node s5-po.cjs <total as shown in the request menu, e.g. 24,640>
// PP_DRY=1 opens "from approved request" and screenshots the menu without creating anything.
const L = require('./lib.cjs');
const DRY = process.env.PP_DRY === '1';
const TOTAL = process.argv[2];
L.run(async () => {
  const { page } = await L.connect();
  await page.goto(L.BASE + '/orders'); await page.waitForLoadState('networkidle').catch(() => {}); await L.sleep(2500);
  await L.hideNav(page); await L.ensureCursor(page);
  const rec = DRY ? null : await L.startRec('s5-po-savings', page); await L.sleep(2500);
  try {
    await L.click(page, page.getByRole('button', { name: L.t('orders.fromApprovedRequest') }), 1200);
    const item = page.getByRole('menuitem').filter({ hasText: new RegExp(TOTAL.replace(/[,٬]/g, '[,٬]')) }).first();
    if (DRY) { await page.screenshot({ path: process.argv[3] }); console.log('dry: menu items', await page.getByRole('menuitem').allInnerTexts()); return; }
    await L.click(page, item, 3500);
    await L.ensureCursor(page); await L.hideNav(page);
    await L.moveTo(page, page.getByText(L.t('orders.create.creatingFromRequest')).first()); await L.sleep(2000);
    const create = page.getByRole('button', { name: L.t('orders.create.submit') });
    await L.scrollToEl(page, create, 560, 2200); await L.sleep(1500);
    await L.click(page, create, 1000);
    for (let i = 0; i < 20 && page.url().includes('/orders/new'); i++) await L.sleep(500);
    await L.ensureCursor(page); await L.hideNav(page); await L.sleep(2000);
    await L.click(page, page.getByRole('button', { name: L.t('orders.detail.submit') }), 3000);
    await L.ensureCursor(page);
    const outcome = page.getByRole('link', { name: L.t('orders.detail.recordOutcome') }).or(page.getByRole('button', { name: L.t('orders.detail.recordOutcome') })).first();
    await L.scrollToEl(page, outcome, 500, 1500);
    await L.click(page, outcome, 3500); await L.ensureCursor(page); await L.hideNav(page); await L.sleep(3500);
    await L.click(page, page.getByRole('button', { name: L.rx('savings.fromOrder.submit') }), 4000);
    await L.ensureCursor(page); await L.sleep(3000);
  } finally { if (rec) await L.stopRec(rec); }
  console.log('done', page.url());
});
