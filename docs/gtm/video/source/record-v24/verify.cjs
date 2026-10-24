// Off-camera: verify every pending saving record as the owner (evidence page → Verify Saving).
const L = require('./lib.cjs');
L.run(async () => {
  const { page } = await L.connect();
  const list = JSON.parse((await L.api(page, '/savings?limit=50')).body).items.filter((x) => x.status === 'pending');
  for (const s of list) {
    await page.goto(L.BASE + '/savings/' + s.id + '/evidence'); await page.waitForLoadState('networkidle').catch(() => {}); await L.sleep(2500);
    await page.getByRole('button', { name: L.t('savings.evidence.verifyButton') }).click(); await L.sleep(3000);
    console.log('verified', s.id.slice(0, 8));
  }
});
