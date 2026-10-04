"""Bring-your-own-data parsing, mapping, frequency, spread and brief rules (hand-worked)."""

import pandas as pd
import pytest

from analytics import user_data as U

CSV = (b"\xef\xbb\xbfDate;Rate;Notional\n"
       b"02/01/2024;4.00%;1,000\n"
       b"03/01/2024;4.10%;1,100\n"
       b"bad date;4.20%;1,200\n"
       b"04/01/2024;n/a;1,300\n"
       b"05/01/2024;4.30%;1,400\n"
       b"05/01/2024;4.35%;1,450\n"
       b"08/01/2024;4.40%;1,500\n")


def test_read_csv_sniffs_separator_and_bom():
    df = U.read_csv(CSV)
    assert list(df.columns) == ["Date", "Rate", "Notional"]  # BOM stripped, ';' detected
    assert len(df) == 7 and df["Rate"].iloc[0] == "4.00%"  # read as text
    assert U.guess_date_column(df) == "Date"


@pytest.mark.parametrize("content", [b"", b"   ", b"only_one_column\n1\n2\n"])
def test_read_csv_rejects_empty_or_single_column(content):
    with pytest.raises(U.UserDataError):
        U.read_csv(content)


def test_build_series_counts_every_dropped_row():
    """7 rows: 'bad date' dropped (1 bad date); 'n/a' dropped (1 bad value); 05/01 appears twice,
    last kept (1 duplicate). Kept = 7 - 1 - 1 - 1 = 4: 2, 3, 5 (4.35) and 8 Jan."""
    s, rep = U.build_series(U.read_csv(CSV), "Date", "Rate", "DD/MM/YYYY")
    assert (rep.rows, rep.bad_dates, rep.bad_values, rep.duplicates, rep.kept) == (7, 1, 1, 1, 4)
    assert list(s.index.strftime("%Y-%m-%d")) == ["2024-01-02", "2024-01-03", "2024-01-05",
                                                  "2024-01-08"]
    assert list(s) == [4.00, 4.10, 4.35, 4.40]  # '%' stripped, number kept as written
    assert "Nothing was filled" in rep.sentence()


def test_thousands_separator_and_month_first_format():
    s, _ = U.build_series(U.read_csv(CSV), "Date", "Notional", "MM/DD/YYYY")
    # read month first, 02/01/2024 is 1 Feb 2024; 1,000 -> 1000
    assert s.index[0] == pd.Timestamp("2024-02-01") and s.iloc[0] == 1000.0


def test_wrong_format_drops_rather_than_guesses():
    """ISO format on DD/MM/YYYY text: no row matches, so the series is rejected (not guessed)."""
    with pytest.raises(U.UserDataError, match="Fewer than 3 usable rows"):
        U.build_series(U.read_csv(CSV), "Date", "Rate", "ISO (YYYY-MM-DD)")


def test_excel_serial_dates():
    """Excel serial 45293 = 1899-12-30 + 45293 days = 2024-01-02."""
    df = pd.DataFrame({"d": ["45293", "45294", "45295"], "v": ["1", "2", "3"]})
    s, _ = U.build_series(df, "d", "v", "Excel serial number")
    assert s.index[0] == pd.Timestamp("2024-01-02") and s.index[-1] == pd.Timestamp("2024-01-04")


def test_same_column_rejected():
    with pytest.raises(U.UserDataError):
        U.build_series(U.read_csv(CSV), "Date", "Date", "DD/MM/YYYY")


@pytest.mark.parametrize("freq, expected", [("B", "daily"), ("W-FRI", "weekly"),
                                            ("MS", "monthly"), ("QS", None)])
def test_infer_frequency(freq, expected):
    """Median gaps: business days 1 -> daily; 7 -> weekly; 28-31 -> monthly; quarters ~91 ->
    unsupported (None, nothing resampled)."""
    assert U.infer_frequency(pd.date_range("2020-01-01", periods=30, freq=freq)) == expected


def _u(label, values, freq="D", unit="%"):
    idx = pd.date_range("2024-01-01", periods=len(values), freq=freq)
    return U.UserSeries(label, unit, "daily" if freq == "D" else "monthly",
                        pd.Series(values, index=idx, dtype=float), "test")


def test_spread_common_dates_only_and_scaled():
    """A = 4.0, 4.1, 4.3, 4.4 on 1-4 Jan; B = 3.5, 3.5, 3.6 on 2-4 Jan. Common dates 2-4 Jan:
    (4.1 - 3.5) x 100 = 60; (4.3 - 3.5) x 100 = 80; (4.4 - 3.6) x 100 = 80 bp. 1 Jan dropped."""
    a = _u("A", [4.0, 4.1, 4.3, 4.4])
    b = U.UserSeries("B", "%", "daily", pd.Series(
        [3.5, 3.5, 3.6], index=pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04"])), "t")
    sp = U.spread(a, b, 100.0, "bp")
    assert sp.label == "A − B" and sp.unit == "bp"
    assert list(sp.data.round(6)) == [60.0, 80.0, 80.0]


def test_spread_rejects_mixed_frequency():
    with pytest.raises(U.UserDataError, match="same frequency"):
        U.spread(_u("A", [1, 2, 3, 4]), _u("B", [1, 2, 3, 4], freq="MS"), 1.0, "x")


def test_brief_rows_apply_desk_brief_rules():
    """Levels 1, 2, 3, 4, 10 (daily). Changes 1, 1, 1, 6: mean 2.25, sample SD 2.5, latest change
    z = (6 - 2.25) / 2.5 = 1.5 -> normal. Level mean 4, sample SD sqrt(50/4) = 3.535534,
    level z = 6 / 3.535534 = 1.697056 -> normal. Percentile = 5/5 = 100."""
    rows, skipped = U.brief_rows([_u("X", [1, 2, 3, 4, 10], unit="bp")], None)
    r = rows.iloc[0]
    assert not skipped
    assert r["Group"] == "USER-SUPPLIED" and r["Change"] == 6
    assert r["Change z"] == pytest.approx(1.5) and r["Level z"] == pytest.approx(1.697056, abs=1e-6)
    assert r["Percentile"] == 100 and r["Level status"] == "normal"


def test_brief_rows_window_counts_back_from_series_end():
    """A 1-month window on daily data from 1 Jan to 30 Apr keeps 30 Mar to 30 Apr."""
    u = _u("Y", list(range(121)))
    rows, _ = U.brief_rows([u], 1)
    assert rows.iloc[0]["From"] == pd.Timestamp("2024-03-30").date()
    rows, skipped = U.brief_rows([_u("Z", [1.0, 2.0])], None)
    assert rows.empty and "fewer than 3" in skipped[0]


def test_module_never_touches_disk():
    """User data is session-memory only: the parsing module has no file or cache calls."""
    import inspect
    src = inspect.getsource(U)
    for needle in ("open(", "to_csv(", "write_", "Path(", "cache", "pickle"):
        assert needle not in src, needle
