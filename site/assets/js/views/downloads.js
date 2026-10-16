import { getJSON, el } from '../app.js';
import { fmt, fmtDate } from '../charts.js';

const size = (b) => (b >= 1048576 ? `${fmt(b / 1048576, 1)} MB` : `${fmt(Math.max(1, Math.round(b / 1024)))} KB`);
const span = (f) => {
  if (!f.first) return '';
  const d = (x) => (x.length === 7 ? x : fmtDate(x));
  return `${d(f.first)} to ${d(f.last)}, `;
};

export async function render(root, meta) {
  const d = await getJSON('downloads');
  const series = d.files.filter((f) => !f.file.startsWith('anchors_'));
  const anchors = d.files.filter((f) => f.file.startsWith('anchors_'));
  root.append(
    el('p', { class: 'takeaway' }, 'The series behind the time-series charts, as CSV, with the unit in most numeric column names.'),
    el('p', { class: 'subtake' },
      `Column suffixes give the unit: _usd_dmt is USD per dry metric tonne, _usd_wmt per wet tonne, _rmb_dmt RMB per dry tonne, _rmb_t RMB per tonne, _pts index points, _pct percent, _mt million tonnes; rates and shares (vat_rate, freight_share_*) are fractions and usdcny is CNY per USD. Built ${fmtDate(meta.build_date)}, version ${meta.version}.`),
  );

  const note = d.note
    ? el('li', {},
      el('div', {},
        el('a', { href: `downloads/${d.note}`, download: '' }, 'Research note, PDF'),
        el('p', {}, 'The question, method, results and validation in a few pages, with charts in the site palette.')),
      el('span', { class: 'dl-size' }, size(d.note_bytes)))
    : null;
  if (note) root.append(el('h2', { class: 'section-title' }, 'Research note'), el('ul', { class: 'downloads' }, note));

  root.append(el('h2', { class: 'section-title' }, 'Derived series'), list(series));
  root.append(el('h2', { class: 'section-title' }, 'Validation and calibration points'),
    el('p', { class: 'subtake' }, 'Published figures used to test the landed cost, the mill margin and the freight model, and to calibrate the freight model, each with its date and source URL; time charter pairs and route rates from the shipping press also carry a short quote.'),
    list(anchors));

  root.append(el('h2', { class: 'section-title' }, 'Terms'),
    el('ul', { class: 'plain' },
      el('li', {}, 'Code: MIT license, in the repository linked below.'),
      el('li', {}, 'FRED and IMF series are redistributed with attribution: Federal Reserve Bank of St. Louis (FRED) and International Monetary Fund, Primary Commodity Prices. World Bank Pink Sheet data are under CC BY 4.0.'),
      el('li', {}, 'Exchange prices (Dalian Commodity Exchange, Shanghai Futures Exchange, SGX) and Baltic Exchange indices belong to their owners. Most files here are derived series computed from them; some columns repeat inputs for reference (for example the BCI, the SGX one-month-ahead settlement, most-active futures prices with their volume and open interest, and China Customs imports), and the validation files repeat the published figures they test against, with links. The pipeline re-fetches the inputs from the public endpoints.'),
      el('li', {}, 'Modeled freight is an estimate, not a Baltic Exchange or Platts assessment.'),
    ),
    el('p', {}, 'Source code and rebuild instructions: ', el('a', { href: 'https://github.com/nathancouturier/iron-ore-china-arbitrage' }, 'github.com/nathancouturier/iron-ore-china-arbitrage'), '.'),
  );
}

function list(files) {
  return el('ul', { class: 'downloads' }, ...files.map((f) => el('li', {},
    el('div', {},
      el('a', { href: `downloads/${f.file}`, download: '' }, f.title),
      el('p', {}, f.description),
      el('details', {},
        el('summary', {}, `${f.file}: ${span(f)}${fmt(f.rows)} rows, ${f.columns.length} columns`),
        el('p', { class: 'cols' }, f.columns.join(', '))),
    ),
    el('span', { class: 'dl-size' }, size(f.bytes)),
  )));
}
