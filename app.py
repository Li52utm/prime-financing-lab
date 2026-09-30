"""Prime Financing Lab: PB vs TRS vs collateral upgrade. Illustrative only.

Run: .venv\\Scripts\\python -m streamlit run app.py
"""

import streamlit as st

from ui.ticket import render_ticket

st.set_page_config(page_title="Prime Financing Lab", page_icon=":material/balance:",
                   layout="wide")

render_ticket()

pages = [
    st.Page("pages/summary_page.py", title="Summary", icon=":material/dashboard:",
            default=True),
    st.Page("pages/client_page.py", title="Client view", icon=":material/person:"),
    st.Page("pages/desk_page.py", title="Desk view", icon=":material/monitoring:"),
    st.Page("pages/capital_page.py", title="Capital", icon=":material/account_balance:"),
    st.Page("pages/stress_page.py", title="Stress lab", icon=":material/bolt:"),
    st.Page("pages/assumptions_page.py", title="Assumptions", icon=":material/list_alt:"),
]
st.navigation(pages).run()
