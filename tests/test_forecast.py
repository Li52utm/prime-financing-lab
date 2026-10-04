"""Forecast Lab maths (EXPERIMENTAL), hand-worked, plus walk-forward no-leakage checks and an
end-to-end run of the offline script on synthetic prices (no network)."""

import json
import math

import numpy as np
import pandas as pd
import pytest

from analytics import forecast as F

IDX = pd.date_range("2024-01-01", periods=5, freq="B")


def test_log_returns_and_forward_targets():
    """closes 100 -> 110: r = ln(1.1) = 0.0953102. forward_sum of 1..5 with h = 2:
    t0 = 2 + 3 = 5, t1 = 7, t2 = 9, last two rows NaN (not yet observed)."""
    r = F.log_returns(pd.Series([100.0, 110.0], index=IDX[:2]))
    assert r.iloc[0] == pytest.approx(0.0953102, abs=1e-7)
    fs = F.forward_sum(pd.Series([1.0, 2, 3, 4, 5], index=IDX), 2)
    assert list(fs[:3]) == [5, 7, 9] and fs[3:].isna().all()
    x = pd.Series([0.1, -0.2, 0.3, 0.1, 0.0], index=IDX)
    assert F.forward_return(x, 1).iloc[0] == pytest.approx(-0.2)
    assert F.realised_forward(x, 2).iloc[0] == pytest.approx(0.04 + 0.09)


def test_naive_variance():
    """r = 0.01, -0.02, 0.03, h = 2: t1 = 0.0001 + 0.0004 = 0.0005; t2 = 0.0004 + 0.0009 = 0.0013."""
    v = F.naive_variance(pd.Series([0.01, -0.02, 0.03], index=IDX[:3]), 2)
    assert np.isnan(v.iloc[0]) and v.iloc[1] == pytest.approx(5e-4) and v.iloc[2] == pytest.approx(1.3e-3)


def test_ewma_variance_hand_worked():
    """r = 0.1, 0.2, 0.3, 0.4; lambda 0.5; seed = mean(0.01, 0.04) = 0.025.
    t0: 0.5(0.025) + 0.5(0.01) = 0.0175; t1: 0.5(0.0175) + 0.5(0.04) = 0.02875 (warm-up, NaN);
    t2: 0.5(0.02875) + 0.5(0.09) = 0.059375; t3: 0.5(0.059375) + 0.5(0.16) = 0.1096875."""
    v = F.ewma_variance(pd.Series([0.1, 0.2, 0.3, 0.4], index=IDX[:4]), 0.5, 2)
    assert v[:2].isna().all()
    assert v.iloc[2] == pytest.approx(0.059375) and v.iloc[3] == pytest.approx(0.1096875)


def test_garch_recursion_and_h_step_sum():
    """omega 0.1, alpha 0.1, beta 0.8, s0 = 1, r = 1, 2: s2 = 0.1 + 0.1(1) + 0.8(1) = 1.0, then
    0.1 + 0.1(4) + 0.8(1.0) = 1.3. h-sum with p = 0.9, vbar = 1, next = 2, h = 2: 2 + (1 + 0.9(1))
    = 3.9. With p = 1 (alpha 0.2, beta 0.8), next 1, h 3: 1 + 1.1 + 1.2 = 3.3."""
    nv = F.garch_next_variance(np.array([1.0, 2.0]), 0.1, 0.1, 0.8, 1.0)
    assert nv == pytest.approx([1.0, 1.3])
    assert F.garch_h_sum(2.0, 0.1, 0.1, 0.8, 2) == pytest.approx(3.9)
    assert F.garch_h_sum(1.0, 0.1, 0.2, 0.8, 3) == pytest.approx(3.3)


def _random_returns(n=400, seed=1):
    rng = np.random.default_rng(seed)
    return pd.Series(rng.normal(0, 0.01, n), index=pd.date_range("2000-01-03", periods=n, freq="B"))


def test_garch_walk_forward_uses_only_past_returns():
    """The fitter sees r_0..r_t at a refit on row t, and changing any return after t leaves every
    forecast made on or before t unchanged."""
    seen = []

    def fake_fitter(x):
        seen.append(len(x))
        return 1e-6, 0.05, 0.9

    r = _random_returns()
    f1, log = F.garch_forecasts(r, 10, 200, 50, fake_fitter)
    assert seen == [201, 251, 301, 351] and [s for s, *_ in log] == [200, 250, 300, 350]
    r2 = r.copy()
    r2.iloc[300:] *= 5  # change the future of row 299
    f2, _ = F.garch_forecasts(r2, 10, 200, 50, fake_fitter)
    pd.testing.assert_series_equal(f1.iloc[:300], f2.iloc[:300])
    assert f1.iloc[:200].isna().all() and f1.iloc[200:].notna().all()


def test_walk_forward_no_leakage():
    """Refit at row t uses training rows s <= t - h only, and perturbing targets that are not yet
    observed at t (rows > t - h) leaves the predictions for t .. t + refit - 1 unchanged."""
    r = _random_returns()
    X = F.features(r, 0.94, 20, 3, 10)
    h = 5
    y = F.forward_return(r, h)
    pred, log = F.walk_forward(X, y, h, 100, 21, lambda a, b: F.fit_ridge(a, b, 1.0),
                               F.predict_ridge)
    assert log and all(last <= start - h for start, last in log)
    assert log[0] == (100, 95)  # first refit: last usable row 100 - 5
    y2 = y.copy()
    y2.iloc[96:] += 1.0  # targets not yet observed at the first refit (row 100)
    pred2, _ = F.walk_forward(X, y2, h, 100, 21, lambda a, b: F.fit_ridge(a, b, 1.0),
                              F.predict_ridge)
    pd.testing.assert_series_equal(pred.iloc[:121], pred2.iloc[:121])
    assert not np.allclose(pred.iloc[121:200], pred2.iloc[121:200])  # later refits see them
    assert pred.iloc[:100].isna().all()


def test_features_known_at_t():
    r = pd.Series([0.01, 0.02, -0.01, 0.03, 0.0, 0.01], index=pd.date_range("2024-01-01", periods=6))
    X = F.features(r, 0.94, 2, 2, 3)
    assert X["r_lag0"].iloc[3] == 0.03 and X["r_lag1"].iloc[3] == -0.01
    assert X["ret5"].iloc[4] == pytest.approx(0.01 + 0.02 - 0.01 + 0.03 + 0.0)
    # rv over 3 days at row 3: sqrt((0.0004 + 0.0001 + 0.0009) / 3) = sqrt(0.00046667)
    assert X["rv"].iloc[3] == pytest.approx(math.sqrt(0.0014 / 3))


def test_ridge_hand_worked():
    """X = 1, 2, 3; y = 1, 2, 3. Standardised z = -1.224745, 0, 1.224745 (population SD sqrt(2/3)).
    Z'Z = 3, Z'(y - 2) = 2.449490. alpha 1: b = 2.449490 / 4 = 0.612372; prediction at X = 3:
    2 + 1.224745 x 0.612372 = 2.75. alpha 0 reproduces y exactly (3.0)."""
    X, y = np.array([[1.0], [2.0], [3.0]]), np.array([1.0, 2.0, 3.0])
    assert F.predict_ridge(F.fit_ridge(X, y, 1.0), np.array([[3.0]]))[0] == pytest.approx(2.75)
    assert F.predict_ridge(F.fit_ridge(X, y, 0.0), np.array([[3.0]]))[0] == pytest.approx(3.0)
    assert F.predict_mean(F.fit_mean(X, y), X).tolist() == [2.0, 2.0, 2.0]


def test_logistic_hand_worked():
    """X = -1, +1 (already standardised), y = 0, 1, L2 = 1. By symmetry the intercept is 0 and the
    slope solves 2 sigma(w) - 2 + w = 0, i.e. w = 2(1 - sigma(w)) = 0.6748 (bisection by hand:
    w = 0.675 gives sigma 0.66262 and 2(1 - 0.66262) = 0.67476)."""
    _, _, w = F.fit_logistic(np.array([[-1.0], [1.0]]), np.array([0.0, 1.0]), 1.0)
    assert w[0] == pytest.approx(0.0, abs=1e-9)
    assert w[1] == pytest.approx(0.6748, abs=2e-4)
    assert w[1] == pytest.approx(2 * (1 - 1 / (1 + math.exp(-w[1]))), abs=1e-9)
    p = F.predict_logistic((np.zeros(1), np.ones(1), w), np.array([[1.0], [-1.0]]))
    assert p[0] > 0.5 > p[1]


def test_losses():
    """QLIKE = ln F + RV/F: (RV 1, F 1) -> 1; (RV 2, F 1) -> 2. MAE of vol: sqrt(0.04) - sqrt(0.01)
    = 0.2 - 0.1 = 0.1."""
    assert F.qlike(np.array([1.0, 2.0]), np.array([1.0, 1.0])).tolist() == [1.0, 2.0]
    assert F.vol_abs_error(np.array([0.04]), np.array([0.01]))[0] == pytest.approx(0.1)


def test_block_bootstrap_and_verdicts():
    """d = 1, 2, 3, 4 with block 4: only one block exists, so every replicate mean is 2.5 and the
    interval collapses to [2.5, 2.5] -> wholly above 0 -> 'does not beat naive'."""
    m, lo, hi = F.block_bootstrap_mean(np.array([1.0, 2, 3, 4]), 4, 500, 1, 0.95)
    assert (m, lo, hi) == (2.5, 2.5, 2.5)
    assert F.verdict(lo, hi) == F.LOSES
    assert F.verdict(-2, -1) == F.BEATS
    assert F.verdict(-1, 1) == F.INCONCLUSIVE
    assert F.verdict(0.0, 1.0) == F.INCONCLUSIVE  # touching zero is not wholly above it
    rng = np.random.default_rng(3)
    d = rng.normal(0, 1, 2000)
    m, lo, hi = F.block_bootstrap_mean(d, 20, 1000, 7, 0.95)
    assert lo < m < hi and (hi - lo) == pytest.approx(2 * 1.96 / math.sqrt(2000), rel=0.35)
    assert F.block_bootstrap_mean(d, 20, 1000, 7, 0.95) == (m, lo, hi)  # fixed seed


def test_equity_curve_costs_and_timing():
    """Simple returns from d1: +10%, -10%, +5% (r = log of those). Position [1, 1, 0] decided at
    the close of each day earns the next day's return:
      d2: (1 - 0.10) x (1 - 0.001 entry cost) = 0.8991
      d3: 0.8991 x 1.05 = 0.944055. The last decision has no next return (dropped).
    Position [0, 1, 0]: d2 flat = 1.0; d3: 1.05 x 0.999 = 1.04895."""
    idx = pd.date_range("2024-01-01", periods=3, freq="B")
    r = pd.Series(np.log([1.10, 0.90, 1.05]), index=idx)
    c = F.equity_curve(r, pd.Series([1.0, 1.0, 0.0], index=idx), 0.001)
    assert list(c.index) == list(idx[1:])
    assert c.tolist() == pytest.approx([0.8991, 0.944055])
    c2 = F.equity_curve(r, pd.Series([0.0, 1.0, 0.0], index=idx), 0.001)
    assert c2.tolist() == pytest.approx([1.0, 1.04895])


def test_curve_stats():
    """Curve 1.1, 0.99, 1.089 over 3 days with 3 'trading days' a year: total 8.9% over 1 year ->
    annual 8.9%; max drawdown 0.99 / 1.1 - 1 = -10%."""
    s = F.curve_stats(pd.Series([1.1, 0.99, 1.089]), 3)
    assert s["total_return"] == pytest.approx(0.089) and s["annual_return"] == pytest.approx(0.089)
    assert s["max_drawdown"] == pytest.approx(-0.1)


def test_headline_counts_and_wording():
    res = [{"verdict": F.BEATS}, {"verdict": F.INCONCLUSIVE}, {"verdict": F.INCONCLUSIVE}]
    h = F.headline(res)
    assert "1 of 3" in h and "0 had higher loss" in h and "2 were inconclusive" in h
    assert "past data only" in h
    for word in ("predict", "reliab", "accurate", "will ", "edge", "signal"):
        assert word not in h.lower()
    assert F.headline([]) == "No comparisons were run."


def test_script_end_to_end_on_synthetic_prices(monkeypatch, tmp_path):
    """The offline script on synthetic random-walk closes (no network, GARCH off): it writes a
    summary with 3 series x (2 vol + 4 return + 4 direction) = 30 comparisons and the frames."""
    import importlib
    from datetime import date

    import assumptions as A
    from data import forecast_store as FS
    from data import markets as M

    from pathlib import Path
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parent.parent / "scripts"))
    run = importlib.import_module("run_forecasts")
    monkeypatch.setattr(run, "arch_model", None)
    monkeypatch.setattr(A, "FORECAST_MIN_TRAIN_DAYS", 300)

    def fake_load(key):
        rng = np.random.default_rng(len(key))
        idx = pd.date_range("2018-01-01", periods=900, freq="B")
        close = 100 * np.exp(np.cumsum(rng.normal(0.0002, 0.01, 900)))
        return M.MarketSeries(M.SERIES[key], pd.DataFrame({"close": close}, index=idx), "cached",
                              date(2021, 6, 11), "2026-10-02T07:00:00")

    monkeypatch.setattr(M, "load_series", fake_load)
    monkeypatch.setattr(FS, "FORECAST_DIR", tmp_path)
    run.main()
    summary = json.loads((tmp_path / "summary.json").read_text(encoding="utf-8"))
    assert summary["schema"] == FS.SCHEMA and summary["experimental"] is True
    assert len(summary["results"]) == 30
    assert {r["verdict"] for r in summary["results"]} <= {F.BEATS, F.LOSES, F.INCONCLUSIVE}
    assert summary["settings"]["FORECAST_COST_BP"] == A.FORECAST_COST_BP
    for key in A.FORECAST_SERIES:
        assert (tmp_path / f"{key}_vol.csv").exists() and (tmp_path / f"{key}_equity.csv").exists()
