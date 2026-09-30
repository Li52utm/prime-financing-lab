"""Step 3: stress lab.

Every preset and shock value is HYPOTHETICAL (an own assumption in assumptions.py). Capital
figures are ILLUSTRATIVE AND SIMPLIFIED, as in engine/capital.py.

1. Price shock: a stock move feeds the TRS mark-to-market V and scales the hedge value, the
   street repo collateral and the SA-CCR adjusted notional. Shows RC, multiplier, EAD, RWA
   and leverage exposure. Street repo cash and client IM stay at their original amounts.
2. Presets: shock the client spread, street spread, shadow cost k and street haircut.
3. Pass-through lag: after a shock the TRS spread reprices fully at once, while the on-sheet
   PB spread reprices by a fraction per month. Street shocks hit the dealer immediately.
4. Term vs rolling: the cost of locking a term spread across a turn versus rolling short
   and paying the spike, applied to the dealer's street funding.
"""

from dataclasses import dataclass, replace

import pandas as pd

import assumptions as A
from engine.capital import (
    CapitalInputs, capital_comparison, trs_capital, trs_mtm_from_price_move, trs_saccr,
)
from engine.financing import FinancingInputs, pb_route, trs_route, year_fraction


@dataclass(frozen=True)
class StressPreset:
    """All values HYPOTHETICAL. Spreads and k as decimals."""
    name: str
    label: str
    client_spread_shock: float
    street_spread_shock: float
    k_shock: float
    street_haircut_change: float
    turn_days: int
    term_premium: float
    gilt_borrow_shock: float = 0.0  # applies to the upgrade gilt borrow fee (all sources)


def get_preset(name: str) -> StressPreset:
    if name not in A.STRESS_PRESETS:
        raise ValueError(f"Unknown preset {name!r}; expected one of {list(A.STRESS_PRESETS)}")
    return StressPreset(name=name, **A.STRESS_PRESETS[name])


def all_presets() -> list[StressPreset]:
    return [get_preset(n) for n in A.STRESS_PRESETS]


# --- 1. Price shock -> TRS mark-to-market ---------------------------------------------

def price_shock(x: FinancingInputs, c: CapitalInputs, price_move: float) -> dict:
    """Effect of a stock move on the TRS counterparty exposure.
    V = -N * price_move (the dealer pays the equity return, so a fall is owed to the dealer).
    The hedge value, the street repo collateral and (for a TRS on a number of shares) the
    SA-CCR adjusted notional scale by (1 + price_move) (PRA CCR (CRR) Art 279b(1)(c)).
    The street repo cash and the client's IM stay at their original amounts."""
    v = trs_mtm_from_price_move(x.notional, price_move)
    cs = replace(c, trs_mtm=v, trs_price_move=price_move)
    sa = trs_saccr(x, cs)
    cap = trs_capital(x, cs)
    return {
        "price_move": price_move,
        "mtm_v": v,
        "rc": sa["rc"],
        "multiplier": sa["multiplier"],
        "pfe": sa["pfe"],
        "ead": sa["ead"],
        "rwa": cap.rwa,
        "leverage_exposure": cap.leverage_exposure,
    }


def price_shock_table(x: FinancingInputs, c: CapitalInputs,
                      moves: list[float] | None = None) -> pd.DataFrame:
    return pd.DataFrame([price_shock(x, c, m) for m in (moves or A.PRICE_SHOCK_GRID)])


# --- 2. Presets ------------------------------------------------------------------------

def apply_preset(x: FinancingInputs, p: StressPreset, pb_repriced: float = 1.0,
                 trs_repriced: float = 1.0,
                 upgrade_repriced: float = A.UPGRADE_REPRICING_FRACTION) -> FinancingInputs:
    """Stressed inputs. Dealer-side shocks (street spread, street haircut, k) apply in full.
    The client spread shock applies to each route in proportion to how far it has repriced."""
    return replace(
        x,
        pb_spread=x.pb_spread + p.client_spread_shock * pb_repriced,
        trs_spread=x.trs_spread + p.client_spread_shock * trs_repriced,
        upgrade_fee=x.upgrade_fee + p.client_spread_shock * upgrade_repriced,
        street_repo_spread=x.street_repo_spread + p.street_spread_shock,
        street_haircut=x.street_haircut + p.street_haircut_change,
        shadow_cost_k=x.shadow_cost_k + p.k_shock,
        gilt_borrow_fee=x.gilt_borrow_fee + p.gilt_borrow_shock,
    )


def stress_comparison(x: FinancingInputs, c: CapitalInputs, p: StressPreset,
                      pb_repriced: float = 0.0) -> pd.DataFrame:
    """Base vs stressed, per route: dealer net, leverage exposure, RoLE, RoLE hurdle (k) and
    the spread needed for RoLE = k. Default: the TRS and upgrade have repriced and PB has not
    (the day the shock hits)."""
    base = capital_comparison(x, c).set_index("route")
    xs = apply_preset(x, p, pb_repriced=pb_repriced)
    stressed = capital_comparison(xs, c).set_index("route")
    out = pd.DataFrame({
        "dealer_net_base": base["dealer_net_gbp"],
        "dealer_net_stressed": stressed["dealer_net_gbp"],
        "leverage_base": base["leverage_exposure_gbp"],
        "leverage_stressed": stressed["leverage_exposure_gbp"],
        "role_base": base["role"],
        "role_stressed": stressed["role"],
        "k_base": x.shadow_cost_k,
        "k_stressed": xs.shadow_cost_k,
        "required_spread_role_base": base["required_spread_role"],
        "required_spread_role_stressed": stressed["required_spread_role"],
    })
    out["dealer_net_change"] = out["dealer_net_stressed"] - out["dealer_net_base"]
    return out.reset_index()


# --- 3. Pass-through lag ------------------------------------------------------------

def pb_repriced_fraction(month: int, fraction_per_month: float) -> float:
    """Cumulative share of the client spread shock passed into the PB spread: min(1, f * m)."""
    return min(1.0, fraction_per_month * month)


def repricing_path(x: FinancingInputs, p: StressPreset,
                   months: int = A.REPRICING_HORIZON_MONTHS,
                   fraction_per_month: float = A.PB_REPRICING_FRACTION_PER_MONTH,
                   month_days: int = A.MONTH_DAYS) -> pd.DataFrame:
    """Month-by-month cost of PB vs TRS after a shock at month 0.

    Each row is one month-long period priced at that month's spreads. Client cost is
    financing cost excluding SDRT (dividends excluded), so the gap shows repricing only.
    cost_gap = PB client cost - TRS client cost (negative = PB cheaper for the client).
    Once PB has fully repriced the gap is NOT the pre-shock gap: PB reprices on its loan
    L = N(1 - pb_margin) and the TRS on N, so
      gap_full = gap_base - (N - L) * client_spread_shock * tau_month.
    dealer_pb_shortfall = PB dealer net if fully repriced - PB dealer net actually earned.
    """
    xm = replace(x, tenor_days=month_days)
    rows = []
    cum_gap = cum_shortfall = 0.0
    for m in range(months + 1):
        f = pb_repriced_fraction(m, fraction_per_month)
        xs = apply_preset(xm, p, pb_repriced=f, trs_repriced=1.0)
        pb, trs = pb_route(xs), trs_route(xs)
        pb_full = pb_route(apply_preset(xm, p, pb_repriced=1.0))
        gap = pb.financing_cost_ex_sdrt - trs.financing_cost_ex_sdrt
        shortfall = pb_full.dealer_net - pb.dealer_net
        cum_gap += gap
        cum_shortfall += shortfall
        rows.append({
            "month": m,
            "pb_repriced_fraction": f,
            "pb_spread": xs.pb_spread,
            "trs_spread": xs.trs_spread,
            "client_cost_pb": pb.financing_cost_ex_sdrt,
            "client_cost_trs": trs.financing_cost_ex_sdrt,
            "cost_gap": gap,
            "cum_cost_gap": cum_gap,
            "dealer_net_pb": pb.dealer_net,
            "dealer_net_trs": trs.dealer_net,
            "dealer_pb_shortfall": shortfall,
            "cum_dealer_pb_shortfall": cum_shortfall,
        })
    return pd.DataFrame(rows)


# --- 4. Term vs rolling ------------------------------------------------------------------

def term_vs_rolling(amount: float, base_spread: float, horizon_days: int, turn_days: int,
                    turn_shock: float, term_premium: float) -> dict:
    """Spread cost over SONIA of funding `amount` for horizon_days (SONIA is common to both).

    rolling: pays base_spread throughout, plus turn_shock for turn_days
      = amount * (base_spread * horizon + turn_shock * turn_days) / 365
    term: locks base_spread + term_premium for the whole horizon
      = amount * (base_spread + term_premium) * horizon / 365
    breakeven term premium = turn_shock * turn_days / horizon
    term_saving > 0 means locking term is cheaper.
    """
    rolling = amount * (base_spread * horizon_days + turn_shock * turn_days) / A.DAYS_IN_YEAR
    term = amount * (base_spread + term_premium) * horizon_days / A.DAYS_IN_YEAR
    return {
        "rolling_cost": rolling,
        "term_cost": term,
        "term_saving": rolling - term,
        "breakeven_term_premium": turn_shock * turn_days / horizon_days,
    }


def term_vs_rolling_by_preset(x: FinancingInputs,
                              horizon_days: int = A.TERM_HORIZON_DAYS) -> pd.DataFrame:
    """Term vs rolling on the dealer's street funding N(1 - street_haircut), per preset."""
    amount = x.notional * (1 - x.street_haircut)
    rows = []
    for p in all_presets():
        r = term_vs_rolling(amount, x.street_repo_spread, horizon_days, p.turn_days,
                            p.street_spread_shock, p.term_premium)
        rows.append({"preset": p.name, "label": p.label, "amount": amount,
                     "turn_days": p.turn_days, "turn_shock": p.street_spread_shock,
                     "term_premium": p.term_premium, **r,
                     "cheaper": "term" if r["term_saving"] > 0 else "rolling"})
    return pd.DataFrame(rows)
