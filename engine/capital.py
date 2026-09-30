"""Step 2: capital and balance-sheet usage per route.

ILLUSTRATIVE AND SIMPLIFIED. This is not a regulatory calculation. It shows the shape of
the capital cost of each route using a small subset of the PRA / Basel rules, cited
inline. Not modelled: CVA risk capital, market risk on the delta-hedged stock, default
fund / CCP exposures, large exposures, SFT minimum haircut floors, and liquidity beyond
a single illustrative HQLA line.

Everything is incremental to the dealer for one trade, in GBP, with a static notional:
the stock price only enters through the TRS mark-to-market input V (for the stress lab).
Maturities in years use tenor_days / 365 as a stand-in for the business-day years that
PRA CCR (CRR) Art 279c asks for.
"""

import math
from dataclasses import dataclass, field, replace

import pandas as pd

import assumptions as A
from engine.financing import (
    GILT_SOURCES, FinancingInputs, pb_route, required_spread, trs_route, upgrade_route,
    year_fraction,
)



# Shown as a banner at the top of the Capital page (step 4).
NOT_MODELLED_BANNER = (
    "Illustrative and simplified. NOT MODELLED: CVA risk capital; market risk on the "
    "delta-hedged stock; default fund and CCP exposures; large exposures; SFT minimum "
    "haircut floors; LCR beyond one illustrative HQLA line."
)


@dataclass(frozen=True)
class NettingSetTrade:
    """Another equity derivative with the same client in the TRS netting set.

    signed_notional is from the dealer's side: delta x adjusted notional (current market
    value). The TRS itself is -notional because the dealer pays the equity return.
    """
    entity: str  # same entity as the TRS underlying -> "subject"
    signed_notional: float
    saccr_type: str = "single"  # "single" or "index"


@dataclass(frozen=True)
class CapitalInputs:
    haircut_regime: str
    haircut_class: str  # "main_index" or "other_listed"
    saccr_type: str  # "single" or "index"
    lcr_level2b: bool
    gilt_band: str
    pb_liquidation_days: int
    include_street_leg: bool
    surplus_cash_placement: str  # "central_bank" or "counted"
    trs_margined: bool
    trs_mtm: float  # dealer-side V
    trs_reset_days: int | None  # None -> no interim resets, M = tenor
    # Stock move since trade start. Scales the hedge value, the street repo collateral and
    # (if trs_notional_in_units) the SA-CCR adjusted notional. Set together with trs_mtm;
    # engine.stress.price_shock does both.
    trs_price_move: float = 0.0
    # PRA CCR (CRR) Art 279b(1)(c): equity adjusted notional = market price x number of units,
    # unless the trade is expressed as a notional amount, in which case the notional is used.
    # Own assumption: the TRS references a number of shares (True).
    trs_notional_in_units: bool = A.TRS_NOTIONAL_IN_UNITS
    netting_set: tuple[NettingSetTrade, ...] = field(default_factory=tuple)
    rw_client: float = A.RW_CLIENT
    rw_street: float = A.RW_STREET
    target_rorwa: float = A.TARGET_RORWA


def default_capital_inputs(asset_class: str = A.DEFAULT_ASSET_CLASS, **overrides) -> CapitalInputs:
    cls = A.CAPITAL_ASSET_CLASSES[asset_class]
    c = CapitalInputs(
        haircut_regime=A.DEFAULT_HAIRCUT_REGIME,
        haircut_class=cls["haircut_class"],
        saccr_type=cls["saccr_type"],
        lcr_level2b=cls["lcr_level2b"],
        gilt_band=A.DEFAULT_GILT_BAND,
        pb_liquidation_days=A.PB_LIQUIDATION_DAYS,
        include_street_leg=A.INCLUDE_STREET_LEG,
        surplus_cash_placement=A.DEFAULT_SURPLUS_CASH_PLACEMENT,
        trs_margined=A.TRS_MARGINED,
        trs_mtm=A.TRS_MTM,
        trs_reset_days=None,
    )
    return replace(c, **overrides)


@dataclass(frozen=True)
class CapitalResult:
    route: str
    rwa: float
    rwa_parts: dict  # component -> RWA
    ead_parts: dict  # component -> exposure value before risk weight
    leverage_exposure: float
    leverage_parts: dict  # component -> leverage exposure
    hqla_change: float  # illustrative; negative = HQLA used
    t_account: dict  # {"assets": {...}, "liabilities": {...}}


# --- Haircuts: Financial Collateral Comprehensive Method ---------------------------

def scaled_haircut(h10: float, days: int) -> float:
    """Scale a 10-day haircut to another liquidation period: H = H10 * sqrt(days / 10).
    PRA CRM (CRR) Art 224(1) tables use this scaling (5-day 14.142 vs 10-day 20)."""
    return h10 * math.sqrt(days / 10)


def equity_haircut_10d(regime: str, haircut_class: str) -> float:
    """PRA CRM (CRR) Art 224(1) Table 3 (Basel 3.1) or UK CRR Art 224 Table 3 (current)."""
    return A.HAIRCUT_REGIMES[regime][haircut_class]


def comprehensive_exposure(e: float, he: float, c: float, hc: float, hfx: float = 0.0) -> float:
    """E* = max{0, E(1 + He) - C(1 - Hc - Hfx)}. PRA CRM (CRR) Art 223(5); Basel CRE22."""
    return max(0.0, e * (1 + he) - c * (1 - hc - hfx))


# --- SA-CCR (PRA CCR (CRR) Art 274-280d; Basel CRE52) --------------------------------

def saccr_mf_unmargined(maturity_days: int) -> float:
    """MF = sqrt(min{max{M, 10/OneBusinessYear}, 1}). Art 279c(1)(a).
    M uses maturity_days / 365 as a proxy for business-day years."""
    m = maturity_days / A.DAYS_IN_YEAR
    return math.sqrt(min(max(m, A.SACCR_MIN_MATURITY_BD / A.ONE_BUSINESS_YEAR), 1.0))


def saccr_mf_margined(mpor_days: int = A.SACCR_MPOR_DAYS) -> float:
    """MF = 1.5 * sqrt(MPOR / OneBusinessYear). Art 279c(1)(b)."""
    return 1.5 * math.sqrt(mpor_days / A.ONE_BUSINESS_YEAR)


def saccr_equity_addon(trades: list[NettingSetTrade], mf: float) -> float:
    """Equity add-on. Art 280d(3)-(4); CRE52.

    AddOn(Entity_k) = SF_k * sum(delta * d * MF) per entity, kept signed.
    AddOn = sqrt[(sum rho_k * AddOn_k)^2 + sum (1 - rho_k^2) * AddOn_k^2].
    All trades share one MF (same maturity / margining).
    """
    entities: dict[tuple[str, str], float] = {}
    for t in trades:
        key = (t.entity, t.saccr_type)
        entities[key] = entities.get(key, 0.0) + t.signed_notional * mf
    systematic = 0.0
    idiosyncratic = 0.0
    for (_, kind), eff_notional in entities.items():
        addon_k = A.SACCR_EQUITY_SF[kind] * eff_notional
        rho = A.SACCR_EQUITY_RHO[kind]
        systematic += rho * addon_k
        idiosyncratic += (1 - rho ** 2) * addon_k ** 2
    return math.sqrt(systematic ** 2 + idiosyncratic)


def saccr_multiplier(z: float, addon: float) -> float:
    """Art 278(3): 1 if z >= 0, else min{1, F + (1 - F) exp(z / y)}, y = 2(1 - F)AggAddOn."""
    if z >= 0 or addon <= 0:
        return 1.0
    floor = A.SACCR_MULTIPLIER_FLOOR
    y = 2 * (1 - floor) * addon
    return min(1.0, floor + (1 - floor) * math.exp(z / y))


def saccr_replacement_cost(v: float, nica: float, margined: bool, vm: float = 0.0,
                           th: float = 0.0, mta: float = 0.0) -> float:
    """Art 275(1): RC = max{CMV - NICA, 0}.  Art 275(2): RC = max{CMV - VM - NICA, TH + MTA - NICA, 0}."""
    if margined:
        return max(v - vm - nica, th + mta - nica, 0.0)
    return max(v - nica, 0.0)


def saccr_ead(v: float, nica: float, addon: float, margined: bool, vm: float = 0.0,
              th: float = 0.0, mta: float = 0.0, alpha: float = A.SACCR_ALPHA) -> dict:
    """Exposure value = alpha * (RC + PFE), PFE = multiplier * AddOn. Art 274(2), 278."""
    rc = saccr_replacement_cost(v, nica, margined, vm, th, mta)
    z = v - vm - nica if margined else v - nica
    mult = saccr_multiplier(z, addon)
    pfe = mult * addon
    return {"rc": rc, "multiplier": mult, "pfe": pfe, "addon": addon, "ead": alpha * (rc + pfe)}


def trs_mtm_from_price_move(notional: float, price_move: float) -> float:
    """Dealer pays the equity return, so a fall in the stock is a gain to the dealer:
    V = -notional * price_move (price_move -0.20 means the stock falls 20%)."""
    return 0.0 - notional * price_move  # 0.0 - avoids a negative zero at no move


# --- Leverage (PRA Leverage Ratio (CRR) Art 429-429e; Basel LEV30) ------------------

def sft_leverage_addon(lent: float, received: float) -> float:
    """E* = max{0, E_i - C_i}, no haircuts. Art 429e(2)."""
    return max(0.0, lent - received)


def derivative_leverage_exposure(v: float, cash_vm: float, addon: float) -> float:
    """alpha * (RC + PFE) with multiplier set to one (Art 429c(5)) and only eligible cash VM
    recognised in RC (Art 429c(3)). IM received does not reduce exposure: collateral
    received is excluded from NICA (Art 429c(4))."""
    return A.SACCR_ALPHA * (max(v - cash_vm, 0.0) + addon)


# --- Routes ------------------------------------------------------------------------

def _surplus_leverage(surplus: float, c: CapitalInputs) -> float:
    return surplus if c.surplus_cash_placement == "counted" else 0.0


def _street_repo(x: FinancingInputs, c: CapitalInputs,
                 stock_value: float | None = None) -> tuple[float, float, float]:
    """Dealer repos the equity (notional N) to a street bank for cash N(1 - street_haircut).
    Returns (cash raised, CCR exposure E*, leverage add-on).
    stock_value: current value of the equity lent (default N). The cash raised stays at the
    original N(1 - h_st); remargining the street repo is not modelled."""
    h_eq5 = scaled_haircut(equity_haircut_10d(c.haircut_regime, c.haircut_class),
                           A.REPO_LIQUIDATION_DAYS)
    value = x.notional if stock_value is None else stock_value
    raised = x.notional * (1 - x.street_haircut)
    ead = comprehensive_exposure(value, h_eq5, raised, 0.0)
    return raised, ead, sft_leverage_addon(value, raised)


def pb_capital(x: FinancingInputs, c: CapitalInputs) -> CapitalResult:
    """On-sheet PB margin loan.

    Dealer T-account (large cap, N = 10m, pb_margin 18%, street haircut 10%):

        Assets                                  | Liabilities
        Margin loan to client   L = N(1-m) 8.2m | Repo from street  N(1-h_st)  9.0m
        Surplus cash N(m-h_st)          0.8m    |
        (client stock: received as collateral and re-used in the street repo, off sheet)

    If h_st > m there is no surplus. The gap N(h_st - m) is an unsecured liability instead.
    The surplus cash sits at the BoE ("central_bank", netted under Art 429a, so no
    leverage exposure) or is placed elsewhere ("counted", adds to leverage exposure).

    Leverage exposure = L (gross SFT asset, Art 429b(1)(b))
                      + max{0, L - N}  client SFT add-on (Art 429e) = 0
                      + max{0, N - N(1-h_st)} = N*h_st  street add-on (if street leg on)
                      + surplus cash (only if "counted")
    RWA = E*_client * RW_client + E*_street * RW_street, where
      E*_client = max{0, L - N(1 - H_eq)} with H_eq at pb_liquidation_days
      E*_street = max{0, N(1 + H_eq5) - N(1 - h_st)}
    """
    loan = x.notional * (1 - x.pb_margin)
    h_eq = scaled_haircut(equity_haircut_10d(c.haircut_regime, c.haircut_class),
                          c.pb_liquidation_days)
    ead_client = comprehensive_exposure(loan, 0.0, x.notional, h_eq)
    raised, ead_street, street_addon = _street_repo(x, c)
    surplus = max(0.0, raised - loan)
    unsecured = max(0.0, loan - raised)

    ead_parts = {"client": ead_client}
    rwa_parts = {"client": ead_client * c.rw_client}
    lev_parts = {"margin_loan": loan, "client_sft_addon": sft_leverage_addon(loan, x.notional),
                 "surplus_cash": _surplus_leverage(surplus, c)}
    if c.include_street_leg:
        ead_parts["street_repo"] = ead_street
        rwa_parts["street_repo"] = ead_street * c.rw_street
        lev_parts["street_sft_addon"] = street_addon

    return CapitalResult(
        route="PB",
        rwa=sum(rwa_parts.values()),
        rwa_parts=rwa_parts,
        ead_parts=ead_parts,
        leverage_exposure=sum(lev_parts.values()),
        leverage_parts=lev_parts,
        hqla_change=0.0,
        t_account={
            "assets": {"Margin loan to client": loan, "Surplus cash": surplus},
            "liabilities": {"Repo from street": raised, "Unsecured funding": unsecured},
        },
    )


def trs_saccr(x: FinancingInputs, c: CapitalInputs) -> dict:
    """SA-CCR exposure of the TRS netting set with the client.
    Adjusted notional = N(1 + price move) for a TRS on a number of shares, else N
    (Art 279b(1)(c)). NICA stays at the cash IM posted, N * trs_im."""
    maturity_days = c.trs_reset_days if c.trs_reset_days else x.tenor_days
    mf = saccr_mf_margined() if c.trs_margined else saccr_mf_unmargined(maturity_days)
    adj_notional = x.notional * (1 + c.trs_price_move) if c.trs_notional_in_units else x.notional
    trades = [NettingSetTrade("subject", -adj_notional, c.saccr_type), *c.netting_set]
    addon = saccr_equity_addon(trades, mf)
    nica = x.notional * x.trs_im
    vm = c.trs_mtm if c.trs_margined else 0.0  # margined: full daily cash VM assumed
    out = saccr_ead(c.trs_mtm, nica, addon, c.trs_margined, vm=vm)
    out.update({"mf": mf, "nica": nica, "vm": vm})
    return out


def trs_capital(x: FinancingInputs, c: CapitalInputs) -> CapitalResult:
    """TRS with a physical hedge held by the dealer.

    Dealer T-account (large cap, N = 10m, IM 15%, street haircut 10%):

        Assets                                  | Liabilities
        Hedge stock                    10.0m    | Repo from street  N(1-h_st)  9.0m
        Surplus cash N(im-h_st)         0.5m    | Client cash IM    N*im       1.5m
        TRS at fair value V (0 at start)        |

    If h_st > im, the gap N(h_st - im) is funded unsecured instead of leaving a surplus.

    After a stock move m (trs_price_move) with V = -N*m: the hedge is worth N(1+m) and the
    TRS asset V offsets it, so assets still total the original cash. The street repo
    stays at the original cash borrowed. If margined, cash VM received (V) adds to cash.

    Leverage exposure = hedge stock N(1+m) (Art 429b; repo does not derecognise it)
                      + 1.4 * (max{V - cash VM, 0} + AddOn)  derivative, multiplier 1 (Art 429c)
                      + max{0, N(1+m) - N(1-h_st)}  street SFT add-on (if street leg on)
                      + surplus cash (only if "counted")
    RWA = SA-CCR EAD * RW_client + E*_street * RW_street.
    Market risk on the delta-hedged stock is NOT MODELLED.
    """
    sa = trs_saccr(x, c)
    hedge = x.notional * (1 + c.trs_price_move)
    raised, ead_street, street_addon = _street_repo(x, c, stock_value=hedge)
    im_cash = x.notional * x.trs_im
    cash_in = raised + im_cash + sa["vm"]
    surplus = max(0.0, cash_in - x.notional)
    unsecured = max(0.0, x.notional - cash_in)

    ead_parts = {"client_saccr": sa["ead"]}
    rwa_parts = {"client_saccr": sa["ead"] * c.rw_client}
    lev_parts = {
        "hedge_stock": hedge,
        "derivative": derivative_leverage_exposure(c.trs_mtm, sa["vm"], sa["addon"]),
        "surplus_cash": _surplus_leverage(surplus, c),
    }
    if c.include_street_leg:
        ead_parts["street_repo"] = ead_street
        rwa_parts["street_repo"] = ead_street * c.rw_street
        lev_parts["street_sft_addon"] = street_addon

    return CapitalResult(
        route="TRS",
        rwa=sum(rwa_parts.values()),
        rwa_parts=rwa_parts,
        ead_parts=ead_parts,
        leverage_exposure=sum(lev_parts.values()),
        leverage_parts=lev_parts,
        hqla_change=0.0,
        t_account={
            "assets": {"Hedge stock": hedge, "Surplus cash": surplus,
                       "TRS fair value": max(c.trs_mtm, 0.0),
                       "Cash VM posted": max(-sa["vm"], 0.0)},
            "liabilities": {"Repo from street": raised, "Client cash IM": im_cash,
                            "Unsecured funding": unsecured,
                            "TRS fair value (liability)": max(-c.trs_mtm, 0.0),
                            "Cash VM received": max(sa["vm"], 0.0)},
        },
    )


def upgrade_capital(x: FinancingInputs, c: CapitalInputs) -> CapitalResult:
    """Collateral upgrade: the client gives equities N and receives gilts G = N(1 - h_up).
    This replaces the step 1 zero placeholder. The result depends on gilt_source.

    reverse_repo: the dealer reverses in gilts for cash R = G(1 - h_g) and funds R by
    repoing the client's equities to the street for N(1 - h_st).
        Assets                                  | Liabilities
        Reverse repo receivable R      8.82m    | Repo from street  N(1-h_st)  9.0m
        Surplus cash                   0.18m    |
        (equities received and gilts delivered: off sheet)
        Leverage = R + max{0, G - N} (client) + max{0, R - G} (reverse repo)
                   + N*h_st (street) + surplus cash (only if "counted")

    borrowed: the dealer borrows gilts against the client's equities (securities for
    securities, not on balance sheet).
        Assets: none            | Liabilities: none
        Leverage = max{0, G - N} (client) + max{0, N - G} (gilt lender) = N*h_up

    inventory: the dealer lends its own gilts, which stay on its balance sheet and were
    already counted, so the incremental leverage is the client add-on max{0, G - N} = 0.
        HQLA change = -G (Level 1 lent) + (1 - 50%) * N if the equity is Level 2B eligible.

    RWA: E*_client = max{0, G(1 + H_g5) - N(1 - H_eq5)} * RW_client, plus source legs * RW_street.
    """
    h_eq5 = scaled_haircut(equity_haircut_10d(c.haircut_regime, c.haircut_class),
                           A.REPO_LIQUIDATION_DAYS)
    h_g5 = scaled_haircut(A.GILT_HAIRCUTS_10D[c.gilt_band], A.REPO_LIQUIDATION_DAYS)
    gilts = x.notional * (1 - x.upgrade_haircut)
    ead_client = comprehensive_exposure(gilts, h_g5, x.notional, h_eq5)

    ead_parts = {"client": ead_client}
    rwa_parts = {"client": ead_client * c.rw_client}
    lev_parts = {"client_sft_addon": sft_leverage_addon(gilts, x.notional)}
    assets: dict = {}
    liabilities: dict = {}
    hqla = 0.0

    if x.gilt_source == "reverse_repo":
        cash_lent = gilts * (1 - x.gilt_haircut)
        raised, ead_street, street_addon = _street_repo(x, c)
        surplus = max(0.0, raised - cash_lent)
        unsecured = max(0.0, cash_lent - raised)
        ead_rr = comprehensive_exposure(cash_lent, 0.0, gilts, h_g5)
        lev_parts["reverse_repo_receivable"] = cash_lent
        lev_parts["surplus_cash"] = _surplus_leverage(surplus, c)
        if c.include_street_leg:
            ead_parts["reverse_repo"] = ead_rr
            rwa_parts["reverse_repo"] = ead_rr * c.rw_street
            lev_parts["reverse_repo_sft_addon"] = sft_leverage_addon(cash_lent, gilts)
            ead_parts["street_repo"] = ead_street
            rwa_parts["street_repo"] = ead_street * c.rw_street
            lev_parts["street_sft_addon"] = street_addon
        assets = {"Reverse repo receivable": cash_lent, "Surplus cash": surplus}
        liabilities = {"Repo from street": raised, "Unsecured funding": unsecured}
    elif x.gilt_source == "borrowed":
        if c.include_street_leg:
            ead_gl = comprehensive_exposure(x.notional, h_eq5, gilts, h_g5)
            ead_parts["gilt_lender"] = ead_gl
            rwa_parts["gilt_lender"] = ead_gl * c.rw_street
            lev_parts["gilt_lender_sft_addon"] = sft_leverage_addon(x.notional, gilts)
    elif x.gilt_source == "inventory":
        eligible = x.notional * (1 - A.LCR_LEVEL2B_EQUITY_HAIRCUT) if c.lcr_level2b else 0.0
        hqla = -gilts + eligible
    else:
        raise ValueError(f"Unknown gilt_source {x.gilt_source!r}; expected one of {GILT_SOURCES}")

    return CapitalResult(
        route="Collateral upgrade",
        rwa=sum(rwa_parts.values()),
        rwa_parts=rwa_parts,
        ead_parts=ead_parts,
        leverage_exposure=sum(lev_parts.values()),
        leverage_parts=lev_parts,
        hqla_change=hqla,
        t_account={"assets": assets, "liabilities": liabilities},
    )


# --- Returns and comparison -----------------------------------------------------

def return_on(dealer_net: float, denominator: float, tau: float) -> float | None:
    """Gross annualised return: dealer_net / (denominator * tau). None if denominator is 0."""
    if denominator <= 0:
        return None
    return dealer_net / (denominator * tau)


def pb_rwa_by_margin(x: FinancingInputs, c: CapitalInputs, margins: list[float]) -> pd.DataFrame:
    """RWA of the PB route as a function of the client margin level."""
    rows = []
    for m in margins:
        r = pb_capital(replace(x, pb_margin=m), c)
        rows.append({"pb_margin": m, "client_ead": r.ead_parts["client"], "rwa": r.rwa})
    return pd.DataFrame(rows)


def k_grid() -> list[float]:
    """Shadow cost k from SHADOW_COST_K_MIN to SHADOW_COST_K_MAX in SHADOW_COST_K_STEP steps."""
    n = round((A.SHADOW_COST_K_MAX - A.SHADOW_COST_K_MIN) / A.SHADOW_COST_K_STEP)
    return [round(A.SHADOW_COST_K_MIN + i * A.SHADOW_COST_K_STEP, 6) for i in range(n + 1)]


def k_sensitivity(x: FinancingInputs, c: CapitalInputs, ks: list[float] | None = None) -> pd.DataFrame:
    """For each k and route: gross RoLE (does not depend on k), RoLE minus k, and the spread
    at which gross RoLE equals k. Long format: one row per (route, k)."""
    frames = []
    for k in ks if ks is not None else k_grid():
        df = capital_comparison(replace(x, shadow_cost_k=k), c)
        frames.append(pd.DataFrame({
            "route": df["route"],
            "k": k,
            "role": df["role"],
            "role_minus_k": df["role"] - k,
            "required_spread_role": df["required_spread_role"],
            "current_spread": df["current_spread"],
        }))
    return pd.concat(frames, ignore_index=True)


def trs_im_spread_for_hurdle(x: FinancingInputs, c: CapitalInputs) -> float | None:
    """IM remuneration spread at which TRS gross RoLE equals the hurdle k.

    Dealer net is linear in the IM spread s: net(s) = net(s0) + N * trs_im * (s - s0) * tau.
    Leverage exposure does not depend on s. Solve net(s) = k * LE * tau.
    The result can fall outside the 0-to-SONIA slider range; the caller should flag that.
    """
    base = x.notional * x.trs_im
    if base <= 0:
        return None
    tau = year_fraction(x.tenor_days)
    net = trs_route(x).dealer_net
    le = trs_capital(x, c).leverage_exposure
    return x.im_remuneration_spread + (x.shadow_cost_k * le * tau - net) / (base * tau)


def trs_vs_im_remuneration(x: FinancingInputs, c: CapitalInputs,
                           spreads: list[float]) -> pd.DataFrame:
    """TRS dealer net, gross RoLE, and the TRS spread needed for RoLE = k, per IM
    remuneration spread."""
    tau = year_fraction(x.tenor_days)
    le = trs_capital(x, c).leverage_exposure
    rows = []
    for s in spreads:
        xs = replace(x, im_remuneration_spread=s)
        net = trs_route(xs).dealer_net
        rows.append({
            "im_remuneration_spread": s,
            "dealer_net_gbp": net,
            "role": return_on(net, le, tau),
            "required_trs_spread_role": required_spread(net, xs.trs_spread, xs.notional, le,
                                                        xs.shadow_cost_k, tau),
        })
    return pd.DataFrame(rows)


def capital_comparison(x: FinancingInputs, c: CapitalInputs) -> pd.DataFrame:
    """One row per route. RoLE is the headline balance-sheet metric; the shadow cost k is
    charged on leverage exposure and is the RoLE hurdle. Required spreads are reported
    for both targets, and the higher one is flagged as binding."""
    tau = year_fraction(x.tenor_days)
    pairs = [
        (pb_route(x), pb_capital(x, c), x.pb_spread, x.notional * (1 - x.pb_margin)),
        (trs_route(x), trs_capital(x, c), x.trs_spread, x.notional),
        (upgrade_route(x), upgrade_capital(x, c), x.upgrade_fee, x.notional),
    ]
    rows = []
    for fin, cap, spread, base in pairs:
        s_rwa = required_spread(fin.dealer_net, spread, base, cap.rwa, c.target_rorwa, tau)
        s_le = required_spread(fin.dealer_net, spread, base, cap.leverage_exposure,
                               x.shadow_cost_k, tau)
        candidates = {k: v for k, v in (("RWA", s_rwa), ("leverage", s_le)) if v is not None}
        binding = max(candidates, key=candidates.get) if candidates else None
        role = return_on(fin.dealer_net, cap.leverage_exposure, tau)
        rows.append({
            "route": fin.route,
            "dealer_net_gbp": fin.dealer_net,
            "rwa_gbp": cap.rwa,
            "leverage_exposure_gbp": cap.leverage_exposure,
            "hqla_change_gbp": cap.hqla_change,
            "rorwa": return_on(fin.dealer_net, cap.rwa, tau),
            "role": return_on(fin.dealer_net, cap.leverage_exposure, tau),
            "shadow_cost_gbp": cap.leverage_exposure * x.shadow_cost_k * tau,
            "spread_name": fin.spread_name,
            "current_spread": spread,
            "required_spread_rorwa": s_rwa,
            "required_spread_role": s_le,
            "binding": binding,
            # Hurdle clearance: clears if gross RoLE >= k. Cushion in bp of spread is
            # current minus required (negative = spread shortfall to reach the hurdle).
            "clears_role_hurdle": None if role is None else bool(role >= x.shadow_cost_k),
            "role_hurdle_cushion_bp": None if s_le is None else (spread - s_le) * 1e4,
        })
    return pd.DataFrame(rows)


def best_for_desk(df: pd.DataFrame) -> str | None:
    """Route with the highest RoLE among those that clear the RoLE hurdle k.
    None if no route clears; the app must then say so rather than name a winner."""
    clearing = df[df["clears_role_hurdle"] == True]  # noqa: E712 (column may hold None)
    if clearing.empty:
        return None
    return clearing.loc[clearing["role"].idxmax(), "route"]
