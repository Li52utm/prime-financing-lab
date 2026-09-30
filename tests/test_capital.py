"""Hand-worked tests for engine/capital.py (ILLUSTRATIVE AND SIMPLIFIED capital).

Base trade: N = 10m, tenor 91 days, pb_margin 20%, trs_im 15% (NICA 1.5m), street haircut 10%,
upgrade haircut 10% (G = 9m), gilt haircut 2%, Basel 3.1 haircuts (main index 20%),
RW client 100%, RW street 40%, surplus cash at the central bank (excluded from leverage).

Common values:
  H_eq5 = 20% x sqrt(5/10) = 14.1421356%     H_g5 = 2% x sqrt(5/10) = 1.41421356%
  MF(91d) = sqrt(91/365) = 0.49931460        AddOn = 0.32 x 10m x MF = 1,597,806.72
"""

import math
from dataclasses import replace

import pytest

from engine.capital import (
    CapitalInputs, NettingSetTrade, best_for_desk, capital_comparison, comprehensive_exposure,
    default_capital_inputs, derivative_leverage_exposure, equity_haircut_10d, k_grid, k_sensitivity,
    trs_im_spread_for_hurdle, trs_vs_im_remuneration,
    pb_capital, pb_rwa_by_margin, return_on, saccr_ead, saccr_equity_addon,
    saccr_mf_margined, saccr_mf_unmargined, saccr_multiplier, saccr_replacement_cost,
    scaled_haircut, sft_leverage_addon, trs_capital, trs_mtm_from_price_move, trs_saccr,
    upgrade_capital,
)
from engine.financing import FinancingInputs

approx = pytest.approx
ADDON_91 = 1_597_806.7158983476
STREET_EAD = 2_414_213.5623730943  # 10m x 1.141421356 - 9m


def fin(**overrides) -> FinancingInputs:
    x = FinancingInputs(
        notional=10_000_000, tenor_days=91, holding_period_days=91, sonia=0.04,
        client_funding_rate=0.06, unsecured_spread=0.01,
        im_remuneration_spread=0.04,  # = SONIA: IM unremunerated (keeps step 1 numbers)
        pb_margin=0.20, trs_im=0.15, street_haircut=0.10,
        pb_spread=0.005, trs_spread=0.004, street_repo_spread=0.003,
        upgrade_haircut=0.10, upgrade_fee=0.003, aim_listed=False,
        gilt_source="reverse_repo", gilt_repo_spread=0.0, gilt_haircut=0.02, gilt_borrow_fee=0.001,
        gilt_borrow_fee_reverse_repo=0.0,
        dividend=0.01, ex_div_day=30, trs_pass_through=0.9, manufactured_pass_through=1.0,
        wht_client=0.0, wht_dealer=0.0, include_sdrt=True, sdrt_rate=0.005,
        dealer_hedge_sdrt_rate=0.0, shadow_cost_k=0.02,
    )
    return replace(x, **overrides)


def cap(**overrides) -> CapitalInputs:
    c = CapitalInputs(
        haircut_regime="basel_3_1", haircut_class="main_index", saccr_type="single",
        lcr_level2b=True, gilt_band="1-3y", pb_liquidation_days=10, include_street_leg=True,
        surplus_cash_placement="central_bank",
        trs_margined=False, trs_mtm=0.0, trs_reset_days=None,
        rw_client=1.0, rw_street=0.4, target_rorwa=0.015,
    )
    return replace(c, **overrides)


# --- Haircuts ------------------------------------------------------------------

def test_haircut_regimes():
    assert equity_haircut_10d("basel_3_1", "main_index") == 0.20
    assert equity_haircut_10d("basel_3_1", "other_listed") == 0.30
    assert equity_haircut_10d("uk_crr_current", "main_index") == 0.15
    assert equity_haircut_10d("uk_crr_current", "other_listed") == 0.25


def test_scaled_haircut_matches_pra_table():
    # PRA Art 224 Table 3 5-day column: 14.142 (main index), 21.213 (other); gilt 1-3y 1.414
    assert scaled_haircut(0.20, 5) == approx(0.141421356)
    assert scaled_haircut(0.30, 5) == approx(0.212132034)
    assert scaled_haircut(0.02, 5) == approx(0.0141421356)
    assert scaled_haircut(0.20, 20) == approx(0.282842712)


def test_comprehensive_exposure():
    # 8.2m cash vs 10m stock at 20%: 8.2m - 8.0m = 200,000
    assert comprehensive_exposure(8_200_000, 0.0, 10_000_000, 0.20) == approx(200_000)
    assert comprehensive_exposure(8_000_000, 0.0, 10_000_000, 0.20) == 0.0


# --- SA-CCR building blocks ----------------------------------------------------------

def test_maturity_factors():
    assert saccr_mf_unmargined(91) == approx(0.49931460)  # sqrt(91/365)
    assert saccr_mf_unmargined(30) == approx(0.28669109)  # sqrt(30/365)
    assert saccr_mf_unmargined(1) == approx(0.2)  # floor sqrt(10/250)
    assert saccr_mf_unmargined(800) == approx(1.0)  # cap at 1 year
    assert saccr_mf_margined(10) == approx(0.3)  # 1.5 x sqrt(10/250)


def test_multiplier():
    # z >= 0 -> 1
    assert saccr_multiplier(500_000, ADDON_91) == 1.0
    # z = -1.5m: 0.05 + 0.95 exp(-1.5m / (1.9 x 1,597,806.72)) = 0.62961473
    assert saccr_multiplier(-1_500_000, ADDON_91) == approx(0.62961473)
    # very negative z -> floor 5%
    assert saccr_multiplier(-1e12, ADDON_91) == approx(0.05)


def test_replacement_cost():
    assert saccr_replacement_cost(2_000_000, 1_500_000, margined=False) == approx(500_000)
    assert saccr_replacement_cost(0.0, 1_500_000, margined=False) == 0.0
    # margined: max(2m - 2m - 1.5m, 0 + 0 - 1.5m, 0) = 0
    assert saccr_replacement_cost(2_000_000, 1_500_000, True, vm=2_000_000) == 0.0
    # threshold 2m, no IM: max(V - VM, TH + MTA - NICA, 0) = 2m
    assert saccr_replacement_cost(0.0, 0.0, True, th=2_000_000) == approx(2_000_000)


def test_equity_addon_single_trade():
    # sqrt((0.5 a)^2 + 0.75 a^2) = a = 0.32 x 10m x 0.49931460 = 1,597,806.72
    mf = saccr_mf_unmargined(91)
    assert saccr_equity_addon([NettingSetTrade("subject", -10e6)], mf) == approx(ADDON_91)


def test_equity_addon_netting():
    mf = saccr_mf_unmargined(91)
    subject = NettingSetTrade("subject", -10e6)
    # same entity, opposite sign: effective notional 0 -> add-on 0
    assert saccr_equity_addon([subject, NettingSetTrade("subject", 10e6)], mf) == approx(0.0)
    # different name, opposite sign: sqrt((0.5a - 0.5a)^2 + 0.75a^2 + 0.75a^2) = sqrt(1.5) a
    assert saccr_equity_addon([subject, NettingSetTrade("other", 10e6)], mf) == approx(
        1_956_905.58)
    # different name, same sign: sqrt(a^2 + 1.5 a^2) = sqrt(2.5) a
    assert saccr_equity_addon([subject, NettingSetTrade("other", -10e6)], mf) == approx(
        2_526_354.24)


def test_saccr_ead_plan_examples():
    # Unmargined: RC 0; PFE = 0.62961473 x 1,597,806.72 = 1,006,002.64; EAD = 1.4 x = 1,408,403.70
    r = saccr_ead(0.0, 1_500_000, ADDON_91, margined=False)
    assert r["pfe"] == approx(1_006_002.64)
    assert r["ead"] == approx(1_408_403.70)
    # Margined MPOR 10: AddOn = 0.32 x 10m x 0.3 = 960,000; mult 0.46742027; EAD 628,212.85
    r = saccr_ead(0.0, 1_500_000, 960_000, margined=True)
    assert r["multiplier"] == approx(0.46742027)
    assert r["ead"] == approx(628_212.85)


def test_trs_mtm_sign():
    # stock -20% -> dealer (pays equity return) is owed 2m
    assert trs_mtm_from_price_move(10e6, -0.20) == approx(2_000_000)
    assert trs_mtm_from_price_move(10e6, 0.10) == approx(-1_000_000)


def test_trs_saccr_responds_to_mtm_unmargined():
    x = fin()
    # V = +2m: RC = 2m - 1.5m = 500,000; z = +0.5m -> multiplier 1
    # EAD = 1.4 x (500,000 + 1,597,806.72) = 2,936,929.40
    r = trs_saccr(x, cap(trs_mtm=2_000_000))
    assert r["rc"] == approx(500_000)
    assert r["multiplier"] == 1.0
    assert r["ead"] == approx(2_936_929.40)
    # V = -1m: RC 0; z = -2.5m -> 0.05 + 0.95 exp(-2.5m / (1.9 x 1,597,806.72)) = 0.46694933
    r = trs_saccr(x, cap(trs_mtm=-1_000_000))
    assert r["rc"] == 0.0
    assert r["multiplier"] == approx(0.46694933)
    assert r["ead"] == approx(1_044_532.69)


def test_trs_saccr_margined_mtm_absorbed_by_vm():
    # full daily VM: z = V - VM - NICA = -1.5m for any V, so same as V = 0: EAD 628,212.85
    r = trs_saccr(fin(), cap(trs_margined=True, trs_mtm=2_000_000))
    assert r["rc"] == 0.0
    assert r["multiplier"] == approx(0.46742027)
    assert r["ead"] == approx(628_212.85)


def test_trs_reset_shortens_maturity():
    # monthly resets: M = 30 days -> MF 0.28669109; AddOn = 0.32 x 10m x MF = 917,411.49
    r = trs_saccr(fin(), cap(trs_reset_days=30))
    assert r["mf"] == approx(0.28669109)
    assert r["addon"] == approx(917_411.49)


# --- Leverage building blocks ----------------------------------------------------

def test_leverage_building_blocks():
    assert sft_leverage_addon(10e6, 9e6) == approx(1e6)
    assert sft_leverage_addon(9e6, 10e6) == 0.0
    # 1.4 x (max(0,0) + 1,597,806.72) = 2,236,929.40; IM not recognised
    assert derivative_leverage_exposure(0.0, 0.0, ADDON_91) == approx(2_236_929.40)
    # margined with cash VM equal to V: RC 0
    assert derivative_leverage_exposure(2e6, 2e6, 960_000) == approx(1_344_000)


# --- PB ----------------------------------------------------------------------------

def test_pb_capital_plan_example():
    # L = 8m; E*_client = max(0, 8m - 10m x 0.8) = 0; street E* = 2,414,213.56
    # RWA = 0 + 0.4 x 2,414,213.56 = 965,685.42
    # Leverage = 8m + max(0, 8m - 10m) + 1m street add-on = 9.0m (surplus 1m at BoE excluded)
    r = pb_capital(fin(), cap())
    assert r.ead_parts["client"] == 0.0
    assert r.ead_parts["street_repo"] == approx(STREET_EAD)
    assert r.rwa == approx(965_685.42)
    assert r.leverage_exposure == approx(9_000_000)
    assert r.t_account["assets"]["Surplus cash"] == approx(1_000_000)
    assert r.t_account["liabilities"]["Repo from street"] == approx(9_000_000)


def test_pb_surplus_cash_counted():
    # surplus 1m placed outside the central bank -> 10.0m
    assert pb_capital(fin(), cap(surplus_cash_placement="counted")).leverage_exposure == approx(
        10_000_000)


def test_pb_default_margin_18pct_basel_vs_uk():
    # m = 18%: L = 8.2m. Basel 3.1: 8.2m - 10m x 0.80 = 200,000 -> RWA 200,000 + 965,685.42
    r = pb_capital(fin(pb_margin=0.18), cap())
    assert r.ead_parts["client"] == approx(200_000)
    assert r.rwa == approx(1_165_685.42)
    # UK CRR current: 8.2m - 10m x 0.85 < 0 -> 0; street 10m x (1 + 0.15 x sqrt(0.5)) - 9m
    r = pb_capital(fin(pb_margin=0.18), cap(haircut_regime="uk_crr_current"))
    assert r.ead_parts["client"] == 0.0
    assert r.ead_parts["street_repo"] == approx(2_060_660.17)


def test_pb_liquidation_5_days():
    # H = 20% x sqrt(0.5) = 14.142%: 10m x 0.85858 = 8.5858m > 8.2m -> 0
    assert pb_capital(fin(pb_margin=0.18), cap(pb_liquidation_days=5)).ead_parts["client"] == 0.0


def test_pb_street_leg_toggle():
    r = pb_capital(fin(), cap(include_street_leg=False))
    assert r.rwa == 0.0
    assert r.leverage_exposure == approx(8_000_000)


def test_pb_unsecured_gap_in_t_account():
    # street haircut 30% > margin 20%: raised 7m vs loan 8m -> 1m unsecured, no surplus
    r = pb_capital(fin(street_haircut=0.30), cap())
    assert r.t_account["liabilities"]["Unsecured funding"] == approx(1_000_000)
    assert r.t_account["assets"]["Surplus cash"] == 0.0


def test_pb_rwa_by_margin():
    # client E*: m=10% 9m-8m = 1m; m=18% 0.2m; m=25% 0; each + street 965,685.42
    df = pb_rwa_by_margin(fin(), cap(), [0.10, 0.18, 0.25])
    assert list(df["client_ead"]) == approx([1_000_000, 200_000, 0.0])
    assert list(df["rwa"]) == approx([1_965_685.42, 1_165_685.42, 965_685.42])


# --- TRS -----------------------------------------------------------------------------

def test_trs_capital_plan_example_unmargined():
    # EAD 1,408,403.70 + street 0.4 x 2,414,213.56 = 2,374,089.12
    # Leverage = 10m + 1.4 x 1,597,806.72 + 1m = 13,236,929.40
    r = trs_capital(fin(), cap())
    assert r.ead_parts["client_saccr"] == approx(1_408_403.70)
    assert r.rwa == approx(2_374_089.12)
    assert r.leverage_exposure == approx(13_236_929.40)
    # T-account: 10m stock + 0.5m surplus = 9m repo + 1.5m IM
    assert r.t_account["assets"]["Surplus cash"] == approx(500_000)
    assert r.t_account["liabilities"]["Client cash IM"] == approx(1_500_000)


def test_trs_capital_plan_example_margined():
    # Leverage = 10m + 1.4 x 960,000 + 1m = 12,344,000
    r = trs_capital(fin(), cap(trs_margined=True))
    assert r.ead_parts["client_saccr"] == approx(628_212.85)
    assert r.leverage_exposure == approx(12_344_000)


def test_trs_leverage_responds_to_mtm():
    # unmargined V = +2m: derivative 1.4 x (2m + 1,597,806.72); total 16,036,929.40
    assert trs_capital(fin(), cap(trs_mtm=2e6)).leverage_exposure == approx(16_036_929.40)


# --- Collateral upgrade ------------------------------------------------------------

def test_upgrade_client_exposure():
    # 9m x 1.0141421 - 10m x 0.8585786 = 541,492.78
    r = upgrade_capital(fin(), cap())
    assert r.ead_parts["client"] == approx(541_492.78)


def test_upgrade_reverse_repo():
    # R = 9m x 0.98 = 8.82m; reverse repo E* = max(0, 8.82m - 9m x 0.98586) = 0
    # Leverage = 8.82m + 0 (client) + 0 (reverse repo) + 1m (street) = 9.82m; surplus 0.18m excluded
    # RWA = 541,492.78 + 0 + 965,685.42 = 1,507,178.21
    r = upgrade_capital(fin(gilt_source="reverse_repo"), cap())
    assert r.ead_parts["reverse_repo"] == 0.0
    assert r.leverage_exposure == approx(9_820_000)
    assert r.rwa == approx(1_507_178.21)
    assert r.t_account["assets"]["Surplus cash"] == approx(180_000)
    assert r.hqla_change == 0.0


def test_upgrade_borrowed():
    # Leverage = max(0, 9m - 10m) + max(0, 10m - 9m) = 1m
    # gilt lender E* = 10m x 1.1414214 - 9m x 0.9858579 = 2,541,492.78; RWA x 0.4 = 1,016,597.11
    r = upgrade_capital(fin(gilt_source="borrowed"), cap())
    assert r.leverage_exposure == approx(1_000_000)
    assert r.ead_parts["gilt_lender"] == approx(2_541_492.78)
    assert r.rwa == approx(541_492.78 + 1_016_597.11)
    assert r.t_account == {"assets": {}, "liabilities": {}}


def test_upgrade_inventory_hqla():
    # Leverage 0 incremental; HQLA = -9m + 50% x 10m = -4m (large cap Level 2B)
    r = upgrade_capital(fin(gilt_source="inventory"), cap())
    assert r.leverage_exposure == 0.0
    assert r.hqla_change == approx(-4_000_000)
    # not Level 2B eligible: -9m
    assert upgrade_capital(fin(gilt_source="inventory"), cap(lcr_level2b=False)).hqla_change == \
        approx(-9_000_000)


def test_upgrade_unknown_source():
    with pytest.raises(ValueError):
        upgrade_capital(fin(gilt_source="magic"), cap())


# --- Returns ---------------------------------------------------------------------

def test_return_on():
    assert return_on(24_600, 13_003_516.91, 0.2) == approx(0.00945898)
    assert return_on(1.0, 0.0, 0.2) is None


def test_capital_comparison_trs_at_73_days():
    """TRS at tenor 73 (tau 0.2), where step 1 gives dealer net 24,600.
    MF = sqrt(0.2) = 0.4472136; AddOn = 1,431,083.51; mult = 0.59719240; EAD = 1,196,485.07
    RWA = 1,196,485.07 + 965,685.42 = 2,162,170.50
    LE  = 10m + 1.4 x 1,431,083.51 + 1m = 13,003,516.91
    RoLE = 24,600 / (13,003,516.91 x 0.2) = 0.94590%; RoRWA = 24,600 / (2,162,170.50 x 0.2) = 5.68873%
    a = 24,600 - 10m x 0.004 x 0.2 = 16,600
    required (RoLE = k 2%)     = (0.02 x 13,003,516.91 x 0.2 - 16,600) / 2m = 1.770703%
    required (RoRWA = 1.5%)    = (0.015 x 2,162,170.50 x 0.2 - 16,600) / 2m = -0.505674%
    binding = leverage
    """
    df = capital_comparison(fin(tenor_days=73, holding_period_days=73), cap()).set_index("route")
    t = df.loc["TRS"]
    assert t["dealer_net_gbp"] == approx(24_600)
    assert t["rwa_gbp"] == approx(2_162_170.50)
    assert t["leverage_exposure_gbp"] == approx(13_003_516.91)
    assert t["role"] == approx(0.00945898)
    assert t["rorwa"] == approx(0.05688728)
    assert t["shadow_cost_gbp"] == approx(13_003_516.91 * 0.02 * 0.2)
    assert t["required_spread_role"] == approx(0.01770703)
    assert t["required_spread_rorwa"] == approx(-0.00505674)
    assert t["binding"] == "leverage"


def test_capital_comparison_required_spread_round_trip():
    # plugging each required spread back in hits its target exactly
    x, c = fin(), cap()
    df = capital_comparison(x, c).set_index("route")
    s = df.loc["PB", "required_spread_role"]
    df2 = capital_comparison(replace(x, pb_spread=s), c).set_index("route")
    assert df2.loc["PB", "role"] == approx(x.shadow_cost_k)
    s = df.loc["Collateral upgrade", "required_spread_rorwa"]
    df3 = capital_comparison(replace(x, upgrade_fee=s), c).set_index("route")
    assert df3.loc["Collateral upgrade", "rorwa"] == approx(c.target_rorwa)


def test_default_capital_inputs():
    c = default_capital_inputs()
    assert c.haircut_regime == "basel_3_1"
    assert c.include_street_leg and not c.trs_margined and c.trs_mtm == 0.0
    assert default_capital_inputs("small_cap").haircut_class == "other_listed"
    assert not default_capital_inputs("convertible_style").lcr_level2b


# --- Shadow cost k sensitivity -------------------------------------------------------

def test_k_grid():
    g = k_grid()
    assert g[0] == 0.0 and g[-1] == approx(0.03) and len(g) == 13  # 0 to 3% in 0.25% steps


def test_k_sensitivity_trs_at_73_days():
    """TRS, tau 0.2, LE 13,003,516.91, a = 16,600, dealer net 24,600.
    k = 0:    required = (0 - 16,600) / 2m = -0.83%
    k = 1%:   required = (0.01 x 13,003,516.91 x 0.2 - 16,600) / 2m = 0.470352%
    RoLE = 0.945898% for every k; RoLE - k at 1% = -0.054102%
    """
    df = k_sensitivity(fin(tenor_days=73, holding_period_days=73), cap(), [0.0, 0.01])
    t = df[df["route"] == "TRS"].set_index("k")
    assert t.loc[0.0, "required_spread_role"] == approx(-0.0083)
    assert t.loc[0.01, "required_spread_role"] == approx(0.00470352)
    assert t.loc[0.0, "role"] == approx(0.00945898) and t.loc[0.01, "role"] == approx(0.00945898)
    assert t.loc[0.01, "role_minus_k"] == approx(-0.00054102)
    assert len(df) == 6  # 3 routes x 2 k values


# --- TRS vs IM remuneration ------------------------------------------------------------

def test_trs_vs_im_remuneration_at_73_days():
    """tau 0.2, IM 1.5m, LE 13,003,516.91 (independent of the IM spread), k = 0.5%.
    net(s) = 24,600 - 1.5m x (4% - s) x 0.2:  s=0 -> 12,600; s=2% -> 18,600; s=4% -> 24,600
    RoLE(s=0) = 12,600 / (13,003,516.91 x 0.2) = 12,600 / 2,600,703.38 = 0.4844843%
    required TRS spread at s=0: a = 12,600 - 8,000 = 4,600;
      (0.005 x 13,003,516.91 x 0.2 - 4,600) / 2m = (13,003.52 - 4,600) / 2m = 0.420176%
    """

    x = fin(tenor_days=73, holding_period_days=73, shadow_cost_k=0.005)
    df = trs_vs_im_remuneration(x, cap(), [0.0, 0.02, 0.04]).set_index("im_remuneration_spread")
    assert list(df["dealer_net_gbp"]) == approx([12_600, 18_600, 24_600])
    assert df.loc[0.0, "role"] == approx(0.004844843)
    assert df.loc[0.0, "required_trs_spread_role"] == approx(0.00420176)


def test_trs_im_spread_for_hurdle():
    """k = 0.5%: target = 0.005 x 13,003,516.91 x 0.2 = 13,003.52
    from s0 = 0 (net 12,600): s* = (13,003.517 - 12,600) / 300,000 = 0.1345056%
    same answer from any starting spread; round trip hits RoLE = k."""

    x = fin(tenor_days=73, holding_period_days=73, shadow_cost_k=0.005)
    s = trs_im_spread_for_hurdle(replace(x, im_remuneration_spread=0.0), cap())
    assert s == approx(0.001345056)
    assert trs_im_spread_for_hurdle(replace(x, im_remuneration_spread=0.03), cap()) == approx(s)
    df = capital_comparison(replace(x, im_remuneration_spread=s), cap()).set_index("route")
    assert df.loc["TRS", "role"] == approx(0.005)
    assert trs_im_spread_for_hurdle(replace(x, trs_im=0.0), cap()) is None


# --- Hurdle clearance ---------------------------------------------------------------------

def test_hurdle_clearance_and_best_for_desk():
    """tau 0.2, reverse repo upgrade. TRS RoLE 0.945898%, LE 13,003,516.91, a = 16,600.
    k = 2%: TRS misses; cushion = (0.40% - 1.770703%) = -137.07 bp. No route clears -> None.
    k = 0.5%: required = (0.005 x 13,003,516.91 x 0.2 - 16,600) / 2m = -0.179824%
      cushion = 0.40% + 0.179824% = 57.98 bp -> clears.
      PB RoLE = 2,600 / (9m x 0.2) = 0.1444% misses; upgrade net -1,200 misses -> best = TRS.
    """
    df = capital_comparison(fin(tenor_days=73, holding_period_days=73), cap()).set_index("route")
    assert not df.loc["TRS", "clears_role_hurdle"]
    assert df.loc["TRS", "role_hurdle_cushion_bp"] == approx(-137.0703, rel=1e-5)
    assert best_for_desk(df.reset_index()) is None

    df = capital_comparison(fin(tenor_days=73, holding_period_days=73, shadow_cost_k=0.005),
                            cap()).set_index("route")
    assert df.loc["TRS", "clears_role_hurdle"]
    assert df.loc["TRS", "role_hurdle_cushion_bp"] == approx(57.9824, rel=1e-5)
    assert df.loc["PB", "role"] == approx(2_600 / (9e6 * 0.2))
    assert not df.loc["PB", "clears_role_hurdle"]
    assert not df.loc["Collateral upgrade", "clears_role_hurdle"]
    assert best_for_desk(df.reset_index()) == "TRS"


def test_break_even_k():
    """Break-even k = gross RoLE. TRS at tau 0.2: 24,600 / (13,003,516.91 x 0.2) = 0.945898%.
    At k = break-even the required spread equals the current spread (cushion 0) and it clears."""
    x = fin(tenor_days=73, holding_period_days=73)
    df = capital_comparison(x, cap()).set_index("route")
    be = df.loc["TRS", "break_even_k"]
    assert be == approx(0.00945898)
    assert list(df["break_even_k"]) == approx(list(df["role"]))
    at_be = capital_comparison(replace(x, shadow_cost_k=be), cap()).set_index("route")
    assert at_be.loc["TRS", "role_hurdle_cushion_bp"] == approx(0.0, abs=1e-9)
    assert at_be.loc["TRS", "clears_role_hurdle"]
