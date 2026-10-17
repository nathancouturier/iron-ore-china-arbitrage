// Runs the site engine on the shared fixtures and prints JSON results.
import fs from 'node:fs';
import * as E from '../site/assets/js/engine.js';

const fx = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const out = {
  calculator: fx.calculator.map((c) => E.calculate(c)),
  vat: fx.vat_dates.map((d) => E.vatRate(d)),
  voyage: fx.voyages.map((v) => ({
    days: E.voyageDays(v).total,
    freight: E.voyageFreight(v, v.tceUsdDay, v.fuelUsdT),
    financingDays: E.financingDays(v, 10),
  })),
  dce62: fx.dce62.map((c) => E.dceTo62(c.price, c.standardFe, c.x)),
  mill: fx.mill.map((c) => E.millMargin(c.steel, c.ore, c.coke, c.oreCoef, c.cokeCoef, c.other)),
  netback: fx.netback.map((c) => E.fobNetback(c.cfr, c.freight, c.moisture)),
};
process.stdout.write(JSON.stringify(out));
