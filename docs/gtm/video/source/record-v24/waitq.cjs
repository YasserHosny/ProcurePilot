// Poll until N quotations are open in the review queue (or ~3 minutes pass).
const L = require('./lib.cjs');
L.run(async () => { const { page } = await L.connect(); const n = +process.argv[2];
  for (let i = 0; i < 36; i++) { const items = JSON.parse((await L.api(page, '/review-tasks?limit=20')).body).items; if (items.length >= n) { console.log('open review tasks', items.length); return; } await L.sleep(5000); }
  console.log('timed out'); });
