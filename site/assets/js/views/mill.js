import { getJSON, el, chartBlock, toggles, staleNotice } from '../app.js';
import { C, base, mount, loadECharts, fmt, fmtSigned, fmtDate, valueAxis, timeAxis, line, presets, zoom, table, ttRow } from '../charts.js';

export async function render(root, meta) {
  const d = await getJSON('mill');
  const L = d.latest;
  const tr = d.test_rebar;
  const h63 = tr.find((r) => r.horizon_days === 63);
  const sign = L.rebar >= 0 ? 'positive' : 'negative';
  root.append(
    staleNotice(meta, ['dce', 'shfe']) || '',
    el('p', { class: 'takeaway' },
      `The futures-implied rebar margin was ${fmtSigned(L.rebar)} RMB per tonne on ${fmtDate(L.date)}: on the market convention, Chinese mills are ${sign === 'negative' ? 'not earning a margin' : 'earning a margin'} on current ore and coke prices.`),
    el('p', { class: 'subtake' },
      `Pre-registered test: after the rebar margin falls into the bottom decile of its previous three years, Dalian ore did not weaken. Over the next three months it moved ${fmtSigned(h63.effect_pct, 1)} percentage points relative to other days (95% interval ${fmtSigned(h63.ci_lo_pct, 1)} to ${fmtSigned(h63.ci_hi_pct, 1)}), the opposite sign to the hypothesis and not distinguishable from zero.`),
  );

  const ly = d.daily.rebar[d.daily.rebar.length - 1][0].slice(0, 4);
  const lyv = d.daily.rebar.filter((p) => p[0].startsWith(ly) && p[1] !== null).map((p) => p[1]);
  const lyNeg = lyv.filter((v) => v < 0).length;
  const negText = lyNeg === lyv.length ? `negative on every trading day of ${ly}` : `negative on ${lyNeg} of ${lyv.length} trading days in ${ly}`;
  const { block: b1, host: h1 } = chartBlock({
    title: `Mill margins swing from boom to loss; the rebar margin has been ${negText}`,
    sub: 'Futures-implied margin, RMB per tonne of steel, daily: rebar (RB) and hot-rolled coil (HC) minus 1.6 x iron ore minus 0.5 x coke minus other costs, most-active contracts.',
    source: `Sources: Shanghai Futures Exchange daily files, Dalian Commodity Exchange annual files, Sina; computed by the pipeline. Data to ${fmtDate(L.date)}.`,
    summary: `Latest rebar ${fmtSigned(L.rebar)} RMB/t, HRC ${fmtSigned(L.hrc)} RMB/t (${L.contracts.rb}, ${L.contracts.hc}, ${L.contracts.i}, ${L.contracts.j}).`,
    cls: 'chart chart--tall',
  });
  root.append(b1);
  await loadECharts();
  const c1 = mount(h1, base({
    grid: { left: 60, right: 20, top: 40, bottom: 36 },
    dataZoom: zoom(),
    tooltip: { trigger: 'axis', formatter: (ps) => `${fmtDate(ps[0].value[0])}${ps.map((p) => ttRow(p.color, `${fmtSigned(p.value[1])} RMB/t`, p.seriesName)).join('')}` },
    xAxis: timeAxis(),
    yAxis: valueAxis('RMB per tonne of steel', { scale: false }),
    series: [
      line('Rebar margin', d.daily.rebar, C.hematite, { markLine: { silent: true, symbol: 'none', lineStyle: { color: C.steel, width: 1 }, label: { show: false }, data: [{ yAxis: 0 }] } }),
      line('HRC margin', d.daily.hrc, C.seawater),
    ],
  }));
  presets(b1, c1, d.daily.rebar[d.daily.rebar.length - 1][0], d.daily.rebar[0][0]);

  // Cost decomposition, monthly
  const m = d.monthly;
  const mdates = m.months.map((x) => `${x}-15`);
  const shares = m.months.map((_, i) => (m.ore[i] + m.coke[i]) / m.rebar[i]).filter((v) => Number.isFinite(v));
  const share = shares.reduce((a, b) => a + b, 0) / shares.length;
  const { block: b2, host: h2 } = chartBlock({
    title: `Ore and coke take ${fmt(share * 100)}% of the rebar price on average; after a fixed ${fmt(d.params.mill_other_costs_rebar.value)} RMB/t of other costs, the margin is what is left`,
    sub: 'Monthly averages, RMB per tonne of steel: stacked cost components (1.6 x iron ore, 0.5 x coke, other costs) against the rebar price. The gap between the line and the stack is the margin.',
    source: 'Sources: SHFE, DCE, Sina; computed by the pipeline.',
    summary: `Latest month ${m.months[m.months.length - 1]}: ore ${fmt(m.ore[m.ore.length - 1])}, coke ${fmt(m.coke[m.coke.length - 1])}, other ${fmt(m.other[m.other.length - 1])}, rebar ${fmt(m.rebar[m.rebar.length - 1])} RMB/t.`,
    cls: 'chart chart--tall',
  });
  root.append(el('div', { style: 'margin-top:16px' }, b2));
  const c2 = mount(h2, base({
    grid: { left: 60, right: 20, top: 40, bottom: 36 },
    dataZoom: zoom(),
    tooltip: { trigger: 'axis', formatter: (ps) => `${ps[0].value[0].slice(0, 7)}${ps.map((p) => ttRow(p.color, `${fmt(p.value[1])} RMB/t`, p.seriesName)).join('')}` },
    xAxis: timeAxis(),
    yAxis: valueAxis('RMB per tonne of steel', { scale: false }),
    series: [
      { type: 'line', name: 'Iron ore, 1.6 x I', stack: 'c', data: mdates.map((x, i) => [x, m.ore[i]]), showSymbol: false, lineStyle: { width: 0 }, areaStyle: { color: C.hematite, opacity: 0.55 }, itemStyle: { color: C.hematite } },
      { type: 'line', name: 'Coke, 0.5 x J', stack: 'c', data: mdates.map((x, i) => [x, m.coke[i]]), showSymbol: false, lineStyle: { width: 0 }, areaStyle: { color: C.pilbara, opacity: 0.5 }, itemStyle: { color: C.pilbara } },
      { type: 'line', name: 'Other costs', stack: 'c', data: mdates.map((x, i) => [x, m.other[i]]), showSymbol: false, lineStyle: { width: 0 }, areaStyle: { color: C.steel, opacity: 0.25 }, itemStyle: { color: C.steel } },
      line('Rebar price', mdates.map((x, i) => [x, m.rebar[i]]), C.topside),
    ],
  }));
  presets(b2, c2, mdates[mdates.length - 1], mdates[0]);

  // Pre-registered test
  const { block: b3, host: h3 } = chartBlock({
    title: 'Low mill margins did not precede weaker iron ore',
    sub: 'Pre-registered test. Difference in the forward change of the Dalian 45-day iron ore price (percentage points) between days when the margin is in the bottom decile of its previous 756 trading days and all other days. Bars: 95% moving block bootstrap intervals.',
    source: 'Sources: computed by the pipeline (pipeline/mill_model.py); design fixed in the decision log before the result was computed.',
    summary: tr.map((r) => `${r.horizon_days} days: ${fmtSigned(r.effect_pct, 2)} (${fmtSigned(r.ci_lo_pct, 2)} to ${fmtSigned(r.ci_hi_pct, 2)}), Newey-West t ${fmt(r.nw_t, 2)}`).join('; '),
  });
  root.append(el('div', { class: 'grid grid--two', style: 'margin-top:16px' }, b3, testTable(d)));
  const th = d.test_hrc;
  const cats = ['1 month (21 days)', '2 months (42 days)', '3 months (63 days)'];
  mount(h3, base({
    grid: { left: 12, right: 24, top: 36, bottom: 44, containLabel: true },
    tooltip: { trigger: 'item', formatter: (p) => { const r = (p.seriesName.startsWith('Rebar') ? tr : th)[p.dataIndex]; return `${cats[p.dataIndex]}${ttRow(p.color, `${fmtSigned(r.effect_pct, 2)} pp`, `${p.seriesName}, 95% interval ${fmtSigned(r.ci_lo_pct, 2)} to ${fmtSigned(r.ci_hi_pct, 2)}`)}`; } },
    legend: { top: 0, left: 0, data: ['Rebar margin (primary)', 'HRC margin (secondary)'] },
    xAxis: valueAxis('Percentage points', { scale: false, nameGap: 28 }),
    yAxis: { type: 'category', data: cats, inverse: true, axisLine: { show: false }, axisTick: { show: false }, axisLabel: { color: C.topside, fontFamily: C.font } },
    series: [
      { type: 'custom', name: 'zero', silent: true, tooltip: { show: false }, data: [[0]], encode: { x: 0 }, z: 1,
        renderItem: (params, api) => {
          const x = api.coord([0, 0])[0];
          const cs = params.coordSys;
          return { type: 'line', shape: { x1: x, y1: cs.y, x2: x, y2: cs.y + cs.height }, style: { stroke: C.topside, lineWidth: 1 } };
        } },
      ciSeries('Rebar margin (primary)', tr, C.hematite, -0.14),
      ciSeries('HRC margin (secondary)', th, C.seawater, 0.14),
    ],
  }));

  root.append(toggles('mill', [
    ['Method', () => [
      el('h3', {}, 'The futures-implied mill margin'),
      el('p', {}, 'Chinese brokers track steel mill profitability with a futures convention: rebar (or hot-rolled coil) minus 1.6 tonnes of iron ore and 0.5 tonnes of coke per tonne of steel, minus a constant for other costs. It is a market convention, not a mill’s accounting margin: it ignores sinter and pellet blends, scrap, energy, labour and the timing of purchases.'),
      el('p', {}, 'Most-active version: each product’s most-active contract, chosen on the previous day’s open interest. Same-month version: January and May contracts of all four products, choosing on each day the month with the larger iron ore open interest.'),
      el('p', {}, 'Pre-registered test (decision log, before computing): signal when the rebar margin is below the 10th percentile of its previous 756 trading days; outcome the forward change in the log of the Dalian 45-day iron ore price over 21, 42 and 63 trading days; effect = mean with signal minus mean without; 95% interval from a moving block bootstrap with 63-day blocks; Newey-West t statistic with lags equal to the horizon. HRC is reported as a secondary line. No other variant was run.'),
    ]],
    ['Assumptions', () => [
      el('ul', {},
        el('li', {}, `Coefficients 1.6 (ore) and 0.5 (coke): Cinda Futures (2017), Orient Securities (2019), SDIC Essence Futures (2022), CITIC Futures.`),
        el('li', {}, `Other costs ${fmt(d.params.mill_other_costs_rebar.value)} RMB/t for rebar (the constant implied by Everbright Futures’ published 2026 margins; published constants range 950 to 1,250), plus ${fmt(d.params.mill_other_costs_hrc_premium.value)} for HRC.`),
        el('li', {}, `Sensitivity of the latest rebar margin to the constant: ${Object.entries(d.sensitivity).map(([k, v]) => `${fmt(Number(k))}: ${fmtSigned(v)}`).join('; ')} RMB/t.`),
        el('li', {}, 'Day-session closing prices, as in broker reports.'),
      ),
    ]],
    ['Data', () => [table('Rebar and HRC margins, monthly averages (RMB per tonne)', [
      { label: 'Month', key: 'm' }, { label: 'Rebar price', get: (r) => fmt(r.rb), num: true }, { label: '1.6 x ore', get: (r) => fmt(r.o), num: true },
      { label: '0.5 x coke', get: (r) => fmt(r.c), num: true }, { label: 'Rebar margin', get: (r) => fmtSigned(r.mg), num: true },
    ], m.months.map((x, i) => ({ m: x, rb: m.rebar[i], o: m.ore[i], c: m.coke[i], mg: m.margin[i] })).reverse())]],
  ]));
}

function ciSeries(name, rows, color, offset) {
  return {
    type: 'custom', name, z: 2,
    itemStyle: { color },
    encode: { x: [1, 2, 3], y: 0, tooltip: [3, 1, 2] },
    data: rows.map((r, i) => [i, r.ci_lo_pct, r.ci_hi_pct, r.effect_pct]),
    renderItem: (params, api) => {
      const i = api.value(0);
      const band = api.size([0, 1])[1];
      const lo = api.coord([api.value(1), i]);
      const hi = api.coord([api.value(2), i]);
      const pt = api.coord([api.value(3), i]);
      const y = lo[1] + offset * band;
      return {
        type: 'group',
        children: [
          { type: 'line', shape: { x1: lo[0], y1: y, x2: hi[0], y2: y }, style: { stroke: color, lineWidth: 2 } },
          { type: 'line', shape: { x1: lo[0], y1: y - 5, x2: lo[0], y2: y + 5 }, style: { stroke: color, lineWidth: 2 } },
          { type: 'line', shape: { x1: hi[0], y1: y - 5, x2: hi[0], y2: y + 5 }, style: { stroke: color, lineWidth: 2 } },
          { type: 'circle', shape: { cx: pt[0], cy: y, r: 6 }, style: { fill: color, stroke: '#ffffff', lineWidth: 2 } },
        ],
      };
    },
  };
}

function testTable(d) {
  const rows = d.test_rebar.map((r) => ({ ...r, kind: 'Rebar' })).concat(d.test_hrc.map((r) => ({ ...r, kind: 'HRC' })));
  return el('div', { class: 'panel' }, table('Pre-registered test results', [
    { label: 'Margin', key: 'kind' }, { label: 'Horizon', get: (r) => `${r.horizon_days} days` },
    { label: 'Signal days', get: (r) => fmt(r.n_signal_days), num: true }, { label: 'Effect, pp', get: (r) => fmtSigned(r.effect_pct, 2), num: true },
    { label: '95% interval', get: (r) => `${fmtSigned(r.ci_lo_pct, 1)} to ${fmtSigned(r.ci_hi_pct, 1)}`, num: true }, { label: 'NW t', get: (r) => fmt(r.nw_t, 2), num: true },
  ], rows), el('p', { class: 'source' }, `Sample ${fmtDate(d.test_rebar[0].sample_start)} to ${fmtDate(d.test_rebar[0].sample_end)}; the first three years are needed to form the trailing decile. Flagged days are about a quarter of the sample because margins trended down.`));
}
