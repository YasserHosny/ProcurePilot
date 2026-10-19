const L = require('./lib.cjs');
(async () => { const { b } = await L.connect(); const pg = b.contexts()[0].pages().find((p) => p.url().includes('procurepilot.iron-sys.com')); pg.setDefaultTimeout(10000);
  pg.on('response', (r) => { if (r.request().method() !== 'GET' && r.url().includes('/api/v1/sav')) console.log('API', r.request().method(), r.status(), r.url().split('/api/v1')[1]); });
  for (let i = 0; i < 6; i++) {
    await pg.goto(L.BASE + '/savings'); await pg.getByText('زيت عباد الشمس').first().waitFor(); await L.sleep(1200);
    const pending = pg.locator('tr, .mat-mdc-row').filter({ hasText: 'قيد التحقق' });
    if (!(await pending.count())) break;
    const row = pending.first(); const b2 = row.getByRole('button', { name: /عرض الأدلة/ }).or(row.getByRole('link', { name: /عرض الأدلة/ }));
    await b2.first().click(); await L.sleep(2500);
    await pg.getByRole('button', { name: /اعتماد الوفر/ }).click(); await L.sleep(1500);
    const dlg = pg.locator('mat-dialog-container button, .mat-mdc-dialog-container button').filter({ hasText: /اعتماد|تأكيد/ });
    if (await dlg.count()) { await dlg.last().click(); await L.sleep(2500); }
    console.log('verified', i + 1, pg.url());
  }
})().catch(e => console.error('FAIL', e.message)).finally(() => process.exit(0));
