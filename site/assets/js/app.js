// App shell: hash routing between views, lazy data loading, shared UI pieces.
import { readTokens, fmtDate, resizeAll, loadECharts } from './charts.js';

const VIEWS = ['overview', 'window', 'freight', 'mill', 'calculator', 'method', 'downloads'];
const loaders = {
  overview: () => import('./views/overview.js'),
  window: () => import('./views/window.js'),
  freight: () => import('./views/freight.js'),
  mill: () => import('./views/mill.js'),
  calculator: () => import('./views/calculator.js'),
  method: () => import('./views/method.js'),
  downloads: () => import('./views/downloads.js'),
};
const rendered = new Set();
const cache = new Map();

export async function getJSON(name) {
  if (!cache.has(name)) {
    cache.set(name, fetch(`data/${name}.json`, { cache: 'no-cache' }).then((r) => {
      if (!r.ok) throw new Error(`${name}: HTTP ${r.status}`);
      return r.json();
    }));
  }
  return cache.get(name);
}

/** Element helper: el('p', {class: 'x'}, 'text', child, ...). Text is set with textContent. */
export function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === 'class') node.className = v;
    else if (k === 'html') node.innerHTML = v;
    else if (k.startsWith('on')) node.addEventListener(k.slice(2), v);
    else node.setAttribute(k, v === true ? '' : v);
  }
  for (const c of children.flat()) {
    if (c === null || c === undefined || c === false) continue;
    node.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return node;
}

/** A chart block: title (the takeaway), subtitle with units, chart host, source line, hidden text summary. */
export function chartBlock({ title, sub, source, summary, cls = 'chart' }) {
  const host = el('div', { class: cls, role: 'img', 'aria-label': `${title}. ${summary || ''}` });
  const block = el(
    'div',
    { class: 'panel' },
    el('h3', { class: 'chart-title' }, title),
    sub ? el('p', { class: 'chart-sub' }, sub) : null,
    host,
    source ? el('p', { class: 'source' }, source) : null,
    summary ? el('p', { class: 'summary' }, summary) : null,
  );
  return { block, host };
}

/** Method / Assumptions / Data toggles, each opening a drawer in place. */
export function toggles(id, sections) {
  const bar = el('div', { class: 'toggles' });
  const drawers = el('div');
  const buttons = [];
  for (const [label, build] of sections) {
    const did = `${id}-${label.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`;
    const drawer = el('div', { class: 'drawer', id: did, hidden: true });
    let built = false;
    const b = el('button', { type: 'button', class: 'btn', 'aria-expanded': 'false', 'aria-controls': did }, label);
    b.addEventListener('click', () => {
      const open = b.getAttribute('aria-expanded') === 'true';
      for (const other of buttons) {
        other.setAttribute('aria-expanded', 'false');
        document.getElementById(other.getAttribute('aria-controls')).hidden = true;
      }
      if (!open) {
        if (!built) {
          drawer.append(...[].concat(build()));
          built = true;
        }
        b.setAttribute('aria-expanded', 'true');
        drawer.hidden = false;
        resizeAll();
      }
    });
    buttons.push(b);
    bar.append(b);
    drawers.append(drawer);
  }
  return el('div', {}, bar, drawers);
}

export function staleNotice(meta, sources) {
  const stale = sources.filter((s) => meta.sources[s] && meta.sources[s].stale);
  if (!stale.length) return null;
  const names = stale.map((s) => meta.sources[s].label).join(', ');
  return el('p', { class: 'stale', role: 'status' }, `The last refresh could not reach: ${names}. Figures from these sources are the last good snapshot.`);
}

async function show(view) {
  if (!VIEWS.includes(view)) view = 'overview';
  for (const v of VIEWS) {
    const sec = document.getElementById(`view-${v}`);
    const tab = document.getElementById(`tab-${v}`);
    const active = v === view;
    sec.hidden = !active;
    tab.setAttribute('aria-selected', String(active));
    tab.setAttribute('tabindex', active ? '0' : '-1');
  }
  const sec = document.getElementById(`view-${view}`);
  if (!rendered.has(view)) {
    rendered.add(view);
    try {
      const mod = await loaders[view]();
      const meta = await getJSON('meta');
      await mod.render(sec, meta);
    } catch (err) {
      rendered.delete(view);
      sec.replaceChildren(sec.querySelector('h2'), el('p', { class: 'stale' }, `This view could not load its data (${err.message}).`));
      console.error(err);
    }
  }
  requestAnimationFrame(resizeAll);
}

let first = true;
function route() {
  const view = (location.hash || '#overview').slice(1);
  // a new view starts at its top, not at the scroll position of the last one
  if (!first) window.scrollTo(0, 0);
  first = false;
  show(view);
}

function keyboardTabs() {
  const tabs = [...document.querySelectorAll('[role="tab"]')];
  tabs.forEach((t, i) => {
    t.addEventListener('keydown', (e) => {
      let j = null;
      if (e.key === 'ArrowRight') j = (i + 1) % tabs.length;
      if (e.key === 'ArrowLeft') j = (i - 1 + tabs.length) % tabs.length;
      if (e.key === 'Home') j = 0;
      if (e.key === 'End') j = tabs.length - 1;
      if (j !== null) {
        e.preventDefault();
        tabs[j].focus();
        location.hash = tabs[j].getAttribute('href');
      }
    });
  });
}

async function init() {
  loadECharts().catch(() => {});
  readTokens();
  keyboardTabs();
  try {
    const meta = await getJSON('meta');
    document.getElementById('asof').textContent =
      `Dalian and SGX data to ${fmtDate(meta.asof.daily)}; monthly IMF benchmark to ${fmtDate(meta.asof.monthly)}. Updated ${fmtDate(meta.build_date)}.`;
    document.getElementById('footer-updated').textContent = `Last update ${fmtDate(meta.build_date)} (version ${meta.version})`;
  } catch (e) {
    document.getElementById('asof').textContent = 'Data could not be loaded.';
  }
  window.addEventListener('hashchange', route);
  route();
}

if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
else init();
