"""Bring your own data: turn a user-supplied CSV into dated series for the stats strip, bands,
z-scores and the Desk Brief rules. Pure functions: nothing here reads or writes files; the page
passes the uploaded or pasted bytes in and keeps the result in session memory only.

Rules (hand-checked in tests/test_user_data.py):
- Dates are parsed with the format the user picks. Rows whose date or value does not parse are
  dropped and counted; nothing is filled or interpolated.
- Values: thousands separators (",") and surrounding spaces are removed; a trailing "%" is
  removed and the number kept as written (5% -> 5, unit chosen by the user). Anything else that
  does not parse is dropped and counted.
- Duplicate dates: the last row for a date is kept and the number dropped is reported.
- Frequency is inferred from the median gap between dates (thresholds in assumptions.py):
  daily, weekly or monthly. Other spacings are not supported (no resampling is done).
"""

import csv
import io
from dataclasses import dataclass

import pandas as pd

import assumptions as A

DATE_FORMATS = {
    "ISO (YYYY-MM-DD)": "%Y-%m-%d",
    "DD/MM/YYYY": "%d/%m/%Y",
    "MM/DD/YYYY": "%m/%d/%Y",
    "Auto (day first)": "auto-dayfirst",
    "Auto (month first)": "auto",
    "Excel serial number": "excel",
}
EXCEL_EPOCH = "1899-12-30"  # Excel's day 0 in the 1900 date system (Microsoft documentation)
USER_LABEL = "USER-SUPPLIED"


class UserDataError(ValueError):
    """The CSV could not be read or mapped; the message is shown on the page."""


@dataclass(frozen=True)
class ParseReport:
    rows: int  # data rows in the file
    bad_dates: int  # rows dropped: date did not parse
    bad_values: int  # rows dropped: value missing or not a number
    duplicates: int  # rows dropped: repeated date (last kept)
    kept: int

    def sentence(self) -> str:
        return (f"{self.rows:,} rows read; {self.kept:,} kept. Dropped: {self.bad_dates:,} with "
                f"an unparsed date, {self.bad_values:,} with a missing or non-numeric value, "
                f"{self.duplicates:,} repeated dates (last row kept). Nothing was filled.")


def read_csv(content: bytes) -> pd.DataFrame:
    """Read CSV bytes (comma, semicolon or tab separated; UTF-8 with or without BOM). All cells are
    read as text so that parsing is explicit and counted."""
    if not content or not content.strip():
        raise UserDataError("The file is empty.")
    if len(content) > A.BYOD_MAX_BYTES:
        raise UserDataError(f"The file is larger than {A.BYOD_MAX_BYTES // 1_000_000} MB.")
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = content.decode("latin-1")
    try:  # separator sniffed among the common ones only (the default sniffer can pick letters)
        sep = csv.Sniffer().sniff(text[:20_000], delimiters=",;\t|").delimiter
    except csv.Error:
        sep = ","
    try:
        df = pd.read_csv(io.StringIO(text), sep=sep, dtype=str, skipinitialspace=True)
    except (pd.errors.ParserError, pd.errors.EmptyDataError, ValueError) as e:
        raise UserDataError(f"Could not read the CSV: {e}") from e
    if df.shape[1] < 2:
        raise UserDataError("Need at least two columns: a date column and a value column.")
    if len(df) > A.BYOD_MAX_ROWS:
        raise UserDataError(f"More than {A.BYOD_MAX_ROWS:,} rows; trim the file first.")
    df.columns = [str(c).strip() for c in df.columns]
    return df


def guess_date_column(df: pd.DataFrame) -> str:
    """First column whose name contains 'date' or 'time', else the first column."""
    for c in df.columns:
        if any(w in c.lower() for w in ("date", "time", "day")):
            return c
    return df.columns[0]


def parse_dates(col: pd.Series, fmt_label: str) -> pd.Series:
    """Parsed dates (NaT where a cell does not match the chosen format)."""
    fmt = DATE_FORMATS[fmt_label]
    s = col.astype(str).str.strip()
    if fmt == "excel":
        n = pd.to_numeric(s, errors="coerce")
        out = pd.to_datetime(EXCEL_EPOCH) + pd.to_timedelta(n, unit="D")
        return out.dt.normalize()
    if fmt.startswith("auto"):
        out = pd.to_datetime(s, format="mixed", dayfirst=fmt == "auto-dayfirst", errors="coerce")
    else:
        out = pd.to_datetime(s, format=fmt, errors="coerce")
    return out.dt.tz_localize(None).dt.normalize() if out.dt.tz is not None else out.dt.normalize()


def parse_values(col: pd.Series) -> pd.Series:
    s = col.astype(str).str.strip().str.replace(",", "", regex=False).str.rstrip("%").str.strip()
    return pd.to_numeric(s, errors="coerce")


def build_series(df: pd.DataFrame, date_col: str, value_col: str,
                 fmt_label: str) -> tuple[pd.Series, ParseReport]:
    if date_col == value_col:
        raise UserDataError("The date column and the value column must differ.")
    dates = parse_dates(df[date_col], fmt_label)
    values = parse_values(df[value_col])
    bad_d = dates.isna()
    bad_v = ~bad_d & values.isna()
    s = pd.Series(values[~bad_d & ~bad_v].to_numpy(),
                  index=pd.DatetimeIndex(dates[~bad_d & ~bad_v]), name=value_col)
    dup = s.index.duplicated(keep="last")
    s = s[~dup].sort_index()
    report = ParseReport(len(df), int(bad_d.sum()), int(bad_v.sum()), int(dup.sum()), len(s))
    if len(s) < 3:
        raise UserDataError(f"Fewer than 3 usable rows in '{value_col}'. {report.sentence()}")
    return s, report


def infer_frequency(index: pd.DatetimeIndex) -> str | None:
    """'daily', 'weekly' or 'monthly' from the median gap in calendar days; None otherwise."""
    if len(index) < 3:
        return None
    gap = float(pd.Series(index).diff().dt.days.dropna().median())
    for freq, (lo, hi) in A.BYOD_FREQ_GAP_DAYS.items():
        if lo <= gap <= hi:
            return freq
    return None


def range_start(s: pd.Series, months: int | None):
    """Window start counted back from the series' own last date (user data may be old)."""
    return None if months is None else s.index[-1] - pd.DateOffset(months=months)


@dataclass
class UserSeries:
    label: str
    unit: str
    frequency: str
    data: pd.Series
    origin: str  # file name, "pasted text" or "spread A − B"


def spread(a: UserSeries, b: UserSeries, scale: float, unit: str) -> UserSeries:
    """(A − B) x scale on dates both carry (series_stats.combine: no filling)."""
    from analytics.series_stats import combine
    if a.frequency != b.frequency:
        raise UserDataError(f"{a.label} is {a.frequency} and {b.label} is {b.frequency}; a spread "
                            "needs both at the same frequency (nothing is resampled).")
    s = combine(a.data, b.data, scale)
    if len(s) < 3:
        raise UserDataError("Fewer than 3 dates are common to both series.")
    return UserSeries(f"{a.label} − {b.label}", unit, a.frequency, s,
                      f"spread of {a.label} and {b.label}")


def brief_rows(series: list[UserSeries], start_months: int | None) -> tuple[pd.DataFrame, list[str]]:
    """Desk Brief rules (analytics.desk_brief) applied to user series, each windowed back from its
    own last date. Returns rows plus a list of series skipped and why."""
    from analytics import desk_brief as B
    rows, skipped = [], []
    for i, u in enumerate(series):
        s = u.data.dropna()
        start = range_start(s, start_months)
        s = s if start is None else s[s.index >= start]
        if len(s) < 3:
            skipped.append(f"{u.label}: fewer than 3 observations in the window.")
            continue
        spec = B.BriefSeries(f"user_{i}", USER_LABEL, u.label, u.unit, u.frequency, (),
                             lambda d: d, u.unit)
        rows.append(B.brief_row(spec, s))
    return pd.DataFrame(rows), skipped
