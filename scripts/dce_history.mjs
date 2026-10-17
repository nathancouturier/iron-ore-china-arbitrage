// Download the Dalian Commodity Exchange annual historical quote files
// (one file per variety and year) for iron ore (i), coke (j) and coking coal (jm).
//
// The DCE website answers plain HTTP clients with an HTTP 412 JavaScript
// challenge, so the files are fetched from inside a headless Chromium page
// that has passed the challenge. Usage:
//   node scripts/dce_history.mjs <output_dir>
// Writes the files and an index.json listing variety, source URL and path.
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

const PAGE = 'http://www.dce.com.cn/dalianshangpin/xqsj/lssj/index.html';
const NAMES = { '铁矿石': 'i', '焦炭': 'j', '焦煤': 'jm' };
const outDir = process.argv[2] || 'data/raw/dce/annual';
fs.mkdirSync(outDir, { recursive: true });

const { chromium } = await loadPlaywright();
const launch = { args: ['--disable-blink-features=AutomationControlled'] };
if (process.env.HTTPS_PROXY) launch.proxy = { server: process.env.HTTPS_PROXY, bypass: 'www.dce.com.cn' };
if (process.env.CHROMIUM_PATH) launch.executablePath = process.env.CHROMIUM_PATH;
const browser = await chromium.launch(launch);
const ctx = await browser.newContext({
  userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36',
  locale: 'zh-CN',
});
const page = await ctx.newPage();

let html = '';
for (let attempt = 0; attempt < 4 && html.length < 5000; attempt++) {
  await page.goto(PAGE, { waitUntil: 'networkidle', timeout: 90000 });
  await page.waitForTimeout(4000 + attempt * 4000);
  html = await page.content();
}
if (html.length < 5000) {
  console.error('DCE history page did not render');
  await browser.close();
  process.exit(2);
}

const re = /rel="([^"]+)">([^<]+)</g;
const items = [];
for (const m of html.matchAll(re)) {
  const v = NAMES[m[2].trim()];
  if (v && !items.some((x) => x.url === m[1])) items.push({ variety: v, url: m[1] });
}

const index = [];
for (const it of items) {
  const name = it.url.replaceAll('/', '_').replace(/^_+/, '');
  const dest = path.join(outDir, name);
  if (fs.existsSync(dest) && fs.statSync(dest).size > 0) {
    index.push({ ...it, path: dest, cached: true });
    continue;
  }
  const b64 = await page.evaluate(async (u) => {
    const r = await fetch(u, { credentials: 'include' });
    if (!r.ok) return 'ERR' + r.status;
    const buf = new Uint8Array(await r.arrayBuffer());
    let s = '';
    for (let i = 0; i < buf.length; i += 0x8000) s += String.fromCharCode.apply(null, buf.subarray(i, i + 0x8000));
    return btoa(s);
  }, it.url);
  if (b64.startsWith('ERR')) {
    console.error('failed', it.url, b64);
    continue;
  }
  fs.writeFileSync(dest, Buffer.from(b64, 'base64'));
  index.push({ ...it, path: dest, cached: false });
  console.log('saved', it.variety, it.url);
  await page.waitForTimeout(1500);
}
fs.writeFileSync(path.join(outDir, 'index.json'), JSON.stringify(index, null, 1));
await browser.close();
console.log('files', index.length);
