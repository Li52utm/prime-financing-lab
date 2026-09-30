"""Hand-worked tests for engine/stress.py. Preset values used here are HYPOTHETICAL.

Fixtures from test_capital: N = 10m, SONIA 4%, pb_margin 20% (L = 8m), trs_im 15%, street
haircut 10%, street spread 0.30%, pb spread 0.50%, trs spread 0.40%, TRS pass-through 90%,
IM unremunerated, k 2%. At tenor 73 days (tau 0.2): PB dealer net 2,600, TRS dealer net
24,600, PB financing ex SDRT 96,000, TRS financing 106,000.

Test preset T (not from assumptions): client +0.20%, street +0.30%, k +1%, haircut +0.
"""

from dataclasses import replace

import pytest

import assumptions as A
from engine.stress import (
    StressPreset, all_presets, apply_preset, get_preset, pb_repriced_fraction, price_shock,
    price_shock_table, repricing_path, stress_comparison, term_vs_rolling,
    term_vs_rolling_by_preset,
)
from tests.test_capital import cap, fin

approx = pytest.approx
T = StressPreset("test", "Test (hypothetical)", client_spread_shock=0.002,
                 street_spread_shock=0.003, k_shock=0.01, street_haircut_change=0.0,
                 turn_days=10, term_premium=0.0008)
H = StressPreset("haircut", "Haircut only (hypothetical)", 0.0, 0.0, 0.0, 0.05, 0, 0.0)


def fin73(**overrides):
    return fin(tenor_days=73, holding_period_days=73, **overrides)


# --- Presets -------------------------------------------------------------------------

def test_presets_defined_and_labelled_hypothetical():
    names = [p.name for p in all_presets()]
    assert names == ["quarter_end_squeeze", "year_end_turn", "collateral_shortage"]
    for p in all_presets():
        assert "hypothetical" in p.label.lower()
    with pytest.raises(ValueError):
        get_preset("black_swan")


def test_apply_preset():
    # PB half repriced: 0.5% + 0.5 x 0.2% = 0.6%; TRS 0.4% + 0.2% = 0.6%; upgrade 0.3% + 0.2%
    # street 0.3% + 0.3% = 0.6%; k 2% + 1% = 3%; haircut unchanged
    xs = apply_preset(fin73(), T, pb_repriced=0.5)
    assert xs.pb_spread == approx(0.006)
    assert xs.trs_spread == approx(0.006)
    assert xs.upgrade_fee == approx(0.005)
    assert xs.street_repo_spread == approx(0.006)
    assert xs.shadow_cost_k == approx(0.03)
    assert xs.street_haircut == approx(0.10)


# --- 1. Price shock ------------------------------------------------------------------

def test_price_shock_down_20pct():
    # V = +2m; RC = 2m - 1.5m = 500,000; z > 0 -> multiplier 1
    # EAD = 1.4 x (500,000 + 1,597,806.72) = 2,936,929.40
    # RWA = 2,936,929.40 + 0.4 x 2,414,213.56 = 3,902,614.83
    # leverage = 10m + 1.4 x (2m + 1,597,806.72) + 1m = 16,036,929.40
    r = price_shock(fin(), cap(), -0.20)
    assert r["mtm_v"] == approx(2_000_000)
    assert r["rc"] == approx(500_000)
    assert r["multiplier"] == 1.0
    assert r["ead"] == approx(2_936_929.40)
    assert r["rwa"] == approx(3_902_614.83)
    assert r["leverage_exposure"] == approx(16_036_929.40)


def test_price_shock_up_10pct():
    # V = -1m; RC 0; multiplier 0.46694933; EAD 1,044,532.69; RWA + 965,685.42 = 2,010,218.12
    r = price_shock(fin(), cap(), 0.10)
    assert r["rc"] == 0.0
    assert r["multiplier"] == approx(0.46694933)
    assert r["ead"] == approx(1_044_532.69)
    assert r["rwa"] == approx(2_010_218.12)


def test_price_shock_margined_absorbed_by_vm():
    # full daily VM: EAD stays at 628,212.85 whatever the move
    assert price_shock(fin(), cap(trs_margined=True), -0.20)["ead"] == approx(628_212.85)


def test_price_shock_table_default_grid():
    df = price_shock_table(fin(), cap())
    assert list(df["price_move"]) == A.PRICE_SHOCK_GRID
    assert df.set_index("price_move").loc[0.0, "ead"] == approx(1_408_403.70)


# --- 2. Stress comparison ----------------------------------------------------------

def test_stress_comparison_day_of_shock():
    # PB not repriced: 2,600 - street 9m x 0.3% x 0.2 (5,400) = -2,800
    # TRS repriced: 24,600 + 10m x 0.2% x 0.2 (4,000) - 5,400 = 23,200
    # upgrade repriced: 4,200 + 4,000 = 8,200 (no street leg in its dealer net)
    df = stress_comparison(fin73(), cap(), T).set_index("route")
    assert df.loc["PB", "dealer_net_stressed"] == approx(-2_800)
    assert df.loc["PB", "dealer_net_change"] == approx(-5_400)
    assert df.loc["TRS", "dealer_net_stressed"] == approx(23_200)
    assert df.loc["Collateral upgrade", "dealer_net_stressed"] == approx(8_200)
    assert df.loc["TRS", "k_stressed"] == approx(0.03)
    assert df.loc["TRS", "leverage_stressed"] == approx(df.loc["TRS", "leverage_base"])


def test_stress_comparison_haircut_change():
    # street haircut 10% -> 15%
    # TRS: repo 8.5m x 4.3% x 0.2 = 73,100; gap 10m x (0.15 - 0.15) = 0
    #   net = 80,000 + 8,000 - 73,100 + 0 + 10,000 = 24,900
    #   leverage = 10m + 1.4 x 1,431,083.51 + 1.5m = 13,503,516.91
    # PB: surplus 0.5m earns 4,000: 64,000 + 8,000 - 73,100 + 4,000 = 2,900; leverage 8m + 1.5m
    df = stress_comparison(fin73(), cap(), H).set_index("route")
    assert df.loc["TRS", "dealer_net_stressed"] == approx(24_900)
    assert df.loc["TRS", "leverage_stressed"] == approx(13_503_516.91)
    assert df.loc["PB", "dealer_net_stressed"] == approx(2_900)
    assert df.loc["PB", "leverage_stressed"] == approx(9_500_000)


# --- 3. Pass-through lag -------------------------------------------------------------

def test_pb_repriced_fraction():
    assert pb_repriced_fraction(0, 0.25) == 0.0
    assert pb_repriced_fraction(2, 0.25) == approx(0.5)
    assert pb_repriced_fraction(5, 0.25) == 1.0  # capped


def test_repricing_path():
    """One 'month' = 73 days (tau 0.2) for clean numbers; f = 50% per month.
    TRS: 106,000 + 10m x 0.2% x 0.2 = 110,000 every month.
    PB:  96,000 + 8m x (0.2% x f_m) x 0.2 -> 96,000; 97,600; 99,200; 99,200
    gap: -14,000; -12,400; -10,800; -10,800   cumulative -14,000; -26,400; -37,200; -48,000
    PB dealer: -2,800 + 8m x (0.2% x f_m) x 0.2 -> -2,800; -1,200; 400; 400
    shortfall vs full (400): 3,200; 1,600; 0; 0   cumulative 3,200; 4,800; 4,800; 4,800
    """
    df = repricing_path(fin73(), T, months=3, fraction_per_month=0.5, month_days=73)
    assert list(df["pb_repriced_fraction"]) == approx([0.0, 0.5, 1.0, 1.0])
    assert list(df["client_cost_trs"]) == approx([110_000] * 4)
    assert list(df["client_cost_pb"]) == approx([96_000, 97_600, 99_200, 99_200])
    assert list(df["cost_gap"]) == approx([-14_000, -12_400, -10_800, -10_800])
    assert list(df["cum_cost_gap"]) == approx([-14_000, -26_400, -37_200, -48_000])
    assert list(df["dealer_net_pb"]) == approx([-2_800, -1_200, 400, 400])
    assert list(df["dealer_net_trs"]) == approx([23_200] * 4)
    assert list(df["cum_dealer_pb_shortfall"]) == approx([3_200, 4_800, 4_800, 4_800])


# --- 4. Term vs rolling ---------------------------------------------------------------

def test_term_vs_rolling():
    # rolling = 10m x (0.3% x 73 + 0.73% x 10) / 365 = 10m x 0.292 / 365 = 8,000
    # term    = 10m x (0.3% + 0.08%) x 73 / 365 = 7,600  -> term saves 400
    # breakeven premium = 0.73% x 10 / 73 = 0.10%
    r = term_vs_rolling(10e6, 0.003, 73, 10, 0.0073, 0.0008)
    assert r["rolling_cost"] == approx(8_000)
    assert r["term_cost"] == approx(7_600)
    assert r["term_saving"] == approx(400)
    assert r["breakeven_term_premium"] == approx(0.001)
    # premium above breakeven: term = 10m x 0.42% x 0.2 = 8,400 -> rolling cheaper by 400
    assert term_vs_rolling(10e6, 0.003, 73, 10, 0.0073, 0.0012)["term_saving"] == approx(-400)


def test_term_vs_rolling_by_preset():
    """Street funding 9m at 0.30%, horizon 91 days. quarter_end_squeeze (hypothetical):
    shock 0.25% for 5 days, term premium 0.02%.
    rolling = 9m x (0.3% x 91 + 0.25% x 5) / 365 = 9m x 0.2855 / 365 = 7,039.73
    term    = 9m x 0.32% x 91 / 365 = 7,180.27 -> rolling cheaper
    breakeven = 0.25% x 5 / 91 = 0.0125 / 91 = 0.0137363% < 0.02%
    """
    qe = A.STRESS_PRESETS["quarter_end_squeeze"]
    assert (qe["street_spread_shock"], qe["turn_days"], qe["term_premium"]) == (0.0025, 5, 0.0002)
    df = term_vs_rolling_by_preset(fin()).set_index("preset")
    assert len(df) == 3
    assert df.loc["quarter_end_squeeze", "rolling_cost"] == approx(7_039.73)
    assert df.loc["quarter_end_squeeze", "term_cost"] == approx(7_180.27)
    assert df.loc["quarter_end_squeeze", "breakeven_term_premium"] == approx(0.0125 / 91)
    assert df.loc["quarter_end_squeeze", "cheaper"] == "rolling"
    for _, row in df.iterrows():
        assert (row["cheaper"] == "term") == (row["term_premium"] < row["breakeven_term_premium"])
