import { getJSON, el, chartBlock, toggles, staleNotice } from '../app.js';
import { C, base, mount, loadECharts, fmt, fmtSigned, fmtPct, fmtDate, fmtMonth, valueAxis, timeAxis, line, modeled, presets, zoom, table, ttRow } from '../charts.js';

const ROUTE = {
  C5: { color: () => C.pilbara, leg: 'port_hedland-qingdao', name: 'C5 West Australia to Qingdao', origin: 'Australia' },
  C3: { color: () => C.seawater, leg: 'tubarao-qingdao', name: 'C3 Tubarao to Qingdao', origin: 'Brazil' },
};

const mean = (xs) => {
  const v = xs.filter((x) => x !== null && x !== undefined);
  return v.length ? v.reduce((s, x) => s + x, 0) / v.length : null;
};
const lastValid = (pairs) => {
  for (let i = pairs.length - 1; i >= 0; i--) if (pairs[i][1] !== null) return pairs[i];
  return [null, null];
};

export async function render(root, meta) {
  const d = await getJSON('freight');
  const m = d.monthly;
  const ev = d.evaluation;
  const n = m.months.length;
  const lm = m.months[n - 1];
  const gap = m.fob_australia.map((a, i) => (a === null || m.fob_brazil[i] === null ? null : a - m.fob_brazil[i]));
  const gapMean = mean(gap);
  const [lastWeek, c5Last] = lastValid(d.weekly.c5);
  const c3Last = lastValid(d.weekly.c3)[1];

  root.append(
    staleNotice(meta, ['baltic', 'brent', 'fred']) || '',
    el('p', { class: 'takeaway' },
      `In ${fmtMonth(lm)} freight took ${fmtPct(m.share_c5[n - 1], 0)} of the CFR price from West Australia and ${fmtPct(m.share_c3[n - 1], 0)} from Brazil; the longer haul left Brazil's index-equivalent netback ${fmt(gap[n - 1], 1)} USD/dmt below Australia's.`),
    el('p', { class: 'subtake' },
      `Route rates are paid data, so freight here is modeled from the Baltic Capesize Index and Brent and checked against ${ev.C3.voyage.n + ev.C5.voyage.n} published route assessments. Since 2014 the Brazilian netback has trailed the Australian one by ${fmt(gapMean, 1)} USD/dmt on average.`),
  );

  await loadECharts();
  root.append(mapBlock(d, c5Last, c3Last, lastWeek));
  root.append(freightBlock(d));
  const g = el('div', { class: 'grid grid--two', style: 'margin-top:16px' });
  root.append(g);
  g.append(diffBlock(d), shareBlock(d));
  root.append(el('div', { style: 'margin-top:16px' }, netbackBlock(d, gap, gapMean)));
  root.append(drawers(d));
}

// 1. Route map ---------------------------------------------------------------
function mapBlock(d, c5Last, c3Last, lastWeek) {
  const v = d.voyages;
  const routeText = (code) => {
    const leg = d.routes.legs[ROUTE[code].leg];
    return `${ROUTE[code].name}: ${fmt(leg.nm)} nautical miles, ${fmt(v[code].laden_days, 1)} days laden at ${fmt(v[code].laden_speed_kn)} knots, ${fmt(v[code].total_days, 1)}-day round voyage`;
  };
  const { block, host } = chartBlock({
    title: 'A Brazilian cargo sails three times as far as a Pilbara cargo to reach Qingdao',
    sub: 'Shortest sea routes from the searoute package, laden leg. Distances in nautical miles; voyage days at the Baltic eco speed of 12 knots.',
    source: 'Sources: searoute 1.6.0 (sea lane network), Natural Earth land via world-atlas 2.0.2; voyage days from the voyage model.',
    summary: `${routeText('C5')}. ${routeText('C3')}.`,
    cls: 'chart chart--map',
  });
  const facts = el('div', { class: 'ledger' },
    routeFact('C5', d, c5Last, lastWeek),
    routeFact('C3', d, c3Last, lastWeek),
  );
  const wrap = el('div', { class: 'grid grid--bridge' }, block, facts);
  requestAnimationFrame(() => {
    echarts.registerMap('land', d.land);
    const ports = d.routes.ports;
    const legs = ['C5', 'C3'].map((code) => ({
      name: ROUTE[code].name,
      coords: d.routes.legs[ROUTE[code].leg].coords,
      lineStyle: { color: ROUTE[code].color(), width: 2.5, opacity: 1 },
    }));
    mount(host, base({
      tooltip: { trigger: 'item', formatter: (p) => (p.seriesType === 'lines' ? routeText(p.name.startsWith('C5') ? 'C5' : 'C3') : p.name) },
      legend: { show: false },
      geo: {
        map: 'land',
        roam: false,
        silent: true,
        boundingCoords: [[-50, 42], [128, -38]],
        left: 4, right: 4, top: 4, bottom: 4,
        itemStyle: { areaColor: C.plate_strong, borderColor: C.plate_strong, borderWidth: 0.5 },
        emphasis: { disabled: true },
      },
      series: [
        { type: 'lines', coordinateSystem: 'geo', polyline: true, data: legs, zlevel: 1 },
        {
          type: 'scatter', coordinateSystem: 'geo', symbolSize: 9, zlevel: 2,
          itemStyle: { color: C.topside, borderColor: '#ffffff', borderWidth: 2 },
          label: { show: true, formatter: (p) => p.name, color: C.topside, fontFamily: C.font, fontSize: 12, fontWeight: 600, distance: 6 },
          data: [['port_hedland', 'bottom'], ['tubarao', 'top'], ['qingdao', 'left']].map(([k, pos]) => ({ name: ports[k].name, value: ports[k].lonlat, label: { position: pos } })),
        },
      ],
    }));
  });
  return wrap;
}

function routeFact(code, d, latest, date) {
  const v = d.voyages[code];
  const leg = d.routes.legs[ROUTE[code].leg];
  const e = d.evaluation[code].voyage;
  return el('div', { class: 'fact' },
    el('p', { class: 'fact__label' }, el('span', { class: 'swatch', style: `border-color:${ROUTE[code].color()}` }), ROUTE[code].name),
    el('p', { class: 'fact__value' }, fmt(latest, 2), el('span', { class: 'fact__unit' }, 'USD/wmt, modeled')),
    el('p', { class: 'fact__note' },
      `Week to ${fmtDate(date)}. ${fmt(leg.nm)} nm; ${fmt(v.laden_days, 1)} days laden, ${fmt(v.total_days, 1)}-day round voyage. Model error on ${e.n} published rates: RMSE ${fmt(e.rmse, 2)} USD/t.`),
  );
}

// 2. Modeled freight with anchors ------------------------------------------------
function freightBlock(d) {
  const ev = d.evaluation;
  const w = d.weekly;
  const an = d.anchors;
  const { block, host } = chartBlock({
    title: `The voyage model tracks published route rates with an error of about ${fmt(ev.C5.voyage.rmse, 1)} USD/t on C5 and ${fmt(ev.C3.voyage.rmse, 1)} USD/t on C3`,
    sub: 'Capesize freight, USD per wet tonne, weekly (Friday). Dashed lines and shading: modeled rate and 80% error band from out-of-sample errors. Dots: published C3 and C5 assessments.',
    source: `Sources: Baltic Capesize Index via East Money, Brent via FRED, published route assessments (Baltic Exchange via Hellenic Shipping News, Splash247 and Signal Group; Platts; Ruida Futures), listed under Data. Modeled, data to ${fmtDate(lastValid(w.c5)[0])}.`,
    summary: ['C3', 'C5'].map((r) => `${r}: voyage model MAE ${fmt(ev[r].voyage.mae, 2)}, RMSE ${fmt(ev[r].voyage.rmse, 2)}, bias ${fmtSigned(ev[r].voyage.bias, 2)} USD/t on ${ev[r].voyage.n} anchors; regression (leave one out) RMSE ${fmt(ev[r].stat_loo.rmse, 2)}`).join('. '),
    cls: 'chart chart--tall',
  });
  const wrap = el('div', { style: 'margin-top:16px' }, block);
  const pts = (route) => an.filter((a) => a.route === route).map((a) => [a.date, a.value_usd_wmt]);
  requestAnimationFrame(() => {
    const chart = mount(host, base({
      grid: { left: 56, right: 20, top: 40, bottom: 36 },
      dataZoom: zoom(),
      legend: { top: 0, left: 0, data: ['C3 Tubarao, modeled', 'C5 West Australia, modeled', 'C3 published', 'C5 published'] },
      tooltip: {
        trigger: 'axis',
        formatter: (ps) => {
          const rows = ps.filter((p) => p.seriesType === 'line' && !p.seriesName.includes('band') && p.value && p.value[1] !== null);
          if (!rows.length) return '';
          const day = rows[0].value[0];
          const t = Date.parse(day);
          const near = an.filter((a) => Math.abs(Date.parse(a.date) - t) <= 3 * 86400000);
          return `Week to ${fmtDate(day)}${rows.map((p) => ttRow(p.color, `${fmt(p.value[1], 2)} USD/wmt`, p.seriesName, true)).join('')}${near.map((a) => ttRow(a.route === 'C3' ? C.seawater : C.pilbara, `${fmt(a.value_usd_wmt, 2)} USD/wmt`, `${a.route} published ${fmtDate(a.date)}, ${a.assessor}`)).join('')}`;
        },
      },
      xAxis: timeAxis(),
      yAxis: valueAxis('USD per wet tonne', { scale: false, nameGap: 36 }),
      series: [
        ...modeled('C3 Tubarao, modeled', w.c3, w.c3_lo, w.c3_hi, C.seawater, 'c3'),
        ...modeled('C5 West Australia, modeled', w.c5, w.c5_lo, w.c5_hi, C.pilbara, 'c5'),
        anchorSeries('C3 published', pts('C3'), C.seawater),
        anchorSeries('C5 published', pts('C5'), C.pilbara),
      ],
    }));
    presets(block, chart, lastValid(w.c5)[0], w.c5[0][0], 'All');
  });
  return wrap;
}

function anchorSeries(name, data, color) {
  return {
    type: 'scatter', name, data, symbolSize: 8, z: 5,
    itemStyle: { color, borderColor: '#ffffff', borderWidth: 1.5 },
  };
}

// 3. C3 minus C5 against the BCI --------------------------------------------------
function diffBlock(d) {
  const s = d.sensitivity.c3_minus_c5_vs_bci;
  const w = d.weekly;
  const pts = w.diff.map((p, i) => [w.bci[i][1], p[1], p[0]]).filter((p) => p[0] !== null && p[1] !== null);
  const xs = pts.map((p) => p[0]);
  const x0 = Math.min(...xs);
  const x1 = Math.max(...xs);
  const { block, host } = chartBlock({
    title: `The Brazil haul costs about ${fmt(s.b * 1000, 1)} USD/t more for every 1,000 BCI points`,
    sub: 'C3 minus C5 modeled freight, USD per wet tonne, against the Baltic Capesize Index (points), weekly since 2014. Line: least squares fit on daily data.',
    source: 'Sources: modeled freight (this site), Baltic Capesize Index via East Money. Modeled.',
    summary: `C3 minus C5 = ${fmt(s.a, 2)} + ${fmt(s.b, 5)} x BCI; correlation ${fmt(s.corr, 2)}; mean ${fmt(s.mean, 2)}, range ${fmt(s.min, 2)} to ${fmt(s.max, 2)} USD/wmt over ${fmt(s.n)} days.`,
  });
  requestAnimationFrame(() => {
    mount(host, base({
      grid: { left: 52, right: 28, top: 16, bottom: 48 },
      legend: { show: false },
      tooltip: {
        trigger: 'item',
        formatter: (p) => (p.seriesType === 'scatter'
          ? `${fmtDate(p.value[2])}${ttRow(C.topside, `${fmt(p.value[1], 2)} USD/wmt`, `C3 minus C5 at BCI ${fmt(p.value[0])}`, true)}`
          : `Fit: ${fmt(s.a, 2)} + ${fmt(s.b * 1000, 2)} per 1,000 BCI points`),
      },
      xAxis: { ...valueAxis('Baltic Capesize Index, points', { scale: false, nameGap: 30, min: 0, max: (v) => Math.ceil(v.max / 2000) * 2000 }), splitLine: { show: false } },
      yAxis: valueAxis('USD per wet tonne', { scale: false, nameGap: 36 }),
      series: [
        { type: 'scatter', data: pts, symbolSize: 5, itemStyle: { color: 'rgba(22, 33, 43, 0.35)' } },
        line('Fit', [[x0, s.a + s.b * x0], [x1, s.a + s.b * x1]], C.hematite, { lineStyle: { width: 2, color: C.hematite } }),
      ],
    }));
  });
  return block;
}

// 4. Freight share of CFR ----------------------------------------------------------
function shareBlock(d) {
  const m = d.monthly;
  const months = m.months.map((x) => `${x}-15`);
  const byYear = {};
  m.months.forEach((x, i) => {
    const y = x.slice(0, 4);
    (byYear[y] ||= { c5: [], c3: [] });
    byYear[y].c5.push(m.share_c5[i]);
    byYear[y].c3.push(m.share_c3[i]);
  });
  const years = Object.keys(byYear).sort();
  const ly = years[years.length - 1];
  const avg = (y, k) => mean(byYear[y][k]);
  const topBoth = years.every((y) => y === ly || (avg(y, 'c5') < avg(ly, 'c5') && avg(y, 'c3') < avg(ly, 'c3')));
  const title = topBoth
    ? `Freight takes a larger share of the CFR price in ${ly} than in any year since ${years[0]}: ${fmtPct(avg(ly, 'c5'), 1)} from Australia, ${fmtPct(avg(ly, 'c3'), 1)} from Brazil`
    : `Freight takes ${fmtPct(mean(m.share_c5), 0)} of the CFR price from Australia and ${fmtPct(mean(m.share_c3), 0)} from Brazil on average`;
  const { block, host } = chartBlock({
    title,
    sub: 'Modeled freight per dry tonne as a share of the 62% Fe CFR China monthly average, percent.',
    source: `Sources: IMF via FRED (CFR), modeled freight (this site). Modeled, data to ${fmtMonth(m.months[m.months.length - 1])}.`,
    summary: years.map((y) => `${y}: Australia ${fmtPct(avg(y, 'c5'), 1)}, Brazil ${fmtPct(avg(y, 'c3'), 1)}`).join('; '),
  });
  requestAnimationFrame(() => {
    const chart = mount(host, base({
      grid: { left: 52, right: 16, top: 36, bottom: 36 },
      dataZoom: zoom(),
      tooltip: { trigger: 'axis', formatter: (ps) => `${fmtMonth(ps[0].value[0].slice(0, 7))}${ps.map((p) => ttRow(p.color, fmtPct(p.value[1], 1), p.seriesName, true)).join('')}` },
      xAxis: timeAxis(),
      yAxis: valueAxis('Share of CFR', { scale: false, nameGap: 36, axisLabel: { color: C.steel, fontFamily: C.font, formatter: (v) => `${Math.round(v * 100)}%` } }),
      series: [
        line('Brazil, C3, modeled', months.map((x, i) => [x, m.share_c3[i]]), C.seawater, { lineStyle: { width: 2, color: C.seawater, type: [6, 4] } }),
        line('Australia, C5, modeled', months.map((x, i) => [x, m.share_c5[i]]), C.pilbara, { lineStyle: { width: 2, color: C.pilbara, type: [6, 4] } }),
      ],
    }));
    presets(block, chart, months[months.length - 1], months[0], 'All');
  });
  return block;
}

// 5. Netbacks ---------------------------------------------------------------------
function netbackBlock(d, gap, gapMean) {
  const m = d.monthly;
  const months = m.months.map((x) => `${x}-15`);
  const pair = (arr) => months.map((x, i) => [x, arr[i]]);
  const n = months.length;
  let gmax = 0;
  gap.forEach((g, i) => { if (g !== null && g > gap[gmax]) gmax = i; });
  const { block, host } = chartBlock({
    title: `Brazil's index-equivalent netback trails Australia's by ${fmt(gapMean, 1)} USD/dmt on average and by ${fmt(gap[n - 1], 1)} in ${fmtMonth(m.months[n - 1])}`,
    sub: 'FOB netback = 62% Fe CFR China minus modeled freight per dry tonne (moisture 8%), USD per dry tonne, monthly. Dashed lines and shading: modeled with the freight error band. Solid: CFR benchmark.',
    source: `Sources: IMF via FRED (CFR), modeled freight (this site). Netbacks modeled, data to ${fmtMonth(m.months[n - 1])}.`,
    summary: `Latest ${fmtMonth(m.months[n - 1])}: CFR ${fmt(m.cfr[n - 1], 2)}, FOB Australia ${fmt(m.fob_australia[n - 1], 2)}, FOB Brazil ${fmt(m.fob_brazil[n - 1], 2)} USD/dmt. Largest gap ${fmt(gap[gmax], 1)} in ${fmtMonth(m.months[gmax])}.`,
    cls: 'chart',
  });
  requestAnimationFrame(() => {
    const chart = mount(host, base({
      grid: { left: 56, right: 20, top: 40, bottom: 36 },
      dataZoom: zoom(),
      legend: { top: 0, left: 0, data: ['CFR China 62% Fe', 'FOB Australia, modeled', 'FOB Brazil, modeled'] },
      tooltip: {
        trigger: 'axis',
        formatter: (ps) => {
          const rows = ps.filter((p) => !p.seriesName.includes('band') && p.value[1] !== null);
          return `${fmtMonth(ps[0].value[0].slice(0, 7))}${rows.map((p) => ttRow(p.color, `${fmt(p.value[1], 2)} USD/dmt`, p.seriesName, p.seriesName.includes('modeled'))).join('')}`;
        },
      },
      xAxis: timeAxis(),
      yAxis: valueAxis('USD per dry tonne', { scale: false, nameGap: 40 }),
      series: [
        line('CFR China 62% Fe', pair(m.cfr), C.topside),
        ...modeled('FOB Australia, modeled', pair(m.fob_australia), pair(m.fob_australia_lo), pair(m.fob_australia_hi), C.pilbara, 'au'),
        ...modeled('FOB Brazil, modeled', pair(m.fob_brazil), pair(m.fob_brazil_lo), pair(m.fob_brazil_hi), C.seawater, 'br'),
      ],
    }));
    presets(block, chart, months[n - 1], months[0], 'All');
  });
  return block;
}

// Drawers ---------------------------------------------------------------------------
function drawers(d) {
  const ev = d.evaluation;
  const s = d.sensitivity;
  const vs = d.vessel;
  const tc = Object.entries(d.tc_calibration);
  const bk = Object.entries(d.bunker_calibration);
  return toggles('freight', [
    ['Method', () => [
      el('h3', {}, 'Voyage model'),
      el('p', { class: 'formula' }, 'Freight (USD/t) = (TCE x total voyage days + bunker cost + port costs) / (cargo x (1 - commission))'),
      el('p', {}, 'Total voyage days = ballast leg + load port days + laden leg + discharge port days, with both legs over the searoute distance at the eco speed. Bunker cost = fuel at sea (laden and ballast consumption per day) plus fuel in port, at the modeled bunker price.'),
      el('p', {}, `The time charter equivalent comes from the Baltic Capesize Index, calibrated on ${tc.reduce((t, [, v]) => t + v.n, 0)} dated public pairs of BCI points and the Capesize time charter average. The relation changed when the Baltic rebased the index, so it is fitted by regime:`),
      el('ul', {}, ...tc.map(([k, v]) => el('li', {}, `${k}: ${v.extra.kind === 'linear' ? `TC = ${fmt(v.a, 1)} + ${fmt(v.b, 4)} x BCI` : `TC = ${fmt(v.b, 4)} x BCI (ratios ${fmt(v.extra.ratio_min, 4)} to ${fmt(v.extra.ratio_max, 4)})`}, ${v.n} pairs, ${v.extra.first} to ${v.extra.last}.`))),
      el('p', {}, 'From 2 January 2026 the Baltic reports the 182,000 dwt average; the 180,000 dwt equivalent is the 182 figure minus 3,503 USD/day, the adjustment the Baltic prescribes.'),
      el('p', {}, `Bunker price from Brent (USD/bbl), fitted on dated Singapore bunker quotes separately before and after the IMO 2020 sulphur cap: ${bk.map(([k, v]) => `${k}: ${fmt(v.a, 1)} + ${fmt(v.b, 3)} x Brent (n = ${v.n}, R² ${fmt(v.r2, 2)})`).join('; ')}.`),
      el('p', {}, 'The voyage model is never fitted to a route rate, so every published assessment is an out-of-sample test. The second estimate regresses the route rate on the BCI and Brent and is scored by leave-one-out cross-validation. The 80% bands use the 10th and 90th percentiles of each model\'s relative errors.'),
      el('p', {}, 'Netbacks are index-equivalent: the CFR benchmark minus freight per dry tonne. Real Australian and Brazilian products carry grade premiums or discounts to the 62% index that this view ignores.'),
    ]],
    ['Assumptions', () => [
      el('h3', {}, 'Vessel and voyage'),
      el('ul', {},
        ...Object.entries(vs).map(([k, v]) => el('li', {}, `${k.replaceAll('_', ' ')}: ${fmt(v.value, k === 'commission' ? 2 : k === 'discharge_days' ? 2 : 0)}${v.alt !== undefined ? ` (sensitivity ${fmt(v.alt)})` : ''}. ${v.source}.`)),
        el('li', {}, d.port_costs_note),
        el('li', {}, d.load_days_note),
      ),
      el('h3', {}, 'Sensitivity'),
      el('ul', {},
        el('li', {}, `At the full BCI182 speed (14 knots on 52 t laden, 44 t ballast) the round voyages shorten to ${fmt(s.speed_14kn.total_days.C5, 1)} days (C5) and ${fmt(s.speed_14kn.total_days.C3, 1)} days (C3); errors on the anchors: C3 RMSE ${fmt(s.speed_14kn.evaluation.C3.rmse, 2)} (bias ${fmtSigned(s.speed_14kn.evaluation.C3.bias, 2)}), C5 RMSE ${fmt(s.speed_14kn.evaluation.C5.rmse, 2)} (bias ${fmtSigned(s.speed_14kn.evaluation.C5.bias, 2)}) USD/t. The eco speed is kept because it matches published round-voyage durations, not because of these errors.`),
        el('li', {}, `On ${fmtDate(s.date)}: base C3 ${fmt(s.base.c3_voyage_usd_wmt, 2)}, C5 ${fmt(s.base.c5_voyage_usd_wmt, 2)} USD/wmt; at 14 knots ${fmt(s.speed_14kn.latest.c3_voyage_usd_wmt, 2)} and ${fmt(s.speed_14kn.latest.c5_voyage_usd_wmt, 2)}; port costs at 50% and 150%: C3 ${fmt(s.port_costs['0.5'].c3_voyage_usd_wmt, 2)} to ${fmt(s.port_costs['1.5'].c3_voyage_usd_wmt, 2)}, C5 ${fmt(s.port_costs['0.5'].c5_voyage_usd_wmt, 2)} to ${fmt(s.port_costs['1.5'].c5_voyage_usd_wmt, 2)}.`),
        el('li', {}, `Moisture ${fmtPct(d.moisture, 0)} converts freight per wet tonne to per dry tonne for netbacks and the bridge.`),
      ),
    ]],
    ['Data', () => [
      table('Out-of-sample errors, USD per tonne', [
        { label: 'Route', key: 'r' }, { label: 'Model', key: 'm' }, { label: 'n', key: 'n', num: true },
        { label: 'MAE', get: (x) => fmt(x.mae, 2), num: true }, { label: 'RMSE', get: (x) => fmt(x.rmse, 2), num: true },
        { label: 'Bias', get: (x) => fmtSigned(x.bias, 2), num: true },
        { label: '80% band', get: (x) => `${fmtSigned(x.rel_q10 * 100, 1)}% to ${fmtSigned(x.rel_q90 * 100, 1)}%`, num: true },
      ], ['C3', 'C5'].flatMap((r) => [
        { r, m: 'Voyage model', ...ev[r].voyage },
        { r, m: 'Regression, leave one out', ...ev[r].stat_loo },
      ])),
      table('Published route assessments against the models (USD per wet tonne)', [
        { label: 'Date', key: 'date' }, { label: 'Route', key: 'route' },
        { label: 'Published', get: (a) => fmt(a.value_usd_wmt, 2), num: true },
        { label: 'Voyage model', get: (a) => fmt(a.voyage_model, 2), num: true },
        { label: 'Error', get: (a) => fmtSigned(a.voyage_model - a.value_usd_wmt, 2), num: true },
        { label: 'Regression', get: (a) => fmt(a.stat_model_loo, 2), num: true },
        { label: 'Source', get: (a) => `${a.assessor}, ${a.reported_by}`, href: 'url' },
      ], d.anchors.slice().sort((x, y) => (x.date < y.date ? 1 : -1))),
    ]],
  ]);
}
