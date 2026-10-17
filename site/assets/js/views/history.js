import { getJSON, el, chartBlock, toggles, staleNotice } from '../app.js';
import { C, base, mount, loadECharts, fmt, fmtSigned, fmtPct, fmtMonth, valueAxis, timeAxis, line, zoom, table, ttRow } from '../charts.js';

const ORIGIN_COLOR = () => ({ Australia: C.pilbara, Brazil: C.seawater, India: C.hematite, 'South Africa': C.topside, Other: C.steel });
const mid = (m) => `${m}-15`;
const mean = (xs) => { const v = xs.filter((x) => x !== null && !Number.isNaN(x)); return v.reduce((a, b) => a + b, 0) / v.length; };

export async function render(root, meta) {
  const d = await getJSON('history');
  const s = d.summary;
  const ratio = s.real_last_12m_mean / s.real_mean_1960_2003;
  root.append(
    staleNotice(meta, ['worldbank', 'wits', 'baltic', 'cpi']) || '',
    el('p', { class: 'takeaway' },
      `Over six decades seaborne iron ore went from a contract price set once a year for Brazilian ore to a daily spot price for delivery to China: in today’s dollars a tonne of 62% ore has cost about ${fmt(ratio, 1)} times its 1960 to 2003 average over the last twelve months (partly because the price now includes the freight to China), and China’s imports grew from ${fmt(s.imports_first_mt)} Mt in ${s.imports_first_year} to ${fmt(s.imports_last_mt)} Mt in ${s.imports_last_year}.`),
    el('p', { class: 'subtake' },
      `The import margin needs the Dalian futures, listed in October 2013, so its monthly series starts in January 2014; this view follows what can be measured further back: the seaborne price since ${fmtMonth(s.price_first_month)}, the delivered cost in RMB since ${fmtMonth(s.landed_first_month)}, China’s imports by origin since ${s.imports_first_year}, the Baltic Dry Index since 1988 and the Capesize index since 1999.`),
  );
  await loadECharts();
  root.append(priceBlock(d));
  root.append(el('div', { style: 'margin-top:16px' }, landedBlock(d)));
  root.append(el('div', { class: 'grid grid--two', style: 'margin-top:16px' }, importsBlock(d), unitValueBlock(d)));
  root.append(el('div', { style: 'margin-top:16px' }, balticBlock(d)));
  root.append(drawers(d));
}

// 1. Price since 1960 ------------------------------------------------------------------
function priceBlock(d) {
  const s = d.summary;
  const p = d.price;
  const contract = d.regimes.filter((r) => r.basis === 'contract_fob_brazil');
  const cEnd = contract[contract.length - 1].end;
  const { block, host } = chartBlock({
    title: `In today’s dollars ore has cost about ${fmt(s.real_last_12m_mean)} USD a tonne over the last twelve months, against ${fmt(s.real_mean_1960_2003)} on average from 1960 to 2003; the real peak was ${fmt(s.real_peak)} in ${fmtMonth(s.real_peak_month)}`,
    sub: `Iron ore, 62% Fe equivalent, USD per dry tonne, monthly: nominal and in dollars of ${fmtMonth(s.cpi_base)} (US CPI-U). Shaded to ${fmtMonth(cEnd)}: annual contract prices for Brazilian ore FOB Brazil, quoted per Fe unit and scaled to 62%; from ${fmtMonth(d.regimes.find((r) => r.basis === 'spot_cfr_china').start)}: spot price CFR China (63.5% Fe to November 2008, scaled to 62%). The change of basis in 2006 adds the sea freight to China. May 1965 is shown as published.`,
    source: `Sources: World Bank Commodity Price Data (Pink Sheet), iron ore, ${fmtMonth(p.months[0])} to ${fmtMonth(p.months[p.months.length - 1])}; US CPI-U via FRED (CPIAUCSL).`,
    summary: `Nominal 62% equivalent: ${fmt(p.nominal[0], 2)} in ${fmtMonth(p.months[0])}, peak ${fmt(s.nominal_peak, 1)} in ${fmtMonth(s.nominal_peak_month)}, ${fmt(p.nominal[p.nominal.length - 1], 1)} in ${fmtMonth(p.months[p.months.length - 1])}. Real: lowest annual average ${fmt(s.real_min_year_value, 1)} in ${s.real_min_year}, peak ${fmt(s.real_peak, 1)} in ${fmtMonth(s.real_peak_month)}.`,
    cls: 'chart chart--tall',
  });
  requestAnimationFrame(() => {
    mount(host, base({
      grid: { left: 60, right: 20, top: 40, bottom: 36 },
      dataZoom: zoom(),
      tooltip: { trigger: 'axis', formatter: (ps) => `${fmtMonth(ps[0].value[0].slice(0, 7))}${ps.map((q) => ttRow(q.color, `${fmt(q.value[1], 1)} USD/dmt`, q.seriesName)).join('')}` },
      xAxis: timeAxis(),
      yAxis: valueAxis('USD per dry tonne, 62% Fe equivalent', { scale: false }),
      series: [
        line(`Real, ${fmtMonth(s.cpi_base)} dollars`, p.months.map((m, i) => [mid(m), p.real[i]]), C.hematite, {
          markArea: { silent: true, itemStyle: { color: C.band }, label: { show: true, position: 'insideTopLeft', color: C.steel, fontFamily: C.font, fontSize: 11, formatter: 'Annual contract, FOB Brazil' }, data: [[{ xAxis: mid(contract[0].start) }, { xAxis: mid(cEnd) }]] },
        }),
        line('Nominal', p.months.map((m, i) => [mid(m), p.nominal[i]]), C.topside),
      ],
    }));
  });
  return block;
}

// 2. Delivered cost since 2006 ------------------------------------------------------------
function landedBlock(d) {
  const s = d.summary;
  const l = d.landed;
  const dIdx = l.dalian.findIndex((v) => v !== null);
  const { block, host } = chartBlock({
    title: `A 62% cargo cost ${fmt(s.landed_last)} RMB per dry tonne delivered in ${fmtMonth(s.landed_last_month)}, ${fmtPct(s.landed_last / s.landed_peak, 0)} of its ${fmtMonth(s.landed_peak_month)} peak of ${fmt(s.landed_peak)}`,
    sub: `Landed cost of a 62% Fe cargo from West Australia, RMB per dry tonne, VAT included, monthly: spot CFR China x USD/CNY x (1 + VAT) + port charges + financing. Import VAT 13% to December 2008, 17% from January 2009, 16% from May 2018, 13% from April 2019. Dalian 45-day 62% equivalent from ${fmtMonth(l.months[dIdx])}.`,
    source: `Sources: World Bank Pink Sheet (spot iron ore CFR China), FRED (USD/CNY, fed funds and SOFR), Dalian Commodity Exchange; VAT notices Caishui [1994] No. 22, Caiguanshui [2008] No. 99, Caishui [2018] No. 32 and Announcement [2019] No. 39. ${fmtMonth(l.months[0])} to ${fmtMonth(l.months[l.months.length - 1])}.`,
    summary: `Landed cost ${fmt(l.landed[0])} in ${fmtMonth(l.months[0])}, peak ${fmt(s.landed_peak)} in ${fmtMonth(s.landed_peak_month)}, ${fmt(s.landed_last)} in ${fmtMonth(s.landed_last_month)}.`,
  });
  requestAnimationFrame(() => {
    mount(host, base({
      grid: { left: 60, right: 20, top: 40, bottom: 36 },
      dataZoom: zoom(),
      tooltip: { trigger: 'axis', formatter: (ps) => `${fmtMonth(ps[0].value[0].slice(0, 7))}${ps.filter((q) => q.value[1] !== null).map((q) => ttRow(q.color, `${fmt(q.value[1])} RMB/dmt`, q.seriesName)).join('')}` },
      xAxis: timeAxis(),
      yAxis: valueAxis('RMB per dry tonne', { scale: false }),
      series: [
        line('Landed cost, VAT included', l.months.map((m, i) => [mid(m), l.landed[i]]), C.hematite),
        line('Dalian 45-day, 62% equivalent', l.months.map((m, i) => [mid(m), l.dalian[i]]), C.topside),
      ],
    }));
  });
  return block;
}

// 3. Imports by origin since 1992 ---------------------------------------------------------
function importsBlock(d) {
  const s = d.summary;
  const im = d.imports;
  const col = ORIGIN_COLOR();
  const { block, host } = chartBlock({
    title: `Australia supplies ${fmtPct(s.share_australia_last, 0)} of China’s imports and Brazil ${fmtPct(s.share_brazil_last, 0)}; India, ${fmtPct(s.share_india_peak, 0)} in ${s.share_india_peak_year}, is down to ${fmtPct(s.share_india_last, 0)}`,
    sub: 'China’s iron ore imports by origin, million tonnes a year (customs weight), HS 260111 (non-agglomerated ores and concentrates) and 260112 (agglomerated ore, mainly pellets).',
    source: `Sources: UN Comtrade via World Bank WITS, ${im.years[0]} to ${im.years[im.years.length - 1]}; matches the China Customs year totals within 1% from 2018.`,
    summary: im.years.filter((y, i) => i % 5 === 0 || i === im.years.length - 1).map((y) => `${y}: ${fmt(im.total_mt[im.years.indexOf(y)])} Mt`).join('; '),
  });
  requestAnimationFrame(() => {
    const narrow = host.clientWidth < 520;
    mount(host, base({
      grid: { left: 68, right: 12, top: narrow ? 56 : 40, bottom: 36 },
      legend: { top: 0, left: 0, data: im.origins },
      tooltip: { trigger: 'axis', formatter: (ps) => `${ps[0].axisValue}${ps.slice().reverse().map((q) => ttRow(q.color, `${fmt(q.value, 1)} Mt`, q.seriesName)).join('')}${ttRow(C.steel, `${fmt(im.total_mt[ps[0].dataIndex])} Mt`, 'Total')}` },
      xAxis: { type: 'category', data: im.years.map(String), axisLabel: { color: C.steel, fontFamily: C.font, interval: narrow ? 7 : 3 }, axisTick: { show: false }, axisLine: { lineStyle: { color: C.grid } } },
      yAxis: valueAxis('Million tonnes', { scale: false }),
      series: im.origins.map((o) => ({ type: 'bar', name: o, stack: 'imp', data: im.qty_mt[o], itemStyle: { color: col[o] }, barCategoryGap: '20%' })),
    }));
  });
  return block;
}

// 4. Unit value by origin -------------------------------------------------------------------
function unitValueBlock(d) {
  const im = d.imports;
  const i0 = im.years.indexOf(2010);
  const diff = im.years.map((_, i) => (im.unit_value.Brazil[i] ?? NaN) - (im.unit_value.Australia[i] ?? NaN));
  const since = mean(diff.slice(i0));
  const before = mean(diff.slice(0, i0));
  const { block, host } = chartBlock({
    title: `At the Chinese border Brazilian ore has cost ${fmt(Math.abs(since), 1)} USD a tonne ${since >= 0 ? 'more' : 'less'} than Australian on average since 2010 (${fmt(Math.abs(before), 1)} before)`,
    sub: 'Average customs value of China’s iron ore imports by origin, USD per tonne of customs weight (wet), CIF, so freight and grade both enter the gap.',
    source: `Sources: UN Comtrade via World Bank WITS (value / quantity), ${im.years[0]} to ${im.years[im.years.length - 1]}.`,
    summary: `Brazil minus Australia, USD per tonne: ${fmtSigned(before, 1)} on average ${im.years[0]} to 2009, ${fmtSigned(since, 1)} from 2010 to ${im.years[im.years.length - 1]}.`,
  });
  requestAnimationFrame(() => {
    const series = ['Australia', 'Brazil'].map((o) => line(o, im.years.map((y, i) => [String(y), im.unit_value[o][i]]), ORIGIN_COLOR()[o], { showSymbol: true, symbolSize: 5 }));
    series.push(line('All origins', im.years.map((y, i) => [String(y), im.unit_value_all[i]]), C.steel));
    mount(host, base({
      grid: { left: 68, right: 12, top: 40, bottom: 36 },
      tooltip: { trigger: 'axis', formatter: (ps) => `${ps[0].value[0]}${ps.map((q) => ttRow(q.color, `${fmt(q.value[1], 1)} USD/t`, q.seriesName)).join('')}` },
      xAxis: { type: 'category', data: im.years.map(String), axisLabel: { color: C.steel, fontFamily: C.font, interval: host.clientWidth < 520 ? 7 : 3 }, axisTick: { show: false }, axisLine: { lineStyle: { color: C.grid } } },
      yAxis: valueAxis('USD per tonne, CIF', { scale: false }),
      series,
    }));
  });
  return block;
}

// 5. Baltic indices since 1988 ----------------------------------------------------------
function balticBlock(d) {
  const s = d.summary;
  const b = d.baltic;
  const neg = b.months.filter((m, i) => b.bci[i] !== null && b.bci[i] <= 0);
  const { block, host } = chartBlock({
    title: `The Capesize index peaked at ${fmt(s.bci_peak)} points (monthly average) in ${fmtMonth(s.bci_peak_month)}${neg.length ? ` and fell below zero in ${neg.length > 1 ? `${fmtMonth(neg[0])} and ${fmtMonth(neg[neg.length - 1])}` : fmtMonth(neg[0])}` : ''}`,
    sub: 'Baltic Dry Index (from October 1988) and Baltic Capesize Index (from April 1999), monthly averages of the daily published values, index points on a logarithmic scale, which cannot show months below zero. The Capesize index has been rebased to larger reference vessels over time; it is shown as published.',
    source: `Sources: Baltic Exchange index values via East Money, ${fmtMonth(b.months[0])} to ${fmtMonth(b.months[b.months.length - 1])}.`,
    summary: `Capesize index peak ${fmt(s.bci_peak)} in ${fmtMonth(s.bci_peak_month)}; ${fmtMonth(b.months[b.months.length - 1])} average to date: BDI ${fmt(b.bdi[b.bdi.length - 1])}, BCI ${fmt(b.bci[b.bci.length - 1])}.`,
  });
  requestAnimationFrame(() => {
    mount(host, base({
      grid: { left: 64, right: 20, top: 40, bottom: 36 },
      dataZoom: zoom(),
      tooltip: { trigger: 'axis', formatter: (ps) => `${fmtMonth(ps[0].value[0].slice(0, 7))}${ps.filter((q) => q.value[1] !== null).map((q) => ttRow(q.color, `${fmt(q.value[1])} points`, q.seriesName)).join('')}` },
      xAxis: timeAxis(),
      yAxis: { ...valueAxis('Index points, log scale', { scale: true }), type: 'log', logBase: 10 },
      series: [
        line('Baltic Capesize Index', b.months.map((m, i) => [mid(m), b.bci[i]]), C.seawater),
        line('Baltic Dry Index', b.months.map((m, i) => [mid(m), b.bdi[i]]), C.topside),
      ],
    }));
  });
  return block;
}

function drawers(d) {
  const s = d.summary;
  const im = d.imports;
  return toggles('history', [
    ['Method', () => [
      el('h3', {}, 'One price axis across six decades'),
      el('p', {}, 'The World Bank iron ore series changes definition three times (1987, 2006 and December 2008). To 1986 it is the annual contract price of Itabira ore FOB Tubarão, from 1987 to 2005 the annual contract price of Carajás sinter feed FOB Ponta da Madeira, both in US cents per dry tonne unit (one unit is 1% Fe in a dry tonne); from 2006 it is a spot price CFR China in USD per dry tonne, at 63.5% Fe to November 2008 and 62% Fe after. Because contract ore was priced per Fe unit, a 62% tonne is 62 units: the chart multiplies the contract price by 0.62 and scales the 63.5% spot price by 62/63.5. The 2006 change of basis from FOB Brazil to CFR China is not adjusted, so the jump that year includes sea freight. The World Bank series shows 15.3 cents per unit in May 1965 against 10.2 in the months around it, inside an annual contract; the value is kept as published.'),
      el('p', {}, `Real prices divide by the US consumer price index (CPI-U, seasonally adjusted) and multiply by its ${fmtMonth(s.cpi_base)} value.`),
      el('p', {}, 'The delivered cost applies the landed-cost chain of the other views to the spot series: CFR x USD/CNY x (1 + import VAT) + port charges per dry tonne + financing (fed funds, then SOFR from April 2018, plus the spread over the West Australian voyage plus ten days). Import VAT on iron ore was 13% from 1 May 1994 to 31 December 2008 (Caishui [1994] No. 22) and 17% from 1 January 2009 (Caiguanshui [2008] No. 99, which lists every HS 2601 line).'),
      el('p', {}, 'Imports by origin sum HS 260111 (ores and concentrates) and 260112 (agglomerated ore, mainly pellets) as China reports them to UN Comtrade: quantity in tonnes of customs weight (wet) and value in US dollars, CIF. An origin missing from a year’s partner list reported no imports that year. From 2018 the partner totals match the China Customs year totals within 1% (Method and data, Cross-checks).'),
    ]],
    ['Assumptions', () => [
      el('ul', {},
        el('li', {}, `Port charges (${fmt(d.params.port_charges_rmb_wmt)} RMB per wet tonne) and the financing spread (${fmt(d.params.financing_spread_bp)} bp) are held at today’s assumptions for the whole period; how port charges have changed since 2006 is not measured here.`),
        el('li', {}, 'Per-Fe-unit scaling is linear for contract prices, which were quoted per unit, and assumes the per-unit price of Itabira or Carajás ore applies to a 62% ore; for spot quotes it ignores the market’s grade premiums, which have varied over time.'),
        el('li', {}, 'Contract prices are FOB Brazil and spot prices CFR China: the two eras are not on the same delivery basis.'),
        el('li', {}, 'Unit values divide customs value by customs weight, so they mix grades, lump, fines and pellets and include freight and insurance.'),
      ),
    ]],
    ['Data', () => [
      el('p', {}, 'Full series: ',
        el('a', { href: 'downloads/iron_ore_price_long_monthly.csv', download: '' }, 'price since 1960'), ', ',
        el('a', { href: 'downloads/landed_cost_long_monthly.csv', download: '' }, 'delivered cost since 2006'), ', ',
        el('a', { href: 'downloads/china_iron_ore_imports_by_origin_annual.csv', download: '' }, 'imports by origin'), ', ',
        el('a', { href: 'downloads/baltic_indices_monthly.csv', download: '' }, 'Baltic indices'), '.'),
      table('China iron ore imports by origin, million tonnes', [
        { label: 'Year', key: 'y' },
        ...im.origins.map((o) => ({ label: o, get: (r) => fmt(im.qty_mt[o][r.i], 1), num: true })),
        { label: 'Total', get: (r) => fmt(im.total_mt[r.i], 1), num: true },
      ], im.years.map((y, i) => ({ y: String(y), i })).reverse()),
      table('Iron ore price, annual average, USD per dry tonne (62% Fe equivalent)', [
        { label: 'Year', key: 'y' },
        { label: 'Nominal', get: (r) => fmt(r.n, 2), num: true },
        { label: `Real, ${fmtMonth(s.cpi_base)} dollars`, get: (r) => fmt(r.r, 2), num: true },
        { label: 'Basis', key: 'b' },
      ], annual(d)),
    ]],
  ]);
}

function annual(d) {
  const by = {};
  d.price.months.forEach((m, i) => {
    const y = m.slice(0, 4);
    (by[y] ||= { n: [], r: [] });
    by[y].n.push(d.price.nominal[i]);
    by[y].r.push(d.price.real[i]);
  });
  const spot = Number(d.regimes.find((r) => r.basis === 'spot_cfr_china').start.slice(0, 4));
  return Object.keys(by).sort().reverse().map((y) => ({ y, n: mean(by[y].n), r: mean(by[y].r), b: Number(y) >= spot ? 'Spot, CFR China' : 'Contract, FOB Brazil' }));
}
