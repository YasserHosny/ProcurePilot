// Recorder for v2.4 (rounds 6 and 7). One script set for both interfaces: PP_LANG=ar|en picks the
// labels from packages/i18n, so the scenes never hard-code UI copy. Paths come from the environment:
//   PP_LANG      ar (round 6) | en (round 7)
//   PP_OUT       output folder for the assembled clips (default ~/Videos/pp-recording/v24/<lang>)
//   PP_CAP       frame scratch folder (default <PP_OUT>/.cap)
//   PP_FFMPEG    an ffmpeg 7 binary (e.g. imageio-ffmpeg's)
// Capture is by tab over CDP (independent of which screen the kiosk window is on); frames are assembled
// to 30 fps by ../opening/assemble.py when recording stops.
const { chromium } = require('@playwright/test');
const fs = require('fs');
const path = require('path');

const LANG = process.env.PP_LANG || 'ar';
const OUT = process.env.PP_OUT || path.join(process.env.HOME, 'Videos/pp-recording/v24', LANG);
const CAP = process.env.PP_CAP || path.join(OUT, '.cap');
const FFMPEG = process.env.PP_FFMPEG;
const BASE = 'https://procurepilot.iron-sys.com';
const REPO = path.resolve(__dirname, '../../../../..');
const ASSEMBLE = path.join(__dirname, '../opening/assemble.py');
const I18N = JSON.parse(fs.readFileSync(path.join(REPO, `packages/i18n/${LANG}.json`), 'utf8'));
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// t('rfq.create.sendButton') -> the label in the recording language; {{x}} placeholders become `vars`.
function t(key, vars = {}) {
  let v = key.split('.').reduce((o, k) => (o && typeof o === 'object' ? o[k] : undefined), I18N);
  if (typeof v !== 'string') throw new Error(`i18n key missing for ${LANG}: ${key}`);
  for (const [k, x] of Object.entries(vars)) v = v.replaceAll(`{{${k}}}`, x);
  return v;
}
// Exact-text regex from a label, for getByRole names; a label with a {{placeholder}} matches its prefix.
function rx(key) {
  const v = key.split('.').reduce((o, k) => (o && typeof o === 'object' ? o[k] : undefined), I18N);
  if (typeof v !== 'string') throw new Error(`i18n key missing for ${LANG}: ${key}`);
  const head = v.split('{{')[0].trim().replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  return new RegExp(head);
}

const CURSOR_JS = `(() => {
  if (document.getElementById('__ppc')) return;
  const c = document.createElement('div'); c.id = '__ppc';
  c.innerHTML = '<svg width="28" height="28" viewBox="0 0 28 28"><path d="M4 2 L4 22 L9.5 16.8 L13.2 25 L16.6 23.5 L12.9 15.6 L20.5 15.6 Z" fill="#0B2545" stroke="#fff" stroke-width="1.6" stroke-linejoin="round"/></svg>';
  Object.assign(c.style, {position:'fixed', left:(window.__ppx??960)+'px', top:(window.__ppy??540)+'px', zIndex:2147483647, pointerEvents:'none', transition:'left .7s cubic-bezier(.4,0,.2,1), top .7s cubic-bezier(.4,0,.2,1)', filter:'drop-shadow(0 1px 2px rgba(0,0,0,.35))'});
  document.documentElement.appendChild(c);
})()`;

async function connect() {
  const b = await chromium.connectOverCDP('http://127.0.0.1:9333');
  const ctx = b.contexts()[0];
  const page = ctx.pages().find((p) => p.url().startsWith(BASE));
  if (!page) throw new Error('no ProcurePilot tab in the kiosk window');
  const cdp = await ctx.newCDPSession(page);
  await cdp.send('Emulation.setDeviceMetricsOverride', { width: 1920, height: 1080, deviceScaleFactor: 1, mobile: false });
  await page.bringToFront();
  page.setDefaultTimeout(15000);
  if (process.env.PP_TENANT) {  // never film the wrong workspace
    const want = require('./tenants.cjs').name;
    const me = await page.evaluate(async () => (await fetch('https://procurepilot.iron-sys.com/api/v1/me', { headers: { Authorization: 'Bearer ' + localStorage.getItem('pp.access_token') } })).json()).catch((e) => { console.error('workspace check failed:', e.message.slice(0, 200)); return null; });
    if (!me || !me.tenant || me.tenant.name !== want) throw new Error(`signed-in workspace is ${me && me.tenant ? me.tenant.name : 'unknown'}, expected ${want}`);
  }
  return { b, page };
}

let curX = 960, curY = 540;
async function ensureCursor(page) {
  await page.evaluate(([x, y]) => { window.__ppx = x; window.__ppy = y; }, [curX, curY]).catch(() => {});
  await page.evaluate(CURSOR_JS).catch(() => {});
}
async function moveTo(page, locator) {
  await locator.scrollIntoViewIfNeeded();
  const box = await locator.boundingBox();
  if (!box) throw new Error('no box for ' + String(locator).slice(0, 100));
  await ensureCursor(page);
  curX = box.x + box.width / 2 - 4; curY = box.y + box.height / 2 - 2;
  await page.evaluate(([x, y]) => { const c = document.getElementById('__ppc'); c.style.left = x + 'px'; c.style.top = y + 'px'; }, [curX, curY]);
  await sleep(800);
}
async function click(page, locator, pause = 500, force = false) { console.log('click', String(locator).slice(0, 120)); await moveTo(page, locator); await locator.click({ force }); await sleep(pause); }
async function type(page, locator, text, delay = 80) { await click(page, locator, 200, true); await locator.pressSequentially(text, { delay }); await sleep(400); }

async function hideNav(page) {
  if (await page.locator('.mat-drawer-opened').count()) { await page.getByRole('button', { name: t('shell.toggleNav') }).click(); await sleep(800); }
}
async function showNav(page) {
  if (!(await page.locator('.mat-drawer-opened').count())) { await page.getByRole('button', { name: t('shell.toggleNav') }).click(); await sleep(1000); }
}

async function startRec(name, page) {
  const dir = path.join(CAP, name); fs.rmSync(dir, { recursive: true, force: true }); fs.mkdirSync(dir, { recursive: true });
  const cdp = await page.context().newCDPSession(page); const times = [];
  cdp.on('Page.screencastFrame', (f) => { const i = times.length; times.push(f.metadata.timestamp);
    fs.writeFileSync(`${dir}/${String(i).padStart(5, '0')}.png`, Buffer.from(f.data, 'base64'));
    cdp.send('Page.screencastFrameAck', { sessionId: f.sessionId }).catch(() => {}); });
  const vp = page.viewportSize() || { width: 1920, height: 1080 };
  await cdp.send('Page.startScreencast', { format: 'png', maxWidth: vp.width, maxHeight: vp.height, everyNthFrame: 1 });
  return { name, dir, cdp, times };
}
async function stopRec(r) {
  await sleep(300); await r.cdp.send('Page.stopScreencast').catch(() => {});
  fs.writeFileSync(`${r.dir}/times.json`, JSON.stringify(r.times));
  if (!r.times.length) throw new Error('no frames captured for ' + r.name);
  fs.mkdirSync(OUT, { recursive: true });
  if (!FFMPEG) throw new Error('set PP_FFMPEG');
  require('child_process').execFileSync('python3', [ASSEMBLE, r.dir, path.join(OUT, `${r.name}.mp4`), FFMPEG]);
  console.log('recorded', r.name, r.times.length, 'frames');
}

// Smoothly scroll the app's own scroll container (not window) so `locator` sits `offset` px from the top.
async function scrollToEl(page, locator, offset = 90, ms = 1800) {
  const h = await locator.elementHandle();
  await page.evaluate(([el, off, dur]) => new Promise((res) => {
    let sc = el.parentElement; while (sc && !(sc.scrollHeight > sc.clientHeight && /(auto|scroll)/.test(getComputedStyle(sc).overflowY))) sc = sc.parentElement;
    sc = sc || document.scrollingElement;
    const start = sc.scrollTop, target = start + el.getBoundingClientRect().top - off, t0 = performance.now();
    const step = (tt) => { const k = Math.min(1, (tt - t0) / dur), e = k < .5 ? 2*k*k : 1 - Math.pow(-2*k + 2, 2) / 2; sc.scrollTop = start + (target - start) * e; k < 1 ? requestAnimationFrame(step) : res(); };
    requestAnimationFrame(step);
  }), [h, offset, ms]);
  await sleep(ms + 300);
}

// Read-only API call from the signed-in tab (same session the UI uses). Never logs the token.
async function api(page, p) {
  return page.evaluate(async (url) => {
    const keys = Object.keys(localStorage); let tok = null;
    for (const k of keys) { const v = localStorage.getItem(k) || ''; const m = v.match(/eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+/); if (m) { tok = m[0]; break; } }
    const r = await fetch(url, { headers: tok ? { Authorization: 'Bearer ' + tok } : {} });
    return { status: r.status, body: await r.text() };
  }, BASE + '/api/v1' + p);
}

const run = (fn) => fn().then(() => process.exit(0)).catch((e) => { console.error('FAIL', e.message); process.exit(1); });

module.exports = { LANG, BASE, OUT, t, rx, connect, sleep, click, type, moveTo, ensureCursor, hideNav, showNav, startRec, stopRec, scrollToEl, api, run };
