import streamlit as st

from ui.assumptions_reader import PATH, read_assumptions
from ui.common import page_header
from ui.ticket import get_ctx

ctx = get_ctx()
page_header("Assumptions", ctx)
st.markdown(
    "Every default comes from `assumptions.py`, read live. **VERIFIED** means checked against the "
    "quoted rule text (PRA Rulebook / UK CRR) on 2026-09-30. **UNVERIFIED** means not yet checked, "
    "or a public source not re-checked here. **n/a** marks own assumptions and hypothetical stress "
    "values, which have no source to verify. Regulatory treatment is illustrative and simplified."
)

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
st.dataframe(view, hide_index=True, width="stretch", height=620, column_config={
    "Source / comment": st.column_config.TextColumn(width="large"),
    "Value": st.column_config.TextColumn(width="medium"),
})

with st.expander("assumptions.py (full file)"):
    st.code(PATH.read_text(encoding="utf-8"), language="python")
