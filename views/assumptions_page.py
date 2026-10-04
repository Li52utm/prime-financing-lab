import json
import pathlib

import pandas as pd
import streamlit as st

from data import markets as M

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

st.markdown("**Market data sources (Markets page).** Each was fetched and checked before use on "
            "2026-10-03. FRED (no response from the development network) and Stooq (bot "
            "challenge instead of data) are not used.")
st.dataframe(pd.DataFrame([{
    "Series": s.name, "Source": s.source, "Code": s.code,
    "Earliest (verified)": s.earliest_verified, "Terms of use": M.TERMS[s.provider],
} for s in M.SERIES.values()]), hide_index=True, width="stretch", row_height=TABLE_ROW_PX,
   column_config={
    "Terms of use": st.column_config.TextColumn(width="large")})

# --- Rates, liquidity and FX source audit (live, scripts/source_audit.py) ----------------
AUDIT = pathlib.Path(__file__).resolve().parent.parent / "data" / "source_audit.json"
st.markdown("**Source audit: rates, liquidity and FX.** Official public providers only, each "
            "fetched live from the development machine by `scripts/source_audit.py` "
            "(full raw first lines in `data/source_audit.md`).")
try:
    audit = json.loads(AUDIT.read_text(encoding="utf-8"))
    st.caption(f"Audit run at {audit['run_at'].replace('T', ' ')}.")
    st.dataframe(pd.DataFrame([{
        "Series": r["name"], "Source": r["source"], "Works": "yes" if r.get("works") else "NO",
        "Frequency": r["frequency"], "Earliest": r.get("earliest", "-"),
        "Latest": r.get("latest", "-"), "Rows": r.get("rows"),
        "Terms": ("TERMS UNVERIFIED. " if r["terms_unverified"] else "") + r["terms"],
    } for r in audit["series"]]), hide_index=True, width="stretch", row_height=TABLE_ROW_PX,
        column_config={"Terms": st.column_config.TextColumn(width="large"),
                       "Rows": st.column_config.NumberColumn(format="%d")})
    st.markdown("**Tried and not used:**")
    st.dataframe(pd.DataFrame([{"Source": n["name"], "URL": n["url"], "Result": n["status"]}
                               for n in audit["not_used"]]),
                 hide_index=True, width="stretch", row_height=TABLE_ROW_PX)
except (OSError, ValueError, KeyError) as e:
    st.error(f"Source audit file not readable ({e}). Run scripts/source_audit.py.")

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
