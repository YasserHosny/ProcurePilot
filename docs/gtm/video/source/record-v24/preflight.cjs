// Read-only state check before a round: who is signed in, interface language, guardrails, open
// low-stock reports, recent RFQs and requests. Prints summaries only.
const L = require('./lib.cjs');
L.run(async () => {
  const { page } = await L.connect();
  const j = async (p) => { const r = await L.api(page, p); try { return [r.status, JSON.parse(r.body)]; } catch { return [r.status, r.body.slice(0, 200)]; } };
  const [s1, me] = await j('/me');
  console.log('me', s1, me && { role: me.role, locale: me.locale || me.preferred_locale || me.language, tenant: me.tenant_name || me.workspace_name });
  const [s2, g] = await j('/rfq/guardrails');
  console.log('guardrails', s2, JSON.stringify(g).slice(0, 600));
  const [s3, ls] = await j('/low-stock-reports?limit=5');
  console.log('low-stock', s3, JSON.stringify(ls).slice(0, 500));
  const [s4, rq] = await j('/rfq?limit=3');
  console.log('rfqs', s4, JSON.stringify(rq).slice(0, 500));
  const [s5, req] = await j('/requests?limit=3');
  console.log('requests', s5, JSON.stringify(req).slice(0, 500));
  console.log('url', page.url(), 'lang attr', await page.evaluate(() => document.documentElement.lang + ' ' + document.documentElement.dir));
});
