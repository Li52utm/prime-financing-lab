"""The Data Sources table lists every source with URL, frequency, earliest date, terms, status."""

from data import markets as M
from data import sources as S


def test_source_table_complete_and_unique():
    audit = S.read_audit()
    df = S.source_table(audit)
    # 25 audited series + 4 Markets-only series (FTSE, S&P, UK 10y, Bund 10y) + SONIA ticket
    # + dated events + user data = 32 rows
    assert len(df) == len(audit["series"]) + 4 + 3 == 32
    assert list(df.columns) == S.COLUMNS
    assert not df.isna().any().any() and (df.astype(str).apply(lambda c: c.str.strip()) != "").all().all()
    for _, r in df.iloc[:-1].iterrows():  # every row but user data carries an http(s) URL
        assert "https://" in r["URL"], r["Series"]
    assert df["Series"].is_unique
    yahoo = df[df["Provider"].str.contains("Yahoo")]
    assert len(yahoo) == 2 and yahoo["Terms"].str.contains("Not an official provider").all()
    assert df.loc[df["Series"] == "US Treasury 2y par yield", "Terms"].str.startswith(
        "TERMS UNVERIFIED").all()
    for key in M.SERIES:
        assert any(M.SERIES[key].name in s or key in ("brent", "gbpusd") for s in df["Series"])


def test_market_status_reads_cache_stamp(monkeypatch, tmp_path):
    """Markets rows show the last fetch from the cache meta, or say none happened."""
    monkeypatch.setattr(M, "CACHE_DIR", tmp_path)
    assert "not fetched on this machine yet" in S._market_status("ftse100")
    import pandas as pd
    M.write_cache("ftse100", pd.DataFrame({"close": [1.0, 2.0]},
                                          index=pd.to_datetime(["2026-10-01", "2026-10-02"])),
                  "2026-10-02T18:00:00")
    assert "last fetched 2026-10-02 18:00, as of 2026-10-02" in S._market_status("ftse100")


def test_not_used_table():
    t = S.not_used_table(S.read_audit())
    assert {"FRED", "Stooq"} <= {n.split()[0] for n in t["Source"]}
