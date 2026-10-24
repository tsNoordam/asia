// Static check of a Pine Script file with TradingView's in-browser Pine Editor
// analyser (no login needed). Pastes the script into the editor of a public
// chart, scrolls through every line and collects error/warning squiggles.
// A control copy with an undeclared identifier appended at the end must be
// flagged, proving the analyser ran over the whole file.
// NOTE: this is NOT a full compile; "Add to chart" / Strategy Tester need login.
// Usage: NODE_PATH=$(npm root -g) node scripts/lint_pine_tradingview.js pine/asian_range_strategy.pine
const { chromium } = require('playwright');
const fs = require('fs');
async function check(p, code) {
  await p.click('.monaco-editor .view-lines');
  await p.keyboard.press('Control+A'); await p.keyboard.press('Delete');
  await p.evaluate(t => navigator.clipboard.writeText(t), code);
  await p.keyboard.press('Control+V');
  await p.waitForTimeout(15000);
  await p.keyboard.press('Control+Home');
  const found = new Set(); let maxLine = 0;
  for (let i = 0; i < 20; i++) {
    await p.waitForTimeout(1500);
    const r = await p.evaluate(() => {
      const nums = Array.from(document.querySelectorAll('.line-numbers')).map(e => parseInt(e.innerText)).filter(n => !isNaN(n));
      const sq = Array.from(document.querySelectorAll('.squiggly-error, .squiggly-warning')).map(e => e.className + '@' + e.parentElement.style.top + '|' + e.style.top);
      return { lo: Math.min(...nums), hi: Math.max(...nums), sq };
    });
    r.sq.forEach(s => found.add(r.lo + '-' + r.hi + ':' + s));
    maxLine = Math.max(maxLine, r.hi);
    for (let k = 0; k < 30; k++) await p.keyboard.press('ArrowDown');
  }
  return { maxLineSeen: maxLine, markers: Array.from(found) };
}
(async () => {
  const b = await chromium.launch();
  const ctx = await b.newContext({ viewport: { width: 1700, height: 1050 }, permissions: ['clipboard-read','clipboard-write'] });
  const p = await ctx.newPage();
  await p.goto('https://www.tradingview.com/chart/?symbol=CME_MINI%3ANQ1%21&interval=1', { waitUntil: 'domcontentloaded', timeout: 60000 });
  await p.waitForTimeout(8000);
  await p.click('[data-name="pine-dialog-button"]');
  await p.waitForTimeout(6000);
  const code = fs.readFileSync(process.argv[2], 'utf8');
  console.log('control (error appended at end):', JSON.stringify(await check(p, code + '\nplot(undeclaredZ)\n')));
  console.log('strategy as-is:', JSON.stringify(await check(p, code)));
  await b.close();
})();
