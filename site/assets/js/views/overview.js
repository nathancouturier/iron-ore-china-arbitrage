import { getJSON, el, chartBlock, toggles, staleNotice } from '../app.js';
import { C, base, mount, loadECharts, fmt, fmtSigned, fmtPct, fmtDate, fmtMonth, reducedMotion, valueAxis, timeAxis, line, table, ttRow } from '../charts.js';

const stateWord = (s) => (s > 0 ? 'open' : s < 0 ? 'closed' : 'inside the band');

export async function render(root, meta) {
  const d = await getJSON('overview');
  const b = d.bridge;
  const P = d.params;
  const f = d.facts;
  const fx = b.usdcny;
  const state = f.margin.state;
  const verb = b.margin_rmb < 0 ? 'more than' : 'less than';
  const sens = d.sensitivity;
  const take = `On ${fmtDate(b.date)} a 62% Fe cargo bought for delivery to Qingdao in about 45 days cost ${fmt(b.landed_rmb)} RMB per dry tonne landed, ${fmt(Math.abs(b.margin_rmb))} RMB ${verb} Dalian pays for 45-day delivery: the import window is ${stateWord(state)}.`;
  const liftNote = sens.lift.lift_usd_dmt
    ? ` Without the 2026 lift of SGX prices from a 61% to a 62% Fe basis (${fmt(sens.lift.lift_usd_dmt, 2)} USD/dmt) the margin would be ${fmtSigned(sens.no_lift.margin_rmb_dmt)}, ${stateWord(sens.no_lift.state)}.`
    : '';
  const edge = (state < 0
    ? `The margin is ${fmt(-d.band - b.margin_rmb)} RMB/dmt beyond the band: a CFR price ${fmt(-sens.cfr_change_to_band_usd, 1)} USD/dmt lower would bring it inside, and ${fmt(-sens.cfr_change_to_open_usd, 1)} USD lower (or Dalian ${fmt(sens.dalian_change_to_open_rmb)} RMB higher) would open the window.`
    : state === 0
      ? `A CFR price ${fmt(-sens.cfr_change_to_open_usd, 1)} USD/dmt lower (or Dalian ${fmt(sens.dalian_change_to_open_rmb)} RMB higher) would open the window.`
      : '') + liftNote;
  root.append(
    staleNotice(meta, ['dce', 'sgx', 'baltic', 'fx']) || '',
    el('p', { class: 'takeaway' }, take),
    el('p', { class: 'subtake' },
      `${edge} Since 2016 the Dalian price has been below the delivered cost of seaborne ore on ${fmtPct(d.share_closed_daily, 0)} of trading days, by more than the ${fmt(d.band)} RMB/dmt cost of using the exchange. The margin is an expected margin, not a riskless arbitrage: price, basis, grade and currency risk remain while the cargo is at sea.`),
  );

  // Bridge, in voyage order: mine, sea, port, mill.
  const rows = [
    { name: 'FOB Australia, index-equivalent', base: 0, v: b.fob_australia_usd_dmt * fx, color: C.pilbara, usd: b.fob_australia_usd_dmt },
    { name: 'Freight C5 West Australia, modeled', base: b.fob_australia_usd_dmt * fx, v: b.freight_c5_usd_dmt * fx, color: C.pilbara, modeled: true, usd: b.freight_c5_usd_dmt, note: `${fmt(b.freight_c5_usd_wmt, 2)} USD/wmt` },
    { name: 'FOB Brazil, index-equivalent', base: 0, v: b.fob_brazil_usd_dmt * fx, color: C.seawater, usd: b.fob_brazil_usd_dmt },
    { name: 'Freight C3 Tubarao, modeled', base: b.fob_brazil_usd_dmt * fx, v: b.freight_c3_usd_dmt * fx, color: C.seawater, modeled: true, usd: b.freight_c3_usd_dmt, note: `${fmt(b.freight_c3_usd_wmt, 2)} USD/wmt` },
    { name: 'CFR Qingdao, 62% Fe', base: 0, v: b.goods_rmb, color: C.steel, usd: b.cfr_usd_dmt },
    { name: `Import VAT ${fmt(b.vat_rate * 100)}%`, base: b.goods_rmb, v: b.vat_rmb, color: '#8d99a2' },
    { name: 'Port charges', base: b.goods_rmb + b.vat_rmb, v: b.port_rmb, color: '#8d99a2' },
    { name: 'Financing, Australian voyage', base: b.goods_rmb + b.vat_rmb + b.port_rmb, v: b.financing_rmb, color: '#8d99a2' },
    { name: 'Landed cost, VAT included', base: 0, v: b.landed_rmb, color: C.hematite },
    { name: 'Dalian 62% equivalent, 45 days', base: 0, v: b.dce62_rmb, color: C.topside },
  ];
  const { block: bridgeBlock, host: bridgeHost } = chartBlock({
    title: `Delivered cost exceeds the Dalian price by ${fmt(Math.abs(b.margin_rmb))} RMB per dry tonne`,
    sub: `Cost bridge on ${fmtDate(b.date)}, RMB per dry tonne (USD converted at ${fmt(fx, 4)} CNY per USD, the New York noon rate of ${fmtDate(b.fx_observation)}${b.fx_observation < b.date ? ', carried forward' : ''}). Freight is modeled.`,
    source: `Sources: SGX iron ore futures (45-day horizon, 62% basis), Dalian Commodity Exchange via Sina, FRED (USD/CNY, SOFR), modeled freight from the Baltic Capesize Index and Brent. Data to ${fmtDate(b.date)}.`,
    summary: rows.map((r) => `${r.name}: ${fmt(r.v)} RMB/dmt`).join('; ') + `. Dalian minus landed cost: ${fmtSigned(b.margin_rmb)} RMB/dmt.`,
    cls: 'chart chart--tall',
  });
  const ledger = el('div', { class: 'ledger' },
    fact('Import margin, Dalian 45-day minus landed cost', fmtSigned(f.margin.value), 'RMB/dmt',
      [el('span', { class: `state state--${state > 0 ? 'open' : state < 0 ? 'closed' : 'inside'}` }, state > 0 ? 'Window open' : state < 0 ? 'Window closed' : 'Inside the band'),
        el('br'), `${fmtDate(f.margin.date)}, against a band of ±${fmt(d.band)} RMB/dmt; ${fmtSigned(sens.no_lift.margin_rmb_dmt)} without the 2026 basis lift. Monthly baseline ${fmtSigned(f.margin_monthly.value)} in ${fmtMonth(f.margin_monthly.month)}.`]),
    fact('Freight share of delivered cost, Australia', fmtPct(f.freight_share.value, 1), '',
      [`modeled C5 freight with its VAT, ${fmtDate(f.freight_share.date)}; ${fmtPct(f.freight_share.share_of_cfr, 1)} of the CFR price`]),
    fact('Rebar mill margin, futures-implied', fmtSigned(f.rebar_margin.value), 'RMB/t',
      [`RB minus 1.6 I minus 0.5 J minus other costs, most-active contracts, ${fmtDate(f.rebar_margin.date)}`]),
  );
  root.append(el('div', { class: 'grid grid--bridge' }, bridgeBlock, ledger));

  const SHORT = ['FOB Australia', 'Freight C5, modeled', 'FOB Brazil', 'Freight C3, modeled', 'CFR Qingdao', `VAT ${fmt(b.vat_rate * 100)}%`, 'Port charges', 'Financing', 'Landed cost', 'Dalian 45-day'];
  const narrow = bridgeHost.clientWidth < 520;
  await loadECharts();
  const cats = narrow ? SHORT : rows.map((r) => r.name);
  const anim = !reducedMotion();
  const chart = mount(bridgeHost, base({
    animation: anim,
    animationDuration: 500,
    animationEasing: 'cubicOut',
    grid: { left: 12, right: 64, top: 8, bottom: 40, containLabel: true },
    legend: { show: false },
    tooltip: {
      trigger: 'item',
      formatter: (p) => {
        const r = rows[p.dataIndex];
        const usd = r.usd !== undefined ? `<div style="color:${C.steel}">${fmt(r.usd, 2)} USD/dmt${r.note ? `, ${r.note}` : ''}</div>` : '';
        return `${ttRow(r.color, `${fmt(r.v, 1)} RMB/dmt`, r.name, r.modeled)}${usd}`;
      },
    },
    xAxis: valueAxis('RMB per dry tonne', { scale: false, min: 0, nameGap: 28, splitNumber: narrow ? 3 : 5, axisLabel: { color: C.steel, fontFamily: C.font, hideOverlap: true } }),
    yAxis: {
      type: 'category', data: cats, inverse: true,
      axisLine: { show: false }, axisTick: { show: false },
      axisLabel: { color: C.topside, fontFamily: C.font, fontSize: 12, width: narrow ? 118 : 210, overflow: 'break' },
    },
    series: [
      { type: 'bar', stack: 'b', data: rows.map((r) => r.base), itemStyle: { color: 'transparent' }, silent: true, tooltip: { show: false }, barMaxWidth: 22 },
      {
        type: 'bar', stack: 'b', barMaxWidth: 22,
        data: rows.map((r) => ({
          value: r.v,
          itemStyle: {
            color: r.modeled ? 'rgba(0,0,0,0)' : r.color,
            borderColor: r.modeled ? r.color : undefined,
            borderWidth: r.modeled ? 2 : 0,
            borderType: r.modeled ? [5, 3] : 'solid',
            borderRadius: [0, 3, 3, 0],
            decal: r.modeled ? { symbol: 'rect', dashArrayX: [1, 0], dashArrayY: [2, 5], rotation: Math.PI / 4, color: r.color, symbolSize: 1 } : null,
          },
        })),
        label: { show: true, position: 'right', color: C.topside, fontFamily: C.font, formatter: (p) => fmt(p.value), fontSize: 12 },
        animationDelay: (i) => (anim ? i * 90 : 0),
      },
    ],
  }));
  chart.setOption({ aria: { enabled: true, decal: { show: false } } });

  // Margin against its band, last twelve months.
  const rv = d.recent.filter((p) => p[1] !== null).map((p) => p[1]);
  const below = rv.filter((v) => v < -d.band).length;
  const above = rv.filter((v) => v > d.band).length;
  const recentTitle = below === rv.length
    ? `The margin stayed below the no-arbitrage band on every one of the last ${rv.length} trading days`
    : above === 0
    ? `The margin stayed below the no-arbitrage band on ${below} of the last ${rv.length} trading days and never rose above it`
    : `The margin was below the no-arbitrage band on ${below} and above it on ${above} of the last ${rv.length} trading days`;
  const { block: recentBlock, host: recentHost } = chartBlock({
    title: recentTitle,
    sub: `Dalian 45-day 62% equivalent minus landed cost, RMB per dry tonne, daily. Shaded: ±${fmt(d.band)} RMB/dmt band (exchange delivery, storage and outbound fees).`,
    source: `Sources: SGX, Dalian Commodity Exchange, FRED; computed by the pipeline. Data to ${fmtDate(b.date)}.`,
    summary: `Latest ${fmtSigned(b.margin_rmb)} RMB/dmt on ${fmtDate(b.date)}.`,
    cls: 'chart chart--short',
  });
  root.append(el('div', { style: 'margin-top:16px' }, recentBlock));
  mount(recentHost, base({
    grid: { left: 56, right: 20, top: 16, bottom: 32 },
    legend: { show: false },
    tooltip: { trigger: 'axis', formatter: (ps) => `${fmtDate(ps[0].value[0])}${ttRow(C.topside, `${fmtSigned(ps[0].value[1], 1)} RMB/dmt`, 'margin')}` },
    xAxis: timeAxis(),
    yAxis: valueAxis('RMB/dmt', { nameGap: 40, scale: false }),
    series: [
      line('Import margin', d.recent, C.topside, {
        markArea: { silent: true, itemStyle: { color: C.band }, data: [[{ yAxis: -d.band }, { yAxis: d.band }]] },
        markLine: { silent: true, symbol: 'none', lineStyle: { color: C.steel, width: 1, type: 'solid' }, label: { show: false }, data: [{ yAxis: 0 }] },
      }),
    ],
  }));

  root.append(toggles('overview', [
    ['Method', () => [
      el('h3', {}, 'How the bridge is built'),
      el('p', {}, 'The bridge starts from the 62% Fe CFR China benchmark (SGX iron ore futures interpolated to the same 45-day horizon as Dalian, lifted to a 62% basis for contract months from January 2026), converts it at the latest USD/CNY noon rate (FRED, carried forward over gaps of up to five business days; the bridge shows the date of the rate used), adds 13% import VAT on the CFR value (import duty on iron ore is zero), port charges converted from a wet to a dry basis, and the interest on the cargo over the laden voyage plus ten days for discharge, clearance and payment. That landed cost is compared with the Dalian price for delivery 45 days ahead, expressed on a 62% Fe basis.'),
      el('p', {}, 'FOB values are index-equivalent netbacks: the CFR benchmark minus modeled freight, converted from per wet tonne to per dry tonne. Real Australian and Brazilian products trade at premiums or discounts to the 62% index for their grade and impurities, which this view ignores.'),
      el('p', {}, 'A positive margin would mean onshore buyers pay more than the delivered cost of seaborne ore. Even then it is an expected margin: the cargo is priced weeks before it can be sold, and Dalian or SGX hedges reduce but do not remove price, basis, grade and currency risk.'),
    ]],
    ['Assumptions', () => [
      el('h3', {}, 'Assumptions behind these figures'),
      el('ul', {},
        el('li', {}, `Port charges ${fmt(P.port_charges_rmb_wmt)} RMB per wet tonne, moisture ${fmtPct(P.moisture, 0)} (sensitivity 6% to 10%).`),
        el('li', {}, `Financing: SOFR plus ${fmt(P.financing_spread_bp)} bp on the CFR value for the laden voyage plus ${fmt(P.financing_extra_days)} days.`),
        el('li', {}, `Dalian: ${fmt(P.cm_target_days)}-day constant maturity, interpolated between contracts with at least ${fmt(P.cm_min_oi_lots)} lots of open interest; 61% Fe contracts lifted by 10 × X = ${fmt(d.x_latest)} RMB/t.`),
        el('li', {}, `2026 SGX settlements are on Platts IODEX at 61% Fe; the CFR figure adds ${fmt(b.basis_adj_usd_dmt, 2)} USD/dmt, the mean gap between the IMF 62% monthly average and the SGX final settlement over the ${d.sgx_basis.spread_2026_months} measured 2026 months (range ${fmt(d.sgx_basis.spread_2026_min, 2)} to ${fmt(d.sgx_basis.spread_2026_max, 2)} USD). One constant is used for every 2026 contract month: the mean over the ${d.sgx_basis.spread_2026_months} months measured so far. The daily series first reaches a 2026 contract on ${fmtDate(d.sgx_basis.first_lifted_day)}, and the IMF average reaches FRED weeks after the month ends, so in the first months of the lifted period no 2026 spread had been published and the whole lift used later information; once one had, the constant differs from the mean then known by at most ${fmt(d.sgx_basis.spread_2026_realtime_max_diff, 1)} USD/dmt (about ${fmt(d.sgx_basis.spread_2026_realtime_max_diff * sens.slope_rmb_per_usd)} RMB/dmt of landed cost). The latest margin uses only published months.`),
        el('li', {}, `The window call depends on that lift. On ${fmtDate(sens.date)} the margin would be ${fmtSigned(sens.lift_min.margin_rmb_dmt)} at the smallest measured spread, ${fmtSigned(sens.lift_max.margin_rmb_dmt)} at the largest and ${fmtSigned(sens.no_lift.margin_rmb_dmt)} with no lift (${stateWord(sens.no_lift.state)}). Measured against the World Bank series instead of the IMF one, the 2026 spread averages ${fmtSigned(sens.lift_world_bank.lift_usd_dmt, 2)} USD and the margin would be ${fmtSigned(sens.lift_world_bank.margin_rmb_dmt)}; the World Bank series has run below the IMF series every month since September 2024 (by about 2 to 5 USD to July 2026), a gap not explained here, so the IMF series is used.`),
        el('li', {}, `Break-evens on ${fmtDate(sens.date)}: each 1 USD/dmt on CFR moves the landed cost by ${fmt(sens.slope_rmb_per_usd, 2)} RMB/dmt; CFR ${fmt(-sens.cfr_change_to_band_usd, 2)} USD lower brings the margin inside the band, ${fmt(-sens.cfr_change_to_open_usd, 2)} USD lower opens the window, as would Dalian ${fmt(sens.dalian_change_to_open_rmb, 1)} RMB higher.`),
        el('li', {}, 'Freight is modeled from the Baltic Capesize Index and Brent; see the Freight and origins view for its errors.'),
      ),
    ]],
    ['Data', () => [table(`Cost bridge on ${fmtDate(b.date)}`, [
      { label: 'Step', key: 'name' },
      { label: 'RMB/dmt', get: (r) => fmt(r.v, 1), num: true },
      { label: 'USD/dmt', get: (r) => (r.usd !== undefined ? fmt(r.usd, 2) : ''), num: true },
    ], rows.concat([{ name: 'Dalian minus landed cost', v: b.margin_rmb }]))]],
  ]));
}

function fact(label, value, unit, notes) {
  return el('div', { class: 'fact' },
    el('p', { class: 'fact__label' }, label),
    el('p', { class: 'fact__value' }, value, unit ? el('span', { class: 'fact__unit' }, unit) : null),
    el('p', { class: 'fact__note' }, ...notes),
  );
}
