// Full-page screenshots of every view at desktop and phone widths, with the
// browser console checked for errors. Usage:
//   node scripts/screenshots.mjs <base_url> <output_dir> [--drawers]
// --drawers also opens the Method, Assumptions and Data drawers in turn.
import fs from 'node:fs';
import path from 'node:path';

async function loadPlaywright() {
  const candidates = ['playwright', process.env.PLAYWRIGHT_MODULE, '/opt/node22/lib/node_modules/playwright/index.mjs'];
  for (const c of candidates) {
    if (!c) continue;
    try { return await import(c); } catch { /* try next */ }
  }
  throw new Error('playwright module not found');
}

const base = process.argv[2] || 'http://127.0.0.1:8000/';
const out = process.argv[3] || 'screenshots';
const drawers = process.argv.includes('--drawers');
const views = ['overview', 'window', 'freight', 'mill', 'calculator', 'method', 'downloads'];
const widths = [[1440, 900], [390, 844]];
fs.mkdirSync(out, { recursive: true });

const { chromium } = await loadPlaywright();
const browser = await chromium.launch();
const problems = [];
for (const [w, h] of widths) {
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, deviceScaleFactor: 1 });
  const page = await ctx.newPage();
  page.on('console', (m) => { if (m.type() === 'error') problems.push(`${w}px console: ${m.text()}`); });
  page.on('pageerror', (e) => problems.push(`${w}px page error: ${e.message}`));
  page.on('requestfailed', (r) => problems.push(`${w}px request failed: ${r.url()}`));
  for (const v of views) {
    await page.goto(`${base}#${v}`, { waitUntil: 'networkidle' });
    await page.waitForTimeout(1200);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    if (overflow > 0) problems.push(`${w}px ${v}: horizontal overflow ${overflow}px`);
    await page.screenshot({ path: path.join(out, `${v}-${w}.png`), fullPage: true });
    if (drawers) {
      const buttons = await page.$$(`#view-${v} .toggles .btn`);
      for (const b of buttons) {
        const label = (await b.textContent()).trim().toLowerCase();
        await b.click();
        await page.waitForTimeout(500);
        const ov = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
        if (ov > 0) problems.push(`${w}px ${v} ${label}: horizontal overflow ${ov}px`);
        await page.screenshot({ path: path.join(out, `${v}-${w}-${label}.png`), fullPage: true });
      }
    }
  }
  await ctx.close();
}
await browser.close();
if (problems.length) {
  console.log(problems.join('\n'));
  process.exitCode = 1;
} else {
  console.log(`Screenshots written to ${out}; no console errors, failed requests or horizontal overflow.`);
}
