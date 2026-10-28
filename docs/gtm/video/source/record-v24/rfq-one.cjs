// PPS-84 re-shoot: one RFQ (the round's three lines) to the round's winner only, not filmed. It exists so the
// winner's re-sent photo quote arrives as an RFQ reply and the guardrail drafts a fresh request (beats 10–11).
// usage: node rfq-one.cjs   (PP_TENANT picks the workspace; PP_NEEDED the needed-by date)
const L = require('./lib.cjs');
const W = require('./tenants.cjs');
const NEEDED = process.env.PP_NEEDED || L.neededByDate();
L.run(async () => {
  const { page } = await L.connect();
  await page.goto(L.BASE + '/rfq/history'); await page.waitForLoadState('networkidle').catch(() => {}); await L.sleep(1500);
  await L.click(page, page.getByRole('link', { name: L.rx('rfq.history.createRfq') }).or(page.getByRole('button', { name: L.rx('rfq.history.createRfq') })).first(), 1500);
  const prods = () => page.locator('input[formcontrolname="workspace_product_id"]');
  const qtys = () => page.locator('input[formcontrolname="quantity"]');
  for (let i = 0; i < W.lines.length; i++) {
    if (i > 0) await L.click(page, page.getByRole('button', { name: L.rx('rfq.create.addLineButton') }), 600);
    await L.type(page, prods().nth(i), W.lines[i][0], 40);
    await L.click(page, page.getByRole('option', { name: W.lines[i][0], exact: true }), 500);
    await L.type(page, qtys().nth(i), W.lines[i][1], 40);
  }
  await L.click(page, page.locator('mat-select[formcontrolname="supplierIds"] .mat-mdc-select-trigger'), 700);
  await L.click(page, page.getByRole('option', { name: W.winner }), 300);
  await page.keyboard.press('Escape'); await L.sleep(600);
  await L.type(page, page.locator('input[formcontrolname="neededByDate"]'), NEEDED, 40);
  await L.type(page, page.locator('textarea[formcontrolname="tenantTerms"]'), W.terms[L.LANG], 20);
  await L.click(page, page.getByRole('button', { name: L.rx('rfq.create.saveDraftButton') }), 2500);
  const send = page.getByRole('button', { name: L.rx('rfq.create.sendButton') });
  await send.waitFor({ timeout: 15000 });
  await L.click(page, send, 4000);
  console.log('url', page.url());
});
