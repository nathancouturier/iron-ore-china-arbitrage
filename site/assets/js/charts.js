// Chart helpers: an ECharts theme read from the CSS design tokens, range
// presets, accessible table twins and number formatting.

const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();

export const C = {};
export function readTokens() {
  for (const k of ['primer', 'plate', 'plate-strong', 'topside', 'steel', 'muted', 'grid', 'seawater', 'pilbara', 'hematite']) {
    C[k.replace('-', '_')] = css(`--${k}`);
  }
  C.band = 'rgba(70, 83, 94, 0.10)';
  C.font = 'Archivo, "Helvetica Neue", Arial, sans-serif';
}

export const reducedMotion = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches;

const nf = (d) => new Intl.NumberFormat('en-GB', { minimumFractionDigits: d, maximumFractionDigits: d });
export function fmt(v, d = 0) {
  if (v === null || v === undefined || Number.isNaN(v)) return 'n/a';
  return nf(d).format(v).replace('-', '−');
}
const axisNumber = (v) => fmt(v, Number.isInteger(v) ? 0 : Math.min(2, String(v).split('.')[1].length));
export function fmtSigned(v, d = 0) {
  if (v === null || v === undefined || Number.isNaN(v)) return 'n/a';
  const s = nf(d).format(Math.abs(v));
  return v > 0 ? `+${s}` : v < 0 ? `−${s}` : s;
}
export function fmtPct(v, d = 1) {
  if (v === null || v === undefined || Number.isNaN(v)) return 'n/a';
  return `${nf(d).format(v * 100)}%`;
}
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
export function fmtDate(iso) {
  if (!iso) return 'n/a';
  const [y, m, d] = iso.split('-').map(Number);
  return d ? `${d} ${MONTHS[m - 1]} ${y}` : `${MONTHS[m - 1]} ${y}`;
}
export function fmtMonth(iso) {
  const [y, m] = iso.split('-').map(Number);
  return `${MONTHS[m - 1]} ${y}`;
}

/** Base options shared by every chart. */
export function base(extra = {}) {
  return {
    animation: false,
    textStyle: { fontFamily: C.font, color: C.steel, fontSize: 12 },
    grid: { left: 64, right: 24, top: 36, bottom: 48, containLabel: false },
    tooltip: {
      trigger: 'axis',
      confine: true,
      backgroundColor: '#ffffff',
      borderColor: C.plate_strong,
      borderWidth: 1,
      padding: [8, 10],
      textStyle: { fontFamily: C.font, color: C.topside, fontSize: 13 },
      axisPointer: { type: 'line', lineStyle: { color: C.steel, width: 1 } },
      extraCssText: 'box-shadow:none;border-radius:2px;font-variant-numeric:tabular-nums;',
    },
    legend: {
      top: 0,
      left: 0,
      itemWidth: 18,
      itemHeight: 10,
      textStyle: { fontFamily: C.font, color: C.topside, fontSize: 12 },
      icon: 'roundRect',
    },
    ...extra,
  };
}

export function timeAxis(name = '') {
  return {
    type: 'time',
    name,
    axisLine: { lineStyle: { color: C.grid } },
    axisTick: { show: false },
    axisLabel: { color: C.steel, fontFamily: C.font, hideOverlap: true },
    splitLine: { show: false },
  };
}

export function valueAxis(name, extra = {}) {
  const { axisLabel = {}, ...rest } = extra;
  return {
    type: 'value',
    name,
    nameLocation: 'middle',
    nameGap: 48,
    nameTextStyle: { color: C.steel, fontFamily: C.font, fontSize: 12 },
    axisLine: { show: false },
    axisTick: { show: false },
    axisLabel: { color: C.steel, fontFamily: C.font, formatter: axisNumber, ...axisLabel },
    splitLine: { lineStyle: { color: C.grid, width: 1, type: 'solid' } },
    scale: true,
    ...rest,
  };
}

export function line(name, data, color, extra = {}) {
  return {
    type: 'line',
    name,
    data,
    showSymbol: false,
    symbolSize: 8,
    lineStyle: { width: 2, color, cap: 'round', join: 'round' },
    itemStyle: { color },
    emphasis: { focus: 'none' },
    ...extra,
  };
}

/** A modeled series: dashed line plus a 10% wash band between lo and hi. */
export function modeled(name, mid, lo, hi, color, stackId) {
  return [
    {
      type: 'line', name: `${name} band low`, data: lo, stack: stackId, showSymbol: false,
      lineStyle: { opacity: 0 }, itemStyle: { color }, silent: true, tooltip: { show: false }, legendHoverLink: false,
    },
    {
      type: 'line', name: `${name} band`, data: hi.map((p, i) => [p[0], p[1] === null || lo[i][1] === null ? null : p[1] - lo[i][1]]),
      stack: stackId, showSymbol: false, lineStyle: { opacity: 0 }, areaStyle: { color, opacity: 0.12 },
      itemStyle: { color }, silent: true, tooltip: { show: false }, legendHoverLink: false,
    },
    line(name, mid, color, { lineStyle: { width: 2, color, type: [6, 4] } }),
  ];
}

/** Push the plot down when the legend wraps onto more lines (narrow screens). */
function fitLegend(chart) {
  const opt = chart.getOption();
  if (!opt.legend || !opt.legend.length || opt.legend[0].show === false || !opt.grid || !opt.grid.length) return;
  const model = chart.getModel().getComponent('legend');
  const view = model && chart.getViewOfComponentModel(model);
  if (!view) return;
  if (chart.baseTop === undefined) chart.baseTop = Number(opt.grid[0].top) || 36;
  const want = Math.max(chart.baseTop, Math.ceil(view.group.getBoundingRect().height + 24));
  if (Number(opt.grid[0].top) !== want) chart.setOption({ grid: { top: want } });
}

/** Load the chart library once; views render their text first and await this before drawing. */
let library;
export function loadECharts() {
  if (window.echarts) return Promise.resolve();
  library ||= new Promise((resolve, reject) => {
    const s = document.createElement('script');
    s.src = 'assets/vendor/echarts-5.5.1/echarts.min.js';
    s.onload = resolve;
    s.onerror = () => reject(new Error('the chart library did not load'));
    document.head.append(s);
  });
  return library;
}

const charts = new Set();
export function mount(el, option) {
  const chart = echarts.init(el, null, { renderer: 'svg' });
  chart.setOption(option);
  fitLegend(chart);
  charts.add(chart);
  return chart;
}
export function resizeAll() {
  charts.forEach((c) => {
    c.resize();
    fitLegend(c);
  });
}
window.addEventListener('resize', resizeAll);

/** Range presets (1Y, 3Y, 5Y, All) acting on a time-axis chart via dataZoom. */
export function presets(container, chart, lastIso, firstIso, initial = 'All') {
  const wrap = document.createElement('div');
  wrap.className = 'controls';
  const label = document.createElement('span');
  label.className = 'controls__label';
  label.textContent = 'Range';
  wrap.append(label);
  const last = new Date(lastIso);
  const opts = [['1Y', 1], ['3Y', 3], ['5Y', 5], ['All', null]];
  const buttons = [];
  const apply = (years) => {
    const start = years ? new Date(last.getFullYear() - years, last.getMonth(), last.getDate()) : new Date(firstIso);
    chart.dispatchAction({ type: 'dataZoom', startValue: start.getTime(), endValue: last.getTime() });
  };
  for (const [txt, years] of opts) {
    const b = document.createElement('button');
    b.type = 'button';
    b.className = 'btn';
    b.textContent = txt;
    b.setAttribute('aria-pressed', String(txt === initial));
    b.addEventListener('click', () => {
      buttons.forEach((x) => x.setAttribute('aria-pressed', 'false'));
      b.setAttribute('aria-pressed', 'true');
      apply(years);
    });
    buttons.push(b);
    wrap.append(b);
  }
  container.append(wrap);
  const init = opts.find((o) => o[0] === initial);
  if (init) setTimeout(() => apply(init[1]), 0);
  return wrap;
}

/** Hidden dataZoom so presets can drive the visible window. */
export const zoom = () => [{ type: 'inside', xAxisIndex: 0, filterMode: 'none', zoomOnMouseWheel: false, moveOnMouseMove: false }];

/** Build a table from column definitions and rows (used behind the Data buttons). */
export function table(caption, columns, rows, maxRows = null) {
  const wrap = document.createElement('div');
  wrap.className = columns.length > 3 ? 'table-wrap table-wrap--stack' : 'table-wrap';
  const t = document.createElement('table');
  const cap = document.createElement('caption');
  cap.textContent = caption;
  t.append(cap);
  const thead = document.createElement('thead');
  const hr = document.createElement('tr');
  for (const c of columns) {
    const th = document.createElement('th');
    th.scope = 'col';
    th.textContent = c.label;
    if (c.num) th.className = 'num';
    hr.append(th);
  }
  thead.append(hr);
  t.append(thead);
  const tbody = document.createElement('tbody');
  const list = maxRows ? rows.slice(-maxRows) : rows;
  const LONG = 30;
  list.forEach((r, i) => {
    const tr = document.createElement('tr');
    for (const c of columns) {
      const td = document.createElement('td');
      const v = typeof c.get === 'function' ? c.get(r) : r[c.key];
      if (c.href && r[c.href]) {
        const a = document.createElement('a');
        a.href = r[c.href];
        a.textContent = v;
        td.append(a);
      } else {
        td.textContent = v === null || v === undefined ? '' : String(v);
      }
      if (c.num) td.className = 'num';
      td.dataset.label = c.label;
      tr.append(td);
    }
    if (list.length > LONG + 10 && i >= LONG) tr.hidden = true;
    tbody.append(tr);
  });
  t.append(tbody);
  wrap.append(t);
  if (list.length > LONG + 10) {
    const more = document.createElement('button');
    more.type = 'button';
    more.className = 'btn';
    more.textContent = `Show all ${list.length} rows`;
    more.addEventListener('click', () => {
      tbody.querySelectorAll('tr[hidden]').forEach((tr) => { tr.hidden = false; });
      more.remove();
    });
    wrap.append(more);
  }
  return wrap;
}

/** Tooltip row: value first, then the series name, keyed by a short line. */
export function ttRow(color, value, name, dashed = false) {
  const key = `<span style="display:inline-block;width:14px;height:0;border-top:2px ${dashed ? 'dashed' : 'solid'} ${color};margin:0 6px 3px 0;vertical-align:middle"></span>`;
  return `<div>${key}<strong>${value}</strong> <span style="color:${C.steel}">${name}</span></div>`;
}
