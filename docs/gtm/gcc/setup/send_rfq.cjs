// Create and send one RFQ in «مطاعم رواق» through the API as the signed-in owner (off-camera rounds only).
// usage: node send_rfq.cjs <round tag> <needed-by YYYY-MM-DD>   (oil ×10, basmati ×30, tomatoes ×20 to the 3 suppliers)
const { chromium } = require('@playwright/test'); const crypto = require('crypto');
const uuidFor = (n) => { const h = crypto.createHash('sha1').update('procurepilot-sa-demo:' + n).digest('hex'); return `${h.slice(0, 8)}-${h.slice(8, 12)}-5${h.slice(13, 16)}-${((parseInt(h[16], 16) & 3) | 8).toString(16)}${h.slice(17, 20)}-${h.slice(20, 32)}`; };
const LINES = [['زيت دوار الشمس (تنكة 18 لتر)', 10], ['أرز بسمتي (كيس 10 كجم)', 30], ['طماطم (كرتون 6 كجم)', 20]];
(async () => {
  const [tag, needed] = process.argv.slice(2);
  const b = await chromium.connectOverCDP('http://127.0.0.1:9333');
  const page = b.contexts()[0].pages().find((p) => p.url().startsWith('https://procurepilot.iron-sys.com'));
  const call = (m, path, body, key) => page.evaluate(async ([m, url, bd, k]) => {
    const h = { Authorization: 'Bearer ' + localStorage.getItem('pp.access_token'), 'Content-Type': 'application/json' }; if (k) h['Idempotency-Key'] = k;
    const r = await fetch(url, { method: m, headers: h, body: bd ? JSON.stringify(bd) : undefined }); const t = await r.text(); let j; try { j = JSON.parse(t); } catch { j = t; } return { status: r.status, body: j };
  }, [m, 'https://procurepilot.iron-sys.com/api/v1' + path, body, key]);
  const me = (await call('GET', '/me')).body; if (me.tenant.name !== 'مطاعم رواق') throw new Error('wrong workspace ' + me.tenant.name);
  const products = (await call('GET', '/products?limit=100')).body.items; const suppliers = (await call('GET', '/suppliers?limit=100')).body.items;
  const lines = LINES.map(([n, q]) => { const p = products.find((x) => x.tenant_name === n); if (!p) throw new Error('missing product ' + n); return { workspace_product_id: p.id, quantity: String(q) }; });
  const created = await call('POST', '/rfq', { lines, recipient_supplier_ids: suppliers.map((s) => s.id), needed_by_date: needed, tenant_terms: 'التوريد لفرع العليا. الدفع خلال 30 يومًا من الاستلام. الأسعار شاملة ضريبة القيمة المضافة 15%.' }, uuidFor('rfq-' + tag));
  if (created.status >= 300) throw new Error('create ' + created.status + ' ' + JSON.stringify(created.body).slice(0, 300));
  const id = created.body.rfq.id; console.log('rfq', id, 'recipients', created.body.recipients.length, 'rejected', created.body.rejected_recipients.length);
  const sent = await call('POST', `/rfq/${id}/send`, {}, uuidFor('rfq-send-' + tag));
  console.log('send', sent.status, JSON.stringify(sent.body).slice(0, 200)); process.exit(0);
})().catch((e) => { console.error('FAIL', e.message); process.exit(1); });
