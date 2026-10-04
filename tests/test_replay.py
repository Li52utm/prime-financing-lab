"""History replay maths against hand-worked numbers. The engine is reused, not changed."""

import math
from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from analytics import replay as R
from engine.capital import default_capital_inputs, trs_capital, trs_saccr
from engine.financing import default_inputs, trs_route

X = default_inputs()  # N = 10m, IM 15% (1.5m), 91-day tenor
C = default_capital_inputs()
PRICES = pd.Series([100.0, 90.0, 80.0, 99.0],
                   index=pd.to_datetime(["2020-03-02", "2020-03-03", "2020-03-04", "2020-03-09"]))


def test_replay_values_vm_and_cash_margined():
    """Moves 0, -10%, -20%, -1% -> V = -N x move = 0, 1.0m, 2.0m, 0.1m.
    VM calls (V_t - V_t-1) = 0, +1.0m, +1.0m, -1.9m. IM call 1.5m on day one only.
    Cash held = 1.5m + cumulative VM = 1.5m, 2.5m, 3.5m, 1.6m.
    Margined: RC = max(V - VM - IM, 0) = 0 every day (full VM)."""
    p = R.replay_trs(PRICES, X, C, margined=True)
    assert p["v"].tolist() == pytest.approx([0, 1.0e6, 2.0e6, 0.1e6])
    assert p["vm_call"].tolist() == pytest.approx([0, 1.0e6, 1.0e6, -1.9e6])
    assert p["im_call"].tolist() == pytest.approx([1.5e6, 0, 0, 0])
    assert p["cash_held"].tolist() == pytest.approx([1.5e6, 2.5e6, 3.5e6, 1.6e6])
    assert p["rc"].tolist() == pytest.approx([0, 0, 0, 0])


def test_replay_unmargined_rc_and_engine_reuse():
    """Unmargined: no VM; RC = max(V - IM, 0) = 0, 0, 0.5m, 0 (2.0m - 1.5m on day 3).
    EAD, RWA and leverage equal the engine's own numbers for the same V and move."""
    p = R.replay_trs(PRICES, X, C, margined=False)
    assert p["vm_call"].abs().sum() == 0 and p["cash_held"].tolist() == pytest.approx([1.5e6] * 4)
    assert p["rc"].tolist() == pytest.approx([0, 0, 0.5e6, 0])
    cc = replace(C, trs_mtm=2.0e6, trs_price_move=-0.2, trs_margined=False)
    assert p["ead"].iloc[2] == pytest.approx(trs_saccr(X, cc)["ead"])
    assert p["rwa"].iloc[2] == pytest.approx(trs_capital(X, cc).rwa)
    assert p["leverage"].iloc[2] == pytest.approx(trs_capital(X, cc).leverage_exposure)
    # EAD = 1.4 x (RC + multiplier x add-on): RC 0.5m and multiplier 1 (V - IM > 0)
    assert p["multiplier"].iloc[2] == 1.0
    assert p["ead"].iloc[2] == pytest.approx(1.4 * (0.5e6 + p["addon"].iloc[2]))


def test_replay_pnl_accrual_and_summary():
    """P&L per calendar day = TRS dealer net / 91; day 4 is 7 calendar days after the strike.
    One-day returns: 3 Mar -10%, 4 Mar 80/90 - 1 = -11.11%, 9 Mar +23.75%, so the worst day is
    4 Mar. Peak EAD also on 4 Mar (unmargined RC 0.5m)."""
    p = R.replay_trs(PRICES, X, C, margined=False)
    assert p["cum_pnl"].iloc[-1] == pytest.approx(trs_route(X).dealer_net / 91 * 7)
    s = R.replay_summary(p)
    assert s["worst_day"] == pd.Timestamp("2020-03-04")
    assert s["worst_return"] == pytest.approx(80 / 90 - 1)
    assert s["peak_day"] == pd.Timestamp("2020-03-04") and s["peak_rc"] == pytest.approx(0.5e6)
    assert s["trough_move"] == pytest.approx(-0.2)


def test_replay_needs_two_closes():
    with pytest.raises(ValueError):
        R.replay_trs(PRICES.iloc[:1], X, C, True)


def test_forward_losses_and_haircut_breach_counts():
    """Closes 100, 100, 70, 100, 100.
    h=1: losses 0, 0.30, -0.4286, 0 -> 20% haircut breached once in 4 windows (25%).
    h=2: losses from d0, d1, d2 = 1-70/100 = 0.30, 0, 1-100/70 = -0.4286 -> 1 breach of 3;
    non-overlapping starts d0, d2 -> 2 blocks, 1 breach. Worst 0.30 starting d0."""
    s = pd.Series([100, 100, 70, 100, 100.0], index=pd.bdate_range("2020-01-06", periods=5))
    l1 = R.forward_losses(s, 1)
    assert l1.tolist() == pytest.approx([0, 0.3, 1 - 100 / 70, 0])
    t = R.haircut_check(l1, {"A": 0.2}, 1).iloc[0]
    assert (t["breaches"], t["windows"], t["breach_pct"]) == (1, 4, pytest.approx(25.0))
    t = R.haircut_check(R.forward_losses(s, 2), {"A": 0.2, "B": 0.35}, 2)
    assert t["breaches"].tolist() == [1, 0] and t["blocks"].tolist() == [2, 2]
    assert t["block_breaches"].tolist() == [1, 0]
    assert t["worst_loss"].iloc[0] == pytest.approx(0.3) and t["worst_start"].iloc[0] == s.index[0]


def test_ewma_vol_and_vol_im_hand_worked():
    """Log returns 0.1, 0, 0.2 with lambda 0.5: var 0.01 -> 0.5(0.01) + 0.5(0) = 0.005 ->
    0.5(0.005) + 0.5(0.04) = 0.0225; vol 0.1, 0.070711, 0.15.
    IM = 2.326348 x 0.15 x sqrt(10) = 0.348952 x 3.162278 = 1.103484 (99%, 10 days)."""
    close = pd.Series(np.exp(np.cumsum([0, 0.1, 0, 0.2])), index=pd.bdate_range("2020-01-06", periods=4))
    v = R.ewma_vol(close, 0.5, 0)
    assert v.tolist() == pytest.approx([0.1, math.sqrt(0.005), 0.15])
    assert R.vol_implied_im(v, 0.99, 10).iloc[-1] == pytest.approx(1.103484, abs=1e-6)
    assert R.ewma_vol(close, 0.5, 2).isna().tolist() == [True, True, False]


def test_ewma_uses_no_future_data():
    """Changing a later price leaves earlier EWMA values unchanged (no look-ahead)."""
    idx = pd.bdate_range("2020-01-06", periods=50)
    a = pd.Series(np.exp(np.cumsum(np.random.default_rng(1).normal(0, 0.01, 50))), index=idx)
    b = a.copy()
    b.iloc[-1] *= 1.5
    va, vb = R.ewma_vol(a, 0.94, 0), R.ewma_vol(b, 0.94, 0)
    assert va.iloc[:-1].equals(vb.iloc[:-1]) and va.iloc[-1] != vb.iloc[-1]


def test_im_backtest_counts():
    """IM 10%, 10%, 30%; losses 0.15, 0.05, 0.2; static 12%: vol breaches on day 1 only (0.15 >
    0.10); static breaches days 1 and 3; vol IM above static on 1 of 3 days."""
    idx = pd.bdate_range("2020-01-06", periods=3)
    bt = R.im_backtest(pd.Series([0.1, 0.1, 0.3], index=idx), 0.12,
                       pd.Series([0.15, 0.05, 0.2], index=idx))
    assert bt == {"days": 3, "vol_breaches": 1, "static_breaches": 2,
                  "vol_above_static_pct": pytest.approx(100 / 3)}
