"""Forecast Lab (EXPERIMENTAL): offline walk-forward test. The app only displays what this writes.

Run:  .venv\\Scripts\\python scripts\\run_forecasts.py

For each series in assumptions.FORECAST_SERIES (closes loaded live, else from data/cache):
- next-10-day volatility: naive (last 10 days' realised variance), EWMA (lambda 0.94) and, if the
  `arch` package is installed, GARCH(1,1) refitted yearly; scored by QLIKE and MAE of volatility.
- next-day and next-5-day return: naive (zero), historical drift, ridge on lagged returns and
  volatility; scored by squared error.
- next-day and next-5-day direction: naive (always up), drift sign, logistic on the same features;
  scored by 0-1 loss (hit rate shown too).
- equity curves (next-day models, long or flat, net of FORECAST_COST_BP per position change)
  against buy-and-hold.

Every setting is fixed in assumptions.py before the run; nothing is tuned on the test period. Each
model is compared with naive on the same dates; the verdict comes from a moving-block bootstrap
interval on the mean loss difference. Results are written to data/forecasts/ (git-ignored).
"""

import pathlib
import sys
import time
from datetime import datetime
from functools import partial

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import assumptions as A  # noqa: E402
from analytics import forecast as F  # noqa: E402
from data import forecast_store as FS  # noqa: E402
from data import markets as M  # noqa: E402

try:
    from arch import arch_model
    import arch
    ARCH_VERSION = arch.__version__
except ImportError:  # GARCH is optional: the run continues with naive and EWMA only
    arch_model, ARCH_VERSION = None, None


def arch_fitter(x: np.ndarray) -> tuple[float, float, float]:
    """GARCH(1,1), zero mean, normal errors, fitted by arch on returns in percent; omega is
    converted back to decimal-return units."""
    res = arch_model(x * 100, mean="Zero", vol="GARCH", p=1, q=1, dist="normal",
                     rescale=False).fit(disp="off")
    p = res.params
    return float(p["omega"]) / 1e4, float(p["alpha[1]"]), float(p["beta[1]"])


def compare(series, target, model, metric, loss_model, loss_naive, extra=None) -> dict:
    d = np.asarray(loss_model) - np.asarray(loss_naive)
    mean, lo, hi = F.block_bootstrap_mean(d, A.FORECAST_BOOT_BLOCK, A.FORECAST_BOOT_N,
                                          A.FORECAST_BOOT_SEED, A.FORECAST_CONFIDENCE)
    row = {"series": series, "target": target, "model": model, "metric": metric, "n": len(d),
           "model_loss": float(np.mean(loss_model)), "naive_loss": float(np.mean(loss_naive)),
           "diff_mean": mean, "ci_lo": lo, "ci_hi": hi, "verdict": F.verdict(lo, hi),
           # e.g. a drift that is positive on every date calls "up" exactly like naive
           "note": "identical to naive on every test date" if np.all(d == 0) else ""}
    row.update(extra or {})
    return row


def run_series(key: str) -> tuple[list[dict], dict, dict[str, pd.DataFrame]]:
    ms = M.load_series(key)
    close = ms.data["close"]
    close = close[close.index >= pd.Timestamp(A.FORECAST_SAMPLE_START)]
    r = F.log_returns(close)
    name = ms.spec.name
    results, frames = [], {}
    min_train = A.FORECAST_MIN_TRAIN_DAYS
    h_vol = A.FORECAST_VOL_HORIZON

    # --- volatility -------------------------------------------------------------------------
    rv = F.realised_forward(r, h_vol)
    naive = F.naive_variance(r, h_vol)
    ewma = F.ewma_variance(r, A.FORECAST_EWMA_LAMBDA, A.FORECAST_EWMA_SEED_DAYS) * h_vol
    vol = pd.DataFrame({"realised": rv, "naive": naive, "ewma": ewma})
    garch_log = []
    if arch_model is not None:
        vol["garch"], garch_log = F.garch_forecasts(r, h_vol, min_train,
                                                    A.FORECAST_GARCH_REFIT_DAYS, arch_fitter)
    vol = vol.iloc[min_train:].dropna()
    vol = vol[(vol.drop(columns="realised") > 0).all(axis=1)]
    for model in [c for c in vol.columns if c not in ("realised", "naive")]:
        results.append(compare(name, f"Next {h_vol}-day volatility", model.upper(), "QLIKE",
                               F.qlike(vol["realised"], vol[model]),
                               F.qlike(vol["realised"], vol["naive"])))
        results.append(compare(name, f"Next {h_vol}-day volatility", model.upper(),
                               "MAE of volatility", F.vol_abs_error(vol["realised"], vol[model]),
                               F.vol_abs_error(vol["realised"], vol["naive"])))
    frames[f"{key}_vol"] = vol

    # --- returns and direction ---------------------------------------------------------------
    X = F.features(r, A.FORECAST_EWMA_LAMBDA, A.FORECAST_EWMA_SEED_DAYS, A.FORECAST_LAGS,
                   A.FORECAST_VOL_WINDOW)
    wf = partial(F.walk_forward, X, min_train=min_train, refit=A.FORECAST_REFIT_DAYS)
    hit_rates, next_day = [], {}
    for h in A.FORECAST_RETURN_HORIZONS:
        y = F.forward_return(r, h)
        up = (y > 0).astype(float).where(y.notna())
        drift, log_d = wf(y, h=h, fit=F.fit_mean, predict=F.predict_mean)
        ridge, log_r = wf(y, h=h, fit=partial(F.fit_ridge, alpha=A.FORECAST_RIDGE_ALPHA),
                          predict=F.predict_ridge)
        prob, log_l = wf(up, h=h, fit=partial(F.fit_logistic, l2=A.FORECAST_LOGIT_L2),
                         predict=F.predict_logistic)
        for log in (log_d, log_r, log_l):  # no look-ahead: last training row <= refit row - h
            assert all(last <= start - h for start, last in log), "look-ahead in walk-forward"
        df = pd.DataFrame({"y": y, "up": up, "drift": drift, "ridge": ridge, "prob": prob}).dropna()
        tgt = f"Next-{'day' if h == 1 else f'{h}-day'} return"
        for model in ("drift", "ridge"):
            results.append(compare(name, tgt, model.capitalize() if model == "drift" else "Ridge",
                                   "Squared error", (df["y"] - df[model]) ** 2, df["y"] ** 2))
        calls = {"Naive (always up)": np.ones(len(df)), "Drift": (df["drift"] > 0).to_numpy(float),
                 "Logistic": (df["prob"] > 0.5).to_numpy(float)}
        wrong = {m: (c != df["up"].to_numpy()).astype(float) for m, c in calls.items()}
        dtgt = f"Next-{'day' if h == 1 else f'{h}-day'} direction"
        for model in ("Drift", "Logistic"):
            results.append(compare(name, dtgt, model, "0-1 loss (wrong calls)", wrong[model],
                                   wrong["Naive (always up)"],
                                   {"model_hit_rate": float(1 - wrong[model].mean()),
                                    "naive_hit_rate": float(1 - wrong["Naive (always up)"].mean())}))
        for m, w in wrong.items():
            hit_rates.append({"series": name, "target": dtgt, "model": m, "n": len(w),
                              "hit_rate": float(1 - w.mean()), "share_long": float(calls[m].mean())})
        if h == 1:
            next_day = {"drift": df["drift"] > 0, "ridge": df["ridge"] > 0, "logistic": df["prob"] > 0.5}
            test_index = df.index

    # --- equity curves (next-day rules, long or flat, net of costs) ---------------------------
    cost = A.FORECAST_COST_BP / 10_000
    r_test = r.loc[test_index[0]:test_index[-1]]
    positions = {"buy_and_hold": pd.Series(1.0, index=r_test.index)}
    for m, pos in next_day.items():  # flat on any day without a forecast
        positions[m] = pos.reindex(r_test.index, fill_value=False).astype(float)
    curves = {m: F.equity_curve(r_test, p, cost) for m, p in positions.items()}
    frames[f"{key}_equity"] = pd.DataFrame(curves)
    eq_stats = [{"series": name, "rule": m,
                 "trades": int(p.diff().abs().fillna(p.iloc[0]).sum()),
                 "share_long": float(p.mean()),
                 **F.curve_stats(curves[m], A.FORECAST_TRADING_DAYS)} for m, p in positions.items()]

    meta = {"key": key, "name": name, "source": ms.spec.source, "provider": ms.spec.provider,
            "status": ms.status, "as_of": str(ms.as_of), "fetched_at": ms.fetched_at,
            "sample_start": str(r.index[0].date()), "sample_end": str(r.index[-1].date()),
            "n_returns": len(r), "vol_test_start": str(vol.index[0].date()),
            "vol_test_end": str(vol.index[-1].date()), "return_test_start": str(test_index[0].date()),
            "return_test_end": str(test_index[-1].date()), "garch_refits": len(garch_log),
            "garch_last_params": (dict(zip(("omega", "alpha", "beta"), garch_log[-1][2:]))
                                  if garch_log else None),
            "hit_rates": hit_rates, "equity_stats": eq_stats}
    return results, meta, frames


def main():
    t0 = time.time()
    results, metas, frames, failures = [], [], {}, []
    for key in A.FORECAST_SERIES:
        try:
            res, meta, fr = run_series(key)
        except M.MarketDataError as e:
            failures.append(f"{key}: {e}")
            print(f"SKIPPED {key}: {e}")
            continue
        results += res
        metas.append(meta)
        frames.update(fr)
        print(f"{meta['name']}: {len(res)} comparisons ({meta['status']}, as of {meta['as_of']}), "
              f"{time.time() - t0:.0f}s")
    settings = {k: v for k, v in vars(A).items() if k.startswith("FORECAST_")}
    summary = {"schema": FS.SCHEMA, "experimental": True,
               "run_at": datetime.now().isoformat(timespec="seconds"),
               "arch_version": ARCH_VERSION, "settings": settings, "series": metas,
               "failures": failures, "results": results, "headline": F.headline(results)}
    FS.write_summary(summary, frames)
    print(summary["headline"])
    for r in results:
        print(f"  {r['series']:<10} {r['target']:<26} {r['model']:<9} {r['metric']:<24} "
              f"diff {r['diff_mean']:+.3e} [{r['ci_lo']:+.3e}, {r['ci_hi']:+.3e}] {r['verdict']}")
    print(f"Wrote {FS.FORECAST_DIR} in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
