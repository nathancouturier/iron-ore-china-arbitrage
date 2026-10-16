import { getJSON, el, chartBlock, toggles, staleNotice } from '../app.js';
import { C, base, mount, fmt, fmtSigned, fmtPct, fmtDate, valueAxis, timeAxis, line, presets, zoom, table, ttRow } from '../charts.js';

export async function render(root, meta) {
  const d = await getJSON('window');
  const s = d.stats_daily;
  const cm = d.convergence_monthly;
  const cd = d.convergence_daily;
  const last = d.daily.margin[d.daily.margin.length - 1];
  root.append(
    staleNotice(meta, ['dce', 'sgx', 'fx']) || '',
    el('p', { class: 'takeaway' },
      `The window has almost never been open: since December 2015 the margin was above +${fmt(d.band)} RMB/dmt on ${fmtPct(s.share_open, 1)} of trading days and below −${fmt(d.band)} on ${fmtPct(s.share_closed, 0)}, averaging ${fmtSigned(s.mean)} RMB/dmt.`),
    el('p', { class: 'subtake' },
      `Deviations from that average fade with a half-life of about ${fmt(cm.half_life, 1)} months on the monthly baseline (95% bootstrap interval ${fmt(cm.boot_half_life_lo, 1)} to ${fmt(cm.boot_half_life_hi, 1)}), but a unit root cannot be rejected on the monthly data (ADF p = ${fmt(cm.adf_p, 2)}), so the evidence for a stable equilibrium gap is weak there; on daily data the ADF p-value is ${fmt(cd.adf_p, 3)}.`),
  );

  // 1. Margin over time with band and annotated episodes
  const ev = d.events || [];
  const { block: b1, host: h1 } = chartBlock({
    title: 'Dalian has priced 45-day iron ore below the delivered cost of a 62% cargo for a decade',
    sub: `Import margin: Dalian 45-day 62% equivalent minus landed cost, RMB per dry tonne, daily. Shaded: ±${fmt(d.band)} RMB/dmt no-arbitrage band.`,
    source: `Sources: SGX iron ore futures (45-day CFR proxy), Dalian Commodity Exchange, FRED; computed by the pipeline. Data to ${fmtDate(last[0])}.`,
    summary: `Mean ${fmtSigned(s.mean)}; median ${fmtSigned(s.median)}; 5th to 95th percentile ${fmtSigned(s.p05)} to ${fmtSigned(s.p95)}; minimum ${fmtSigned(s.min)} on ${fmtDate(s.min_at)}; maximum ${fmtSigned(s.max)} on ${fmtDate(s.max_at)}.`,
    cls: 'chart chart--tall',
  });
  root.append(b1);
  const c1 = mount(h1, base({
    grid: { left: 60, right: 20, top: 36, bottom: 36 },
    dataZoom: zoom(),
    tooltip: { trigger: 'axis', formatter: (ps) => `${fmtDate(ps[0].value[0])}${ps.map((p) => ttRow(p.color, `${fmtSigned(p.value[1], 1)} RMB/dmt`, p.seriesName)).join('')}` },
    xAxis: timeAxis(),
    yAxis: valueAxis('RMB per dry tonne', { scale: false }),
    series: [
      line('Import margin (45-day Dalian)', d.daily.margin, C.topside, {
        markArea: { silent: true, itemStyle: { color: C.band }, data: [[{ yAxis: -d.band }, { yAxis: d.band }]] },
        markLine: { silent: true, symbol: 'none', lineStyle: { color: C.steel, width: 1 }, label: { show: false }, data: [{ yAxis: 0 }] },
        markPoint: {
          symbol: 'circle', symbolSize: 10, itemStyle: { color: C.hematite, borderColor: '#fff', borderWidth: 2 },
          label: { show: true, position: 'right', formatter: (p) => p.name, color: C.topside, fontFamily: C.font, fontSize: 11, width: 150, overflow: 'break' },
          data: ev.map((e) => ({ name: e.short, coord: [e.date, e.value] })),
        },
      }),
    ],
  }));
  presets(b1, c1, last[0], d.daily.margin[0][0]);
  if (ev.length) {
    b1.append(el('ol', { class: 'events' }, ...ev.map((e) => el('li', {},
      el('strong', {}, `${fmtDate(e.date)}, ${fmtSigned(e.value)} RMB/dmt. `), `${e.text} Sources: `,
      ...e.sources.flatMap((src, i) => [i ? '; ' : '', el('a', { href: src.url }, src.name)]), '.'))));
  }

  // 2. Naive against maturity-aligned
  const { block: b2, host: h2 } = chartBlock({
    title: 'Comparing with the most-active contract overstates the discount, because the curve is usually backwardated',
    sub: 'Import margin, RMB per dry tonne, monthly averages: against the 45-day constant-maturity Dalian price and against the most-active contract (about 100 days out).',
    source: 'Sources: Dalian Commodity Exchange annual files and Sina, IMF via FRED; computed by the pipeline.',
    summary: `Mean margin by Dalian maturity: 30 days ${fmtSigned(d.maturity['30'])}, 45 days ${fmtSigned(d.maturity['45'])}, 60 days ${fmtSigned(d.maturity['60'])}, 90 days ${fmtSigned(d.maturity['90'])}, most active ${fmtSigned(d.maturity.most_active)} RMB/dmt.`,
  });
  root.append(el('div', { class: 'grid grid--two', style: 'margin-top:16px' }, b2, histBlock(d)));
  const months = d.monthly.months.map((m) => `${m}-15`);
  mount(h2, base({
    grid: { left: 60, right: 20, top: 40, bottom: 36 },
    tooltip: { trigger: 'axis', formatter: (ps) => `${ps[0].value[0].slice(0, 7)}${ps.map((p) => ttRow(p.color, `${fmtSigned(p.value[1], 1)} RMB/dmt`, p.seriesName)).join('')}` },
    xAxis: timeAxis(),
    yAxis: valueAxis('RMB per dry tonne', { scale: false }),
    series: [
      line('45-day constant maturity', months.map((m, i) => [m, d.monthly.margin[i]]), C.topside),
      line('Most-active contract', months.map((m, i) => [m, d.monthly.naive[i]]), C.pilbara),
    ],
  }));

  // 3. Half-life and band sensitivity
  root.append(el('div', { class: 'panel', style: 'margin-top:16px' },
    el('h3', { class: 'chart-title' }, 'Gaps close slowly, and the statistical evidence that they close at all is weak on monthly data'),
    el('p', { class: 'chart-sub' }, 'AR(1) on the margin: m(t) = c + ρ m(t−1) + e. Half-life = ln(0.5) / ln(ρ). Intervals from 2,000 recursive residual bootstrap draws.'),
    el('div', { class: 'stats' },
      stat('Half-life, monthly baseline', `${fmt(cm.half_life, 1)} months`, `95% interval ${fmt(cm.boot_half_life_lo, 1)} to ${fmt(cm.boot_half_life_hi, 1)}; ρ = ${fmt(cm.rho, 3)}; n = ${cm.n}`),
      stat('ADF test, monthly', `${fmt(cm.adf_stat, 2)}`, `p = ${fmt(cm.adf_p, 3)}; 5% critical value ${fmt(cm.adf_crit_5pct, 2)}; ${cm.adf_lags} lags`),
      stat('Half-life, daily series', `${fmt(cd.half_life, 0)} trading days`, `95% interval ${fmt(cd.boot_half_life_lo, 0)} to ${fmt(cd.boot_half_life_hi, 0)}; ADF ${fmt(cd.adf_stat, 2)}, p = ${fmt(cd.adf_p, 3)}`),
    ),
    el('p', { class: 'source' }, 'Sources: computed by the pipeline from the margin series above (ironarb/stats.py).'),
  ));

  // 4. Tornado
  const t = d.tornado;
  const rows = t.rows.slice().reverse();
  const { block: b4, host: h4 } = chartBlock({
    title: 'Port charges and the band matter most; no reasonable assumption opens the window in the latest month',
    sub: `Change in the latest monthly margin net of the band (${t.period}, base ${fmtSigned(t.base_distance, 1)} RMB/dmt below the open threshold) when one assumption moves, RMB per dry tonne.`,
    source: 'Sources: computed by the pipeline (pipeline/analysis.py).',
    summary: t.rows.map((r) => `${r.assumption}: ${fmtSigned(r.low, 1)} to ${fmtSigned(r.high, 1)}`).join('; '),
  });
  root.append(el('div', { style: 'margin-top:16px' }, b4));
  mount(h4, base({
    grid: { left: 12, right: 40, top: 30, bottom: 40, containLabel: true },
    tooltip: { trigger: 'item', formatter: (p) => ttRow(p.color, `${fmtSigned(p.value, 1)} RMB/dmt`, `${rows[p.dataIndex].assumption}, ${p.seriesName.toLowerCase()}`) },
    legend: { top: 0, left: 0, data: ['Low value', 'High value'] },
    xAxis: valueAxis('RMB per dry tonne', { scale: false, nameGap: 28 }),
    yAxis: { type: 'category', data: rows.map((r) => r.assumption), axisLine: { show: false }, axisTick: { show: false }, axisLabel: { color: C.topside, fontFamily: C.font, width: 240, overflow: 'break' } },
    series: [
      { type: 'bar', name: 'Low value', data: rows.map((r) => r.low), itemStyle: { color: C.seawater, borderRadius: 3 }, barMaxWidth: 14, barGap: '20%' },
      { type: 'bar', name: 'High value', data: rows.map((r) => r.high), itemStyle: { color: C.hematite, borderRadius: 3 }, barMaxWidth: 14 },
    ],
  }));

  root.append(toggles('window', [
    ['Method', () => [
      el('h3', {}, 'Margin, maturity alignment and the band'),
      el('p', {}, 'Margin = Dalian 62% equivalent at a constant 45-day maturity minus the landed cost of 62% Fe fines (CFR x USD/CNY x (1 + VAT) + port charges + financing). The daily series uses SGX iron ore futures as the CFR proxy (from December 2015), interpolated to the same 45-day horizon between the two contracts whose month midpoints bracket it; the current-month contract is left out because it settles on the month's average and so lags the market; the monthly baseline uses the IMF 62% Fe CFR China monthly average (FRED PIORECRUSDM) against the monthly average of the daily Dalian 45-day price (from January 2014).'),
      el('p', {}, 'The constant-maturity price interpolates linearly in calendar days to expiry between the two contracts that bracket 45 days, using only contracts with at least 1,700 lots of open interest (one Capesize cargo) and more than five days to expiry. When no eligible contract expires before 45 days, the price is extrapolated along the slope of the two nearest eligible contracts. Before 2018 most liquidity sat in the January, May and September contracts, so extrapolation was needed on about two thirds of days; since 2019 the 45-day point is interpolated on most days.'),
      el('p', {}, 'The no-arbitrage band of ±25 RMB/dmt approximates the cost of using the exchange: delivery fee 0.5 RMB/t, warehouse storage 0.3 RMB/t per day (0.5 before 2021) for about a month, and the ship outbound fee cap of 12 RMB/t, about 21.5 to 27.5 RMB/t in total.'),
      el('p', {}, 'Episodes are the largest deviations of the margin from its average, one per period of at least six months.'),
    ]],
    ['Assumptions', () => [
      el('ul', {},
        el('li', {}, `Band: shares of trading days above, inside and below it for a band of 15, 25 and 35 RMB/dmt: ${Object.entries(d.band_sensitivity).map(([k, v]) => `±${fmt(Number(k))}: ${fmtPct(v.share_open, 1)} open, ${fmtPct(v.share_inside, 1)} inside`).join('; ')}.`),
        el('li', {}, `FX: using the PBoC central parity instead of the New York noon rate changes the monthly margin by ${fmtSigned(d.fx_effect.monthly_mean_diff_central_parity_minus_dexchus, 2)} RMB/dmt on average.`),
        el('li', {}, 'Stationarity tests use the full sample; the 2021 policy shock dominates the variance.'),
      ),
    ]],
    ['Data', () => [
      table('Import margin, monthly baseline (RMB per dry tonne)', [
        { label: 'Month', key: 'm' }, { label: '45-day', get: (r) => fmt(r.a, 1), num: true }, { label: 'Most active', get: (r) => fmt(r.b, 1), num: true },
      ], d.monthly.months.map((m, i) => ({ m, a: d.monthly.margin[i], b: d.monthly.naive[i] })).reverse()),
    ]],
  ]));
}

function histBlock(d) {
  const { block, host } = chartBlock({
    title: 'Most days sit 40 to 120 RMB below delivered cost; days above the band are rare',
    sub: 'Distribution of the daily import margin, number of trading days per 20 RMB/dmt bin.',
    source: 'Sources: computed by the pipeline from the daily margin.',
    summary: d.histogram.counts.map((c, i) => `${d.histogram.edges[i]} to ${d.histogram.edges[i + 1]}: ${c}`).join('; '),
  });
  requestAnimationFrame(() => {
    const centers = d.histogram.counts.map((_, i) => (d.histogram.edges[i] + d.histogram.edges[i + 1]) / 2);
    mount(host, base({
      grid: { left: 52, right: 16, top: 16, bottom: 44 },
      legend: { show: false },
      tooltip: { trigger: 'axis', formatter: (ps) => ttRow(C.steel, `${ps[0].value} days`, `${fmt(Number(ps[0].name) - 10)} to ${fmt(Number(ps[0].name) + 10)} RMB/dmt`) },
      xAxis: { type: 'category', data: centers.map(String), name: 'RMB per dry tonne', nameLocation: 'middle', nameGap: 28, axisLabel: { color: C.steel, interval: 4, formatter: (v) => fmt(Number(v)) }, axisTick: { show: false }, axisLine: { lineStyle: { color: C.grid } } },
      yAxis: valueAxis('Trading days', { scale: false, nameGap: 36 }),
      series: [{ type: 'bar', data: d.histogram.counts.map((c, i) => ({ value: c, itemStyle: { color: centers[i] > d.band ? C.seawater : centers[i] < -d.band ? C.hematite : C.steel, borderRadius: [3, 3, 0, 0] } })), barCategoryGap: '8%' }],
    }));
  });
  return block;
}

function stat(label, value, note) {
  return el('div', { class: 'stat' }, el('p', { class: 'stat__label' }, label), el('p', { class: 'stat__value' }, value), el('p', { class: 'stat__note' }, note));
}
