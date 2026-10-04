import streamlit as st

from data import sources as SRC
from ui.assumptions_reader import PATH, read_assumptions
from ui.common import TABLE_ROW_PX, page_header
from ui.ticket import get_ctx

ctx = get_ctx()
page_header("Assumptions", ctx)
st.markdown(
    "Every default comes from `assumptions.py`, read live. **VERIFIED** means checked against the "
    "quoted rule text (PRA Rulebook / UK CRR) on 2026-09-30. **UNVERIFIED** means not yet checked, "
    "or a public source not re-checked here. **n/a** marks own assumptions and hypothetical stress "
    "values, which have no source to verify. Regulatory treatment is illustrative and simplified."
)

q = ctx.sonia_quote
st.info(
    f"**SONIA source.** Loaded live from the Bank of England IADB, series IUDSOIA; fallback FRED "
    f"series IUDSOIA; the last good value is cached in `data/cache/sonia.json`; if both fail and "
    f"there is no cache, the `SONIA` placeholder below is used. Now: {q.rate * 100:.4f}% as of "
    f"{q.as_of.strftime('%d %b %Y') if q.as_of else 'n/a'} ({q.source}, status {q.status})"
    + ("; manual override in use." if ctx.sonia_overridden else "."),
    )

# --- Data sources: every source the app uses, in one table ---------------------------------
st.subheader("Data sources")
st.markdown("Every source the app uses: where it is used, its URL, frequency, verified earliest "
            "date, terms and status. Rates, liquidity and FX rows come from the live audit run by "
            "`scripts/source_audit.py` (raw first lines in `data/source_audit.md`); Markets rows "
            "show their last fetch on this machine. Load order everywhere: live, then cache "
            "(`data/cache/`, git-ignored), then an error on the page.")
try:
    audit = SRC.read_audit()
    st.caption(f"Audit run at {audit['run_at'].replace('T', ' ')}. Yahoo Finance (FTSE 100, "
               "S&P 500) is not an official provider; its rows say so.")
    st.dataframe(SRC.source_table(audit), hide_index=True, width="stretch",
                 row_height=TABLE_ROW_PX, height=560,
                 column_config={"Series": st.column_config.TextColumn(width="medium"),
                                "Frequency": st.column_config.TextColumn(width="small"),
                                "Earliest": st.column_config.TextColumn(width="small"),
                                "Status": st.column_config.TextColumn(width="large"),
                                "Terms": st.column_config.TextColumn(width="large"),
                                "URL": st.column_config.TextColumn(width="medium")})
    st.markdown("**Tried and not used:**")
    st.dataframe(SRC.not_used_table(audit), hide_index=True, width="stretch",
                 row_height=TABLE_ROW_PX)
except (OSError, ValueError, KeyError) as e:
    st.error(f"Source audit file not readable ({e}). Run scripts/source_audit.py.")
st.markdown("**Charts dropped or not built** (no free official data, nothing substituted): UK "
            "2s10s (no Bank of England 2y nominal yield); France and Italy 2s10s (no free official "
            "daily or monthly 2y); euro policy rate versus €STR (not built: the ECB deposit rate "
            "series was not audited). France-Germany and Italy-Germany 10y spreads are MONTHLY. "
            "Official euro excess liquidity exists only from 27 Sep 2024; the longer line is "
            "DF + CA − MLF, labelled as not excess liquidity.")

st.subheader("Assumptions")
df = read_assumptions()
c1, c2 = st.columns([2, 3])
status = c1.multiselect("Status", ["VERIFIED", "UNVERIFIED", "n/a"],
                        default=["VERIFIED", "UNVERIFIED", "n/a"], key="assumption_status")
query = c2.text_input("Search name or comment", key="assumption_query")
view = df[df["Status"].isin(status)]
if query:
    mask = (view["Name"].str.contains(query, case=False)
            | view["Source / comment"].str.contains(query, case=False))
    view = view[mask]
counts = df["Status"].value_counts()
st.caption(" · ".join(f"{k}: {counts.get(k, 0)}" for k in ["VERIFIED", "UNVERIFIED", "n/a"]))
st.dataframe(view, hide_index=True, width="stretch", height=620, row_height=TABLE_ROW_PX,
             column_config={
    "Source / comment": st.column_config.TextColumn(width="large"),
    "Value": st.column_config.TextColumn(width="medium"),
})

with st.expander("assumptions.py (full file)"):
    st.code(PATH.read_text(encoding="utf-8"), language="python")
