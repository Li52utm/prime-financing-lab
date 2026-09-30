"""Hand-worked tests for engine/financing.py.

Base case (chosen so tau is exact):
  N = 10,000,000   T = 73 days -> tau = 73/365 = 0.2   holding period 73 days (full SDRT this tenor)
  SONIA r = 4%, client funding r_c = 6%, dealer unsecured spread s_u = 1%
  pb_margin 20%, trs_im 15%, street_haircut 10%
  pb_spread 0.50%, trs_spread 0.40%, street_repo_spread 0.30%
  upgrade_haircut 10%, upgrade_fee 0.30%, gilt haircut 2%, gilt repo SONIA flat, gilt borrow 0.10%
  dividend 1% of N (= 100,000) with ex-day 30 (inside tenor), TRS pass-through 90%, manufactured 100%
  WHT 0, SDRT on at 0.5% (= 50,000), not AIM, dealer hedge SDRT 0, k = 2%
"""

from dataclasses import replace

import pytest

from engine.financing import (
    FinancingInputs, amortised_sdrt, annualised_bp, breakeven_trs_spread, compare_routes,
    default_inputs, dividend_in_window, funding_gap_cost, net_dividend, pb_route,
    required_spread, robs, shadow_bs_cost, tenor_days, trs_route, upgrade_route, year_fraction,
)

approx = pytest.approx


def base(**overrides) -> FinancingInputs:
    x = FinancingInputs(
        notional=10_000_000, tenor_days=73, holding_period_days=73, sonia=0.04,
        client_funding_rate=0.06, unsecured_spread=0.01,
        pb_margin=0.20, trs_im=0.15, street_haircut=0.10,
        pb_spread=0.005, trs_spread=0.004, street_repo_spread=0.003,
        upgrade_haircut=0.10, upgrade_fee=0.003, aim_listed=False,
        gilt_repo_spread=0.0, gilt_haircut=0.02, gilt_borrow_fee=0.001,
        dividend=0.01, ex_div_day=30, trs_pass_through=0.9, manufactured_pass_through=1.0,
        wht_client=0.0, wht_dealer=0.0, include_sdrt=True, sdrt_rate=0.005,
        dealer_hedge_sdrt_rate=0.0, shadow_cost_k=0.02,
    )
    return replace(x, **overrides)


# --- Helpers ----------------------------------------------------------------

def test_year_fraction():
    assert year_fraction(73) == approx(0.2)
    assert year_fraction(91) == approx(0.249315068)  # 91/365


def test_tenor_days():
    assert (tenor_days("1M"), tenor_days("3M"), tenor_days("6M")) == (30, 91, 182)
    with pytest.raises(ValueError):
        tenor_days("2Y")


def test_dividend_in_window_boundaries():
    assert dividend_in_window(30, 73)
    assert dividend_in_window(73, 73)  # ex-date on maturity counts
    assert not dividend_in_window(74, 73)
    assert not dividend_in_window(0, 73)  # ex on trade date: buyer does not receive it


def test_net_dividend():
    assert net_dividend(100_000, 0.15) == approx(85_000)


def test_funding_gap_cost_shortfall_pays_spread():
    # 1,000,000 x (0.04 + 0.01) x 0.2 = 10,000
    assert funding_gap_cost(1_000_000, 0.04, 0.01, 0.2) == approx(10_000)


def test_funding_gap_cost_surplus_earns_sonia_flat():
    # -1,000,000 x 0.04 x 0.2 = -8,000 (earns SONIA; unsecured spread NOT applied)
    assert funding_gap_cost(-1_000_000, 0.04, 0.01, 0.2) == approx(-8_000)


def test_funding_gap_cost_zero():
    assert funding_gap_cost(0.0, 0.04, 0.01, 0.2) == 0.0


def test_shadow_bs_cost():
    assert shadow_bs_cost(8_000_000, 0.02, 0.2) == approx(32_000)


def test_annualised_bp():
    # 46,000 / (10m x 0.2) = 0.023 -> 230 bp
    assert annualised_bp(46_000, 10_000_000, 0.2) == approx(230)


def test_robs_and_zero_balance_sheet():
    assert robs(2_600, 8_000_000, 0.2) == approx(0.001625)
    assert robs(4_200, 0.0, 0.2) is None


def test_required_spread_helper():
    # a = 2,600 - 8m x 0.005 x 0.2 = -5,400; target = 0.02 x 8m x 0.2 = 32,000
    # s = (32,000 + 5,400) / (8m x 0.2) = 0.023375
    assert required_spread(2_600, 0.005, 8_000_000, 8_000_000, 0.02, 0.2) == approx(0.023375)
    assert required_spread(1.0, 0.003, 10_000_000, 0.0, 0.02, 0.2) is None


def test_amortised_sdrt():
    # 50,000 x 73/365 = 10,000
    assert amortised_sdrt(50_000, 73, 365) == approx(10_000)
    # hold equal to or shorter than tenor -> whole charge this tenor
    assert amortised_sdrt(50_000, 73, 73) == approx(50_000)
    assert amortised_sdrt(50_000, 73, 30) == approx(50_000)
    with pytest.raises(ValueError):
        amortised_sdrt(50_000, 73, 0)


# --- PB ---------------------------------------------------------------------

def test_pb_client_cost_split():
    # loan L = 8m; interest 8m x 4.5% x 0.2 = 72,000; margin 2m x 6% x 0.2 = 24,000; SDRT 50,000
    # financing 146,000; dividend credit 100,000; net 46,000
    r = pb_route(base())
    assert r.financing_cost == approx(146_000)
    assert r.dividend_credit == approx(100_000)
    assert r.net_cost == approx(46_000)
    assert r.sdrt_one_off == approx(50_000)
    assert r.sdrt == approx(50_000)
    assert r.financing_cost_ex_sdrt == approx(96_000)


def test_pb_sdrt_amortised_over_holding_period():
    # hold 365 days: SDRT charged this tenor = 50,000 x 73/365 = 10,000
    # financing = 72,000 + 24,000 + 10,000 = 106,000; net = 106,000 - 100,000 = 6,000
    r = pb_route(base(holding_period_days=365))
    assert r.sdrt_one_off == approx(50_000)
    assert r.sdrt == approx(10_000)
    assert r.financing_cost == approx(106_000)
    assert r.net_cost == approx(6_000)


def test_pb_dealer_with_cash_surplus():
    # street repo 9m x 4.3% x 0.2 = 77,400; gap 10m x (0.10 - 0.20) = -1m -> earns -8,000
    # net = 72,000 - 77,400 + 8,000 = 2,600
    r = pb_route(base())
    assert r.dealer_net == approx(2_600)
    assert r.balance_sheet == approx(8_000_000)
    assert r.shadow_cost == approx(32_000)
    assert r.robs == approx(0.001625)  # 2,600 / (8m x 0.2), gross (shadow not deducted)
    assert r.required_spread == approx(0.023375)


def test_pb_dealer_with_cash_shortfall():
    # street_haircut 30% > pb_margin 20%: repo 7m x 4.3% x 0.2 = 60,200
    # gap +1m pays (4% + 1%) x 0.2 = 10,000; net = 72,000 - 60,200 - 10,000 = 1,800
    r = pb_route(base(street_haircut=0.30))
    assert r.dealer_net == approx(1_800)


def test_pb_withholding_tax():
    # client receives 85,000 instead of 100,000; financing unchanged; net 146,000 - 85,000
    r = pb_route(base(wht_client=0.15))
    assert r.dividend_credit == approx(85_000)
    assert r.financing_cost == approx(146_000)
    assert r.net_cost == approx(61_000)


def test_pb_dividend_outside_window():
    r = pb_route(base(ex_div_day=80))
    assert r.dividend_credit == 0.0
    assert r.net_cost == approx(146_000)


def test_pb_aim_exempt_from_sdrt():
    r = pb_route(base(aim_listed=True))
    assert r.sdrt_one_off == 0.0
    assert r.financing_cost == approx(96_000)


def test_pb_sdrt_toggle_off():
    assert pb_route(base(include_sdrt=False)).financing_cost == approx(96_000)


# --- TRS --------------------------------------------------------------------

def test_trs_client_cost_split():
    # floating 10m x 4.4% x 0.2 = 88,000; IM 1.5m x 6% x 0.2 = 18,000 -> financing 106,000
    # dividend credit 90% x 100,000 = 90,000 -> net 16,000
    r = trs_route(base())
    assert r.financing_cost == approx(106_000)
    assert r.dividend_credit == approx(90_000)
    assert r.net_cost == approx(16_000)
    assert r.sdrt == 0.0 and r.sdrt_one_off == 0.0


def test_trs_dealer():
    # receive 88,000; repo 77,400; gap 10m x (0.10 - 0.15) = -0.5m earns 4,000
    # dividend kept 100,000 - 90,000 = 10,000 -> net = 88,000 - 77,400 + 4,000 + 10,000 = 24,600
    r = trs_route(base())
    assert r.dealer_net == approx(24_600)
    assert r.balance_sheet == approx(10_000_000)
    assert r.shadow_cost == approx(40_000)
    assert r.robs == approx(0.0123)  # 24,600 / (10m x 0.2)
    # a = 24,600 - 10m x 0.004 x 0.2 = 16,600; s = (40,000 - 16,600) / 2m = 0.0117
    assert r.required_spread == approx(0.0117)


def test_trs_dealer_hedge_sdrt_if_no_relief():
    # UNVERIFIED relief switched off: hedge pays 0.5% x 10m = 50,000 -> 24,600 - 50,000
    assert trs_route(base(dealer_hedge_sdrt_rate=0.005)).dealer_net == approx(-25_400)


def test_trs_dealer_withholding_tax():
    # dealer receives 85,000 net but passes 90,000 -> dividend leg -5,000; net 24,600 - 15,000
    assert trs_route(base(wht_dealer=0.15)).dealer_net == approx(9_600)


# --- Collateral upgrade -----------------------------------------------------

def test_upgrade_client_cost_split():
    # gilts G = 9m; cash C = 9m x 0.98 = 8.82m
    # fee 10m x 0.3% x 0.2 = 6,000; gilt repo 8.82m x 4% x 0.2 = 70,560
    # shortfall 1.18m x 6% x 0.2 = 14,160; SDRT 50,000 -> financing 140,720
    # manufactured dividend 100,000 -> net 40,720
    r = upgrade_route(base())
    assert r.financing_cost == approx(140_720)
    assert r.dividend_credit == approx(100_000)
    assert r.net_cost == approx(40_720)
    assert r.financing_cost_ex_sdrt == approx(90_720)


def test_upgrade_sdrt_amortised():
    # 10,000 SDRT this tenor instead of 50,000 -> financing 140,720 - 40,000 = 100,720
    assert upgrade_route(base(holding_period_days=365)).financing_cost == approx(100_720)


def test_upgrade_dealer_and_placeholder_balance_sheet():
    # fee 6,000 - gilt borrow 9m x 0.1% x 0.2 = 1,800 -> 4,200; dividend leg 100,000 - 100,000 = 0
    r = upgrade_route(base())
    assert r.dealer_net == approx(4_200)
    assert r.balance_sheet == 0.0
    assert r.balance_sheet_is_placeholder
    assert r.robs is None
    assert r.required_spread is None
    assert r.shadow_cost == 0.0


# --- Comparison -------------------------------------------------------------

def test_breakeven_trs_spread_with_sdrt():
    # s = (46,000 - 10m x 4% x 0.2 - 18,000 + 90,000) / 2m = 38,000 / 2m = 0.019
    x = base()
    s = breakeven_trs_spread(x)
    assert s == approx(0.019)
    assert trs_route(replace(x, trs_spread=s)).net_cost == approx(pb_route(x).net_cost)


def test_breakeven_trs_spread_without_sdrt():
    # PB net -4,000 -> s = (-4,000 - 80,000 - 18,000 + 90,000) / 2m = -0.006
    assert breakeven_trs_spread(base(include_sdrt=False)) == approx(-0.006)


def test_breakeven_trs_spread_with_amortised_sdrt():
    # PB net 6,000 (hold 365) -> s = (6,000 - 8,000) / 2m = -0.001
    assert breakeven_trs_spread(base(holding_period_days=365)) == approx(-0.001)


def test_compare_routes_table():
    df = compare_routes(base()).set_index("route")
    assert list(df.index) == ["PB", "TRS", "Collateral upgrade"]
    assert df.loc["PB", "financing_cost_bp"] == approx(730)  # 146,000 / 2m
    assert df.loc["PB", "dividend_credit_bp"] == approx(500)  # 100,000 / 2m
    assert df.loc["PB", "net_cost_bp"] == approx(230)  # 46,000 / 2m
    assert df.loc["PB", "financing_cost_ex_sdrt_bp"] == approx(480)  # 96,000 / 2m
    assert df.loc["TRS", "financing_cost_bp"] == approx(530)  # 106,000 / 2m
    assert df.loc["Collateral upgrade", "balance_sheet_note"] == "PLACEHOLDER (step 2)"


def test_default_inputs_from_assumptions():
    x = default_inputs()
    assert x.tenor_days == 91 and x.holding_period_days == 365
    assert x.include_sdrt and not x.aim_listed
    assert default_inputs("small_cap").aim_listed
    assert pb_route(default_inputs("small_cap")).sdrt == 0.0
    assert default_inputs(tenor="1M", notional=5e6).notional == 5e6
