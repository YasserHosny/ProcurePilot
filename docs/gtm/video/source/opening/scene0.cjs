// Opening "chaos" clip: a live recording of supplier quotes arriving on WhatsApp and being copied into Excel by hand.
// usage: node scene0.cjs desktop|mobile
const { chromium } = require('@playwright/test');
const { spawn } = require('child_process'); const fs = require('fs');
const S = '/tmp/claude-1000/-media-yasserhosny-My-Passport-Work-Projects-ProcurePilot/1c3520f5-a777-4834-b5ef-0684f2157c72/scratchpad', O = '/tmp/claude-1000/-media-yasserhosny-My-Passport-Work-Projects-ProcurePilot/1c3520f5-a777-4834-b5ef-0684f2157c72/scratchpad/opening', OUT = process.env.HOME + '/Videos/pp-recording';
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const MOBILE = process.argv[2] === 'mobile'; const W = MOBILE ? 480 : 1920, H = MOBILE ? 1040 : 1080;
(async () => {
  const b = await chromium.connectOverCDP('http://127.0.0.1:9333'); const ctx = b.contexts()[0];
  const page = await ctx.newPage(); page.setDefaultTimeout(15000);
  const cdp = await ctx.newCDPSession(page);
  await cdp.send('Emulation.setDeviceMetricsOverride', { width: W, height: H, deviceScaleFactor: 1, mobile: MOBILE });
  await page.goto('file://' + O + '/DesktopChaos.html' + (MOBILE ? '#m' : '')); await page.evaluate(() => document.fonts.ready);
  await page.bringToFront(); await sleep(1500);
  // drawn pointer (desktop) or tap circle (mobile), same look as the app scenes
  await page.evaluate((m) => { const c = document.createElement('div'); c.id = '__ppc';
    if (m) Object.assign(c.style, {width:'34px',height:'34px',marginLeft:'-17px',marginTop:'-17px',borderRadius:'50%',background:'rgba(60,60,60,.28)',border:'2px solid rgba(255,255,255,.85)'});
    else c.innerHTML = '<svg width="28" height="28" viewBox="0 0 28 28"><path d="M4 2 L4 22 L9.5 16.8 L13.2 25 L16.6 23.5 L12.9 15.6 L20.5 15.6 Z" fill="#111" stroke="#fff" stroke-width="1.6" stroke-linejoin="round"/></svg>';
    Object.assign(c.style, {position:'fixed',left:(m?240:1100)+'px',top:(m?700:600)+'px',zIndex:2147483647,pointerEvents:'none',transition:'left .6s cubic-bezier(.4,0,.2,1), top .6s cubic-bezier(.4,0,.2,1)'});
    document.documentElement.appendChild(c); }, MOBILE);
  const move = async (sel) => { const bx = await page.locator(sel).first().boundingBox(); const x = bx.x + bx.width / 2, y = bx.y + bx.height / 2;
    await page.evaluate(([x, y]) => { const c = document.getElementById('__ppc'); c.style.left = x + 'px'; c.style.top = y + 'px'; }, [x - (MOBILE ? 0 : 4), y - (MOBILE ? 0 : 2)]); await sleep(650); return [x, y]; };
  const click = async (sel, pause = 400) => { const [x, y] = await move(sel); await page.mouse.click(x, y); await sleep(pause); };
  const arrive = (k, m, t) => page.evaluate(([k, m, t]) => window.arrive(k, m, t), [k, m, t]);
  // Tab-level capture (CDP screencast): independent of which screen the kiosk window is on.
  const dir = O + '/cap-' + (MOBILE ? 'mobile' : 'desktop'); fs.rmSync(dir, { recursive: true, force: true }); fs.mkdirSync(dir);
  const frames = [];
  cdp.on('Page.screencastFrame', async (f) => { const i = frames.length; frames.push(f.metadata.timestamp);
    fs.writeFileSync(dir + '/' + String(i).padStart(5, '0') + '.png', Buffer.from(f.data, 'base64'));
    cdp.send('Page.screencastFrameAck', { sessionId: f.sessionId }).catch(() => {}); });
  await cdp.send('Page.startScreencast', { format: 'png', maxWidth: W, maxHeight: H, everyNthFrame: 1 });
  await sleep(1500);
  try {
    await arrive('amana', '📷 صورة', '9:41'); await sleep(450);
    await arrive('sayed', 'البصل بـ ١٧ النهارده', '9:41'); await sleep(450);
    await arrive('maadi', 'الزيت خلص… هنطلب إمتى؟', '9:42'); await sleep(450);
    await arrive('nour', 'السعر اتغير، كلمني', '9:42'); await sleep(500);
    await click('#it-amana', 1300);
    await click('#qimg', 1300); await click('#lb', 500);
    if (MOBILE) await page.evaluate(() => { document.body.classList.remove('chat'); showSheet(true); }), await sleep(500);
    else await click('#icxl', 500);
    const cell = (r, c) => '#t tr:nth-child(' + r + ') td:nth-child(' + c + ')';
    const put = async (r, c, txt, d = 70) => { await click(cell(r, c), 150); await page.keyboard.type(txt, { delay: d }); };
    await put(2, 2, 'النور'); await put(2, 3, 'زيت عباد'); await put(2, 4, '1635');
    await put(3, 2, 'الأمانة'); await put(3, 3, 'زيت عباد'); await put(3, 4, '1610');
    await put(4, 2, 'الأمانة'); await put(4, 3, 'أرز'); await put(4, 4, '9l0'); await sleep(500);
    await page.keyboard.press('Backspace', { delay: 90 }); await page.keyboard.press('Backspace'); await page.keyboard.type('10', { delay: 90 });
    await sleep(400); await arrive('sayed', 'آخر سعر للبصل ١٦٫٥٠', '9:43');
    if (MOBILE) await page.evaluate(() => showSheet(false)), await sleep(900);
    else { await click('#icwa', 900); }
  } finally {
    await sleep(300); await cdp.send('Page.stopScreencast');
    fs.writeFileSync(dir + '/times.json', JSON.stringify(frames));
    await page.close(); console.log('frames', frames.length); process.exit(0);
  }
})();
