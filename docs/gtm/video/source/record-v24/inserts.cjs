// Result inserts for the re-take: the same records in their real end state, recorded after the fact.
// usage: node inserts.cjs <quotation id> <request id>
//   s2r-authorised: quote review header with «Reviewed & Authorized» beside the title (crop to the header in the edit).
//   s4r-approved:   the web request page's Approval block showing «Approved» and the decision date.
const L = require('./lib.cjs');
L.run(async () => {
  const [quote, request] = process.argv.slice(2);
  const { page } = await L.connect();
  await page.goto(L.BASE + `/quotations/${quote}/review`); await page.waitForLoadState('networkidle').catch(() => {}); await L.sleep(2000);
  await L.hideNav(page); await L.ensureCursor(page);
  let rec = await L.startRec('s2r-authorised', page); await L.sleep(1200);
  try { await L.moveTo(page, page.getByText(L.t('quotations.review.status.reviewed')).first()); await L.sleep(3500); } finally { await L.stopRec(rec); }
  await page.goto(L.BASE + `/requests/${request}`); await page.waitForLoadState('networkidle').catch(() => {}); await L.sleep(2000);
  await L.hideNav(page); await L.ensureCursor(page);
  const block = page.getByText(L.t('requests.approval.sectionTitle'), { exact: true }).first();
  await L.scrollToEl(page, block, 380, 10);
  rec = await L.startRec('s4r-approved', page); await L.sleep(1200);
  try { await L.moveTo(page, page.getByText(L.t('requests.status.approved'), { exact: true }).last()); await L.sleep(3500); } finally { await L.stopRec(rec); }
  await page.screenshot({ path: process.argv[4] || '/dev/null' });
});
