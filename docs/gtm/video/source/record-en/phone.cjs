// Phone scenes in the 390x844 emulated tab, captured over CDP. usage: node phone.cjs <steps.json> [recName]
const { chromium } = require('@playwright/test'); const fs = require('fs');
const S = '/tmp/claude-1000/-media-yasserhosny-My-Passport-Work-Projects-ProcurePilot/1c3520f5-a777-4834-b5ef-0684f2157c72/scratchpad';
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
(async () => {
  const steps = JSON.parse(fs.readFileSync(process.argv[2], 'utf8')); const name = process.argv[3];
  const b = await chromium.connectOverCDP('http://127.0.0.1:9333'); const ctx = b.contexts()[0];
  const page = ctx.pages().find((p) => p.url().startsWith('http://localhost:4310')); await page.bringToFront();
  const cdp = await ctx.newCDPSession(page);
  await cdp.send('Emulation.setDeviceMetricsOverride', { width: 390, height: 844, deviceScaleFactor: 1, mobile: true });
  await sleep(800);
  const tapUi = `(() => { if (document.getElementById('__ppc')) return; const c=document.createElement('div'); c.id='__ppc';
    Object.assign(c.style,{position:'fixed',left:'195px',top:'620px',width:'34px',height:'34px',marginLeft:'-17px',marginTop:'-17px',borderRadius:'50%',background:'rgba(60,60,60,.28)',border:'2px solid rgba(255,255,255,.85)',zIndex:2147483647,pointerEvents:'none',transition:'left .6s cubic-bezier(.4,0,.2,1), top .6s cubic-bezier(.4,0,.2,1), transform .15s'}); document.documentElement.appendChild(c); })()`;
  let dir, times = [];
  for (const c of steps) {
    if (c.a === 'goto') { await page.goto(c.url); await sleep(c.ms || 4000); }
    else if (c.a === 'rec') { dir = `${S}/cap/${name}`; fs.rmSync(dir, { recursive: true, force: true }); fs.mkdirSync(dir, { recursive: true });
      cdp.on('Page.screencastFrame', (f) => { const i = times.length; times.push(f.metadata.timestamp); fs.writeFileSync(`${dir}/${String(i).padStart(5, '0')}.png`, Buffer.from(f.data, 'base64')); cdp.send('Page.screencastFrameAck', { sessionId: f.sessionId }).catch(() => {}); });
      await cdp.send('Page.startScreencast', { format: 'png', maxWidth: 390, maxHeight: 844 }); await sleep(1200); }
    else if (c.a === 'tap') { await page.evaluate(tapUi); await page.evaluate(([x, y]) => { const e = document.getElementById('__ppc'); e.style.left = x + 'px'; e.style.top = y + 'px'; }, [c.x, c.y]); await sleep(700);
      await page.evaluate(() => { document.getElementById('__ppc').style.transform = 'scale(.75)'; }); await page.mouse.click(c.x, c.y); await sleep(150);
      await page.evaluate(() => { const e = document.getElementById('__ppc'); if (e) e.style.transform = 'scale(1)'; }).catch(() => {}); await sleep(c.pause || 800); }
    else if (c.a === 'type') { await page.keyboard.type(c.text, { delay: c.delay || 110 }); await sleep(c.pause || 800); }
    else if (c.a === 'key') { await page.keyboard.press(c.key); await sleep(c.pause || 500); }
    else if (c.a === 'wait') await sleep(c.ms);
    else if (c.a === 'shot') await page.screenshot({ path: c.path });
  }
  if (dir) { await cdp.send('Page.stopScreencast'); fs.writeFileSync(`${dir}/times.json`, JSON.stringify(times));
    require('child_process').execFileSync('python3', [`${S}/opening/assemble.py`, dir, `${process.env.HOME}/Videos/pp-recording/en/${name}.mp4`, `${S}/vid/lib/python3.12/site-packages/imageio_ffmpeg/binaries/ffmpeg-linux-x86_64-v7.0.2`]);
    console.log('recorded', name, times.length); }
  process.exit(0);
})();
