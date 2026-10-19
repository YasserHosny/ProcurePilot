const { chromium } = require('@playwright/test');
const { spawn } = require('child_process');
const fs = require('fs');
const S = '/tmp/claude-1000/-media-yasserhosny-My-Passport-Work-Projects-ProcurePilot/1c3520f5-a777-4834-b5ef-0684f2157c72/scratchpad';
const OUT = process.env.HOME + '/Videos/pp-recording';
const BASE = 'https://procurepilot.iron-sys.com';
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const CURSOR_JS = `(() => {
  if (document.getElementById('__ppc')) return;
  const c = document.createElement('div'); c.id = '__ppc';
  c.innerHTML = '<svg width="28" height="28" viewBox="0 0 28 28"><path d="M4 2 L4 22 L9.5 16.8 L13.2 25 L16.6 23.5 L12.9 15.6 L20.5 15.6 Z" fill="#111" stroke="#fff" stroke-width="1.6" stroke-linejoin="round"/></svg>';
  Object.assign(c.style, {position:'fixed', left:(window.__ppx??960)+'px', top:(window.__ppy??540)+'px', zIndex:2147483647, pointerEvents:'none', transition:'left .7s cubic-bezier(.4,0,.2,1), top .7s cubic-bezier(.4,0,.2,1)', filter:'drop-shadow(0 1px 2px rgba(0,0,0,.35))'});
  document.documentElement.appendChild(c);
})()`;

async function connect() {
  const b = await chromium.connectOverCDP('http://127.0.0.1:9333');
  const ctx = b.contexts()[0];
  const page = ctx.pages().find((p) => p.url().includes('procurepilot')) || ctx.pages()[0];
  await page.bringToFront();
  page.setDefaultTimeout(15000);
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
  if (!box) throw new Error('no box');
  await ensureCursor(page);
  curX = box.x + box.width / 2 - 4; curY = box.y + box.height / 2 - 2;
  await page.evaluate(([x, y]) => { const c = document.getElementById('__ppc'); c.style.left = x + 'px'; c.style.top = y + 'px'; }, [curX, curY]);
  await sleep(800);
}
async function click(page, locator, pause = 500, force = false) { console.log('click', String(locator).slice(0, 120)); await moveTo(page, locator); await locator.click({ force }); await sleep(pause); }
async function type(page, locator, text, delay = 80) { await click(page, locator, 200, true); await locator.pressSequentially(text, { delay }); await sleep(400); }

function startRec(name) {
  const stop = `${S}/stop-${name}`; try { fs.unlinkSync(stop); } catch {}
  const file = `${OUT}/${name}.mp4`;
  const p = spawn('python3', [`${S}/screencast.py`, file, stop, '3286', '0', '1920', '1080'], { stdio: 'inherit', detached: false });
  return { stop, file, p };
}
async function stopRec(r) { fs.writeFileSync(r.stop, ''); await new Promise((res) => r.p.on('exit', res)); }

module.exports = { connect, sleep, click, type, moveTo, ensureCursor, startRec, stopRec, BASE };
// Smoothly scroll the app's own scroll container (not window) so `locator` sits `offset` px from the top.
async function scrollToEl(page, locator, offset = 90, ms = 1800) {
  const h = await locator.elementHandle();
  await page.evaluate(([el, off, dur]) => new Promise((res) => {
    let sc = el.parentElement; while (sc && !(sc.scrollHeight > sc.clientHeight && /(auto|scroll)/.test(getComputedStyle(sc).overflowY))) sc = sc.parentElement;
    sc = sc || document.scrollingElement;
    const start = sc.scrollTop, target = start + el.getBoundingClientRect().top - off, t0 = performance.now();
    const step = (t) => { const k = Math.min(1, (t - t0) / dur), e = k < .5 ? 2*k*k : 1 - Math.pow(-2*k + 2, 2) / 2; sc.scrollTop = start + (target - start) * e; k < 1 ? requestAnimationFrame(step) : res(); };
    requestAnimationFrame(step);
  }), [h, offset, ms]);
  await sleep(ms + 300);
}
module.exports.scrollToEl = scrollToEl;
