"""Step 1: financing cost of a long equity position via three routes.

Routes: on-sheet prime brokerage (PB), total return swap (TRS), collateral upgrade.

Scope and simplifications:
- Static notional. Price moves and variation margin are ignored.
- Balance sheet figures here are accounting balance sheet only. The headline balance-sheet
  metric is return on leverage exposure in engine/capital.py (illustrative).
- The collateral upgrade is off the accounting balance sheet (securities for securities),
  so its ROBS here is None. Its real leverage exposure is in engine/capital.py.

Conventions: GBP, ACT/365, rates and spreads as decimals. Costs are GBP over the tenor.
"""

from dataclasses import dataclass, replace

import pandas as pd

import assumptions as A


@dataclass(frozen=True)
class FinancingInputs:
    notional: float
    tenor_days: int
    holding_period_days: int  # client's intended hold; one-off SDRT is amortised over it
    sonia: float
    client_funding_rate: float
    unsecured_spread: float
    im_remuneration_spread: float  # client earns SONIA minus this on TRS cash IM
    # asset-class terms
    pb_margin: float
    trs_im: float
    street_haircut: float
    pb_spread: float
    trs_spread: float
    street_repo_spread: float
    upgrade_haircut: float
    upgrade_fee: float
    aim_listed: bool
    # collateral upgrade gilt leg
    gilt_source: str  # how the dealer sources the gilts: one of GILT_SOURCES
    gilt_repo_spread: float  # gilt repo rate over SONIA (client's repo and dealer's reverse repo)
    gilt_haircut: float
    gilt_borrow_fee: float
    # dividends and tax
    dividend: float  # gross dividend as a fraction of notional
    ex_div_day: int  # days from trade start
    trs_pass_through: float
    manufactured_pass_through: float
    wht_client: float
    wht_dealer: float
    include_sdrt: bool
    sdrt_rate: float
    dealer_hedge_sdrt_rate: float
    # balance sheet
    shadow_cost_k: float  # shadow cost of balance sheet, also the ROBS hurdle


def default_inputs(asset_class: str = A.DEFAULT_ASSET_CLASS, tenor: str = A.DEFAULT_TENOR,
                   **overrides) -> FinancingInputs:
    """Build inputs from assumptions.py, then apply any overrides."""
    inputs = FinancingInputs(
        notional=A.DEFAULT_NOTIONAL,
        tenor_days=tenor_days(tenor),
        holding_period_days=A.HOLDING_PERIOD_DAYS,
        sonia=A.SONIA,
        client_funding_rate=A.CLIENT_FUNDING_RATE,
        unsecured_spread=A.DEALER_UNSECURED_SPREAD,
        im_remuneration_spread=A.IM_REMUNERATION_SPREAD,
        **A.ASSET_CLASSES[asset_class],
        gilt_source=A.DEFAULT_GILT_SOURCE,
        gilt_repo_spread=A.GILT_REPO_SPREAD,
        gilt_haircut=A.GILT_HAIRCUT,
        gilt_borrow_fee=A.GILT_BORROW_FEE,
        dividend=A.DIVIDEND,
        ex_div_day=A.EX_DIV_DAY,
        trs_pass_through=A.TRS_PASS_THROUGH,
        manufactured_pass_through=A.MANUFACTURED_PASS_THROUGH,
        wht_client=A.WHT_CLIENT,
        wht_dealer=A.WHT_DEALER,
        include_sdrt=A.INCLUDE_SDRT,
        sdrt_rate=A.SDRT_RATE,
        dealer_hedge_sdrt_rate=A.DEALER_HEDGE_SDRT_RATE,
        shadow_cost_k=A.SHADOW_COST_K,
    )
    return replace(inputs, **overrides)


@dataclass(frozen=True)
class RouteResult:
    route: str
    financing_cost: float  # headline: interest, margin opportunity cost, fees, amortised SDRT
    dividend_credit: float  # dividend (or manufactured dividend) received by the client
    net_cost: float  # financing_cost - dividend_credit
    sdrt_one_off: float  # full SDRT paid on purchase (0 if off, AIM, or TRS)
    sdrt: float  # amortised SDRT charged to this tenor, included in financing_cost
    financing_cost_ex_sdrt: float
    dealer_net: float  # sum of dealer_parts
    dealer_parts: dict  # DEALER_PART_NAMES -> GBP over the tenor
    balance_sheet: float
    balance_sheet_off_sheet: bool
    shadow_cost: float  # reported separately; NOT deducted from ROBS
    robs: float | None  # gross annualised return on balance sheet
    spread_name: str  # the dealer pricing lever for this route
    required_spread: float | None  # spread at which gross ROBS == shadow_cost_k


GILT_SOURCES = ("reverse_repo", "borrowed", "inventory")

DEALER_PART_NAMES = (
    "sonia_from_client",  # SONIA leg received on the loan / TRS notional
    "spread_income",  # client spread or upgrade fee
    "street_funding",  # street repo at SONIA + street spread (negative)
    "cash_gap",  # surplus earns SONIA; shortfall pays SONIA + unsecured spread
    "im_remuneration",  # interest paid to the client on TRS cash IM (negative)
    "gilt_reverse_repo",  # interest earned reversing in the upgrade gilts (reverse_repo source)
    "dividend_pickup",  # dividend kept net of WHT minus amount passed to the client
    "hedge_sdrt",  # SDRT on the dealer's TRS hedge (negative)
    "gilt_borrow",  # cost of sourcing gilts in the upgrade (negative)
)


def _dealer_parts(**parts: float) -> dict:
    return {name: parts.get(name, 0.0) for name in DEALER_PART_NAMES}


# --- Helpers ----------------------------------------------------------------

def year_fraction(days: int) -> float:
    """ACT/365."""
    return days / A.DAYS_IN_YEAR


def tenor_days(tenor: str) -> int:
    if tenor not in A.TENOR_DAYS:
        raise ValueError(f"Unknown tenor {tenor!r}; expected one of {list(A.TENOR_DAYS)}")
    return A.TENOR_DAYS[tenor]


def dividend_in_window(ex_div_day: int, tenor_days: int) -> bool:
    """A dividend counts if its ex-date falls after trade start and on or before maturity."""
    return 0 < ex_div_day <= tenor_days


def net_dividend(gross: float, wht: float) -> float:
    return gross * (1 - wht)


def funding_gap_cost(gap: float, sonia: float, unsecured_spread: float, tau: float) -> float:
    """Cost of the dealer's cash gap. A shortfall (gap > 0) pays SONIA + unsecured spread.
    A surplus (gap < 0) earns SONIA flat, which gives a negative cost."""
    if gap > 0:
        return gap * (sonia + unsecured_spread) * tau
    return gap * sonia * tau


def im_remuneration(x: "FinancingInputs", tau: float) -> float:
    """Interest the dealer pays the client on TRS cash IM: N * trs_im * (SONIA - spread) * tau.
    It reduces the client's cost and the dealer's net by the same amount."""
    return x.notional * x.trs_im * (x.sonia - x.im_remuneration_spread) * tau


def shadow_bs_cost(balance_sheet: float, k: float, tau: float) -> float:
    return balance_sheet * k * tau


def annualised_bp(amount: float, notional: float, tau: float) -> float:
    return amount / (notional * tau) * 1e4


def robs(dealer_net: float, balance_sheet: float, tau: float) -> float | None:
    """Gross annualised return on balance sheet. Undefined (None) when balance sheet is 0."""
    if balance_sheet <= 0:
        return None
    return dealer_net / (balance_sheet * tau)


def required_spread(dealer_net: float, current_spread: float, spread_base: float,
                    balance_sheet: float, hurdle: float, tau: float) -> float | None:
    """Spread s at which gross ROBS equals the hurdle.

    Dealer net is linear in its spread: net(s) = a + spread_base * s * tau,
    where a = net(current) - spread_base * current * tau.
    Solve a + spread_base * s * tau = hurdle * balance_sheet * tau.
    """
    if balance_sheet <= 0:
        return None
    a = dealer_net - spread_base * current_spread * tau
    return (hurdle * balance_sheet * tau - a) / (spread_base * tau)


def _dividend_amount(x: FinancingInputs) -> float:
    return x.notional * x.dividend if dividend_in_window(x.ex_div_day, x.tenor_days) else 0.0


def _sdrt_applies(x: FinancingInputs) -> bool:
    return x.include_sdrt and not x.aim_listed


def client_sdrt(x: FinancingInputs) -> float:
    """One-off SDRT paid by the client on buying the shares (PB and collateral upgrade)."""
    return x.notional * x.sdrt_rate if _sdrt_applies(x) else 0.0


def amortised_sdrt(one_off: float, tenor_days: int, holding_period_days: int) -> float:
    """Share of one-off SDRT charged to one tenor: one_off * min(1, tenor / holding period).
    If the hold is no longer than the tenor, the whole charge falls in this tenor."""
    if holding_period_days <= 0:
        raise ValueError("holding_period_days must be positive")
    return one_off * min(1.0, tenor_days / holding_period_days)


def _client_sdrt_amortised(x: FinancingInputs) -> float:
    return amortised_sdrt(client_sdrt(x), x.tenor_days, x.holding_period_days)


def _street_repo_cost(x: FinancingInputs, tau: float) -> float:
    return x.notional * (1 - x.street_haircut) * (x.sonia + x.street_repo_spread) * tau


# --- Routes -----------------------------------------------------------------

def pb_route(x: FinancingInputs) -> RouteResult:
    """On-sheet PB: the client buys the stock and borrows L = N(1 - pb_margin) from the dealer.
    The dealer repos the stock in the street and funds the gap N(street_haircut - pb_margin)."""
    tau = year_fraction(x.tenor_days)
    loan = x.notional * (1 - x.pb_margin)
    interest = loan * (x.sonia + x.pb_spread) * tau
    margin_cost = x.notional * x.pb_margin * x.client_funding_rate * tau
    sdrt = _client_sdrt_amortised(x)
    financing_cost = interest + margin_cost + sdrt
    client_div = net_dividend(_dividend_amount(x), x.wht_client)

    gap = x.notional * (x.street_haircut - x.pb_margin)
    parts = _dealer_parts(
        sonia_from_client=loan * x.sonia * tau,
        spread_income=loan * x.pb_spread * tau,
        street_funding=-_street_repo_cost(x, tau),
        cash_gap=-funding_gap_cost(gap, x.sonia, x.unsecured_spread, tau),
    )
    dealer_net = sum(parts.values())

    return RouteResult(
        route="PB",
        financing_cost=financing_cost,
        dividend_credit=client_div,
        net_cost=financing_cost - client_div,
        sdrt_one_off=client_sdrt(x),
        sdrt=sdrt,
        financing_cost_ex_sdrt=financing_cost - sdrt,
        dealer_net=dealer_net,
        dealer_parts=parts,
        balance_sheet=loan,
        balance_sheet_off_sheet=False,
        shadow_cost=shadow_bs_cost(loan, x.shadow_cost_k, tau),
        robs=robs(dealer_net, loan, tau),
        spread_name="pb_spread",
        required_spread=required_spread(dealer_net, x.pb_spread, loan, loan, x.shadow_cost_k, tau),
    )


def trs_route(x: FinancingInputs) -> RouteResult:
    """TRS: the client pays SONIA + trs_spread on N, receives pass-through x gross dividend,
    and posts cash IM, which earns SONIA - im_remuneration_spread. The dealer buys the hedge,
    repos it, and funds N(street_haircut - trs_im)."""
    tau = year_fraction(x.tenor_days)
    floating = x.notional * (x.sonia + x.trs_spread) * tau
    im_cost = x.notional * x.trs_im * x.client_funding_rate * tau
    im_interest = im_remuneration(x, tau)
    gross_div = _dividend_amount(x)
    passed_div = x.trs_pass_through * gross_div
    financing_cost = floating + im_cost - im_interest

    gap = x.notional * (x.street_haircut - x.trs_im)
    # UNVERIFIED: dealer hedge SDRT treatment (intermediary relief); see assumptions.py
    hedge_sdrt = x.notional * x.dealer_hedge_sdrt_rate if _sdrt_applies(x) else 0.0
    parts = _dealer_parts(
        sonia_from_client=x.notional * x.sonia * tau,
        spread_income=x.notional * x.trs_spread * tau,
        street_funding=-_street_repo_cost(x, tau),
        cash_gap=-funding_gap_cost(gap, x.sonia, x.unsecured_spread, tau),
        im_remuneration=-im_interest if im_interest else 0.0,
        dividend_pickup=net_dividend(gross_div, x.wht_dealer) - passed_div,
        hedge_sdrt=-hedge_sdrt if hedge_sdrt else 0.0,
    )
    dealer_net = sum(parts.values())

    return RouteResult(
        route="TRS",
        financing_cost=financing_cost,
        dividend_credit=passed_div,
        net_cost=financing_cost - passed_div,
        sdrt_one_off=0.0,
        sdrt=0.0,
        financing_cost_ex_sdrt=financing_cost,
        dealer_net=dealer_net,
        dealer_parts=parts,
        balance_sheet=x.notional,
        balance_sheet_off_sheet=False,
        shadow_cost=shadow_bs_cost(x.notional, x.shadow_cost_k, tau),
        robs=robs(dealer_net, x.notional, tau),
        spread_name="trs_spread",
        required_spread=required_spread(dealer_net, x.trs_spread, x.notional, x.notional,
                                        x.shadow_cost_k, tau),
    )


def upgrade_route(x: FinancingInputs) -> RouteResult:
    """Collateral upgrade: the client buys the stock, lends it to the dealer for gilts
    G = N(1 - upgrade_haircut), and repos the gilts for cash C = G(1 - gilt_haircut).
    The client funds the shortfall N - C itself.

    Dealer P&L depends on gilt_source (matching engine.capital.upgrade_capital):
    - reverse_repo: earns the fee; repos the client's equities to the street for
      N(1 - h_st) at SONIA + street spread; reverses in the gilts for R = G(1 - gilt_haircut)
      at SONIA + gilt_repo_spread; the cash gap (raised - R) earns SONIA or costs
      SONIA + unsecured spread; pays the gilt borrow fee on G (own assumption: sourcing
      or specialness cost on top of the GC reverse repo rate).
    - borrowed / inventory: fee minus gilt borrow fee on G (securities for securities).
    """
    if x.gilt_source not in GILT_SOURCES:
        raise ValueError(f"Unknown gilt_source {x.gilt_source!r}; expected one of {GILT_SOURCES}")
    tau = year_fraction(x.tenor_days)
    gilts = x.notional * (1 - x.upgrade_haircut)
    cash = gilts * (1 - x.gilt_haircut)
    fee = x.notional * x.upgrade_fee * tau
    gilt_repo = cash * (x.sonia + x.gilt_repo_spread) * tau
    shortfall_cost = (x.notional - cash) * x.client_funding_rate * tau
    sdrt = _client_sdrt_amortised(x)
    # UNVERIFIED: assumes stock-lending relief means the loan itself attracts no SDRT.
    financing_cost = fee + gilt_repo + shortfall_cost + sdrt
    gross_div = _dividend_amount(x)
    manufactured = x.manufactured_pass_through * gross_div

    legs = {}
    balance_sheet = 0.0
    if x.gilt_source == "reverse_repo":
        raised = x.notional * (1 - x.street_haircut)
        cash_lent = gilts * (1 - x.gilt_haircut)
        legs = {
            "street_funding": -_street_repo_cost(x, tau),
            "gilt_reverse_repo": cash_lent * (x.sonia + x.gilt_repo_spread) * tau,
            "cash_gap": -funding_gap_cost(cash_lent - raised, x.sonia, x.unsecured_spread, tau),
        }
        # Accounting assets: reverse repo receivable plus any surplus cash.
        balance_sheet = cash_lent + max(0.0, raised - cash_lent)
    parts = _dealer_parts(
        spread_income=fee,
        dividend_pickup=net_dividend(gross_div, x.wht_dealer) - manufactured,
        gilt_borrow=-gilts * x.gilt_borrow_fee * tau,
        **legs,
    )
    dealer_net = sum(parts.values())
    # borrowed / inventory: off the accounting balance sheet (securities for securities),
    # so accounting ROBS is None. Leverage exposure comes from engine.capital.upgrade_capital.

    return RouteResult(
        route="Collateral upgrade",
        financing_cost=financing_cost,
        dividend_credit=manufactured,
        net_cost=financing_cost - manufactured,
        sdrt_one_off=client_sdrt(x),
        sdrt=sdrt,
        financing_cost_ex_sdrt=financing_cost - sdrt,
        dealer_net=dealer_net,
        dealer_parts=parts,
        balance_sheet=balance_sheet,
        balance_sheet_off_sheet=balance_sheet == 0.0,
        shadow_cost=shadow_bs_cost(balance_sheet, x.shadow_cost_k, tau),
        robs=robs(dealer_net, balance_sheet, tau),
        spread_name="upgrade_fee",
        required_spread=required_spread(dealer_net, x.upgrade_fee, x.notional, balance_sheet,
                                        x.shadow_cost_k, tau),
    )


# --- Comparison -------------------------------------------------------------

def breakeven_trs_spread(x: FinancingInputs) -> float:
    """TRS spread at which the client's TRS net cost equals its PB net cost.

    Net cost (financing - dividend credit) is used because dividend treatment differs by route.
    SDRT follows x.include_sdrt and is amortised over x.holding_period_days.
    Solve N(r + s)tau + N*trs_im*r_c*tau - IM remuneration - p*div = NetCost_PB for s.
    """
    tau = year_fraction(x.tenor_days)
    cost_pb = pb_route(x).net_cost
    im_cost = x.notional * x.trs_im * x.client_funding_rate * tau
    passed_div = x.trs_pass_through * _dividend_amount(x)
    return ((cost_pb - x.notional * x.sonia * tau - im_cost + im_remuneration(x, tau)
             + passed_div) / (x.notional * tau))


def compare_routes(x: FinancingInputs) -> pd.DataFrame:
    """One row per route. Headline is financing cost; dividend credit and net shown separately.
    Financing cost is also shown excluding (amortised) SDRT."""
    tau = year_fraction(x.tenor_days)

    def bp(amount: float) -> float:
        return annualised_bp(amount, x.notional, tau)

    rows = []
    for r in (pb_route(x), trs_route(x), upgrade_route(x)):
        rows.append({
            "route": r.route,
            "financing_cost_gbp": r.financing_cost,
            "financing_cost_bp": bp(r.financing_cost),
            "dividend_credit_gbp": r.dividend_credit,
            "dividend_credit_bp": bp(r.dividend_credit),
            "net_cost_gbp": r.net_cost,
            "net_cost_bp": bp(r.net_cost),
            "financing_cost_ex_sdrt_gbp": r.financing_cost_ex_sdrt,
            "financing_cost_ex_sdrt_bp": bp(r.financing_cost_ex_sdrt),
            "sdrt_one_off_gbp": r.sdrt_one_off,
            "sdrt_amortised_gbp": r.sdrt,
            "dealer_net_gbp": r.dealer_net,
            "balance_sheet_gbp": r.balance_sheet,
            "balance_sheet_note": "off-sheet: see leverage exposure" if r.balance_sheet_off_sheet else "",
            "shadow_cost_gbp": r.shadow_cost,
            "robs_gross": r.robs,
            "spread_name": r.spread_name,
            "required_spread_for_hurdle": r.required_spread,
        })
    return pd.DataFrame(rows)
