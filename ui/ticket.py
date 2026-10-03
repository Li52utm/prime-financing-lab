"""Sidebar trade ticket. Builds engine inputs from assumptions.py defaults and the widgets,
and stores them in st.session_state["ctx"] for every page."""

from dataclasses import dataclass

import streamlit as st

import assumptions as A
from data.sonia import STALE_BUSINESS_DAYS, SoniaQuote, load_sonia
from engine.capital import CapitalInputs, NettingSetTrade, default_capital_inputs
from engine.financing import GILT_SOURCES, FinancingInputs, default_inputs

ASSET_LABELS = {
    "large_cap": "Large-cap (main index)",
    "small_cap": "Small-cap (AIM)",
    "convertible_style": "Convertible-style",
}
GILT_SOURCE_LABELS = {
    "reverse_repo": "Reverse repo (cash)",
    "borrowed": "Borrowed (securities for securities)",
    "inventory": "Own inventory",
}
NETTING_CASE_LABELS = {
    "different_name": "Client short TRS, different name",
    "same_name": "Client short TRS, same name",
}


@dataclass(frozen=True)
class Context:
    fin: FinancingInputs
    cap: CapitalInputs
    asset_class: str
    asset_label: str
    tenor: str
    netting_on: bool
    netting_case: str
    netting_notional: float
    sonia_quote: SoniaQuote  # live / cached / fallback value as loaded
    sonia_overridden: bool  # True if the manual override replaced it


SONIA_TTL_SECONDS = 6 * 3600


@st.cache_data(ttl=SONIA_TTL_SECONDS, show_spinner="Fetching SONIA...")
def cached_sonia() -> SoniaQuote:
    """Live SONIA via data.sonia (network), cached in-process for 6 hours."""
    return load_sonia()


def render_sonia(sb) -> tuple[SoniaQuote, float, bool]:
    """SONIA block at the top of the sidebar. Returns (quote, SONIA used, overridden)."""
    q = cached_sonia()
    as_of = q.as_of.strftime("%d %b %Y") if q.as_of else "n/a"
    age = f" ({q.business_days_old} business days old)" if q.as_of else ""
    sb.subheader("SONIA")
    sb.markdown(
        f"**{q.rate * 100:.4f}%**  \n"
        f"As of: {as_of}{age}  \n"
        f"Source: {q.source}  \n"
        f"Status: **{q.status}**")
    if q.status == "cached":
        sb.warning(f"Live SONIA fetch failed. Using the cached value as of {as_of}.",
                   icon=":material/warning:")
    elif q.status == "fallback":
        sb.warning("Live SONIA and the cache are unavailable. Using the placeholder in "
                   "assumptions.py, which is not a market level.", icon=":material/warning:")
    elif q.stale:
        sb.warning(f"SONIA as-of date is more than {STALE_BUSINESS_DAYS} business days old "
                   f"({as_of}).", icon=":material/warning:")
    overridden = sb.toggle("Manual SONIA override", value=False, key="sonia_override")
    sonia = q.rate
    if overridden:
        sonia = sb.slider("Override SONIA (%)", 0.0, 15.0, round(q.rate * 100, 2), step=0.01,
                          format="%.2f", key="sonia_override_pct") / 100
        sb.caption("Override in use: the loaded SONIA is ignored.")
    return q, sonia, overridden


def netting_trade(case: str, notional: float) -> NettingSetTrade:
    """The client's other trade, dealer-side signed notional (client short -> dealer long)."""
    entity = "subject" if case == "same_name" else "other"
    return NettingSetTrade(entity, notional)


def render_ticket() -> Context:
    sb = st.sidebar
    sb.header("Trade ticket")
    quote, sonia, overridden = render_sonia(sb)
    sb.divider()
    notional_m = sb.number_input("Notional (GBP m)", min_value=1.0, max_value=1000.0,
                                 value=A.DEFAULT_NOTIONAL / 1e6, step=1.0, key="notional_m")
    tenor = sb.radio("Tenor", list(A.TENOR_DAYS), index=list(A.TENOR_DAYS).index(A.DEFAULT_TENOR),
                     horizontal=True, key="tenor")
    asset_class = sb.selectbox("Asset class", list(ASSET_LABELS), format_func=ASSET_LABELS.get,
                               index=list(ASSET_LABELS).index(A.DEFAULT_ASSET_CLASS),
                               key="asset_class")
    c1, c2 = sb.columns(2)
    dividend_pct = c1.number_input("Dividend (% of N)", min_value=0.0, max_value=20.0,
                                   value=A.DIVIDEND * 100, step=0.1, key="dividend_pct")
    ex_div_day = c2.number_input("Ex-div day", min_value=0, max_value=365, value=A.EX_DIV_DAY,
                                 step=1, key="ex_div_day")
    sdrt = sb.toggle("Include SDRT (0.5%)", value=A.INCLUDE_SDRT, key="sdrt")
    holding = sb.number_input("Holding period (days, SDRT amortisation)", min_value=1,
                              max_value=3650, value=A.HOLDING_PERIOD_DAYS, step=1,
                              key="holding_days")
    netting_on = sb.toggle("Netting set: include client's other trade", value=False,
                           key="netting")
    netting_case = A.NETTING_DEFAULT_CASE
    netting_notional = A.NETTING_OTHER_NOTIONAL
    if netting_on:
        netting_case = sb.radio("Other trade", list(NETTING_CASE_LABELS),
                                format_func=NETTING_CASE_LABELS.get, key="netting_case")
        netting_notional = sb.number_input("Other trade notional (GBP m, hypothetical)",
                                           min_value=0.0, max_value=1000.0,
                                           value=A.NETTING_OTHER_NOTIONAL / 1e6, step=1.0,
                                           key="netting_notional_m") * 1e6
        sb.caption("Requires a legally enforceable netting agreement.")
    margined = sb.toggle("TRS margined (daily VM)", value=A.TRS_MARGINED, key="margined")
    gilt_source = sb.selectbox("Upgrade gilt source", list(GILT_SOURCES),
                               format_func=GILT_SOURCE_LABELS.get,
                               index=list(GILT_SOURCES).index(A.DEFAULT_GILT_SOURCE),
                               key="gilt_source")
    k_pct = sb.slider("Shadow cost of balance sheet k (%)", A.SHADOW_COST_K_MIN * 100,
                      A.SHADOW_COST_K_MAX * 100, A.SHADOW_COST_K * 100,
                      step=A.SHADOW_COST_K_STEP * 100, format="%.2f", key="k_pct")
    target_rorwa_pct = sb.number_input("Target return on RWA (%)", min_value=0.0,
                                       max_value=20.0, value=A.TARGET_RORWA * 100, step=0.25,
                                       key="target_rorwa_pct")
    # Slider runs from SONIA flat to SONIA (IM earns nothing), using the SONIA in use.
    im_max_bp = round(sonia * 1e4 / 5) * 5.0
    if st.session_state.get("im_spread_bp", 0.0) > im_max_bp:
        st.session_state["im_spread_bp"] = im_max_bp
    im_spread_bp = sb.slider("TRS IM remuneration: SONIA minus (bp)",
                             A.IM_REMUNERATION_SPREAD_MIN * 1e4, im_max_bp,
                             min(A.IM_REMUNERATION_SPREAD * 1e4, im_max_bp), step=5.0,
                             key="im_spread_bp")

    with sb.expander("Advanced"):
        regime = st.selectbox("Haircut regime", list(A.HAIRCUT_REGIMES),
                              format_func=lambda r: A.HAIRCUT_REGIMES[r]["label"],
                              index=list(A.HAIRCUT_REGIMES).index(A.DEFAULT_HAIRCUT_REGIME),
                              key="regime")
        street_leg = st.toggle("Include street counterparty leg", value=A.INCLUDE_STREET_LEG,
                               key="street_leg")
        surplus = st.selectbox("Surplus cash placement", ["central_bank", "counted"],
                               format_func={"central_bank": "Central bank (excluded)",
                                            "counted": "Placed elsewhere (counted)"}.get,
                               key="surplus")
        pb_liq = st.radio("PB liquidation period (days)", [10, 5],
                          index=[10, 5].index(A.PB_LIQUIDATION_DAYS), horizontal=True,
                          key="pb_liq")
        rw_client_pct = st.number_input("Risk weight: client (%)", 0.0, 1250.0,
                                        A.RW_CLIENT * 100, step=5.0, key="rw_client_pct")
        rw_street_pct = st.number_input("Risk weight: street bank (%)", 0.0, 1250.0,
                                        A.RW_STREET * 100, step=5.0, key="rw_street_pct")
        units = st.toggle("TRS on a number of shares (notional moves with price)",
                          value=A.TRS_NOTIONAL_IN_UNITS, key="units")
        resets = st.toggle("TRS resets monthly (SA-CCR maturity = next reset)", value=False,
                           key="resets")

    fin = default_inputs(
        asset_class, tenor,
        notional=notional_m * 1e6,
        sonia=sonia,
        dividend=dividend_pct / 100,
        ex_div_day=int(ex_div_day),
        include_sdrt=sdrt,
        holding_period_days=int(holding),
        gilt_source=gilt_source,
        shadow_cost_k=k_pct / 100,
        im_remuneration_spread=im_spread_bp / 1e4,
    )
    cap = default_capital_inputs(
        asset_class,
        haircut_regime=regime,
        include_street_leg=street_leg,
        surplus_cash_placement=surplus,
        pb_liquidation_days=int(pb_liq),
        rw_client=rw_client_pct / 100,
        rw_street=rw_street_pct / 100,
        trs_margined=margined,
        trs_notional_in_units=units,
        trs_reset_days=A.MONTH_DAYS if resets else None,
        target_rorwa=target_rorwa_pct / 100,
        netting_set=(netting_trade(netting_case, netting_notional),) if netting_on else (),
    )
    ctx = Context(fin, cap, asset_class, ASSET_LABELS[asset_class], tenor, netting_on,
                  netting_case, netting_notional, quote, overridden)
    st.session_state["ctx"] = ctx
    return ctx


def get_ctx() -> Context:
    return st.session_state["ctx"]
