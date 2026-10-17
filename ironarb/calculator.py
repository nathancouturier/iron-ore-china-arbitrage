"""The site calculator in Python: the reference implementation the JavaScript
module ``site/assets/js/engine.js`` must match (tests/test_parity.py)."""

from __future__ import annotations

from typing import Any

from . import margins, units


def calculate(inp: dict[str, float]) -> dict[str, Any]:
    """Inputs: cfrUsdDmt, usdcny, vat, portRmbWmt, moisture, freightUsdWmt,
    usdRatePct, spreadBp, financingDays, dce62RmbDmt, band."""
    freight_dmt = units.per_wmt_to_per_dmt(inp["freightUsdWmt"], inp["moisture"])
    fob = inp["cfrUsdDmt"] - freight_dmt
    fin = margins.financing_usd(inp["cfrUsdDmt"], inp["usdRatePct"], inp["spreadBp"], inp["financingDays"])
    lc = margins.landed_cost(inp["cfrUsdDmt"], inp["usdcny"], inp["vat"], inp["portRmbWmt"], inp["moisture"], fin)
    margin = margins.import_margin(inp["dce62RmbDmt"], lc.total_rmb)
    state = int(margins.window_state([margin], inp["band"])[0])
    return {
        "freightUsdDmt": freight_dmt,
        "fobUsdDmt": fob,
        "financingUsdDmt": fin,
        "goodsRmb": lc.goods_rmb,
        "vatRmb": lc.vat_rmb,
        "portRmb": lc.port_rmb,
        "financingRmb": lc.financing_rmb,
        "landedRmb": lc.total_rmb,
        "marginRmb": margin,
        "state": state,
        "freightShareOfLanded": freight_dmt * inp["usdcny"] * (1 + inp["vat"]) / lc.total_rmb,
    }
