const L = require('./lib.cjs');
const REQ = '36722942-aba7-4f57-bc79-abb6fd80759e';
const hideNav = async (page) => { if (await page.locator('.mat-drawer-opened').count()) { await page.getByRole('button', { name: 'Toggle navigation' }).click(); await L.sleep(800); } };
(async () => {
  const { b, page } = await L.connect();
  const web = b.contexts()[0].pages().find((p) => p.url().includes('procurepilot.iron-sys.com')); await web.bringToFront();
  const pg = web; pg.setDefaultTimeout(15000);
  await pg.goto(L.BASE + '/orders'); await L.sleep(3000); await hideNav(pg); await L.ensureCursor(pg);
  const rec = await L.startRec('s5-po-savings', page); await L.sleep(2500);
  try {
    await L.click(pg, pg.getByRole('button', { name: 'From approved request' }), 1200);
    await L.click(pg, pg.getByRole('menuitem').filter({ hasText: /24,940/ }).first(), 3500);
    await L.ensureCursor(pg); await hideNav(pg);
    await L.moveTo(pg, pg.getByText('Creating from Request').first()); await L.sleep(2000);
    const create = pg.getByRole('button', { name: 'Create Purchase Order' });
    await L.scrollToEl(pg, create, 560, 2200); await L.sleep(1500);
    await L.click(pg, create, 1000);
    for (let i = 0; i < 20 && pg.url().includes('/orders/new'); i++) await L.sleep(500);
    if (pg.url().includes('/orders/new')) { await pg.goto(L.BASE + '/orders'); await L.sleep(2500); await L.click(pg, pg.getByRole('link', { name: /Open order PO-000007/ }), 3000); }
    await L.ensureCursor(pg); await hideNav(pg); await L.sleep(2000);
    await L.click(pg, pg.getByRole('button', { name: 'Submit order' }), 3000);
    await L.ensureCursor(pg);
    const rec2 = pg.getByRole('link', { name: 'Record outcome' });
    await L.scrollToEl(pg, rec2, 500, 1500);
    await L.click(pg, rec2, 3500); await L.ensureCursor(pg); await hideNav(pg); await L.sleep(3500);
    await L.click(pg, pg.getByRole('button', { name: /Save 3 outcomes/ }), 4000);
    await L.ensureCursor(pg);
    // closing shot: savings ledger with the sidebar back on
    if (!(await pg.locator('.mat-drawer-opened').count())) { await L.click(pg, pg.getByRole('button', { name: 'Toggle navigation' }), 1200); }
    await L.moveTo(pg, pg.getByText('Savings Ledger').first()); await L.sleep(6000);
  } finally { await L.stopRec(rec); }
  console.log('done', pg.url());
})().then(() => process.exit(0)).catch((e) => { console.error('FAIL', e.message); process.exit(1); });
