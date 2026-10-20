// Keeps a 390x844 emulated phone tab alive and executes commands from CMD (one JSON per file write).
const { chromium } = require('@playwright/test');
const fs = require('fs'); const { spawn } = require('child_process');
const S = process.argv[2]; const CMD = S + '/phone-cmd.json', OUT = S + '/phone-out.txt';
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const CURSOR = `(() => { if (document.getElementById('__ppc')) return; const c=document.createElement('div'); c.id='__ppc';
  Object.assign(c.style,{position:'fixed',left:'195px',top:'600px',width:'34px',height:'34px',marginLeft:'-17px',marginTop:'-17px',borderRadius:'50%',background:'rgba(60,60,60,.28)',border:'2px solid rgba(255,255,255,.85)',zIndex:2147483647,pointerEvents:'none',transition:'left .6s cubic-bezier(.4,0,.2,1), top .6s cubic-bezier(.4,0,.2,1), transform .15s'}); document.documentElement.appendChild(c); })()`;
(async () => {
  const b = await chromium.connectOverCDP('http://127.0.0.1:9333');
  const ctx = b.contexts()[0];
  const page = ctx.pages().find((p) => p.url().startsWith('http://localhost:4310'));
  const cdp = await ctx.newCDPSession(page);
  await cdp.send('Emulation.setDeviceMetricsOverride', { width: 390, height: 844, deviceScaleFactor: 1, mobile: true });
  await page.bringToFront(); await page.goto(process.argv[3] || page.url()); await sleep(6000);
  let rec = null; fs.writeFileSync(OUT, 'ready\n');
  for (;;) {
    if (!fs.existsSync(CMD)) { await sleep(300); continue; }
    const cmds = JSON.parse(fs.readFileSync(CMD, 'utf8')); fs.unlinkSync(CMD);
    for (const c of cmds) {
      try {
        if (c.a === 'shot') await page.screenshot({ path: c.path });
        else if (c.a === 'tap') { await page.evaluate(CURSOR); await page.evaluate(([x, y]) => { const e = document.getElementById('__ppc'); e.style.left = x + 'px'; e.style.top = y + 'px'; }, [c.x, c.y]); await sleep(750);
          await page.evaluate(() => { const e = document.getElementById('__ppc'); e.style.transform = 'scale(.75)'; }); await page.mouse.click(c.x, c.y); await sleep(160);
          await page.evaluate(() => { const e = document.getElementById('__ppc'); e.style.transform = 'scale(1)'; }); await sleep(c.pause || 800); }
        else if (c.a === 'wait') await sleep(c.ms);
        else if (c.a === 'type') { await page.keyboard.type(c.text, { delay: c.delay || 110 }); await sleep(c.pause || 800); }
        else if (c.a === 'key') { await page.keyboard.press(c.key); await sleep(c.pause || 500); }
        else if (c.a === 'goto') { await page.goto(c.url); await sleep(c.ms || 4000); }
        else if (c.a === 'rec') { try { fs.unlinkSync(S + '/stop-phone'); } catch {} rec = spawn('python3', [S + '/screencast.py', c.file, S + '/stop-phone', '3286', '0', '390', '844'], { stdio: 'ignore' }); await sleep(1500); }
        else if (c.a === 'stop') { fs.writeFileSync(S + '/stop-phone', ''); await new Promise((r) => rec.on('exit', r)); rec = null; }
        else if (c.a === 'quit') { if (rec) { fs.writeFileSync(S + '/stop-phone', ''); } process.exit(0); }
        fs.appendFileSync(OUT, 'ok ' + c.a + '\n');
      } catch (e) { fs.appendFileSync(OUT, 'ERR ' + c.a + ' ' + e.message + '\n'); }
    }
  }
})().catch((e) => { fs.appendFileSync(OUT, 'FATAL ' + e.message + '\n'); process.exit(1); });
