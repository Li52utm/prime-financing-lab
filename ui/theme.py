"""Terminal desk theme: shared CSS and the top banner. Injected once per run from app.py.

Colours live in ui.common (palette) and .streamlit/config.toml (Streamlit theme). Only system
font stacks are used, so nothing is downloaded.
"""

import html

from ui.common import ACCENT, AXIS, INK, INK_2, MONO, MUTED, PAGE, PANEL_2, SURFACE

THEME_MARKER = "pfl-theme-v1"  # lets tests confirm the CSS loaded
STATUS_COLORS = {"live": ACCENT, "cached": "#ffc247", "fallback": "#d77ee8",
                 "manual override": "#6dd3ff"}

CSS = f"""
<style>
/* {THEME_MARKER} */
:root {{ --pfl-accent: {ACCENT}; --pfl-ink: {INK}; --pfl-ink2: {INK_2}; --pfl-muted: {MUTED};
        --pfl-page: {PAGE}; --pfl-panel: {SURFACE}; --pfl-panel2: {PANEL_2}; --pfl-line: {AXIS};
        --pfl-mono: {MONO}; }}

/* Density */
[data-testid="stMainBlockContainer"], .block-container {{
  padding-top: 3.6rem !important; padding-bottom: 2rem !important;
  padding-left: 1.6rem !important; padding-right: 1.6rem !important; max-width: none !important; }}
[data-testid="stVerticalBlock"] {{ gap: 0.55rem; }}
[data-testid="stSidebarContent"] [data-testid="stVerticalBlock"] {{ gap: 0.35rem; }}
[data-testid="stSidebarHeader"] {{ height: 0.6rem; min-height: 0; padding: 0; }}
[data-testid="stSidebarUserContent"] {{ padding-top: 0.6rem; }}
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p {{ font-size: 0.8rem; line-height: 1.45; }}

/* Chrome: header strip and top navigation */
[data-testid="stHeader"] {{ background: var(--pfl-page); border-bottom: 1px solid var(--pfl-line); }}
[data-testid="stDecoration"] {{ display: none; }}
[data-testid="stToolbar"] {{ opacity: 0.6; }}

/* Top banner */
.pfl-banner {{ display: flex; flex-wrap: wrap; align-items: baseline; gap: 0.4rem 1.4rem;
  border: 1px solid var(--pfl-line); border-left: 3px solid var(--pfl-accent);
  background: var(--pfl-panel); padding: 0.45rem 0.9rem; margin: 0 0 0.6rem 0;
  font-family: var(--pfl-mono); }}
.pfl-brand {{ color: var(--pfl-accent); font-weight: 700; letter-spacing: 0.14em; font-size: 0.95rem; }}
.pfl-page {{ color: var(--pfl-ink); letter-spacing: 0.08em; font-size: 0.85rem; }}
.pfl-sonia {{ color: var(--pfl-ink2); font-size: 0.8rem; margin-left: auto; }}
.pfl-status {{ font-weight: 700; letter-spacing: 0.06em; }}

/* Headings */
[data-testid="stMain"] h1, [data-testid="stMain"] h2, [data-testid="stMain"] h3 {{
  color: var(--pfl-accent); text-transform: uppercase; letter-spacing: 0.07em;
  font-weight: 700; border-bottom: 1px solid var(--pfl-line); padding: 0.2rem 0 0.25rem 0; }}
[data-testid="stMain"] h2 {{ font-size: 0.98rem !important; margin-top: 0.9rem; }}
[data-testid="stMain"] h3 {{ font-size: 0.9rem !important; margin-top: 0.8rem; }}
[data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3 {{
  color: var(--pfl-accent); text-transform: uppercase; letter-spacing: 0.08em;
  font-size: 0.82rem !important; }}

/* Metrics: green value, small uppercase label, tabular figures */
[data-testid="stMetricValue"] {{ color: var(--pfl-accent); font-size: 1.45rem !important;
  font-variant-numeric: tabular-nums; }}
[data-testid="stMetricLabel"] p {{ color: var(--pfl-muted); text-transform: uppercase;
  letter-spacing: 0.06em; font-size: 0.72rem !important; }}
[data-testid="stMetricDelta"] {{ font-size: 0.75rem !important; }}

/* Top navigation: square tabs, green underline on the active page */
[data-testid="stTopNavLink"] {{ border-radius: 0 !important; letter-spacing: 0.04em; }}
[data-testid="stTopNavLink"][aria-current="page"] {{ box-shadow: inset 0 -2px 0 var(--pfl-accent); }}

/* Panels: square, thin borders, no shadows */
[data-testid="stLayoutWrapper"], [data-testid="stExpander"] details,
[data-testid="stAlert"], [data-testid="stAlertContainer"], [data-testid="stDataFrame"],
[data-testid="stPlotlyChart"] {{ border-radius: 0 !important; box-shadow: none !important; }}
[data-testid="stExpander"] details {{ border: 1px solid var(--pfl-line) !important;
  background: var(--pfl-panel); }}
[data-testid="stExpander"] summary p {{ color: var(--pfl-ink2); font-size: 0.78rem; }}
[data-testid="stAlertContainer"] {{ background: var(--pfl-panel2) !important;
  border: 1px solid var(--pfl-line); padding: 0.45rem 0.8rem !important; }}
[data-testid="stAlertContainer"] p {{ font-size: 0.8rem; }}
[data-testid="stMain"] [data-testid="stMarkdownContainer"] p,
[data-testid="stMain"] [data-testid="stMarkdownContainer"] li {{ font-size: 0.84rem; line-height: 1.5; }}
/* Metric values render inside a markdown container: keep them large (beats the rule above) */
[data-testid="stMain"] [data-testid="stMetricValue"] [data-testid="stMarkdownContainer"] p,
[data-testid="stMain"] [data-testid="stMetricValue"] p {{ font-size: 1.45rem; line-height: 1.25; }}
[data-testid="stMain"] [data-testid="stMetricLabel"] [data-testid="stMarkdownContainer"] p {{
  font-size: 0.72rem; }}
[data-testid="stMain"] [data-testid="stMetricDelta"] [data-testid="stMarkdownContainer"] p {{
  font-size: 0.75rem; }}
[data-testid="stCaptionContainer"] p {{ color: var(--pfl-muted); font-size: 0.76rem; }}
[data-testid="stPlotlyChart"] {{ border: 1px solid var(--pfl-line); }}
</style>
"""


def banner_html(page_title: str, ctx) -> str:
    """'PRIME FINANCING LAB / SUMMARY ... SONIA 3.7329% · 30 SEP 2026 · BOE IADB · LIVE'."""
    q = ctx.sonia_quote
    if ctx.sonia_overridden:
        status, rate, detail = "manual override", ctx.fin.sonia, "OVERRIDE"
    else:
        status, rate = q.status, q.rate
        as_of = q.as_of.strftime("%d %b %Y").upper() if q.as_of else "NO DATE"
        detail = f"{as_of} · {q.source.upper()}"
    color = STATUS_COLORS.get(status, INK)
    return (
        '<div class="pfl-banner" data-testid="pfl-banner">'
        '<span class="pfl-brand">PRIME FINANCING LAB</span>'
        f'<span class="pfl-page">/ {html.escape(page_title.upper())}</span>'
        f'<span class="pfl-sonia">SONIA {rate * 100:.4f}% · {html.escape(detail)} · '
        f'<span class="pfl-status" style="color:{color}">{status.upper()}</span></span>'
        "</div>"
    )
