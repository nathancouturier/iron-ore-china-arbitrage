import { getJSON, el, chartBlock, toggles, staleNotice } from '../app.js';
import { C, base, mount, loadECharts, fmt, fmtSigned, fmtPct, fmtDate, fmtMonth, valueAxis, timeAxis, line, presets, zoom, table, ttRow } from '../charts.js';

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
      `On the monthly baseline, gaps from the margin's long-run level (${fmtSigned(cm.long_run_mean)} RMB/dmt) fade with a half-life of about ${fmt(cm.half_life, 1)} months (95% bootstrap interval ${fmt(cm.boot_half_life_lo, 1)} to ${fmt(cm.boot_half_life_hi, 1)}), but a unit root cannot be rejected there (ADF p = ${fmt(cm.adf_p, 2)}), so the evidence for a stable gap is weak; on the daily series the half-life is ${fmt(cd.half_life)} trading days and the ADF p-value ${fmt(cd.adf_p, 3)}.`),
  );

  // 1. Margin over time with band and annotated episodes
  const ev = d.events || [];
  const { block: b1, host: h1 } = chartBlock({
    title: 'Dalian has priced 45-day iron ore below the delivered cost of a 62% cargo for a decade',
    sub: `Import margin: Dalian 45-day 62% equivalent minus landed cost, RMB per dry tonne, daily. Shaded: ±${fmt(d.band)} RMB/dmt no-arbitrage band. Numbered: the three largest episodes, explained below.`,
    source: `Sources: SGX iron ore futures (45-day CFR proxy), Dalian Commodity Exchange, FRED; computed by the pipeline. Data to ${fmtDate(last[0])}.`,
    summary: `Mean ${fmtSigned(s.mean)}; median ${fmtSigned(s.median)}; 5th to 95th percentile ${fmtSigned(s.p05)} to ${fmtSigned(s.p95)}; minimum ${fmtSigned(s.min)} on ${fmtDate(s.min_at)}; maximum ${fmtSigned(s.max)} on ${fmtDate(s.max_at)}.`,
    cls: 'chart chart--tall',
  });
  root.append(b1);
  await loadECharts();
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
          symbol: 'circle', symbolSize: 20, itemStyle: { color: C.hematite, borderColor: '#fff', borderWidth: 2 },
          label: { show: true, position: 'inside', formatter: (p) => p.name, color: '#ffffff', fontFamily: C.font, fontSize: 11, fontWeight: 700 },
          tooltip: { show: false },
          data: ev.map((e, i) => ({ name: String(i + 1), coord: [e.date, e.value] })),
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
  // The monthly baseline prices the cargo at the spot index average; the daily series uses
  // SGX futures at the same 45-day horizon as Dalian, so the two part in steep backwardation.
  let gi = 0;
  d.monthly.months.forEach((_, i) => {
    const g = Math.abs((d.monthly.margin[i] ?? 0) - (d.monthly.daily_avg[i] ?? d.monthly.margin[i] ?? 0));
    const best = Math.abs((d.monthly.margin[gi] ?? 0) - (d.monthly.daily_avg[gi] ?? d.monthly.margin[gi] ?? 0));
    if (d.monthly.daily_avg[i] !== null && g > best) gi = i;
  });
  const gapText = `It prices the cargo at the spot index average, while the daily series uses SGX futures at the same 45-day horizon as Dalian, so the two part when the curve is steeply backwardated: ${fmtMonth(d.monthly.months[gi])} is ${fmtSigned(d.monthly.margin[gi])} here and ${fmtSigned(d.monthly.daily_avg[gi])} as the average of the daily margin.`;
  const { block: b2, host: h2 } = chartBlock({
    title: 'Comparing with the most-active contract overstates the discount, because the curve is usually backwardated',
    sub: `Monthly baseline (IMF 62% CFR monthly average), RMB per dry tonne: against the 45-day constant-maturity Dalian price and against the most-active contract (${fmt(d.ma_dte_mean)} days to expiry on average). ${gapText}`,
    source: `Sources: IMF 62% Fe CFR via FRED, Dalian Commodity Exchange annual files and Sina, FRED (USD/CNY, SOFR). Monthly, ${fmtMonth(d.monthly.months[0])} to ${fmtMonth(d.monthly.months[d.monthly.months.length - 1])}.`,
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
    el('p', { class: 'source' }, `Sources: the monthly baseline (${fmtMonth(d.monthly.months[0])} to ${fmtMonth(d.monthly.months[d.monthly.months.length - 1])}) and the daily margin (to ${fmtDate(last[0])}) above.`),
  ));

  // 4. Tornado
  const t = d.tornado;
  const rows = t.rows.slice().reverse();
  const { block: b4, host: h4 } = chartBlock({
    title: `${t.rows[0].assumption.split(' (')[0]} and the ${t.rows[1].assumption.split(' (')[0].toLowerCase()} matter most; ${Math.max(...t.rows.map((r) => Math.max(r.low, r.high ?? -Infinity))) < -t.base_distance ? 'no single assumption in its range opens the window' : 'one assumption in its range would open the window'} in ${fmtMonth(t.period)}`,
    sub: `Change in the latest monthly margin when one assumption moves, RMB per dry tonne. In ${fmtMonth(t.period)} the margin sits ${fmt(-t.base_distance, 1)} RMB/dmt below the +${fmt(d.band)} open threshold.`,
    source: `Sources: IMF via FRED, Dalian Commodity Exchange, FRED, SAFE (central parity). ${fmtMonth(t.period)}.`,
    summary: t.rows.map((r) => (r.high === null ? `${r.assumption}: ${fmtSigned(r.low, 1)}` : `${r.assumption}: ${fmtSigned(r.low, 1)} to ${fmtSigned(r.high, 1)}`)).join('; '),
  });
  root.append(el('div', { style: 'margin-top:16px' }, b4));
  const narrow4 = h4.clientWidth < 520;
  mount(h4, base({
    grid: { left: 12, right: narrow4 ? 16 : 40, top: 30, bottom: 40, containLabel: true },
    tooltip: { trigger: 'item', formatter: (p) => ttRow(p.color, `${fmtSigned(p.value, 1)} RMB/dmt`, `${rows[p.dataIndex].assumption}, ${p.seriesName.toLowerCase()}`) },
    legend: { top: 0, left: 0, data: ['Low value', 'High value', 'Alternative'] },
    xAxis: valueAxis('RMB per dry tonne', { scale: false, nameGap: 28, splitNumber: narrow4 ? 3 : 6, axisLabel: { color: C.steel, fontFamily: C.font, hideOverlap: true } }),
    yAxis: { type: 'category', data: rows.map((r) => r.assumption), axisLine: { show: false }, axisTick: { show: false }, axisLabel: { color: C.topside, fontFamily: C.font, fontSize: narrow4 ? 11 : 12, width: narrow4 ? 120 : 240, overflow: 'break' } },
    series: [
      { type: 'bar', name: 'Low value', stack: 'lo', data: rows.map((r) => (r.high === null ? null : r.low)), itemStyle: { color: C.seawater, borderRadius: 3 }, barMaxWidth: 14, barGap: '20%' },
      { type: 'bar', name: 'Alternative', stack: 'lo', data: rows.map((r) => (r.high === null ? r.low : null)), itemStyle: { color: C.steel, borderRadius: 3 }, barMaxWidth: 14 },
      { type: 'bar', name: 'High value', data: rows.map((r) => r.high), itemStyle: { color: C.hematite, borderRadius: 3 }, barMaxWidth: 14 },
    ],
  }));

  root.append(toggles('window', [
    ['Method', () => [
      el('h3', {}, 'Margin, maturity alignment and the band'),
      el('p', {}, 'Margin = Dalian 62% equivalent at a constant 45-day maturity minus the landed cost of 62% Fe fines (CFR x USD/CNY x (1 + VAT) + port charges + financing). The daily series uses SGX iron ore futures as the CFR proxy (from December 2015), interpolated to the same 45-day horizon between the two contracts whose month midpoints bracket it; the current-month contract is left out because it settles on the month’s average and so lags the market; the monthly baseline uses the IMF 62% Fe CFR China monthly average (FRED PIORECRUSDM) against the monthly average of the daily Dalian 45-day price (from January 2014).'),
      el('p', {}, 'The constant-maturity price interpolates linearly in calendar days to expiry between the two contracts that bracket 45 days, using only contracts with at least 1,700 lots of open interest (one Capesize cargo) and more than five days to expiry. When no eligible contract expires before 45 days, the price is extrapolated along the slope of the two nearest eligible contracts. Before 2018 most liquidity sat in the January, May and September contracts, so extrapolation was needed on about two thirds of days; since 2019 the 45-day point is interpolated on most days.'),
      el('p', {}, 'The no-arbitrage band of ±25 RMB/dmt approximates the cost of using the exchange: delivery fee 0.5 RMB/t, warehouse storage 0.3 RMB/t per day (0.5 before 2021) for about a month, and the ship outbound fee cap of 12 RMB/t, about 21.5 to 27.5 RMB/t in total.'),
      el('p', {}, 'Episodes are the largest deviations of the margin from its average, one per period of at least six months.'),
      el('p', {}, 'Two comparisons answer slightly different questions. The daily series is the hedgeable one: a cargo priced on the index average around arrival, hedged on SGX, against Dalian at the same horizon. The monthly baseline follows the textbook framing: a cargo bought at the spot index, sold on Dalian 45 days later. In steep backwardation (2021) spot CFR sits well above the 45-day SGX price, so the monthly baseline shows a deeper discount.'),
    ]],
    ['Assumptions', () => [
      el('ul', {},
        el('li', {}, `Band: shares of trading days above, inside and below it for a band of 15, 25 and 35 RMB/dmt: ${Object.entries(d.band_sensitivity).map(([k, v]) => `±${fmt(Number(k))}: ${fmtPct(v.share_open, 1)} open, ${fmtPct(v.share_inside, 1)} inside`).join('; ')}.`),
        el('li', {}, `FX: using the PBoC central parity instead of the New York noon rate changes the monthly margin by ${fmtSigned(d.fx_effect.monthly_mean_diff_central_parity_minus_dexchus, 2)} RMB/dmt on average.`),
        el('li', {}, 'Stationarity tests use the full sample; the 2021 policy shock dominates the variance.'),
      ),
    ]],
    ['Data', () => [
      el('p', {}, 'Full daily and monthly series: ', el('a', { href: 'downloads/import_margin_daily.csv', download: '' }, 'daily CSV'), ', ', el('a', { href: 'downloads/import_margin_monthly.csv', download: '' }, 'monthly CSV'), '.'),
      table('Import margin, monthly baseline (RMB per dry tonne)', [
        { label: 'Month', key: 'm' }, { label: '45-day', get: (r) => fmt(r.a, 1), num: true }, { label: 'Most active', get: (r) => fmt(r.b, 1), num: true },
      ], d.monthly.months.map((m, i) => ({ m, a: d.monthly.margin[i], b: d.monthly.naive[i] })).reverse()),
    ]],
  ]));
}

function histBlock(d) {
  const s = d.stats_daily;
  const e = d.histogram.edges;
  const w = e[1] - e[0];
  const n = d.histogram.counts.reduce((a, b) => a + b, 0);
  const { block, host } = chartBlock({
    title: `Half of all trading days sit between ${fmt(-s.p75)} and ${fmt(-s.p25)} RMB below delivered cost; ${fmtPct(s.share_open, 1)} sit above the band`,
    sub: `Distribution of the daily import margin, number of trading days per ${fmt(w)} RMB/dmt bin; bin edges fall on −${fmt(d.band)} and +${fmt(d.band)}. Red: below the band (window closed); grey: inside it; blue: above it (window open).`,
    source: `Sources: SGX, Dalian Commodity Exchange, FRED. ${fmt(n)} trading days, ${fmtDate(d.daily.margin[0][0])} to ${fmtDate(d.daily.margin[d.daily.margin.length - 1][0])}.`,
    summary: d.histogram.counts.map((c, i) => `${fmt(e[i])} to ${fmt(e[i + 1])}: ${c}`).join('; '),
  });
  requestAnimationFrame(() => {
    const lows = d.histogram.counts.map((_, i) => e[i]);
    const tick = host.clientWidth < 520 ? 200 : 100;
    mount(host, base({
      grid: { left: 52, right: 16, top: 16, bottom: 44 },
      legend: { show: false },
      tooltip: { trigger: 'axis', formatter: (ps) => { const i = ps[0].dataIndex; return ttRow(ps[0].color, `${fmt(ps[0].value)} days`, `${fmt(e[i])} to ${fmt(e[i + 1])} RMB/dmt`); } },
      xAxis: { type: 'category', data: lows.map(String), name: 'RMB per dry tonne', nameLocation: 'middle', nameGap: 28, axisLabel: { color: C.steel, interval: 0, formatter: (v) => (Number(v) % tick === 0 ? fmt(Number(v)) : '') }, axisTick: { show: false }, axisLine: { lineStyle: { color: C.grid } } },
      yAxis: valueAxis('Trading days', { scale: false, nameGap: 36 }),
      series: [{ type: 'bar', data: d.histogram.counts.map((c, i) => ({ value: c, itemStyle: { color: e[i] >= d.band ? C.seawater : e[i + 1] <= -d.band ? C.hematite : C.steel, borderRadius: [3, 3, 0, 0] } })), barCategoryGap: '8%' }],
    }));
  });
  return block;
}

function stat(label, value, note) {
  return el('div', { class: 'stat' }, el('p', { class: 'stat__label' }, label), el('p', { class: 'stat__value' }, value), el('p', { class: 'stat__note' }, note));
}
