// Poll the latest RFQ until the guardrail converts it into a draft request; print evaluations meanwhile.
const L = require('./lib.cjs');
L.run(async () => { const { page } = await L.connect();
  for (let i = 0; i < 24; i++) {
    const rfq = JSON.parse((await L.api(page, '/rfq?limit=1')).body).items[0];
    if (rfq.converted_purchase_request_id) { console.log('converted', rfq.converted_purchase_request_id); return; }
    const resp = JSON.parse((await L.api(page, `/rfq/${rfq.id}/responses`)).body).items;
    console.log(i, resp.map((r) => r.supplier_id.slice(0, 4) + ':' + r.lines.map((l) => l.pending_match ? 'P' : 'm').join('') + ':' + JSON.stringify((r.guardrail_evaluations || []).map((g) => g.reason))).join(' | '));
    await L.sleep(5000);
  }
});
