// Read-only round status: the latest RFQ's responses, recent quotations, and requests created today.
const L = require('./lib.cjs');
L.run(async () => {
  const { page } = await L.connect();
  const j = async (p) => { const r = await L.api(page, p); try { return JSON.parse(r.body); } catch { return { status: r.status, raw: r.body.slice(0, 200) }; } };
  const rfq = (await j('/rfq?limit=1')).items[0];
  console.log('rfq', rfq.id.slice(0, 8), rfq.status, 'responses', rfq.response_count, 'converted', rfq.converted_purchase_request_id);
  const q = await j('/quotations?limit=5');
  for (const x of (q.items || [])) console.log('quote', x.id.slice(0, 8), x.status, x.supplier_name || x.supplier_id, x.total_amount || x.total, x.currency, x.created_at);
  const sv = await j('/savings?limit=6');
  for (const x of (sv.items || [])) console.log('saving', x.id.slice(0, 8), x.status, JSON.stringify(x.saving || x.saving_amount || x.realised_saving || ''), x.created_at);
  const req = await j('/requests?limit=3');
  for (const x of (req.items || [])) console.log('request', x.id.slice(0, 8), x.status, x.estimated_total_amount || x.estimated_total, x.auto_prepared ? 'auto:' + x.auto_prepared.supplier_name : '', x.created_at);
});
