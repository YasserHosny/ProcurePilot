// Populate a demo workspace (profiles.cjs) through the API, as the signed-in owner in the kiosk Chrome
// (CDP :9333). Idempotency keys are fixed, so a re-run returns the same rows instead of duplicating them.
// usage: PP_PROFILE=sa|sa-en|ie PP_OWNER_GMAIL=<gmail username> NODE_PATH=<web node_modules> node setup_workspace.cjs [--guardrail-only]
// The owner signs in first; this script never touches credentials and refuses to run against any other workspace.
const { chromium } = require('@playwright/test');
const BASE = 'https://procurepilot.iron-sys.com/api/v1';
// Idempotency keys must be UUIDs: derive a stable one from a readable name (sha1-based, version nibble 5).
// Profile: PP_PROFILE=sa (default) | sa-en | ie, see profiles.cjs.
const P = require('./profiles.cjs')[process.env.PP_PROFILE || 'sa'];
if (!P) throw new Error('unknown PP_PROFILE ' + process.env.PP_PROFILE);
// Idempotency keys must be UUIDs: derive a stable one from a readable name (sha1-based, version nibble 5).
const uuidFor = (name) => { const h = require('crypto').createHash('sha1').update(P.ns + ':' + name).digest('hex'); return `${h.slice(0, 8)}-${h.slice(8, 12)}-5${h.slice(13, 16)}-${((parseInt(h[16], 16) & 3) | 8).toString(16)}${h.slice(17, 20)}-${h.slice(20, 32)}`; };
// Supplier contact addresses are Gmail plus-aliases of the owner's mailbox, given at run time (the repo is public).
const OWNER_GMAIL = process.env.PP_OWNER_GMAIL; if (!OWNER_GMAIL) throw new Error('set PP_OWNER_GMAIL to the Gmail username that owns the supplier aliases');
const { tenant: TENANT, branches: BRANCHES, costCentres: COST_CENTRES, suppliers: SUPPLIERS, products: PRODUCTS } = P;

(async () => {
  const b = await chromium.connectOverCDP('http://127.0.0.1:9333');
  const page = b.contexts()[0].pages().find((p) => p.url().startsWith('https://procurepilot.iron-sys.com'));
  if (!page) throw new Error('no ProcurePilot tab in the kiosk');
  const call = (method, path, body, key) => page.evaluate(async ([m, url, bd, k]) => {
    const tok = localStorage.getItem('pp.access_token');
    const h = { Authorization: 'Bearer ' + tok, 'Content-Type': 'application/json' };
    if (k) h['Idempotency-Key'] = k;  // already a UUID
    const r = await fetch(url, { method: m, headers: h, body: bd ? JSON.stringify(bd) : undefined });
    const t = await r.text(); let j; try { j = JSON.parse(t); } catch { j = t; }
    return { status: r.status, body: j };
  }, [method, BASE + path, body, key ? uuidFor(key) : null]);
  const ok = (r, what) => { if (r.status >= 300) throw new Error(`${what}: ${r.status} ${JSON.stringify(r.body).slice(0, 300)}`); return r.body; };

  const me = ok(await call('GET', '/me'), 'me');
  if (me.tenant.name !== TENANT || me.tenant.currency !== P.currency) throw new Error(`wrong workspace: ${me.tenant.name} ${me.tenant.currency}`);
  console.log('workspace', me.tenant.name, me.tenant.currency, me.tenant.tax_model);

  const ids = { branch: {}, cc: {}, supplier: {} };
  for (const x of BRANCHES) ids.branch[x.key] = ok(await call('POST', '/organisation/branches', { name: x.name, address: x.address, region: x.region }, `sa-branch-${x.key}`), x.name).id;
  console.log('branches', Object.keys(ids.branch).length);
  for (const x of COST_CENTRES) ids.cc[x.key] = ok(await call('POST', '/organisation/cost-centres', { name: x.name, code: x.code, branch_id: ids.branch[x.key], budget_owner_membership_id: me.membership_id }, `sa-cc-${x.key}`), x.name).id;
  console.log('cost centres', Object.keys(ids.cc).length);
  for (const x of COST_CENTRES) ok(await call('POST', '/organisation/budgets', { amount: P.budget, currency: P.currency, period: 'monthly', period_start: '2026-10-01', scope: 'cost_centre', cost_centre_id: ids.cc[x.key] }, `sa-budget-${x.key}`), 'budget ' + x.name);
  console.log(`budgets 3 × ${P.currency} ${P.budget} monthly`);
  for (const x of SUPPLIERS) ids.supplier[x.key] = ok(await call('POST', '/suppliers', { name: x.name, payment_terms: x.payment_terms, lead_time_days: x.lead_time_days, contact_email: `${OWNER_GMAIL}+${P.aliasPrefix}${x.key}@gmail.com` }, `sa-supplier-${x.key}`), x.name).id;
  console.log('suppliers', Object.keys(ids.supplier).length);
  let n = 0;
  for (const [name, unit, count, size] of PRODUCTS) { ok(await call('POST', '/products', { tenant_name: name, base_unit: unit, pack: { pack_count: count, unit_size: size } }, `sa-product-${n}`), name); n++; }
  console.log('products', n);
  // /rfq/guardrails ignores Idempotency-Key, and two enabled guardrails stop auto-preparation (the orchestrator needs
  // exactly one to fire): update the existing demo guardrail instead of adding another on a re-run.
  const rule = { max_order_value_amount: P.guardrailLimit, max_order_value_currency: P.currency, supplier_allowlist: Object.values(ids.supplier), min_response_count: 1, max_price_variance_pct: '0.20', default_branch_id: ids.branch.olaya, default_cost_centre_id: ids.cc.olaya, enabled: true };
  const existing = ok(await call('GET', '/rfq/guardrails'), 'list guardrails');
  if (existing.length > 1) throw new Error(`${existing.length} guardrails exist; keep one before re-running`);
  const g = existing.length ? await call('PATCH', `/rfq/guardrails/${existing[0].id}`, rule) : await call('POST', '/rfq/guardrails', rule);
  console.log(existing.length ? 'guardrail updated' : 'guardrail created', g.status, g.status < 300 ? g.body.id : JSON.stringify(g.body).slice(0, 200));
  process.exit(0);
})().catch((e) => { console.error('FAIL', e.message); process.exit(1); });
