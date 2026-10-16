"""Report stage: the research note PDF (A4, four to five pages).

Charts are drawn with matplotlib in the site palette; the text is set with
reportlab in Liberation Serif. Every number is read from ``data/derived``
(analysis.json and the derived CSVs) and ``data/anchors/events.json``, so the
note always matches the site.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib import font_manager
from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch, mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    CondPageBreak,
    Image,
    KeepTogether,
    ListFlowable,
    ListItem,
    Paragraph,
    SimpleDocTemplate,
    Table,
    TableStyle,
)

from ironarb.params import PARAMS

from .anchors import TOLERANCE

ROOT = Path(__file__).resolve().parents[1]
DERIVED = ROOT / "data" / "derived"
OUT = ROOT / "site" / "downloads" / "Iron-Ore-China-Import-Arbitrage-Research-Note.pdf"
WORK = ROOT / "data" / "cache" / "report"
FONT_DIR = Path("/usr/share/fonts/truetype/liberation")
URL = "https://nathancouturier.github.io/iron-ore-china-arbitrage/"
REPO = "https://github.com/nathancouturier/iron-ore-china-arbitrage"

# Site palette (design tokens in site/assets/css/site.css)
TOPSIDE = "#16212b"
STEEL = "#46535e"
MUTED = "#5d6a74"
GRID = "#d5dbdd"
PLATE = "#e6eae9"
SEAWATER = "#0a6e94"
PILBARA = "#c25e14"
HEMATITE = "#8c3459"
FIG_W = 6.85  # inches, the text width
DPI = 200
MINUS = "−"


# Formatting -----------------------------------------------------------------------
def num(v: float, d: int = 0) -> str:
    s = f"{abs(v):,.{d}f}"
    return f"{MINUS}{s}" if v < 0 and float(s.replace(",", "")) != 0 else s


def signed(v: float, d: int = 0) -> str:
    s = num(abs(v), d)
    return f"+{s}" if v > 0 else (f"{MINUS}{s}" if v < 0 else s)


def pct(v: float, d: int = 1) -> str:
    return f"{num(v * 100, d)}%"


def day(iso: str) -> str:
    return pd.Timestamp(iso).strftime("%-d %b %Y")


def month(iso: str) -> str:
    return pd.Period(iso, "M").strftime("%b %Y")


# Charts ---------------------------------------------------------------------------
def _style() -> None:
    for f in ("LiberationSans-Regular.ttf", "LiberationSans-Bold.ttf"):
        font_manager.fontManager.addfont(str(FONT_DIR / f))
    plt.rcParams.update(
        {
            "font.family": "Liberation Sans",
            "font.size": 8,
            "axes.edgecolor": GRID,
            "axes.labelcolor": STEEL,
            "axes.titlesize": 9,
            "axes.titleweight": "bold",
            "axes.titlecolor": TOPSIDE,
            "axes.titlelocation": "left",
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.spines.left": False,
            "axes.grid": True,
            "axes.grid.axis": "y",
            "grid.color": GRID,
            "grid.linewidth": 0.6,
            "xtick.color": STEEL,
            "ytick.color": STEEL,
            "ytick.left": False,
            "legend.frameon": False,
            "legend.fontsize": 7.5,
            "axes.formatter.use_mathtext": False,
            "axes.unicode_minus": True,
        }
    )


def _save(fig: plt.Figure, name: str) -> Path:
    WORK.mkdir(parents=True, exist_ok=True)
    path = WORK / f"{name}.png"
    fig.savefig(path, dpi=DPI, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


def fig_margin(daily: pd.DataFrame, band: float, events: list[dict[str, Any]]) -> Path:
    fig, ax = plt.subplots(figsize=(FIG_W, 2.3))
    m = daily["margin_rmb_dmt"]
    ax.axhspan(-band, band, color=STEEL, alpha=0.10, lw=0)
    ax.axhline(0, color=STEEL, lw=0.8)
    ax.plot(m.index, m.values, color=TOPSIDE, lw=0.9)
    for i, e in enumerate(events, start=1):
        x = pd.Timestamp(e["date"])
        y = float(m.loc[x])
        ax.plot([x], [y], "o", ms=9, color=HEMATITE, mec="white", mew=1.2, zorder=5)
        ax.text(x, y, str(i), color="white", ha="center", va="center", fontsize=6.5, fontweight="bold", zorder=6)
    ax.set_ylabel("RMB per dry tonne")
    ax.set_title("Import margin: Dalian 45-day 62% equivalent minus landed cost, daily")
    ax.margins(x=0.01)
    return _save(fig, "margin")


def fig_bridge(last: pd.Series) -> Path:
    fx = float(last["usdcny"])
    rows = [
        ("FOB Australia, index-equivalent", 0.0, last["fob_australia_usd_dmt"] * fx, PILBARA, False),
        ("Freight C5, modeled", last["fob_australia_usd_dmt"] * fx, last["c5_model_usd_dmt"] * fx, PILBARA, True),
        ("FOB Brazil, index-equivalent", 0.0, last["fob_brazil_usd_dmt"] * fx, SEAWATER, False),
        ("Freight C3, modeled", last["fob_brazil_usd_dmt"] * fx, last["c3_model_usd_dmt"] * fx, SEAWATER, True),
        ("CFR Qingdao, 62% Fe", 0.0, last["goods_rmb_dmt"], STEEL, False),
        (f"Import VAT {num(last['vat_rate'] * 100)}%", last["goods_rmb_dmt"], last["vat_rmb_dmt"], "#8d99a2", False),
        ("Port charges", last["goods_rmb_dmt"] + last["vat_rmb_dmt"], last["port_rmb_dmt"], "#8d99a2", False),
        (
            "Financing",
            last["goods_rmb_dmt"] + last["vat_rmb_dmt"] + last["port_rmb_dmt"],
            last["financing_rmb_dmt"],
            "#8d99a2",
            False,
        ),
        ("Landed cost, VAT included", 0.0, last["landed_rmb_dmt"], HEMATITE, False),
        ("Dalian 62% equivalent, 45 days", 0.0, last["dce62_rmb_dmt"], TOPSIDE, False),
    ]
    fig, ax = plt.subplots(figsize=(FIG_W, 2.55))
    for i, (_label, left, width, color, modeled) in enumerate(rows):
        if modeled:
            ax.barh(i, width, left=left, height=0.6, color="white", edgecolor=color, hatch="////", lw=1.0, ls="--")
        else:
            ax.barh(i, width, left=left, height=0.6, color=color)
        ax.text(left + width + 8, i, num(width), va="center", fontsize=7.5, color=TOPSIDE)
    ax.set_yticks(range(len(rows)), [r[0] for r in rows], color=TOPSIDE)
    ax.invert_yaxis()
    ax.grid(axis="x", color=GRID, lw=0.6)
    ax.grid(axis="y", visible=False)
    ax.set_xlabel("RMB per dry tonne")
    ax.set_xlim(0, max(r[1] + r[2] for r in rows) * 1.1)
    ax.set_title(f"Delivered cost bridge on {day(str(last.name)[:10])}, RMB per dry tonne")
    return _save(fig, "bridge")


def fig_freight(freight: pd.DataFrame, anchors: pd.DataFrame, monthly: pd.DataFrame) -> Path:
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(FIG_W, 2.4), gridspec_kw={"width_ratios": [1.35, 1]})
    w = freight.resample("W-FRI").last()
    for k, color, label in [("c3", SEAWATER, "C3 Tubarao"), ("c5", PILBARA, "C5 West Australia")]:
        a1.fill_between(w.index, w[f"{k}_model_usd_wmt_lo"], w[f"{k}_model_usd_wmt_hi"], color=color, alpha=0.15, lw=0)
        a1.plot(w.index, w[f"{k}_model_usd_wmt"], color=color, lw=0.9, ls=(0, (4, 2)), label=f"{label}, modeled")
        pts = anchors[anchors["route"] == k.upper()]
        a1.scatter(pts["date"], pts["value_usd_wmt"], s=13, facecolor="white", edgecolor=color, lw=0.9, zorder=4)
    a1.set_ylabel("USD per wet tonne")
    a1.set_title("Modeled freight and published rates (circles)")
    a1.legend(loc="upper left")
    idx = pd.PeriodIndex(monthly.index, freq="M").to_timestamp()
    a2.plot(idx, monthly["freight_share_cfr_c3"] * 100, color=SEAWATER, lw=0.9, ls=(0, (4, 2)), label="C3 Tubarao")
    a2.plot(
        idx, monthly["freight_share_cfr_c5"] * 100, color=PILBARA, lw=0.9, ls=(0, (4, 2)), label="C5 West Australia"
    )
    a2.set_title("Modeled freight as a share of CFR")
    a2.set_ylabel("Percent of the CFR price")
    a2.legend(loc="upper left")
    fig.tight_layout(w_pad=2.0)
    return _save(fig, "freight")


def fig_mill(mill: pd.DataFrame) -> Path:
    fig, ax = plt.subplots(figsize=(FIG_W, 2.1))
    ax.axhline(0, color=STEEL, lw=0.8)
    ax.plot(mill.index, mill["rebar_margin_ma_rmb_t"], color=HEMATITE, lw=0.8, label="Rebar")
    ax.plot(mill.index, mill["hrc_margin_ma_rmb_t"], color=SEAWATER, lw=0.8, label="Hot-rolled coil")
    ax.set_ylabel("RMB per tonne of steel")
    ax.set_title("Futures-implied mill margin: steel minus 1.6 x ore minus 0.5 x coke minus other costs")
    ax.legend(loc="upper left", ncols=2)
    ax.margins(x=0.01)
    return _save(fig, "mill")


# Document -------------------------------------------------------------------------
def _fonts() -> None:
    pdfmetrics.registerFont(
        TTFont("LiberationSerif", "/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf")
    )
    pdfmetrics.registerFont(TTFont("LiberationSerif-Bold", str(FONT_DIR / "LiberationSerif-Bold.ttf")))
    pdfmetrics.registerFont(TTFont("LiberationSerif-Italic", str(FONT_DIR / "LiberationSerif-Italic.ttf")))
    pdfmetrics.registerFontFamily(
        "LiberationSerif", normal="LiberationSerif", bold="LiberationSerif-Bold", italic="LiberationSerif-Italic"
    )


def _styles() -> dict[str, ParagraphStyle]:
    body = ParagraphStyle(
        "body", fontName="LiberationSerif", fontSize=9.5, leading=12.6, alignment=TA_LEFT, spaceAfter=5
    )
    return {
        "title": ParagraphStyle(
            "title", parent=body, fontName="LiberationSerif-Bold", fontSize=17, leading=20, spaceAfter=4
        ),
        "meta": ParagraphStyle("meta", parent=body, fontSize=8.5, textColor=colors.HexColor(STEEL), spaceAfter=10),
        "h": ParagraphStyle(
            "h",
            parent=body,
            fontName="LiberationSerif-Bold",
            fontSize=11,
            leading=14,
            spaceBefore=8,
            spaceAfter=3,
        ),
        "body": body,
        "cap": ParagraphStyle("cap", parent=body, fontSize=7.8, leading=10, textColor=colors.HexColor(STEEL)),
        "cell": ParagraphStyle("cell", parent=body, fontSize=8, leading=10, spaceAfter=0),
    }


def _table(rows: list[list[str]], widths: list[float], st: dict[str, ParagraphStyle], num_cols: int = 0) -> Table:
    data = [[Paragraph(str(c), st["cell"]) for c in r] for r in rows]
    t = Table(data, colWidths=[w * mm for w in widths], repeatRows=1, hAlign="LEFT")
    style = [
        ("FONTNAME", (0, 0), (-1, -1), "LiberationSerif"),
        ("LINEBELOW", (0, 0), (-1, 0), 0.6, colors.HexColor(STEEL)),
        ("LINEBELOW", (0, -1), (-1, -1), 0.4, colors.HexColor(GRID)),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
    ]
    for i in range(1, len(rows)):
        if i % 2 == 0:
            style.append(("BACKGROUND", (0, i), (-1, i), colors.HexColor("#f2f4f3")))
    t.setStyle(TableStyle(style))
    return t


def _img(path: Path, width_in: float = FIG_W) -> Image:
    with PILImage.open(path) as im:
        w, h = im.size
    return Image(str(path), width=width_in * inch, height=width_in * inch * h / w)


def _footer(canvas, doc) -> None:
    canvas.saveState()
    canvas.setFont("LiberationSerif", 7.5)
    canvas.setFillColor(colors.HexColor(MUTED))
    canvas.drawString(
        18 * mm, 10 * mm, f"Nathan Couturier. Iron ore into China: delivered cost and the import window. {URL}"
    )
    canvas.drawRightString(A4[0] - 18 * mm, 10 * mm, str(doc.page))
    canvas.restoreState()


def imports_text(a: dict[str, Any]) -> str:
    """The pre-registered imports test and its exploratory check, in words."""
    t, x = a["imports_test"], a["imports_test_ex_2021_2022"]
    r, rx = t["rows"][-1], x["rows"][-1]

    def sig(q: dict[str, Any]) -> bool:
        return q["ci_lo_pp"] > 0 or q["ci_hi_pp"] < 0

    yrs = " and ".join(str(y) for y in x["exclude_years"])
    head = (
        f"Imports (pre-registered; China Customs monthly bulletins from 2018): a monthly margin "
        f"{num(t['per_rmb_dmt'])} RMB/dmt higher precedes {signed(r['effect_pp'], 1)} percentage points of "
        f"year-on-year import growth over the next {r['horizon_months']} months (95% interval "
        f"{signed(r['ci_lo_pp'], 1)} to {signed(r['ci_hi_pp'], 1)}, Newey-West t {num(r['nw_t'], 1)}, {r['n_obs']} months). "
    )
    tail = (
        f"without those years (an exploratory check) the slope is {signed(rx['effect_pp'], 1)} with an interval from "
        f"{signed(rx['ci_lo_pp'], 1)} to {signed(rx['ci_hi_pp'], 1)}."
    )
    if sig(r) and not sig(rx):
        return (
            head
            + f"The link rests on {yrs}, when policy pushed Dalian far below import parity while imports fell; "
            + tail
            + " The data do not separate an effect of the window on imports from the policy that moved both."
        )
    return head + tail[0].upper() + tail[1:]


def build() -> Path:
    a = json.loads((DERIVED / "analysis.json").read_text())
    daily = pd.read_csv(DERIVED / "import_margin_daily.csv", parse_dates=["date"]).set_index("date")
    monthly = pd.read_csv(DERIVED / "import_margin_monthly.csv").set_index("month")
    freight = pd.read_csv(DERIVED / "freight_modeled_daily.csv", parse_dates=["date"]).set_index("date")
    mill = pd.read_csv(DERIVED / "mill_margin_daily.csv", parse_dates=["date"]).set_index("date")
    mill = mill[mill.index >= pd.Timestamp("2014-01-01")]
    events = json.loads((ROOT / "data" / "anchors" / "events.json").read_text())
    by_date = {e["date"]: e for e in events}
    episodes = [by_date[str(dv["period"])[:10]] for dv in a["deviations_daily"]]
    anchors = pd.DataFrame(a["freight"]["anchors"])
    anchors["date"] = pd.to_datetime(anchors["date"])

    band = PARAMS["band_rmb_dmt"]["value"]
    last = daily.iloc[-1]
    ld = str(daily.index[-1])[:10]
    wd, wm = a["window_daily"], a["window_monthly"]
    cd, cm = a["convergence_daily"], a["convergence_monthly"]
    fe = a["freight"]["evaluation"]
    sens = a["freight"]["sensitivity"]
    dsens = a["daily_sensitivity"]
    an_ = anchors[anchors["route"] == "C3"].dropna(subset=["voyage_model"]).sort_values("date").tail(5)
    rec_c3 = float((an_["voyage_model"] - an_["value_usd_wmt"]).mean())
    tr = {r["horizon_days"]: r for r in a["mill_test_rebar"]}
    th = {r["horizon_days"]: r for r in a["mill_test_hrc"]}
    pp = a["anchors"]["port_price"]
    ic = a["anchors"]["import_cost"]
    mm_ = a["anchors"]["mill_margin"]
    lm = monthly.index[-1]
    gap = monthly["fob_australia_usd_dmt"] - monthly["fob_brazil_usd_dmt"]
    share_m = (monthly["margin_rmb_dmt"] / monthly["landed_rmb_dmt"]).mean()
    rebar = mill["rebar_margin_ma_rmb_t"].dropna()
    ly = str(rebar.index[-1].year)
    ly_neg = float((rebar.loc[ly] < 0).mean())
    curve = pd.read_csv(DERIVED / "dce_iron_ore_curve_daily.csv", parse_dates=["date"]).set_index("date")
    ma_dte = float(curve.loc[curve.index >= pd.Timestamp("2014-01-01"), "dce_i_ma_dte_days"].mean())
    xs = pd.read_csv(DERIVED / "dce_x_schedule.csv")["x_rmb_per_0_1pct"].unique()
    x_text = f"X = {num(xs[0], 1)} RMB per 0.1% Fe in every period" if len(xs) == 1 else "X set by the exchange rule"
    no_sign = all(r["ci_hi_pct"] > 0 for r in a["mill_test_rebar"])
    all_pos = all(r["effect_pct"] > 0 for r in a["mill_test_rebar"] + a["mill_test_hrc"])
    excl = [
        f"{n} at {r['horizon_days']} days"
        for n, rows in [("rebar", a["mill_test_rebar"]), ("HRC", a["mill_test_hrc"])]
        for r in rows
        if r["ci_lo_pct"] > 0 or r["ci_hi_pct"] < 0
    ]
    year_share = monthly.groupby(monthly.index.str[:4])[["freight_share_cfr_c5", "freight_share_cfr_c3"]].mean()
    top_year = all(
        year_share.loc[lm[:4], c] > year_share.drop(index=lm[:4])[c].max()
        for c in ["freight_share_cfr_c5", "freight_share_cfr_c3"]
    )
    state = (
        "closed" if last["margin_rmb_dmt"] < -band else ("open" if last["margin_rmb_dmt"] > band else "inside the band")
    )

    _style()
    figs = {
        "margin": fig_margin(daily, band, episodes),
        "bridge": fig_bridge(last),
        "freight": fig_freight(freight[freight.index >= pd.Timestamp("2014-01-01")], anchors, monthly),
        "mill": fig_mill(mill),
    }

    _fonts()
    st = _styles()
    story: list[Any] = []
    P = lambda text, s="body": Paragraph(text, st[s])  # noqa: E731

    story += [
        P("Iron ore into China: delivered cost and the import window", "title"),
        P(
            f"Nathan Couturier. Research note, data to {day(ld)} (daily) and {month(lm)} (monthly benchmark). "
            f"Interactive version, data and code: {URL}",
            "meta",
        ),
        P("Question", "h"),
        P(
            "When does it pay to bring a cargo of seaborne iron ore into China, from where, and who captures the "
            "margin between the mine and the blast furnace? The note traces the delivered cost of a 62% Fe cargo along "
            "the voyage: the index-equivalent FOB netback (the CFR index price minus modeled Capesize freight), CFR "
            "Qingdao, then USD/CNY, import VAT, port charges and voyage financing to the landed cost, which it compares "
            "with the Dalian futures price for the matching delivery; then it asks whether Chinese steel mill margins "
            "support the ore price."
        ),
        P("Answer", "h"),
    ]
    bullets = [
        f"On {day(ld)} a 62% Fe cargo from West Australia bought for delivery to Qingdao in about 45 days cost "
        f"{num(last['landed_rmb_dmt'])} RMB per dry tonne landed, VAT included, against {num(last['dce62_rmb_dmt'])} for 45-day Dalian delivery: a margin of "
        f"{signed(last['margin_rmb_dmt'])} RMB/dmt, so the window is {state}. The call is close: without the "
        f"{num(dsens['lift']['lift_usd_dmt'], 2)} USD/dmt lift that puts 2026 SGX prices on a 62% Fe basis the margin would be "
        f"{signed(dsens['no_lift']['margin_rmb_dmt'])}, and a CFR price {num(-dsens['cfr_change_to_band_usd'], 1)} USD lower "
        "would bring it inside the band.",
        f"The window has almost never been open. On the daily series (from December 2015) the margin exceeded the "
        f"{num(band)} RMB/dmt cost of using the exchange on {pct(wd['share_open'])} of trading days and never for more than "
        f"{max(r['length'] for r in wd['runs'] if r['state'] == 1)} days in a row; on the monthly baseline it was "
        f"below the band in {pct(wm['share_closed'], 0)} of {wm['n']} months and averaged {signed(wm['mean'])} RMB/dmt "
        f"({pct(-share_m)} of landed cost).",
        f"Gaps fade slowly: the half-life is {num(cm['half_life'], 1)} months on monthly data (95% interval "
        f"{num(cm['boot_half_life_lo'], 1)} to {num(cm['boot_half_life_hi'], 1)}), but a unit root cannot be rejected "
        f"there (ADF p = {num(cm['adf_p'], 2)}); on daily data the half-life is {num(cd['half_life'])} trading days "
        f"(ADF p = {num(cd['adf_p'], 3)}). The margin reverts to a negative level, not to zero.",
        f"Freight takes {pct(monthly['freight_share_cfr_c5'].mean())} of the CFR price from West Australia and "
        f"{pct(monthly['freight_share_cfr_c3'].mean())} from Brazil on average since 2014; Brazil's index-equivalent "
        f"netback trails Australia's by {num(gap.mean(), 1)} USD/dmt on average and by {num(gap.iloc[-1], 1)} in {month(lm)}.",
        f"Most of the discount sits in Dalian. On {len(pp['rows'])} dated Fastmarkets Qingdao port prices "
        f"({pp['rows'][0]['date'][:4]} to {pp['rows'][-1]['date'][:4]}), Dalian's 45-day price was "
        f"{num(-pp['dce45_minus_port_range'][1])} to {num(-pp['dce45_minus_port_range'][0])} RMB/dmt below the port "
        f"price of 62% fines, while the port price minus the landed cost ranged from "
        f"{signed(pp['port_minus_landed_range'][0])} to {signed(pp['port_minus_landed_range'][1])} RMB/dmt. Mills are squeezed: the "
        f"rebar futures margin was {signed(rebar.iloc[-1])} RMB/t on {day(str(rebar.index[-1])[:10])}, negative on "
        + ("every trading day" if ly_neg == 1 else f"{pct(ly_neg, 0)} of trading days")
        + f" of {ly}, and the pre-registered test finds "
        + (
            "no sign that low mill margins precede weaker ore."
            if no_sign
            else "that low mill margins precede weaker ore."
        ),
    ]
    story.append(
        ListFlowable([ListItem(P(b), leftIndent=10) for b in bullets], bulletType="bullet", start="•", leftIndent=10)
    )
    story += [
        KeepTogether(
            [
                _img(figs["bridge"]),
                P(
                    "Figure 1. Freight is modeled (hatched). FOB values are index-equivalent netbacks (CFR minus freight per "
                    "dry tonne) and ignore brand premiums and discounts. Sources: SGX, Dalian Commodity Exchange via Sina, "
                    "FRED; freight modeled from the Baltic Capesize Index and Brent.",
                    "cap",
                ),
            ]
        ),
        P("Data and conventions", "h"),
        P(
            "Seaborne price: IMF 62% Fe CFR China monthly average (FRED PIORECRUSDM) for the monthly baseline from "
            "January 2014; SGX iron ore futures interpolated to a 45-day horizon for the daily series from December 2015 "
            "(the current-month contract is not used because it settles on the month's average). SGX contracts from "
            "January 2026 settle on Platts IODEX at 61% Fe and are lifted to 62% by one constant, the mean measured monthly "
            f"spread to the IMF 62% average ({num(a['sgx_basis']['info']['spread_2026_mean'], 2)} USD/dmt). The daily series "
            "compares forward with forward (the hedgeable trade); the monthly baseline compares the spot index with 45-day "
            "Dalian and shows a deeper discount in steep backwardation. Dalian: every iron ore contract from "
            "the exchange's annual files (2013 to 2024) and Sina (2025 onward), expressed on a 62% Fe basis (standard grade "
            "61% from I2205, plus 10 x X with " + x_text + "), interpolated to a constant 45-day "
            f"maturity across contracts with at least {num(PARAMS['cm_min_oi_lots']['value'])} lots of open interest. "
            f"USD/CNY from FRED (DEXCHUS); SOFR (fed funds before April 2018) plus "
            f"{num(PARAMS['financing_spread_bp']['value'])} bp for financing; import VAT 17%, 16% from 1 May 2018 and 13% "
            f"from 1 April 2019, duty zero. Port charges {num(PARAMS['port_charges_rmb_wmt']['value'])} RMB per wet tonne "
            f"and moisture {pct(PARAMS['moisture']['value'], 0)} (per dry = per wet / "
            f"{num(1 - PARAMS['moisture']['value'], 2)}). Rebar and hot-rolled coil from the Shanghai Futures Exchange; "
            "coke from Dalian."
        ),
        KeepTogether(
            [
                P("The import window", "h"),
                _img(figs["margin"]),
                P(
                    f"Figure 2. Shaded: the no-arbitrage band of ±{num(band)} RMB/dmt (delivery fee, about a month of "
                    "warehouse storage and the vessel outbound fee cap at the fees in force since mid-2021; they were "
                    "higher before). Numbered: the three largest deviations from the mean, at least 120 trading days "
                    "apart. Sources: SGX, Dalian Commodity Exchange, FRED; computed by the pipeline.",
                    "cap",
                ),
            ]
        ),
    ]
    win_rows = [
        ["", "Monthly baseline", "Daily series"],
        ["Period", f"{month(monthly.index[0])} to {month(lm)}", f"{day(str(daily.index[0])[:10])} to {day(ld)}"],
        ["Observations", num(wm["n"]), num(wd["n"])],
        ["Mean, median (RMB/dmt)", f"{num(wm['mean'], 1)}, {num(wm['median'], 1)}", f"{num(wd['mean'], 1)}, {num(wd['median'], 1)}"],
        ["Share open, inside, closed", f"{pct(wm['share_open'])}, {pct(wm['share_inside'])}, {pct(wm['share_closed'])}",
         f"{pct(wd['share_open'])}, {pct(wd['share_inside'])}, {pct(wd['share_closed'])}"],
        ["Minimum", f"{num(wm['min'], 1)} ({month(wm['min_at'])})", f"{num(wd['min'], 1)} ({day(wd['min_at'][:10])})"],
        ["AR(1) half-life (95% interval)", f"{num(cm['half_life'], 1)} months ({num(cm['boot_half_life_lo'], 1)} to {num(cm['boot_half_life_hi'], 1)})",
         f"{num(cd['half_life'], 1)} days ({num(cd['boot_half_life_lo'], 1)} to {num(cd['boot_half_life_hi'], 1)})"],
        ["ADF statistic, p-value", f"{num(cm['adf_stat'], 2)}, {num(cm['adf_p'], 3)}", f"{num(cd['adf_stat'], 2)}, {num(cd['adf_p'], 3)}"],
    ]  # fmt: skip
    story += [
        _table(win_rows, [52, 61, 61], st),
        P("Table 1. Import margin statistics. Open: above +25 RMB/dmt; closed: below −25.", "cap"),
        P(
            "The two largest deviations have documented policy causes; the third is an artifact of an expiring "
            "contract. "
            + " ".join(
                f"({i}) {day(e['date'])}, {signed(float(daily.loc[pd.Timestamp(e['date']), 'margin_rmb_dmt']))} RMB/dmt: "
                f"{e['text']} [{'; '.join(s['name'] for s in e['sources'])}]"
                for i, e in enumerate(episodes, start=1)
            )
        ),
        P(
            "Sensitivity of the latest monthly margin "
            f"({month(a['tornado']['period'])}, {num(-a['tornado']['base_distance'], 1)} RMB/dmt below the open threshold): "
            + "; ".join(
                f"{r['assumption']} {signed(r['low'], 1)}"
                + (f" / {signed(r['high'], 1)}" if r["high"] is not None else "")
                for r in a["tornado"]["rows"][:5]
            )
            + ". No single assumption in its range opens the window. Against the most-active contract (about "
            f"{num(ma_dte)} days to expiry on average) the mean monthly margin would be "
            f"{num(a['maturity_comparison']['most_active'], 1)} instead of {num(a['maturity_comparison']['45'], 1)} RMB/dmt, "
            "because the Dalian curve is usually backwardated."
        ),
        P(imports_text(a)),
        P("Freight and origins", "h"),
        P(
            "Capesize route rates (C3 Tubarao to Qingdao, C5 West Australia to Qingdao) are paid data, so freight is "
            "modeled. A voyage model converts the Baltic Capesize Index into a time charter rate (calibrated by regime on "
            f"{sum(v['n'] for v in a['freight']['tc_calibration'].values())} dated public pairs) and Brent into a bunker "
            "price (calibrated separately before and after the IMO 2020 sulphur cap), then prices the round voyage at the "
            "Baltic eco speed of 12 knots over searoute distances "
            f"({num(a['freight']['voyages']['C5']['laden_nm'])} and {num(a['freight']['voyages']['C3']['laden_nm'])} nautical "
            f"miles). It is never fitted to a route rate; against published assessments it scores RMSE "
            f"{num(fe['C5']['voyage']['rmse'], 2)} USD/t on C5 (n = {fe['C5']['voyage']['n']}) and "
            f"{num(fe['C3']['voyage']['rmse'], 2)} on C3 (n = {fe['C3']['voyage']['n']}); a regression on the BCI and Brent "
            f"scores {num(fe['C5']['stat_loo']['rmse'], 2)} and {num(fe['C3']['stat_loo']['rmse'], 2)} out of sample. "
            f"In the voyage model the C3 minus C5 spread rises by about {num(sens['c3_minus_c5_vs_bci']['b'] * 1000, 1)} USD/t per 1,000 BCI "
            f"points (correlation {num(sens['c3_minus_c5_vs_bci']['corr'], 2)}). In {lm[:4]} freight takes "
            f"{pct(year_share.loc[lm[:4], 'freight_share_cfr_c5'])} of CFR from Australia and "
            f"{pct(year_share.loc[lm[:4], 'freight_share_cfr_c3'])} from Brazil"
            + (", the highest annual shares since 2014." if top_year else ".")
        ),
        KeepTogether(
            [
                _img(figs["freight"]),
                P(
                    "Figure 3. Left: modeled C3 and C5 (dashed lines) with shaded 80% error bands and the published assessments used to "
                    "score them (circles: Baltic Exchange via the shipping press, Platts, Ruida Futures). Right: modeled "
                    "freight per dry tonne as a share of the 62% CFR price. Sources: East Money (BCI), FRED, IMF.",
                    "cap",
                ),
            ]
        ),
        P("Mill margins", "h"),
        P(
            "The Chinese market convention values a tonne of steel against 1.6 t of iron ore, 0.5 t of coke and a fixed "
            f"{num(PARAMS['mill_other_costs_rebar']['value'])} RMB/t of other costs (rebar; HRC 150 more), a broker "
            "convention rather than an accounting margin. The pre-registered test (written before computing it) asks "
            "whether a rebar margin in the bottom decile of its previous three years precedes weaker Dalian ore over one "
            "to three months."
        ),
        KeepTogether(
            [
                _img(figs["mill"]),
                P(
                    "Figure 4. Most-active contracts. Sources: Shanghai Futures Exchange, Dalian Commodity Exchange, Sina.",
                    "cap",
                ),
            ]
        ),
    ]
    test_rows = [["Margin", "Horizon", "Signal days", "Effect, pp", "95% interval", "Newey-West t"]]
    for name, src in [("Rebar", tr), ("HRC", th)]:
        for h in (21, 42, 63):
            r = src[h]
            test_rows.append(
                [name, f"{h} days", num(r["n_signal_days"]), signed(r["effect_pct"], 2),
                 f"{signed(r['ci_lo_pct'], 1)} to {signed(r['ci_hi_pct'], 1)}", num(r["nw_t"], 2)]
            )  # fmt: skip
    story += [
        KeepTogether(
            [
                _table(test_rows, [22, 22, 26, 26, 40, 30], st),
                P(
                    "Table 2. Difference in the forward log change of the Dalian 45-day price between signal days and other days; "
                    "95% intervals from a moving block bootstrap (63-day blocks). The hypothesis was a negative effect; "
                    + ("every estimate is positive" if all_pos else "the estimates have mixed signs")
                    + (
                        f" and only {', '.join(excl)} has an interval that excludes zero."
                        if excl
                        else " and every interval includes zero."
                    ),
                    "cap",
                ),
            ]
        ),
    ]
    mrows = mm_["rows"]
    sdic = [r for r in mrows if r["independent"]]
    ebr = [r for r in mrows if not r["independent"]]
    sdic_err = max((r["error_rmb_t"] for r in sdic), key=abs)
    ebr_err = max(abs(r["error_rmb_t"]) for r in ebr)
    val_rows = [
        ["Check", "n", "Result", "Tolerance"],
        ["Import cost, Ruida Futures estimates, FX that best fits theirs (PBoC central parity)", str(len(ic["rows"])),
         f"max error {num(ic['max_abs_error_ours_central_parity'], 1)} RMB/t "
         f"({num(ic['max_abs_error_ours'], 1)} with the New York rate used for the headline)", f"{num(TOLERANCE['import_cost_rmb_t'])} RMB/t"],
        ["Fastmarkets Qingdao port price to USD/dmt", str(len(pp["rows"])), f"max error {num(pp['max_abs_error_usd'], 2)} USD/dmt",
         f"{num(TOLERANCE['port_price_usd_dmt'])} USD/dmt"],
        ["Rebar margin, SDIC Essence Futures (independent)", str(len(sdic)), f"error {signed(sdic_err, 2)} RMB/t",
         f"{num(TOLERANCE['mill_margin_rmb_t'])} RMB/t"],
        ["Rebar margin, Everbright Futures 2026 (constant calibrated on these)", str(len(ebr)),
         f"max error {num(ebr_err, 1)} RMB/t; checks prices and contracts only", "calibration"],
        ["C3 freight, voyage model", str(fe["C3"]["voyage"]["n"]), f"RMSE {num(fe['C3']['voyage']['rmse'], 2)} USD/t",
         f"{num(TOLERANCE['freight_rmse_usd_t']['C3'], 1)} USD/t"],
        ["C5 freight, voyage model", str(fe["C5"]["voyage"]["n"]), f"RMSE {num(fe['C5']['voyage']['rmse'], 2)} USD/t",
         f"{num(TOLERANCE['freight_rmse_usd_t']['C5'], 1)} USD/t"],
    ]  # fmt: skip
    story += [
        KeepTogether(
            [
                P("Validation", "h"),
                _table(val_rows, [55, 10, 82, 27], st),
                P(
                    "Table 3. Tolerances are enforced by the test suite. The mill "
                    "margin's other-cost constant is calibrated on Everbright Futures, so those rows are not independent "
                    f"checks; the {num(PARAMS['port_charges_rmb_wmt']['value'])} RMB/wmt port charge was set with the Ruida and "
                    "Fastmarkets figures in view (they imply 30 to 35 and 31 to 40), so those two rows test the price, FX, VAT and "
                    "moisture conventions more than the port charge. The freight model's time charter and bunker maps "
                    "are fitted on separate public pairs, never on route rates, so the C3 and C5 rows are out of sample. "
                    "Each anchor, with its link, is listed on the Method and data page.",
                    "cap",
                ),
            ]
        ),
        P("Limitations", "h"),
        P(
            "The margin is an expected margin, not a riskless arbitrage: price, basis, grade and currency risk remain while "
            "the cargo is at sea. Dalian prices the cheapest deliverable brand with fixed quality discounts, so part of the "
            "persistent discount is a brand and grade effect. Freight is modeled, with the errors shown above; the "
            "published anchors cluster in 2021 to 2026 and the model has run above the most recent C3 rates "
            f"(mean error {signed(rec_c3, 1)} USD/t on the last five). Port charges are a single assumption. The daily "
            "series uses SGX futures, lifted from a 61% to a 62% basis in 2026 by one constant; the latest window call "
            "depends on that lift, and against the World Bank series instead of the IMF one the 2026 spread averages "
            f"{signed(dsens['lift_world_bank']['lift_usd_dmt'], 2)} USD, which would put the margin at "
            f"{signed(dsens['lift_world_bank']['margin_rmb_dmt'])}. The third episode rests on an expiring contract. "
            "Import volumes come from the English China Customs bulletins, which start in 2018, and the imports test "
            "cannot separate an effect of the window from the policy episodes of 2021 and 2022."
        ),
        P("Sources", "h"),
        P(
            "FRED: IMF iron ore (PIORECRUSDM), Federal Reserve USD/CNY (DEXCHUS), New York Fed SOFR, effective federal "
            "funds rate (DFF), EIA Brent (DCOILBRENTEU); World Bank Pink Sheet; "
            "Dalian Commodity Exchange annual files and rules; Shanghai Futures Exchange daily files; Sina futures history; "
            "SGX daily settlement files; Baltic Capesize Index via East Money; SAFE central parity; China Customs (GACC) "
            "monthly bulletins; searoute; Natural Earth. "
            "Validation: Ruida Futures daily reports, Fastmarkets, Everbright Futures, SDIC Essence Futures, Baltic "
            "Exchange route reports in the shipping press. Episode sources: NDRC, MIIT, World Bank Commodity Markets "
            f"Outlook, DCE notices. Full list with links and retrieval dates: {URL}#method. Code: {REPO}."
        ),
    ]

    OUT.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(OUT),
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=18 * mm,
        title="Iron ore into China: delivered cost and the import window",
        author="Nathan Couturier",
        subject="Research note: seaborne iron ore delivered cost against Dalian futures",
        creator="Nathan Couturier",
    )
    # a section heading never sits alone at the foot of a page
    story = [
        x
        for f in story
        for x in ([CondPageBreak(25 * mm), f] if isinstance(f, Paragraph) and f.style.name == "h" else [f])
    ]
    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return OUT


def run() -> dict[str, str]:
    path = build()
    from pypdf import PdfReader  # noqa: PLC0415

    pages = len(PdfReader(str(path)).pages)
    return {"report": f"{path.name}, {pages} pages, built {datetime.now(UTC).date().isoformat()}"}
