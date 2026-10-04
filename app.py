"""Prime Financing Lab: PB vs TRS vs collateral upgrade. Illustrative only.

Run: .venv\\Scripts\\python -m streamlit run app.py
"""

import streamlit as st

from ui.theme import CSS, banner_html
from ui.ticket import render_ticket

st.set_page_config(page_title="Prime Financing Lab", page_icon=":material/balance:",
                   layout="wide")
st.markdown(CSS, unsafe_allow_html=True)  # shared theme CSS, once per run

ctx = render_ticket()

# Grouped so the top bar stays on one line at laptop width (each group is a dropdown)
pages = {
    "Financing": [
        st.Page("views/summary_page.py", title="Summary", default=True),
        st.Page("views/client_page.py", title="Client view"),
        st.Page("views/desk_page.py", title="Desk view"),
        st.Page("views/capital_page.py", title="Capital"),
        st.Page("views/stress_page.py", title="Stress lab"),
        st.Page("views/replay_page.py", title="Replay history"),
    ],
    "Market data": [
        st.Page("views/markets_page.py", title="Markets"),
        st.Page("views/rates_page.py", title="Rates & Liquidity"),
        st.Page("views/brief_page.py", title="Desk Brief"),
        st.Page("views/byod_page.py", title="Bring your own data"),
    ],
    "Learn": [
        st.Page("views/glossary_page.py", title="Glossary"),
        st.Page("views/trainer_page.py", title="Concept Trainer"),
    ],
    "Reference": [
        st.Page("views/assumptions_page.py", title="Assumptions"),
    ],
}
page = st.navigation(pages, position="top")
st.markdown(banner_html(page.title, ctx), unsafe_allow_html=True)
page.run()
