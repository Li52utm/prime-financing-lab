"""Replay real equity history through the TRS capital engine (illustrative, simplified).

Reuses engine.capital (trs_saccr, trs_capital, trs_mtm_from_price_move) and engine.financing
(trs_route) without changing them. Simplifications, all stated on the page:
- Static notional: the TRS is struck at the first close of the window with notional N and is not
  resized or reset; the price move is measured from that close.
- Margining is daily on closing prices when on; VM settles the full change in V that day
  (no threshold, no minimum transfer amount, no settlement lag).
- IM is the ticket IM (N x trs_im), posted on day one and never recalled or topped up.
- The street repo is not remargined (engine behaviour: cash raised stays at N(1 - h_st)).
- Dealer financing P&L accrues the ticket's TRS dealer net evenly per calendar day; SONIA,
  spreads and the borrow fee stay at the ticket's values throughout.
- The dealer is delta-hedged, so the hedge P&L offsets V; market risk is not modelled.
"""

from dataclasses import replace
from statistics import NormalDist

import numpy as np
import pandas as pd

from engine.capital import CapitalInputs, trs_capital, trs_mtm_from_price_move, trs_saccr
from engine.financing import FinancingInputs, trs_route


def window(close: pd.Series, start, end) -> pd.Series:
    p = close.dropna()
    return p[(p.index >= pd.Timestamp(start)) & (p.index <= pd.Timestamp(end))]


def replay_trs(prices: pd.Series, x: FinancingInputs, c: CapitalInputs, margined: bool
               ) -> pd.DataFrame:
    """Day-by-day path. VM call > 0: the client pays the dealer (the stock fell)."""
    if len(prices) < 2:
        raise ValueError("need at least two closes in the window")
    p0, d0 = float(prices.iloc[0]), prices.index[0]
    im = x.notional * x.trs_im
    per_day = trs_route(x).dealer_net / x.tenor_days  # GBP per calendar day, static
    rows, v_prev, cum_vm = [], 0.0, 0.0
    for i, (day, price) in enumerate(prices.items()):
        move = float(price) / p0 - 1.0
        v = trs_mtm_from_price_move(x.notional, move)
        vm_call = (v - v_prev) if margined else 0.0
        cum_vm += vm_call
        cc = replace(c, trs_mtm=v, trs_price_move=move, trs_margined=margined)
        sa, cap = trs_saccr(x, cc), trs_capital(x, cc)
        rows.append({
            "date": day, "close": float(price), "move": move, "v": v, "vm_call": vm_call,
            "im_call": im if i == 0 else 0.0, "cash_held": im + cum_vm, "rc": sa["rc"],
            "multiplier": sa["multiplier"], "addon": sa["addon"], "ead": sa["ead"],
            "rwa": cap.rwa, "leverage": cap.leverage_exposure,
            "cum_pnl": per_day * (day - d0).days,
        })
        v_prev = v
    return pd.DataFrame(rows).set_index("date")


def replay_summary(path: pd.DataFrame) -> dict:
    """Worst day = largest one-day fall in the stock (largest VM call to the client when
    margined); peak exposure = highest EAD."""
    ret = path["close"].pct_change()
    worst = ret.idxmin()
    peak = path["ead"].idxmax()
    return {"worst_day": worst, "worst_return": float(ret.loc[worst]),
            "worst_vm_call": float(path.loc[worst, "vm_call"]),
            "peak_day": peak, "peak_ead": float(path.loc[peak, "ead"]),
            "peak_rc": float(path.loc[peak, "rc"]), "max_rwa": float(path["rwa"].max()),
            "max_leverage": float(path["leverage"].max()),
            "trough_move": float(path["move"].min()), "end_pnl": float(path["cum_pnl"].iloc[-1])}


# --- Empirical haircut check -----------------------------------------------------------------

def forward_losses(close: pd.Series, horizon: int) -> pd.Series:
    """Loss over the next `horizon` trading days, dated at the start: 1 - P(t+h) / P(t).
    Positive = the price fell."""
    p = close.dropna()
    return (1.0 - p.shift(-horizon) / p).dropna()


def haircut_check(losses: pd.Series, haircuts: dict[str, float], horizon: int) -> pd.DataFrame:
    """Breaches of each haircut: overlapping windows (every start day) and non-overlapping
    windows (every horizon-th start day from the first)."""
    blocks = losses.iloc[::horizon]
    rows = []
    for label, h in haircuts.items():
        rows.append({"regime": label, "haircut": h, "windows": int(len(losses)),
                     "breaches": int((losses > h).sum()),
                     "breach_pct": float((losses > h).mean() * 100),
                     "blocks": int(len(blocks)), "block_breaches": int((blocks > h).sum()),
                     "worst_loss": float(losses.max()), "worst_start": losses.idxmax()})
    return pd.DataFrame(rows)


# --- Volatility-implied IM ---------------------------------------------------------------------

def ewma_vol(close: pd.Series, lam: float, burn_in: int) -> pd.Series:
    """Daily EWMA volatility of log returns: var_t = lam var_(t-1) + (1 - lam) r_t^2, seeded
    with r_1^2. Uses returns up to and including day t only. The first burn_in values are NaN."""
    r = np.log(close.dropna()).diff().dropna()
    var = (r ** 2).ewm(alpha=1 - lam, adjust=False).mean()
    vol = np.sqrt(var)
    vol.iloc[:burn_in] = np.nan
    return vol


def vol_implied_im(vol: pd.Series, confidence: float, horizon: int) -> pd.Series:
    """IM as a fraction of notional: z(confidence) x daily vol x sqrt(horizon)."""
    return NormalDist().inv_cdf(confidence) * vol * np.sqrt(horizon)


def im_backtest(im: pd.Series, static_im: float, losses: pd.Series) -> dict:
    """Days on which the next-horizon loss exceeded the IM set that day, for the vol-implied IM
    and the static ticket IM (same days for both)."""
    df = pd.concat({"im": im, "loss": losses}, axis=1, sort=True).dropna()
    return {"days": int(len(df)), "vol_breaches": int((df["loss"] > df["im"]).sum()),
            "static_breaches": int((df["loss"] > static_im).sum()),
            "vol_above_static_pct": float((df["im"] > static_im).mean() * 100) if len(df) else np.nan}
