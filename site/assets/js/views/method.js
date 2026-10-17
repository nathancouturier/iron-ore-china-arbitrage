import { getJSON, el, toggles } from '../app.js';
import { fmt, fmtSigned, fmtPct, fmtDate, fmtMonth, table } from '../charts.js';

// Cross-check columns: plain label and format
const pc = (v) => fmtPct(v, 1);
const us = (v) => fmtSigned(v, 2);
const CC = {
  product: ['Product', String], year: ['Year', String], rows: ['Contract-days', (v) => fmt(v)],
  settle_identical: ['Settlement identical', pc], close_identical: ['Close identical', pc],
  oi_ratio_sina_to_dce: ['Open interest, Sina / exchange', (v) => fmt(v, 2)], oi_ratio_sina_to_shfe: ['Open interest, Sina / exchange', (v) => fmt(v, 2)],
  months: ['Months', (v) => fmt(v)], sgx_minus_imf_mean: ['SGX minus IMF, mean (USD/dmt)', us], sgx_minus_wb_mean: ['SGX minus World Bank, mean (USD/dmt)', us],
  imf_minus_wb_mean: ['IMF minus World Bank, mean (USD/dmt)', us], imf_minus_wb_max_abs: ['IMF minus World Bank, largest gap (USD/dmt)', (v) => fmt(v, 2)],
  days: ['Days', (v) => fmt(v)], mean_diff: ['New York minus fixing, mean (CNY)', (v) => fmtSigned(v, 4)], max_abs_diff: ['Largest gap (CNY)', (v) => fmt(v, 4)],
  date: ['Date', String], published: ['Published', (v) => fmt(v)], east_money: ['East Money', (v) => fmt(v)], source: ['Source', String],
  monthly_sum_mt: ['Sum of months (Mt)', (v) => fmt(v, 2)], year_total_mt: ['Year total (Mt)', (v) => fmt(v, 2)], diff_pct: ['Difference (%)', (v) => fmtSigned(v, 2)],
};

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
  const sdic = mmA.rows.filter((x) => x.independent);
  const ebr = mmA.rows.filter((x) => !x.independent);

  const rows = [
    { c: 'Import cost, Ruida Futures estimates, with the FX that best fits their figures (PBoC central parity; Ruida does not state its rate)', n: ic.rows.length, r: `max error ${fmt(ic.max_abs_error_ours_central_parity, 1)} RMB/t; with the New York rate used for the headline figures it is ${fmt(ic.max_abs_error_ours, 1)}`, t: `${fmt(T.import_cost_rmb_t)} RMB/t`, ok: ic.max_abs_error_ours_central_parity < T.import_cost_rmb_t },
    { c: 'Port price, Fastmarkets fot Qingdao converted to USD/dmt', n: pp.rows.length, r: `max error ${fmt(pp.max_abs_error_usd, 2)} USD/dmt`, t: `${fmt(T.port_price_usd_dmt)} USD/dmt`, ok: pp.max_abs_error_usd < T.port_price_usd_dmt },
    { c: 'Rebar mill margin, SDIC Essence Futures (independent: its own formula and constant)', n: sdic.length, r: `error ${sdic.map((x) => fmtSigned(x.error_rmb_t, 2)).join(', ')} RMB/t`, t: `${fmt(T.mill_margin_rmb_t)} RMB/t`, ok: Math.max(...sdic.map((x) => Math.abs(x.error_rmb_t))) < T.mill_margin_rmb_t },
    { c: 'Rebar mill margin, Everbright Futures 2026 (the 1,080 constant is calibrated on these, so they check prices and contract choice only)', n: ebr.length, r: `max error ${fmt(Math.max(...ebr.map((x) => Math.abs(x.error_rmb_t))), 1)} RMB/t`, t: 'calibration', ok: null },
    { c: 'C3 freight, voyage model, out of sample', n: fe.C3.voyage.n, r: `RMSE ${fmt(fe.C3.voyage.rmse, 2)}, MAE ${fmt(fe.C3.voyage.mae, 2)} USD/t`, t: `RMSE ${fmt(T.freight_rmse_usd_t.C3, 1)} USD/t`, ok: fe.C3.voyage.rmse < T.freight_rmse_usd_t.C3 },
    { c: 'C5 freight, voyage model, out of sample', n: fe.C5.voyage.n, r: `RMSE ${fmt(fe.C5.voyage.rmse, 2)}, MAE ${fmt(fe.C5.voyage.mae, 2)} USD/t`, t: `RMSE ${fmt(T.freight_rmse_usd_t.C5, 1)} USD/t`, ok: fe.C5.voyage.rmse < T.freight_rmse_usd_t.C5 },
    { c: 'BCI values quoted in the press', n: bci.length, r: `${bci.filter((b) => b.published === b.east_money).length} of ${bci.length} identical`, t: 'exact', ok: bci.every((b) => b.published === b.east_money) },
    { c: 'Dalian iron ore settlements, exchange files against Sina', n: ccRows, r: `${fmtPct(ccSame, 1)} of liquid contract-days identical`, t: 'cross-check', ok: null },
    { c: 'SGX final settlement against the IMF 62% average, months to December 2025', n: sgx.pre2026_months, r: `mean ${fmtSigned(sgx.pre2026_final_vs_bench_mean, 2)} USD/dmt, standard deviation ${fmt(sgx.pre2026_final_vs_bench_sd, 2)}`, t: 'cross-check', ok: null },
  ];
  const tested = rows.filter((r) => r.ok !== null);
  const passed = tested.filter((r) => r.ok).length;

  root.append(
    el('p', { class: 'takeaway' }, `Every series comes from public sources with a dated retrieval (hand-collected anchors with a link) and passes through a step in code; ${passed} of ${tested.length} checks against published figures pass their tolerance (calibration rows aside).`),
    el('p', { class: 'subtake' }, 'Tolerances are enforced by the test suite. Two parameters lean on these sources. The 1,080 RMB/t of other costs in the mill margin is calibrated on Everbright Futures\u2019 2026 margins, so those rows are not counted as checks. The port-charge default of 30 RMB/wmt was set with the Ruida and Fastmarkets figures in view (Ruida\u2019s estimates imply an adder of 30 to 35 RMB/t over goods and VAT, Fastmarkets\u2019 a port charge of 31 to 40 RMB/wmt), so those two checks test the price, FX, VAT and moisture conventions more than the port charge. The import-cost check passes with the FX rate that best fits the broker\u2019s figures (PBoC central parity; Ruida does not state its rate), not with the New York rate used for the headline figures. The freight model\u2019s time charter and bunker maps are fitted on separate public pairs, never on route rates, so the C3 and C5 rows are out of sample. Conventions, formulas, sources, the validation anchors and the limitations sit behind the buttons below; the calibration anchors are in the downloads. From a clean clone, make all rebuilds the model outputs, site data, downloads and note from recent data and the committed history; the cross-source checks and the data audit need the raw history and come from the last make full, which re-fetches every source.'),
    el('div', { class: 'panel' },
      el('h3', { class: 'chart-title' }, 'Validation against published figures'),
      table('Validation summary', [
        { label: 'Check', key: 'c' }, { label: 'n', get: (r) => (r.n === null ? '' : fmt(r.n)), num: true },
        { label: 'Result', key: 'r' }, { label: 'Tolerance', key: 't' },
        { label: 'Status', get: (r) => (r.ok === null ? 'reported' : r.ok ? 'pass' : 'fail') },
      ], rows),
      el('p', { class: 'source' }, `Sources: Ruida Futures daily reports (2022 to 2023), Fastmarkets (2019 to 2022), SDIC Essence and Everbright Futures (2022, 2026), Baltic Exchange route assessments reported in the shipping press, Platts and Ruida Futures (2016 to 2026), against this site's data to ${fmtDate(d.daily_sensitivity.date)}. Every anchor behind these checks is linked under Validation detail (the two press BCI values under Cross-checks); the anchor files are in the downloads, with a quote for the time charter pairs and for route rates from the shipping press.`),
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
        { k: 'Import VAT', v: '13% on metal ores from 1 May 1994; 17% from 1 January 2009; 16% from 1 May 2018; 13% from 1 April 2019. Import duty on HS 2601 is zero.', s: 'Caishui [1994] No. 22; Caiguanshui [2008] No. 99 (HS 2601 listed); Caishui [2018] No. 32; MOF, STA, GACC Announcement [2019] No. 39; 2026 tariff schedule', u: 'https://fgk.chinatax.gov.cn/zcfgk/c102416/c5202330/content.html' },
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
      el('p', {}, 'Stages, in order: ingest (download with retries, cache, SHA-256 manifest), transform (contract panels, trading calendar, constant maturity, most-active series, sea-route distances), validate (schema and cross-source checks), model (margins, freight, statistics), report (research note PDF), export (one JSON per view, CSV downloads), audit (data/AUDIT.md). Volume and open interest are normalized to single-sided lots (Chinese exchanges switched on 1 January 2020). FX, rates, Brent and BCI are carried forward at most five business days; Chinese holidays have no Dalian observation and are not filled.'),
      el('p', {}, 'Daily CFR proxy: SGX iron ore futures interpolated to the 45-day horizon between the two contracts whose month midpoints bracket it. The current-month contract is not used because it settles on the average of the month and so lags the market.'),
      el('p', {}, `SGX settlements for 2026 contract months are on Platts IODEX at 61% Fe; every 2026 contract month is lifted by one constant, the mean of the measured monthly spreads between the IMF 62% average and the SGX final settlement (${fmt(sgx.spread_2026_mean, 2)} USD/dmt over ${sgx.spread_2026_months} months, range ${fmt(sgx.spread_2026_min, 2)} to ${fmt(sgx.spread_2026_max, 2)}). The daily series first reaches a 2026 contract on ${fmtDate(sgx.first_lifted_day)}, and the IMF average reaches FRED weeks after the month ends (the latest month is ${fmtMonth(d.sources.imf.asof)}), so in the first months of the lifted period no 2026 spread had been published and the whole lift used later information; once one had, the constant differs from the mean then known by at most ${fmt(sgx.spread_2026_realtime_max_diff, 1)} USD/dmt. Before 2026 the SGX final settlement averaged ${fmtSigned(sgx.pre2026_final_vs_bench_mean, 2)} USD/dmt against the IMF series (standard deviation ${fmt(sgx.pre2026_final_vs_bench_sd, 2)}).`),
      el('p', {}, 'Daily series and monthly baseline: the daily series compares forward with forward (SGX and Dalian at the same 45-day horizon), the trade a desk can hedge; the monthly baseline compares the spot index average with the 45-day Dalian price. In steep backwardation, as in 2021, the monthly baseline shows a deeper discount.'),
      el('p', {}, `Constant-maturity robustness: excluding Dalian contracts in their delivery month moves the mean daily margin by ${fmtSigned(d.curve_robustness.daily_mean_diff, 2)} RMB/dmt and the share of open days from the default to ${fmtPct(d.curve_robustness.daily.share_open, 2)}; it removes the open run of 3 to 10 May 2016, which leaned on the expiring May contract.`),
    ]],
    ['Sources', () => [
      el('h3', {}, 'Sources, as-of dates and retrieval'),
      table('Sources', [
        { label: 'Series', key: 'label', href: 'url' }, { label: 'Data to', get: (r) => fmtDate(r.asof) },
        { label: 'Retrieved', get: (r) => fmtDate(r.retrieved) }, { label: 'Status', get: (r) => (r.stale ? 'last good snapshot' : 'current') },
      ], Object.values(d.sources)),
      el('p', { class: 'source' }, 'Raw files are listed with SHA-256 hashes in data/raw/manifest.json. FRED (including the IMF iron ore series) and World Bank raw files are committed with attribution. Raw exchange, Baltic and China Customs files are re-fetched by the pipeline and not committed; so that a clean clone rebuilds without them, the repository keeps snapshots of the inputs the models use (SGX settlements by contract month, the Dalian curve and most-active Dalian and Shanghai prices with volume and open interest, the BCI and BDI, the PBoC central parity, China Customs monthly imports) next to the derived series.'),
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
        { label: 'Error', get: (r) => fmtSigned(r.error_rmb_t, 2), num: true }, { label: 'Formula', key: 'formula' },
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
      c.table && c.table.length ? table(c.title, Object.keys(c.table[0]).filter((k) => k !== 'url').map((k) => ({ label: (CC[k] || [k])[0], get: (r) => (CC[k] ? CC[k][1](r[k]) : r[k]), num: typeof c.table[0][k] === 'number' && k !== 'year', ...(k === 'source' ? { href: 'url' } : {}) })), c.table) : null))],
    ['Limitations', () => [
      el('h3', {}, 'Limitations'),
      el('ul', {},
        el('li', {}, `The Dalian contract prices the cheapest deliverable brand at a Chinese port; a 62% index cargo is not that brand, so part of the persistent negative margin is a grade and brand effect, not an unexploited opportunity. On ${pp.rows.length} dated Fastmarkets port prices Dalian sat ${fmt(-pp.dce45_minus_port_range[1])} to ${fmt(-pp.dce45_minus_port_range[0])} RMB/dmt below the port price of 62% fines.`),
        el('li', {}, 'The margin is an expected margin, not a riskless arbitrage: price, basis, grade and currency risk remain while the cargo is at sea, and hedges with Dalian or SGX futures reduce but do not remove them.'),
        el('li', {}, 'Route freight rates are paid data; the modeled C3 and C5 series carry the errors shown in the validation table. Published route anchors cluster in 2021 to 2026, with two in 2016; none were found for 2014, 2015 or 2017 to 2020.'),
        el('li', {}, 'The monthly baseline compares averages; actual cargoes are priced on index averages around loading or arrival, with brand premiums and discounts.'),
        el('li', {}, `Port charges are a single assumption (${fmt(d.params.port_charges_rmb_wmt.value)} RMB/wmt); no official North China port tariff was found.`),
        el('li', {}, 'Other quality items (silica, alumina, phosphorus) are not adjusted; for a 62% IODEX-spec cargo delivered against the 61% contract they would add about 7.5 RMB/t.'),
        el('li', {}, `The 2026 SGX basis lift adds about ${fmt(sgx.spread_2026_mean, 1)} USD/dmt (measured range ${fmt(sgx.spread_2026_min, 1)} to ${fmt(sgx.spread_2026_max, 1)} USD), about ${fmt(sgx.spread_2026_mean * d.daily_sensitivity.slope_rmb_per_usd)} RMB/dmt of landed cost, ${d.daily_sensitivity.no_lift.state !== d.daily_sensitivity.lift.state ? 'which is enough to change the window state of the latest daily margin' : `which moves the latest daily margin (${fmtSigned(d.daily_sensitivity.lift.margin_rmb_dmt)} with it, ${fmtSigned(d.daily_sensitivity.no_lift.margin_rmb_dmt)} without) but not its window state`}; measured against the World Bank series instead of the IMF one the spread averages ${fmtSigned(sgx.spread_2026_wb_mean, 2)} USD. See the Assumptions drawer on the Overview.`),
        el('li', {}, 'The mill-margin constant of 1,080 RMB/t is calibrated on Everbright Futures\u2019 2026 figures; published constants range from 950 to 1,250, which moves the latest rebar margin by more than 100 RMB/t either way.'),
        el('li', {}, 'China import volumes come from the English pages of China Customs, which start in January 2018, so year-on-year import growth is available from January 2019; September and October 2024 and the latest month use the preliminary release. The test cannot separate an effect of the window on imports from the 2021 and 2022 policy episodes that moved both (Import window view).'),
      ),
    ]],
  ]));
}
