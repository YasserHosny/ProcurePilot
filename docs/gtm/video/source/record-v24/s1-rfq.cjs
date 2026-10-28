// Beat 3: build one RFQ (oil 8, rice 12, onions 80) to three suppliers and send it.
// PP_DRY=1 fills the form without recording and stops before saving (rehearsal; nothing is created).
const L = require('./lib.cjs');
const W = require('./tenants.cjs');
const DRY = process.env.PP_DRY === '1';
const NEEDED = process.env.PP_NEEDED || L.neededByDate();
const TERMS = W.terms[L.LANG];
L.run(async () => {
  const { page } = await L.connect();
  await page.goto(L.BASE + '/rfq/history'); await page.waitForLoadState('networkidle').catch(() => {}); await L.sleep(1500);
  await L.hideNav(page); await L.ensureCursor(page);
  const rec = DRY ? null : await L.startRec('s1-rfq', page); await L.sleep(2000);
  try {
    await L.click(page, page.getByRole('link', { name: L.rx('rfq.history.createRfq') }).or(page.getByRole('button', { name: L.rx('rfq.history.createRfq') })).first(), 1500);
    await L.hideNav(page); await L.ensureCursor(page);
    const prods = () => page.locator('input[formcontrolname="workspace_product_id"]');
    const qtys = () => page.locator('input[formcontrolname="quantity"]');
    const lines = W.lines;
    for (let i = 0; i < lines.length; i++) {
      if (i > 0) await L.click(page, page.getByRole('button', { name: L.rx('rfq.create.addLineButton') }), 600);
      await L.type(page, prods().nth(i), lines[i][0], 60);
      await L.click(page, page.getByRole('option', { name: lines[i][0], exact: true }), 500);
      await L.type(page, qtys().nth(i), lines[i][1], 120);
    }
    await L.click(page, page.locator('mat-select[formcontrolname="supplierIds"] .mat-mdc-select-trigger'), 700);
    for (const s of W.suppliers) await L.click(page, page.getByRole('option', { name: s }), 300);
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
