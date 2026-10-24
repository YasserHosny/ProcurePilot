// Switch the signed-in owner's interface language from the account menu. usage: node lang.cjs <ar|en> [shot.png]
const L = require('./lib.cjs');
L.run(async () => {
  const { page } = await L.connect();
  await page.goto(L.BASE + '/savings'); await page.waitForLoadState('networkidle').catch(() => {}); await L.sleep(2000);
  const want = process.argv[2];
  if ((await page.evaluate(() => document.documentElement.lang)) === want) { console.log('already', want); return; }
  await page.locator('header button, mat-toolbar button').filter({ hasText: /^\s*YA\s*$/ }).first().click(); await L.sleep(1000);
  const items = await page.getByRole('menuitem').allInnerTexts(); console.log('menu', items);
  const target = page.getByRole('menuitem').filter({ hasText: want === 'en' ? /English|الإنجليزية|English/ : /العربية|Arabic/ }).first();
  await target.click(); await L.sleep(3000);
  console.log('lang now', await page.evaluate(() => document.documentElement.lang + ' ' + document.documentElement.dir));
  if (process.argv[3]) await page.screenshot({ path: process.argv[3] });
});
