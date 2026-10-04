"""Desk Brief rules, checked against hand-worked numbers."""

import math

import pandas as pd
import pytest

import assumptions as A
from analytics import desk_brief as B
from ui.brief_html import brief_html


def days(*pairs):
    return pd.Series([v for _, v in pairs], index=pd.to_datetime([d for d, _ in pairs]))


LEVELS = days(("2026-09-01", 1.0), ("2026-09-02", 2.0), ("2026-09-03", 3.0),
              ("2026-09-04", 4.0), ("2026-09-07", 10.0))
YIELD = B.BriefSeries("x", "G", "Test yield", "%", "daily", ("x",), lambda d: d["x"], "bp", 100.0)


def test_status_threshold_is_strict():
    # |z| > 2 is stretched; exactly 2 is normal; NaN (no variation) is normal
    assert A.BRIEF_STRETCH_Z == 2.0
    assert B.status(2.01) == "stretched" and B.status(-2.5) == "stretched"
    assert B.status(2.0) == "normal" and B.status(float("nan")) == "normal"


def test_brief_row_hand_worked():
    """Levels 1, 2, 3, 4, 10 (%). Mean 4; deviations -3,-2,-1,0,6 -> sum sq 50, var 50/4 = 12.5,
    sd 3.535534. Level z = 6 / 3.535534 = 1.697056 -> normal. Changes 1,1,1,6: mean 2.25,
    sd sqrt((1.5625*3 + 14.0625)/3) = sqrt(6.25) = 2.5; change z = (6 - 2.25)/2.5 = 1.5 -> normal.
    Latest change 6 percentage points = 600 bp. Percentile: 5 of 5 at or below -> 100."""
    r = B.brief_row(YIELD, LEVELS)
    assert r["Last"] == 10.0 and r["Change"] == pytest.approx(600.0)
    assert r["Change z"] == pytest.approx(1.5) and r["Level z"] == pytest.approx(1.697056, abs=1e-6)
    assert r["Percentile"] == 100.0 and r["Obs"] == 5
    assert r["Level status"] == r["Move status"] == "normal"
    assert B.row_sentence(r) == (
        "Test yield stood at 10.000% on 07 Sep 2026, +600.0 bp on the day (change z +1.50, normal). "
        "The level is at the 100th percentile of 5 daily observations since 01 Sep 2026 "
        "(level z +1.70, normal).")


def test_ordinals():
    assert [B._ord(p) for p in (1, 2, 3, 4, 11, 12, 13, 21, 22, 100, 99.6)] == [
        "1st", "2nd", "3rd", "4th", "11th", "12th", "13th", "21st", "22nd", "100th", "100th"]


def test_change_since_daily_and_monthly():
    """Daily: latest 15 Feb; cutoff 15 Feb - 30 days = 16 Jan; last obs on or before is 1 Jan
    (value 1.0), so change = 5.0 - 1.0 = 4.0. Monthly: previous observation (20 Jan, 2.0) -> 3.0."""
    s = days(("2026-01-01", 1.0), ("2026-01-20", 2.0), ("2026-02-15", 5.0))
    c = B.change_since(s, 30, "daily")
    assert str(c["start"]) == "2026-01-01" and c["change"] == pytest.approx(4.0)
    assert B.change_since(s, 30, "monthly")["change"] == pytest.approx(3.0)
    assert B.change_since(s.iloc[1:], 30, "daily") is None  # nothing 30 days before


def test_movers_rank_by_absolute_change_z_and_skip_nan():
    rows = pd.DataFrame({"Series": list("abcd"), "Change z": [0.5, -3.0, math.nan, 2.0]})
    assert list(B.movers(rows, 3)["Series"]) == ["b", "d", "a"]


def test_funding_sentence_hand_worked():
    """SONIA 4.20 then 4.25; Bank Rate 4.25 both days, 31 days apart. Spread -5.0 bp then 0.0 bp:
    5.0 bp higher. Germany 2s10s: 2y 2.0 / 10y 1.9 (−10 bp) then 2y 2.0 / 10y 2.3 (+30 bp):
    40 bp higher and positively sloped."""
    d0, d1 = "2026-08-01", "2026-09-01"
    data = {"sonia": days((d0, 4.20), (d1, 4.25)), "boe_bank_rate": days((d0, 4.25), (d1, 4.25)),
            "de_2y": days((d0, 2.0), (d1, 2.0)), "de_10y": days((d0, 1.9), (d1, 2.3))}
    out = B.funding_sentences(data, 30)
    assert out[0] == ("SONIA − Bank Rate stood at 0.0 bp on 01 Sep 2026, 5.0 bp higher than on "
                      "01 Aug 2026 (-5.0 bp then).")
    assert out[1] == ("Germany 2s10s stood at 30.0 bp on 01 Sep 2026, 40.0 bp higher than on "
                      "01 Aug 2026 (-10.0 bp then). The curve is positively sloped (10y above 2y).")
    assert len(out) == 2  # series without data are left out, not invented


def test_liquidity_sentence_percent_change():
    """Reserves 800,000 then 760,000 GBP m -> GBP 800.0 bn to 760.0 bn: 40.0 bn lower, -5.0%."""
    data = {"boe_reserves": days(("2026-08-05", 800_000.0), ("2026-09-09", 760_000.0))}
    (s,) = B.funding_sentences(data, 30)
    assert s == ("BoE reserve balances stood at GBP 760.0 bn on 09 Sep 2026, GBP 40.0 bn lower than on "
                 "05 Aug 2026 (GBP 800.0 bn then). That is -5.0% over the period.")


def test_build_rows_skips_missing_inputs():
    rows, skipped = B.build_rows({"sonia": LEVELS})
    assert list(rows["Series"]) == ["SONIA"]
    assert any(s.startswith("Bank Rate: not available") for s in skipped)
    assert any(s.startswith("SONIA − Bank Rate: not available") for s in skipped)


def test_brief_html_escapes_and_labels():
    page = brief_html("Desk Brief", "04 Oct 2026 08:00", "5Y", ["a < b"], [], [],
                      [{"Series": "X & Y", "Last": "1"}], [], ["src"])
    assert "RULES-BASED, NOT A FORECAST" in page
    assert "a &lt; b" in page and "X &amp; Y" in page and "<p>None.</p>" in page


def test_mover_sentence_hand_worked():
    r = B.brief_row(YIELD, LEVELS)  # +600 bp, change z 1.5 (see test_brief_row_hand_worked)
    assert B.mover_sentence(r) == ("Test yield: +600.0 bp on the latest day to 07 Sep 2026, "
                                   "change z +1.50 (daily data).")
