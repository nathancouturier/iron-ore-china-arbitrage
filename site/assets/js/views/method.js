import { getJSON, el, toggles } from '../app.js';
import { fmt, fmtSigned, fmtPct, fmtDate, table } from '../charts.js';

export async function render(root) {
  const d = await getJSON('method');
  const A = d.anchors;
  const T = d.tolerance;
  const ic = A.import_cost;
  const pp = A.port_price;
  const mmA = A.mill_margin;
  const fe = d.freight_eval;
  const sgx = d.sgx_basis.info;
  const check = (prefix) => (d.cross_checks.find((c) => c.title.startsWith(prefix)) || { table: [] }).table;
  const ccI = check('DCE').filter((r) => r.product === 'I');
  const ccRows = ccI.reduce((t, r) => t + r.rows, 0);
  const ccSame = ccRows ? ccI.reduce((t, r) => t + r.rows * r.settle_identical, 0) / ccRows : null;
  const bci = check('BCI');

  const rows = [
    { c: 'Import cost, Ruida Futures estimates', n: ic.rows.length, r: `max error ${fmt(ic.max_abs_error_ours_central_parity, 1)} RMB/t with the PBoC central parity (${fmt(ic.max_abs_error_ours, 1)} with the New York rate)`, t: `${fmt(T.import_cost_rmb_t)} RMB/t`, ok: ic.max_abs_error_ours_central_parity < T.import_cost_rmb_t },
    { c: 'Port price, Fastmarkets fot Qingdao converted to USD/dmt', n: pp.rows.length, r: `max error ${fmt(pp.max_abs_error_usd, 2)} USD/dmt`, t: `${fmt(T.port_price_usd_dmt)} USD/dmt`, ok: pp.max_abs_error_usd < T.port_price_usd_dmt },
    { c: 'Rebar mill margin, broker reports', n: mmA.rows.length, r: `max error ${fmt(mmA.max_abs_error, 1)} RMB/t`, t: `${fmt(T.mill_margin_rmb_t)} RMB/t`, ok: mmA.max_abs_error < T.mill_margin_rmb_t },
    { c: 'C3 freight, voyage model, out of sample', n: fe.C3.voyage.n, r: `RMSE ${fmt(fe.C3.voyage.rmse, 2)}, MAE ${fmt(fe.C3.voyage.mae, 2)} USD/t`, t: `RMSE ${fmt(T.freight_rmse_usd_t.C3, 1)} USD/t`, ok: fe.C3.voyage.rmse < T.freight_rmse_usd_t.C3 },
    { c: 'C5 freight, voyage model, out of sample', n: fe.C5.voyage.n, r: `RMSE ${fmt(fe.C5.voyage.rmse, 2)}, MAE ${fmt(fe.C5.voyage.mae, 2)} USD/t`, t: `RMSE ${fmt(T.freight_rmse_usd_t.C5, 1)} USD/t`, ok: fe.C5.voyage.rmse < T.freight_rmse_usd_t.C5 },
    { c: 'BCI values quoted in the press', n: bci.length, r: `${bci.filter((b) => b.published === b.east_money).length} of ${bci.length} identical`, t: 'exact', ok: bci.every((b) => b.published === b.east_money) },
    { c: 'Dalian iron ore settlements, exchange files against Sina', n: ccRows, r: `${fmtPct(ccSame, 1)} of liquid contract-days identical`, t: 'cross-check', ok: null },
    { c: 'SGX final settlement against the IMF 62% average, to 2025', n: null, r: `mean ${fmtSigned(sgx.pre2026_final_vs_bench_mean, 2)} USD/dmt, standard deviation ${fmt(sgx.pre2026_final_vs_bench_sd, 2)}`, t: 'cross-check', ok: null },
  ];
  const tested = rows.filter((r) => r.ok !== null);
  const passed = tested.filter((r) => r.ok).length;

  root.append(
    el('p', { class: 'takeaway' }, `Every figure comes from public data with a dated retrieval and a step in code; ${passed} of ${tested.length} checks against published figures pass their tolerance.`),
    el('p', { class: 'subtake' }, 'Tolerances were fixed before reconciling and are enforced by the test suite; no parameter was tuned to meet them. Conventions, formulas, sources, every anchor and the limitations sit behind the buttons below. Rebuild everything from a clean clone with one command (make all).'),
    el('div', { class: 'panel' },
      el('h3', { class: 'chart-title' }, 'Validation against published figures'),
      table('Validation summary', [
        { label: 'Check', key: 'c' }, { label: 'n', get: (r) => (r.n === null ? '' : fmt(r.n)), num: true },
        { label: 'Result', key: 'r' }, { label: 'Tolerance', key: 't' },
        { label: 'Status', get: (r) => (r.ok === null ? 'reported' : r.ok ? 'pass' : 'fail') },
      ], rows),
      el('p', { class: 'source' }, 'Sources: anchor files in data/anchors with URLs and quotes; computed by pipeline/anchors.py and pipeline/freight_model.py, enforced by tests/test_anchors.py.'),
    ),
  );

  root.append(toggles('method', [
    ['Conventions', () => [
      el('h3', {}, 'Market conventions used'),
      table('Conventions', [{ label: 'Item', key: 'k' }, { label: 'Convention', key: 'v' }, { label: 'Source', key: 's', href: 'u' }], [
        { k: 'Seaborne benchmark', v: '62% Fe fines CFR China (Qingdao), USD per dry metric tonne. Platts IODEX moved to a 61% Fe basis on 2 January 2026; Fastmarkets 62% continues.', s: 'IMF via FRED PIORECRUSDM; Platts notes', u: 'https://fred.stlouisfed.org/series/PIORECRUSDM' },
        { k: 'Dalian iron ore futures (I)', v: '100 t per lot, RMB per tonne on a dry basis (moisture is a weight deduction), VAT included; last trading day is the 10th trading day of the delivery month; listed 18 October 2013.', s: 'DCE iron ore business rules (2026)', u: 'http://www.dce.com.cn/dalianshangpin/sspz/487477/index.html' },
        { k: 'Dalian standard grade', v: '62% Fe up to contract I2204; 61% Fe from I2205. Between 60.0% and 63.5% Fe each 0.1% is worth X RMB/t, so a 62% cargo is worth 10 x X over the 61% price.', s: 'DCE announcement, 19 May 2021; F/DCE I005-2026', u: 'http://www.dce.com.cn/dalianshangpin/sspz/487477/index.html' },
        { k: 'Wet and dry', v: 'Freight and port handling are paid on wet (bill of lading) weight; CFR and Dalian are per dry tonne. Per dry tonne = per wet tonne / (1 − moisture). Default moisture 8% (Fastmarkets base), sensitivity 6% to 10%.', s: 'Fastmarkets iron ore methodology (2026)', u: 'https://www.fastmarkets.com/uploads/2026/10/fm-mb-iron-ore-indices.pdf' },
        { k: 'Import VAT', v: '17% to 30 April 2018; 16% from 1 May 2018; 13% from 1 April 2019. Import duty on HS 2601 is zero.', s: 'Caishui [2018] No. 32; MOF, STA, GACC Announcement [2019] No. 39; 2026 tariff schedule', u: 'https://fgk.chinatax.gov.cn/zcfgk/c102416/c5202330/content.html' },
        { k: 'Customs value', v: 'CIF. Landed cost uses CFR; deemed insurance of 0.3% of goods plus freight (Article 36, GACC Order 213) would add about 0.3 RMB/dmt of VAT plus the premium.', s: 'GACC Order 213, Article 36', u: 'https://fgw.sh.gov.cn/ys-gjmy-1.1.1.1.1/20240206/db04a0e249b042b0a9dfd555f84940be.html' },
        { k: 'Capesize routes', v: 'C3 Tubarao to Qingdao and C5 West Australia to Qingdao, 170,000 mt 10% more or less in owner’s option, 5% total commission; discharge 30,000 mt per day SHINC with 24 h turn time.', s: 'Baltic Exchange route descriptions (Circular 44/24, Circular 33/20)', u: 'https://www.balticexchange.com/en/data-services/market-information0/indices.html' },
        { k: 'Mill margin', v: 'RB (or HC) − 1.6 x I − 0.5 x J − other costs, a broker convention, not an accounting margin.', s: 'Cinda Futures (2017), Orient Securities (2019), SDIC Essence Futures (2022)', u: 'https://finance.sina.com.cn/money/future/fmnews/2022-06-02/doc-imizirau6147496.shtml' },
      ]),
      el('div', { class: 'grid grid--two', style: 'margin-top:16px' },
        el('div', {},
          el('h3', {}, 'X has been 1.5 RMB per 0.1% Fe in every period so far'),
          el('p', { class: 'chart-sub' }, 'Computed from the rule: average daily settlement of the nearest delivery-month contract over the six-month window.'),
          table('Dalian Fe premium X by publication', [
            { label: 'Published', key: 'published' }, { label: 'Window', get: (r) => `${r.window_start} to ${r.window_end}` },
            { label: 'Average, RMB/t', get: (r) => fmt(r.avg_front_settle_rmb, 1), num: true }, { label: 'X', get: (r) => fmt(r.x_rmb_per_0_1pct, 1), num: true },
            { label: 'Delivery months', key: 'applies_to_delivery_months' },
          ], d.x_schedule)),
        el('div', {},
          el('h3', {}, 'Import VAT schedule'),
          table('VAT by date', [{ label: 'From', get: (r) => fmtDate(r[0]) }, { label: 'Rate', get: (r) => fmtPct(r[1], 0), num: true }], d.vat_schedule),
          el('h3', { style: 'margin-top:14px' }, 'Constant-maturity method by year'),
          table('Days by method for the 45-day point', [
            { label: 'Year', key: 'year' }, { label: 'Interpolated', get: (r) => fmt((r.interpolated || 0) + (r.exact || 0)), num: true },
            { label: 'Extrapolated', get: (r) => fmt((r.extrapolated_linear || 0) + (r.extrapolated_flat || 0)), num: true },
          ], d.cm_methods)),
      ),
    ]],
    ['Formulas', () => [
      el('h3', {}, 'Formulas (RMB per dry tonne unless stated)'),
      el('pre', { class: 'formula' },
        'Financing (USD/dmt)  = CFR x (USD rate + spread) x days / 360\n' +
        'Landed cost          = CFR x USDCNY x (1 + VAT) + port charges / (1 - moisture) + financing x USDCNY\n' +
        'Dalian 62% equiv.    = Dalian price (61% basis) + 10 x X        (contracts from I2205)\n' +
        'Import margin        = Dalian 62% equiv. at 45 days - landed cost\n' +
        'FOB netback (USD/dmt)= CFR - freight (USD/wmt) / (1 - moisture)\n' +
        'Voyage freight       = (TCE x voyage days + bunker cost + port costs) / (cargo x (1 - commission))\n' +
        'Mill margin (RMB/t)  = steel - 1.6 x ore - 0.5 x coke - other costs'),
      el('h3', {}, 'Pipeline'),
      el('p', {}, 'Stages: ingest (download with retries, cache, SHA-256 manifest), transform (contract panels, trading calendar, constant maturity, most-active series), validate (cross-source checks), model (margins, freight, statistics), export (one JSON per view, CSV downloads), report (research note PDF). Volume and open interest are normalised to single-sided lots (Chinese exchanges switched on 1 January 2020). FX, rates, Brent and BCI are carried forward at most five business days; Chinese holidays have no Dalian observation and are not filled.'),
      el('p', {}, 'Daily CFR proxy: SGX iron ore futures interpolated to the 45-day horizon between the two contracts whose month midpoints bracket it. The current-month contract is not used because it settles on the average of the month and so lags the market.'),
      el('p', {}, `SGX settlements for 2026 contract months are on Platts IODEX at 61% Fe; they are lifted by the measured monthly spread to the IMF 62% average (mean ${fmt(sgx.spread_2026_mean, 2)} USD/dmt over ${sgx.spread_2026_months} months, range ${fmt(sgx.spread_2026_min, 2)} to ${fmt(sgx.spread_2026_max, 2)}). Before 2026 the SGX final settlement averaged ${fmtSigned(sgx.pre2026_final_vs_bench_mean, 2)} USD/dmt against the IMF series (standard deviation ${fmt(sgx.pre2026_final_vs_bench_sd, 2)}).`),
      el('p', {}, `Constant-maturity robustness: excluding Dalian contracts in their delivery month moves the mean daily margin by ${fmtSigned(d.curve_robustness.daily_mean_diff, 2)} RMB/dmt and the share of open days from the default to ${fmtPct(d.curve_robustness.daily.share_open, 2)}; it removes the open run of 3 to 10 May 2016, which leaned on the expiring May contract.`),
    ]],
    ['Sources', () => [
      el('h3', {}, 'Sources, as-of dates and retrieval'),
      table('Sources', [
        { label: 'Series', key: 'label', href: 'url' }, { label: 'Data to', get: (r) => fmtDate(r.asof) },
        { label: 'Retrieved', get: (r) => fmtDate(r.retrieved) }, { label: 'Status', get: (r) => (r.stale ? 'last good snapshot' : 'current') },
      ], Object.values(d.sources)),
      el('p', { class: 'source' }, 'Raw files are listed with SHA-256 hashes in data/raw/manifest.json. FRED, IMF and World Bank raw data are committed with attribution; exchange and third-party data are re-fetched by the pipeline and only derived series are published.'),
    ]],
    ['Validation detail', () => [
      table('Import cost: Ruida Futures estimate against our landed cost (RMB per tonne)', [
        { label: 'Report', key: 'report_date', href: 'url' }, { label: 'Platts 62%, USD', get: (r) => fmt(r.platts62_usd_dmt, 2), num: true },
        { label: 'Ruida', get: (r) => fmt(r.ruida_import_cost_rmb_t), num: true }, { label: 'Ours, NY rate', get: (r) => fmt(r.our_landed_rmb_dmt, 1), num: true },
        { label: 'Error', get: (r) => fmtSigned(r.error_rmb, 1), num: true }, { label: 'Ours, central parity', get: (r) => fmt(r.our_landed_central_parity_rmb_dmt, 1), num: true },
        { label: 'Error', get: (r) => fmtSigned(r.error_central_parity_rmb, 1), num: true }, { label: 'Their adder', get: (r) => fmt(r.implied_adder_rmb_t, 1), num: true },
      ], ic.rows),
      el('p', { class: 'source' }, `Ruida's figure is reproduced within ${fmt(ic.max_abs_error_reconstructed, 1)} RMB/t by Platts x PBoC central parity of the report day x 1.13 + ${fmt(ic.inferred.median_adder_rmb_t, 1)} RMB/t (their adder ranges ${fmt(ic.inferred.adder_range[0], 1)} to ${fmt(ic.inferred.adder_range[1], 1)}). The two larger errors with the New York rate fall in 2023, when the New York rate traded up to 0.14 above the fixing.`),
      table('Port price: Fastmarkets 62% fines fot Qingdao converted to USD per dry tonne', [
        { label: 'Date', key: 'date', href: 'url' }, { label: 'RMB/wmt', get: (r) => fmt(r.fastmarkets_rmb_wmt), num: true },
        { label: 'Fastmarkets USD/dmt', get: (r) => fmt(r.fastmarkets_implied_usd_dmt, 2), num: true }, { label: 'Ours', get: (r) => fmt(r.our_conversion_usd_dmt, 2), num: true },
        { label: 'Error', get: (r) => fmtSigned(r.error_usd_dmt, 2), num: true }, { label: 'Port charge that closes the gap, RMB/wmt', get: (r) => fmt(r.implied_port_charge_rmb_wmt, 1), num: true },
      ], pp.rows),
      table('Mill margin: broker figures against ours (RMB per tonne)', [
        { label: 'Date', key: 'date', href: 'url' }, { label: 'Publisher', key: 'publisher' }, { label: 'Contracts', key: 'contracts' },
        { label: 'Published', get: (r) => fmtSigned(r.published_rmb_t, 1), num: true }, { label: 'Ours', get: (r) => fmtSigned(r.ours_rmb_t, 1), num: true },
        { label: 'Error', get: (r) => fmtSigned(r.error_rmb_t, 1), num: true }, { label: 'Formula', key: 'formula' },
      ], mmA.rows),
      table('Freight: modeled route rates against published assessments (USD per wet tonne)', [
        { label: 'Date', key: 'date', href: 'url' }, { label: 'Route', key: 'route' }, { label: 'Assessor', key: 'assessor' },
        { label: 'Published', get: (r) => fmt(r.value_usd_wmt, 2), num: true }, { label: 'Voyage model', get: (r) => fmt(r.voyage_model, 2), num: true },
        { label: 'Error', get: (r) => fmtSigned(r.voyage_model - r.value_usd_wmt, 2), num: true },
        { label: 'Regression, out of sample', get: (r) => fmt(r.stat_model_loo, 2), num: true }, { label: 'Error', get: (r) => fmtSigned(r.stat_model_loo - r.value_usd_wmt, 2), num: true },
      ], d.freight_anchors.map((r) => ({ ...r, date: r.date.slice(0, 10) })).sort((x, y) => (x.date < y.date ? 1 : -1))),
      el('p', { class: 'source' }, ['C3', 'C5'].map((k) => `${k}: voyage model MAE ${fmt(fe[k].voyage.mae, 2)}, RMSE ${fmt(fe[k].voyage.rmse, 2)} (n = ${fe[k].voyage.n}); regression leave-one-out MAE ${fmt(fe[k].stat_loo.mae, 2)}, RMSE ${fmt(fe[k].stat_loo.rmse, 2)}`).join('. ') + ' USD/wmt.'),
    ]],
    ['Cross-checks', () => d.cross_checks.map((c) => el('div', { style: 'margin-bottom:12px' },
      el('h4', {}, c.title), el('p', {}, c.text),
      c.table && c.table.length ? table(c.title, Object.keys(c.table[0]).map((k) => ({ label: k.replaceAll('_', ' '), key: k })), c.table) : null))],
    ['Limitations', () => [
      el('h3', {}, 'Limitations'),
      el('ul', {},
        el('li', {}, `The Dalian contract prices the cheapest deliverable brand at a Chinese port; a 62% index cargo is not that brand, so part of the persistent negative margin is a grade and brand effect, not an unexploited opportunity. On ${pp.rows.length} dated Fastmarkets port prices Dalian sat ${fmt(-pp.dce45_minus_port_range[1])} to ${fmt(-pp.dce45_minus_port_range[0])} RMB/dmt below the port price of 62% fines.`),
        el('li', {}, 'The margin is an expected margin, not a riskless arbitrage: price, basis, grade and currency risk remain while the cargo is at sea, and hedges with Dalian or SGX futures reduce but do not remove them.'),
        el('li', {}, 'Route freight rates are paid data; the modeled C3 and C5 series carry the errors shown in the validation table. Published anchors cluster in 2021 to 2026; none were found for 2015 or 2017 to 2020.'),
        el('li', {}, 'The monthly baseline compares averages; actual cargoes are priced on index averages around loading or arrival, with brand premiums and discounts.'),
        el('li', {}, `Port charges are a single assumption (${fmt(d.params.port_charges_rmb_wmt.value)} RMB/wmt); no official North China port tariff was found.`),
        el('li', {}, 'Other quality items (silica, alumina, phosphorus) are not adjusted; for a 62% IODEX-spec cargo delivered against the 61% contract they would add about 7.5 RMB/t.'),
        el('li', {}, `The 2026 SGX basis lift adds about ${fmt(sgx.spread_2026_mean, 1)} USD/dmt with a measured range of ${fmt(sgx.spread_2026_min, 1)} to ${fmt(sgx.spread_2026_max, 1)} USD.`),
        el('li', {}, 'China import volumes by month (China Customs) could not be fetched from the build environment, so the optional test of imports against the window was not run.'),
      ),
    ]],
  ]));
}
