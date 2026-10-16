import { getJSON, el, chartBlock, toggles } from '../app.js';
import { C, base, mount, loadECharts, fmt, fmtSigned, fmtPct, fmtDate, valueAxis, ttRow } from '../charts.js';
import { calculate, vatRate } from '../engine.js';

const FIELDS = [
  ['cfrUsdDmt', 'CFR 62% Fe, USD/dmt', 0.05, 'Seaborne benchmark, cost and freight Qingdao'],
  ['usdcny', 'USD/CNY', 0.0001, 'CNY per USD'],
  ['vat', 'Import VAT', 0.01, '0.13 since 1 April 2019'],
  ['portRmbWmt', 'Port charges, RMB/wmt', 1, 'Per wet tonne handled'],
  ['moisture', 'Moisture', 0.005, 'Share of wet weight'],
  ['freightUsdWmt', 'Freight, USD/wmt', 0.05, 'Capesize voyage rate'],
  ['usdRatePct', 'USD rate, %', 0.01, 'SOFR (fed funds before April 2018)'],
  ['spreadBp', 'Finance spread, bp', 5, 'Over the USD rate'],
  ['financingDays', 'Financing days', 0.5, 'Laden voyage plus 10 days'],
  ['dce62RmbDmt', 'Dalian 62% equivalent, RMB/dmt', 0.5, 'At the matching maturity'],
  ['band', 'No-arbitrage band, RMB/dmt', 1, 'Exchange delivery costs'],
];

export async function render(root) {
  const d = await getJSON('calculator');
  const state = { ...d.defaults, route: 'C5', ...d.routes.C5 };
  root.append(
    el('p', { class: 'takeaway' }, 'Change any input to see the landed cost and the import margin move, with the same formulas the study uses.'),
    el('p', { class: 'subtake' }, `Defaults are the latest values in the data (${fmtDate(d.defaults.date)}). The calculator runs in your browser; a parity test checks it against the Python engine to 1e-9.`),
  );

  const form = el('form', { class: 'panel', onsubmit: (e) => e.preventDefault(), 'aria-label': 'Calculator inputs' });
  const routeSel = el('select', { id: 'f-route' },
    ...Object.entries(d.routes).map(([k, r]) => el('option', { value: k, selected: k === 'C5' }, r.label)));
  form.append(el('h3', { class: 'chart-title' }, 'Inputs'),
    el('div', { class: 'fields' },
      el('div', { class: 'field' }, el('label', { for: 'f-route' }, 'Route'), routeSel, el('small', {}, 'Sets freight and financing days')),
      el('div', { class: 'field' }, el('label', { for: 'f-date' }, 'VAT date'), el('input', { id: 'f-date', type: 'date', value: d.defaults.date }), el('small', {}, 'Sets the VAT rate by schedule')),
      ...FIELDS.map(([k, label, step, help]) => el('div', { class: 'field' },
        el('label', { for: `f-${k}` }, label),
        el('input', { id: `f-${k}`, type: 'number', inputmode: 'decimal', step: String(step), value: String(state[k]) }),
        el('small', {}, help))),
    ),
    el('button', { type: 'button', class: 'btn', id: 'f-reset', style: 'margin-top:12px' }, 'Reset to latest data'),
  );

  const out = el('div', { class: 'ledger', 'aria-live': 'polite' });
  const { block, host } = chartBlock({
    title: 'Landed cost against the Dalian price',
    sub: 'RMB per dry tonne, from your inputs.',
    source: 'Computed in the browser with site/assets/js/engine.js.',
    summary: 'Updates as inputs change.',
    cls: 'chart',
  });
  root.append(el('div', { class: 'calc' }, form, el('div', {}, out, el('div', { style: 'margin-top:16px' }, block))));
  await loadECharts();
  const chart = mount(host, base({ animation: false }));

  const read = () => {
    for (const [k] of FIELDS) state[k] = Number(document.getElementById(`f-${k}`).value);
  };
  const update = () => {
    read();
    const r = calculate(state);
    const st = r.state > 0 ? ['Window open', 'open'] : r.state < 0 ? ['Window closed', 'closed'] : ['Inside the band', 'inside'];
    out.replaceChildren(
      factEl('Landed cost, VAT included', `${fmt(r.landedRmb, 1)}`, 'RMB/dmt', `Goods ${fmt(r.goodsRmb, 1)}, VAT ${fmt(r.vatRmb, 1)}, port ${fmt(r.portRmb, 1)}, financing ${fmt(r.financingRmb, 2)}`),
      factEl('Import margin, Dalian minus landed', fmtSigned(r.marginRmb, 1), 'RMB/dmt', null, st),
      factEl('FOB netback, index-equivalent', fmt(r.fobUsdDmt, 2), 'USD/dmt', `Freight ${fmt(r.freightUsdDmt, 2)} USD/dmt is ${fmtPct(r.freightShareOfLanded, 1)} of landed cost with its VAT`),
    );
    const rows = [
      ['CFR, converted', 0, r.goodsRmb, C.steel], ['Import VAT', r.goodsRmb, r.vatRmb, '#8d99a2'], ['Port charges', r.goodsRmb + r.vatRmb, r.portRmb, '#8d99a2'],
      ['Financing', r.goodsRmb + r.vatRmb + r.portRmb, r.financingRmb, '#8d99a2'], ['Landed cost', 0, r.landedRmb, C.hematite], ['Dalian 62% equivalent', 0, state.dce62RmbDmt, C.topside],
    ];
    chart.setOption({
      grid: { left: 12, right: 64, top: 8, bottom: 40, containLabel: true },
      legend: { show: false },
      tooltip: { trigger: 'item', formatter: (p) => ttRow(rows[p.dataIndex][3], `${fmt(rows[p.dataIndex][2], 1)} RMB/dmt`, rows[p.dataIndex][0]) },
      xAxis: valueAxis('RMB per dry tonne', { scale: false, min: 0, nameGap: 28 }),
      yAxis: { type: 'category', inverse: true, data: rows.map((x) => x[0]), axisLine: { show: false }, axisTick: { show: false }, axisLabel: { color: C.topside, fontFamily: C.font } },
      series: [
        { type: 'bar', stack: 'b', data: rows.map((x) => x[1]), itemStyle: { color: 'transparent' }, silent: true, tooltip: { show: false }, barMaxWidth: 22 },
        { type: 'bar', stack: 'b', data: rows.map((x) => ({ value: x[2], itemStyle: { color: x[3], borderRadius: [0, 3, 3, 0] } })), barMaxWidth: 22,
          label: { show: true, position: 'right', formatter: (p) => fmt(p.value, 1), color: C.topside, fontFamily: C.font } },
      ],
    }, true);
  };
  const setRoute = (code) => {
    state.route = code;
    for (const k of ['freightUsdWmt', 'financingDays']) {
      state[k] = d.routes[code][k];
      document.getElementById(`f-${k}`).value = String(state[k]);
    }
  };
  routeSel.addEventListener('change', () => { setRoute(routeSel.value); update(); });
  document.getElementById('f-date').addEventListener('change', (e) => {
    if (!e.target.value) return;
    document.getElementById('f-vat').value = String(vatRate(e.target.value));
    update();
  });
  form.addEventListener('input', (e) => { if (e.target.type === 'number') update(); });
  document.getElementById('f-reset').addEventListener('click', () => {
    Object.assign(state, d.defaults, d.routes.C5, { route: 'C5' });
    routeSel.value = 'C5';
    document.getElementById('f-date').value = d.defaults.date;
    for (const [k] of FIELDS) document.getElementById(`f-${k}`).value = String(state[k]);
    update();
  });
  update();

  root.append(toggles('calculator', [
    ['Method', () => [
      el('p', {}, 'Landed cost = CFR x USD/CNY x (1 + VAT) + port charges / (1 − moisture) + CFR x (USD rate + spread) x financing days / 360 x USD/CNY. Import margin = Dalian 62% equivalent − landed cost. FOB netback = CFR − freight / (1 − moisture). Freight is paid per wet tonne; CFR and Dalian are per dry tonne.'),
    ]],
    ['Assumptions', () => [el('p', {}, 'Defaults come from the latest data and the study parameters (port charges 30 RMB/wmt, moisture 8%, spread 150 bp, band 25 RMB/dmt). Customs value is approximated by CFR: China Customs deems insurance at 0.3% of goods plus freight when unknown (Article 36, GACC Order 213), which would add about 0.3 RMB/dmt of VAT plus the premium itself.')]],
    ['Data', () => [el('p', {}, `Latest inputs (${fmtDate(d.defaults.date)}): CFR ${fmt(d.defaults.cfrUsdDmt, 2)} USD/dmt, USD/CNY ${fmt(d.defaults.usdcny, 4)}, USD rate ${fmt(d.defaults.usdRatePct, 2)}%, Dalian 62% equivalent ${fmt(d.defaults.dce62RmbDmt, 1)} RMB/dmt; C5 freight ${fmt(d.routes.C5.freightUsdWmt, 2)} USD/wmt and ${fmt(d.routes.C5.financingDays, 1)} financing days; C3 freight ${fmt(d.routes.C3.freightUsdWmt, 2)} USD/wmt and ${fmt(d.routes.C3.financingDays, 1)} days.`)]],
  ]));
}

function factEl(label, value, unit, note, st) {
  return el('div', { class: 'fact' },
    el('p', { class: 'fact__label' }, label),
    el('p', { class: 'fact__value' }, value, el('span', { class: 'fact__unit' }, unit)),
    st ? el('p', { class: 'fact__note' }, el('span', { class: `state state--${st[1]}` }, st[0])) : null,
    note ? el('p', { class: 'fact__note' }, note) : null,
  );
}
