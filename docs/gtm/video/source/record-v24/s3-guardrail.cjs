// Beat 10: the guardrail's draft request (banner, cost centre, total), then Submit for approval.
// usage: node s3-guardrail.cjs <request id>   PP_DRY=1 screenshots the draft without recording or submitting.
const L = require('./lib.cjs');
const DRY = process.env.PP_DRY === '1';
const REQ = process.argv[2];
L.run(async () => {
  const { page } = await L.connect();
  await page.goto(L.BASE + '/requests'); await page.waitForLoadState('networkidle').catch(() => {}); await L.sleep(2500);
  await L.hideNav(page); await L.ensureCursor(page);
  const rec = DRY ? null : await L.startRec('s3-guardrail-draft', page); await L.sleep(2500);
  try {
    const row = page.locator('tr.mat-mdc-row').filter({ hasText: REQ.slice(0, 8) }).first();
    if (await row.count()) await L.click(page, row, 3000); else { await page.goto(L.BASE + '/requests/' + REQ); await L.sleep(3000); }
    if (!page.url().includes(REQ)) { await page.goto(L.BASE + '/requests/' + REQ); await L.sleep(3000); }
    await L.hideNav(page); await L.ensureCursor(page);
    await L.moveTo(page, page.getByText(L.t('requests.autoPrepared.title')).first()); await L.sleep(4000);
    await L.moveTo(page, page.getByText('المطبخ — المعادي').first()); await L.sleep(2500);
    if (DRY) { await page.screenshot({ path: process.argv[3] }); console.log('dry: draft shown'); return; }
    const submit = page.getByRole('button', { name: L.t('requests.form.submitButton') });
    await L.scrollToEl(page, submit, 600, 1800); await L.sleep(2500);
    await L.click(page, submit, 4000);
    await L.ensureCursor(page); await L.sleep(1500);
  } finally { if (rec) await L.stopRec(rec); }
  console.log('done', page.url());
});
