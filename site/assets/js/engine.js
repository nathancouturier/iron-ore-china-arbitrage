// Delivered-cost engine: the same formulas as the Python package `ironarb`
// (units.py, vat.py, margins.py, voyage.py, dce.py). Pure functions, no DOM,
// so the parity test can run this module under Node.

export const VAT_SCHEDULE = [
  ['1994-01-01', 0.17],
  ['2018-05-01', 0.16],
  ['2019-04-01', 0.13],
];

/** Import VAT rate in force on an ISO date (YYYY-MM-DD). */
export function vatRate(isoDate) {
  let rate = VAT_SCHEDULE[0][1];
  for (const [start, r] of VAT_SCHEDULE) if (isoDate >= start) rate = r;
  return rate;
}

/** Cost or price per wet tonne expressed per dry tonne. */
export function perWmtToPerDmt(valuePerWmt, moisture) {
  if (!(moisture >= 0 && moisture < 1)) throw new RangeError('moisture must be in [0, 1)');
  return valuePerWmt / (1 - moisture);
}

/** Interest on the cargo value over the financing period, actual/360 (USD/dmt). */
export function financingUsd(cfrUsdDmt, usdRatePct, spreadBp, days) {
  return cfrUsdDmt * (usdRatePct / 100 + spreadBp / 10000) * days / 360;
}

/** Landed cost components, RMB per dry tonne (VAT on the CFR value only). */
export function landedCost(cfrUsdDmt, usdcny, vat, portRmbWmt, moisture, financingUsdDmt) {
  const goods = cfrUsdDmt * usdcny;
  const tax = goods * vat;
  const port = perWmtToPerDmt(portRmbWmt, moisture);
  const fin = financingUsdDmt * usdcny;
  return { goods, vat: tax, port, financing: fin, total: goods + tax + port + fin };
}

export function importMargin(dce62RmbDmt, landedRmbDmt) {
  return dce62RmbDmt - landedRmbDmt;
}

/** +1 open, 0 inside the band, -1 closed. */
export function windowState(margin, band) {
  if (margin > band) return 1;
  if (margin < -band) return -1;
  return 0;
}

/** Index-equivalent FOB netback, USD per dry tonne. */
export function fobNetback(cfrUsdDmt, freightUsdWmt, moisture) {
  return cfrUsdDmt - perWmtToPerDmt(freightUsdWmt, moisture);
}

/** A 61% Fe contract price on a 62% basis: ten 0.1% steps of X. */
export function dceTo62(price, standardFe, x) {
  const steps = Math.round((62 - standardFe) / 0.1);
  return price + steps * x;
}

export function millMargin(steel, ore, coke, oreCoef, cokeCoef, otherCosts) {
  return steel - oreCoef * ore - cokeCoef * coke - otherCosts;
}

/** Voyage days: laden, ballast and port time. */
export function voyageDays(v) {
  const laden = v.ladenNm / (24 * v.ladenSpeedKn);
  const ballast = v.ballastNm / (24 * v.ballastSpeedKn);
  const port = v.loadPortDays + v.dischargePortDays;
  return { laden, ballast, port, total: laden + ballast + port };
}

/** Voyage freight in USD per wet tonne of cargo. */
export function voyageFreight(v, tceUsdDay, fuelUsdT, portFuelUsdT = fuelUsdT) {
  const d = voyageDays(v);
  const seaFuel = d.laden * v.ladenFuelTDay + d.ballast * v.ballastFuelTDay;
  const portFuel = d.port * v.portFuelTDay;
  const gross = tceUsdDay * d.total + seaFuel * fuelUsdT + portFuel * portFuelUsdT + v.portCostsUsd;
  return gross / (v.cargoT * (1 - v.commission));
}

export function financingDays(v, extraDays) {
  return voyageDays(v).laden + extraDays;
}

/**
 * Full calculator: from the inputs on the Calculator view to the bridge.
 * All amounts per dry tonne; freight is entered per wet tonne.
 */
export function calculate(inp) {
  const freightDmt = perWmtToPerDmt(inp.freightUsdWmt, inp.moisture);
  const fob = inp.cfrUsdDmt - freightDmt;
  const fin = financingUsd(inp.cfrUsdDmt, inp.usdRatePct, inp.spreadBp, inp.financingDays);
  const lc = landedCost(inp.cfrUsdDmt, inp.usdcny, inp.vat, inp.portRmbWmt, inp.moisture, fin);
  const margin = importMargin(inp.dce62RmbDmt, lc.total);
  return {
    freightUsdDmt: freightDmt,
    fobUsdDmt: fob,
    financingUsdDmt: fin,
    goodsRmb: lc.goods,
    vatRmb: lc.vat,
    portRmb: lc.port,
    financingRmb: lc.financing,
    landedRmb: lc.total,
    marginRmb: margin,
    state: windowState(margin, inp.band),
    freightShareOfLanded: (freightDmt * inp.usdcny * (1 + inp.vat)) / lc.total,
  };
}
