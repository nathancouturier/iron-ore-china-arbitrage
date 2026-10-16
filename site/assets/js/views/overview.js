import { getJSON, el, chartBlock, toggles, staleNotice } from '../app.js';
import { C, base, mount, fmt, fmtSigned, fmtPct, fmtDate, fmtMonth, reducedMotion, valueAxis, timeAxis, line, table, ttRow } from '../charts.js';

const stateWord = (s) => (s > 0 ? 'open' : s < 0 ? 'closed' : 'inside the band');

export async function render(root, meta) {
  const d = await getJSON('overview');
  const b = d.bridge;
  const P = d.params;
  const f = d.facts;
  const fx = b.usdcny;
  const state = f.margin.state;
  const verb = b.margin_rmb < 0 ? 'more than' : 'less than';
  const take = `On ${fmtDate(b.date)} a 62% Fe cargo landed in Qingdao cost ${fmt(b.landed_rmb)} RMB per dry tonne, ${fmt(Math.abs(b.margin_rmb))} RMB ${verb} Dalian pays for 45-day delivery: the import window is ${stateWord(state)}.`;
  root.append(
    staleNotice(meta, ['dce', 'sgx', 'baltic', 'fx']) || '',
    el('p', { class: 'takeaway' }, take),
    el('p', { class: 'subtake' },
      `Since 2016 the Dalian price has been below the delivered cost of seaborne ore on ${fmtPct(d.share_closed_daily, 0)} of trading days, by more than the ${fmt(d.band)} RMB/dmt cost of using the exchange. The margin is an expected margin, not a riskless arbitrage: price, basis, grade and currency risk remain while the cargo is at sea.`),
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
    sub: `Cost bridge on ${fmtDate(b.date)}, RMB per dry tonne (USD converted at ${fmt(fx, 4)} CNY per USD). Freight is modeled.`,
    source: `Sources: SGX iron ore futures (45-day horizon, 62% basis), Dalian Commodity Exchange via Sina, FRED (USD/CNY, SOFR), modeled freight from the Baltic Capesize Index and Brent. Data to ${fmtDate(b.date)}.`,
    summary: rows.map((r) => `${r.name}: ${fmt(r.v)} RMB/dmt`).join('; ') + `. Dalian minus landed cost: ${fmtSigned(b.margin_rmb)} RMB/dmt.`,
    cls: 'chart chart--tall',
  });
  const ledger = el('div', { class: 'ledger' },
    fact('Import margin, Dalian 45-day minus landed cost', fmtSigned(f.margin.value), 'RMB/dmt',
      [el('span', { class: `state state--${state > 0 ? 'open' : state < 0 ? 'closed' : 'inside'}` }, state > 0 ? 'Window open' : state < 0 ? 'Window closed' : 'Inside the band'),
        el('br'), `${fmtDate(f.margin.date)}, against a band of ±${fmt(d.band)} RMB/dmt. Monthly baseline ${fmtSigned(f.margin_monthly.value)} in ${fmtMonth(f.margin_monthly.month)}.`]),
    fact('Freight share of delivered cost, Australia', fmtPct(f.freight_share.value, 1), '',
      [`modeled C5 freight with its VAT, ${fmtDate(f.freight_share.date)}; ${fmtPct(f.freight_share.share_of_cfr, 1)} of the CFR price`]),
    fact('Rebar mill margin, futures-implied', fmtSigned(f.rebar_margin.value), 'RMB/t',
      [`RB minus 1.6 I minus 0.5 J minus other costs, most-active contracts, ${fmtDate(f.rebar_margin.date)}`]),
  );
  root.append(el('div', { class: 'grid grid--bridge' }, bridgeBlock, ledger));

  const SHORT = ['FOB Australia', 'Freight C5, modeled', 'FOB Brazil', 'Freight C3, modeled', 'CFR Qingdao', `VAT ${fmt(b.vat_rate * 100)}%`, 'Port charges', 'Financing', 'Landed cost', 'Dalian 45-day'];
  const narrow = bridgeHost.clientWidth < 520;
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
  const recentTitle = above === 0
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
      el('p', {}, 'The bridge starts from the 62% Fe CFR China benchmark (SGX iron ore futures interpolated to the same 45-day horizon as Dalian, lifted to a 62% basis for contract months from January 2026), converts it at the day’s USD/CNY, adds 13% import VAT on the CFR value (import duty on iron ore is zero), port charges converted from a wet to a dry basis, and the interest on the cargo while it is at sea. That landed cost is compared with the Dalian price for delivery 45 days ahead, expressed on a 62% Fe basis.'),
      el('p', {}, 'FOB values are index-equivalent netbacks: the CFR benchmark minus modeled freight, converted from per wet tonne to per dry tonne. Real Australian and Brazilian products trade at premiums or discounts to the 62% index (Pilbara Blend is 61.5% Fe, Brazilian fines are higher grade), which this view ignores.'),
      el('p', {}, 'A positive margin would mean onshore buyers pay more than the delivered cost of seaborne ore. Even then it is an expected margin: the cargo is priced weeks before it can be sold, and Dalian or SGX hedges reduce but do not remove price, basis, grade and currency risk.'),
    ]],
    ['Assumptions', () => [
      el('h3', {}, 'Assumptions behind these figures'),
      el('ul', {},
        el('li', {}, `Port charges ${fmt(P.port_charges_rmb_wmt)} RMB per wet tonne, moisture ${fmtPct(P.moisture, 0)} (sensitivity 6% to 10%).`),
        el('li', {}, `Financing: SOFR plus ${fmt(P.financing_spread_bp)} bp on the CFR value for the laden voyage plus ${fmt(P.financing_extra_days)} days.`),
        el('li', {}, `Dalian: ${fmt(P.cm_target_days)}-day constant maturity, interpolated between contracts with at least ${fmt(P.cm_min_oi_lots)} lots of open interest; 61% Fe contracts lifted by 10 × X = ${fmt(d.x_latest)} RMB/t.`),
        el('li', {}, `2026 SGX settlements are on Platts IODEX at 61% Fe; the CFR figure adds ${fmt(b.basis_adj_usd_dmt, 2)} USD/dmt, the mean 2026 gap between the IMF 62% benchmark and SGX final settlements (range ${fmt(d.sgx_basis.spread_2026_min, 2)} to ${fmt(d.sgx_basis.spread_2026_max, 2)} USD).`),
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
