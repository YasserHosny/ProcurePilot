// Populate the Saudi demo workspace «مطاعم رواق» through the API, as the signed-in owner in the kiosk Chrome
// (CDP :9333). Idempotency keys are fixed, so a re-run returns the same rows instead of duplicating them.
// usage: PP_OWNER_GMAIL=<gmail username> NODE_PATH=<web node_modules> node setup_workspace.cjs [--guardrail-only]
// The owner signs in first; this script never touches credentials and refuses to run against any other workspace.
const { chromium } = require('@playwright/test');
const BASE = 'https://procurepilot.iron-sys.com/api/v1';
// Idempotency keys must be UUIDs: derive a stable one from a readable name (sha1-based, version nibble 5).
const uuidFor = (name) => { const h = require('crypto').createHash('sha1').update('procurepilot-sa-demo:' + name).digest('hex'); return `${h.slice(0, 8)}-${h.slice(8, 12)}-5${h.slice(13, 16)}-${((parseInt(h[16], 16) & 3) | 8).toString(16)}${h.slice(17, 20)}-${h.slice(20, 32)}`; };
const TENANT = 'مطاعم رواق';
// Supplier contact addresses are Gmail plus-aliases of the owner's mailbox, given at run time (the repo is public).
const OWNER_GMAIL = process.env.PP_OWNER_GMAIL; if (!OWNER_GMAIL) throw new Error('set PP_OWNER_GMAIL to the Gmail username that owns the supplier aliases');

const BRANCHES = [
  { key: 'olaya', name: 'فرع العليا', address: 'حي العليا، الرياض', region: 'SA' },
  { key: 'malqa', name: 'فرع الملقا', address: 'حي الملقا، الرياض', region: 'SA' },
  { key: 'tahlia', name: 'فرع التحلية', address: 'شارع التحلية، جدة', region: 'SA' },
];
const COST_CENTRES = [
  { key: 'olaya', name: 'المطبخ — العليا', code: 'KIT-OLY' },
  { key: 'malqa', name: 'المطبخ — الملقا', code: 'KIT-MLQ' },
  { key: 'tahlia', name: 'المطبخ — جدة', code: 'KIT-JED' },
];
const SUPPLIERS = [
  { key: 'dhahabi', name: 'الذهبي للتموين', payment_terms: 'الدفع خلال 30 يومًا', lead_time_days: 2 },
  { key: 'wafra', name: 'الوفرة للمواد الغذائية', payment_terms: 'الدفع خلال 30 يومًا', lead_time_days: 3 },
  { key: 'qassim', name: 'خضار القصيم الطازجة', payment_terms: 'الدفع عند الاستلام', lead_time_days: 1 },
];
// [name, base unit, pack_count, unit_size]
const PRODUCTS = [
  ['أرز بسمتي (كيس 10 كجم)', 'kilogram', 1, '10'],
  ['زيت دوار الشمس (تنكة 18 لتر)', 'litre', 1, '18'],
  ['دجاج مبرد (كرتون 10 كجم)', 'kilogram', 1, '10'],
  ['طماطم (كرتون 6 كجم)', 'kilogram', 1, '6'],
  ['بصل أحمر (كيس 20 كجم)', 'kilogram', 1, '20'],
  ['بطاطس (كيس 20 كجم)', 'kilogram', 1, '20'],
  ['خيار (كرتون 5 كجم)', 'kilogram', 1, '5'],
  ['ليمون (كرتون 5 كجم)', 'kilogram', 1, '5'],
  ['لحم غنم طازج', 'kilogram', 1, '1'],
  ['سكر أبيض (كيس 10 كجم)', 'kilogram', 1, '10'],
  ['دقيق (كيس 45 كجم)', 'kilogram', 1, '45'],
  ['حليب طويل الأجل (كرتون 12 × 1 لتر)', 'litre', 12, '1'],
  ['زبادي (كرتون 12 × 1 كجم)', 'kilogram', 12, '1'],
  ['بيض (كرتون 30 حبة)', 'each', 1, '30'],
  ['جبنة بيضاء (تنكة 16 كجم)', 'kilogram', 1, '16'],
  ['خبز صامولي (كيس 50 حبة)', 'each', 1, '50'],
  ['علب ألومنيوم للتغليف (كرتون 500 حبة)', 'each', 1, '500'],
  ['أكواب ورقية (كرتون 1000 حبة)', 'each', 1, '1000'],
  ['سائل غسيل أطباق (جالون 20 لتر)', 'litre', 1, '20'],
  ['مياه شرب (كرتون 40 × 330 مل)', 'millilitre', 40, '330'],
];

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
  if (me.tenant.name !== TENANT || me.tenant.currency !== 'SAR') throw new Error(`wrong workspace: ${me.tenant.name} ${me.tenant.currency}`);
  console.log('workspace', me.tenant.name, me.tenant.currency, me.tenant.tax_model);

  const ids = { branch: {}, cc: {}, supplier: {} };
  for (const x of BRANCHES) ids.branch[x.key] = ok(await call('POST', '/organisation/branches', { name: x.name, address: x.address, region: x.region }, `sa-branch-${x.key}`), x.name).id;
  console.log('branches', Object.keys(ids.branch).length);
  for (const x of COST_CENTRES) ids.cc[x.key] = ok(await call('POST', '/organisation/cost-centres', { name: x.name, code: x.code, branch_id: ids.branch[x.key], budget_owner_membership_id: me.membership_id }, `sa-cc-${x.key}`), x.name).id;
  console.log('cost centres', Object.keys(ids.cc).length);
  for (const x of COST_CENTRES) ok(await call('POST', '/organisation/budgets', { amount: '60000', currency: 'SAR', period: 'monthly', period_start: '2026-10-01', scope: 'cost_centre', cost_centre_id: ids.cc[x.key] }, `sa-budget-${x.key}`), 'budget ' + x.name);
  console.log('budgets 3 × SAR 60,000 monthly');
  for (const x of SUPPLIERS) ids.supplier[x.key] = ok(await call('POST', '/suppliers', { name: x.name, payment_terms: x.payment_terms, lead_time_days: x.lead_time_days, contact_email: `${OWNER_GMAIL}+pp-sa-${x.key}@gmail.com` }, `sa-supplier-${x.key}`), x.name).id;
  console.log('suppliers', Object.keys(ids.supplier).length);
  let n = 0;
  for (const [name, unit, count, size] of PRODUCTS) { ok(await call('POST', '/products', { tenant_name: name, base_unit: unit, pack: { pack_count: count, unit_size: size } }, `sa-product-${n}`), name); n++; }
  console.log('products', n);
  // /rfq/guardrails ignores Idempotency-Key, and two enabled guardrails stop auto-preparation (the orchestrator needs
  // exactly one to fire): update the existing demo guardrail instead of adding another on a re-run.
  const rule = { max_order_value_amount: '10000', max_order_value_currency: 'SAR', supplier_allowlist: Object.values(ids.supplier), min_response_count: 1, max_price_variance_pct: '0.20', default_branch_id: ids.branch.olaya, default_cost_centre_id: ids.cc.olaya, enabled: true };
  const existing = ok(await call('GET', '/rfq/guardrails'), 'list guardrails');
  if (existing.length > 1) throw new Error(`${existing.length} guardrails exist; keep one before re-running`);
  const g = existing.length ? await call('PATCH', `/rfq/guardrails/${existing[0].id}`, rule) : await call('POST', '/rfq/guardrails', rule);
  console.log(existing.length ? 'guardrail updated' : 'guardrail created', g.status, g.status < 300 ? g.body.id : JSON.stringify(g.body).slice(0, 200));
  process.exit(0);
})().catch((e) => { console.error('FAIL', e.message); process.exit(1); });
