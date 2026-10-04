"""Glossary: plain-English definitions, why each matters for financing, and links to where the
concept shows up in this app. All text is hand-written in content/glossary.py."""

import streamlit as st

from content.glossary import TERMS

st.caption(f"{len(TERMS)} terms, hand-written for this app. Each entry links to the page and "
           "chart where the concept shows up; where the app has no chart, the entry says why. "
           "Regulatory descriptions are simplified and illustrative.")
q = st.text_input("Filter terms", key="gl_filter", placeholder="e.g. repo, margin, SONIA")
shown = [t for t in TERMS if not q or q.lower() in (t.name + " " + t.definition).lower()]
if not shown:
    st.info(f"No term matches '{q}'.")
for t in shown:
    with st.container(border=True):
        st.markdown(f"#### {t.name}")
        st.markdown(t.definition)
        st.markdown(f"**Why it matters for financing:** {t.why_financing}")
        if t.links:
            st.markdown("**Where it shows up in this app:**")
            for ln in t.links:
                st.page_link(ln.page, label=f"{ln.label} → {ln.chart}",
                             icon=":material/arrow_forward:")
        else:
            st.caption(f"Not charted: {t.not_charted}")
