"""Shared UI pieces: banners, formatting, dense tables, explainers, chart styling."""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import assumptions as A

SUBTITLE = "Illustrative, not a regulatory calculation"
PLACEHOLDER_BANNER = (
    "Default spreads and the balance-sheet charge k are placeholder assumptions, "
    "not market levels."
)

# Dark-mode categorical slots from the dataviz reference palette (first three validated
# all-pairs in dark mode). Routes always take slots 1-3; non-route series use slots 5-8.
ROUTE_COLORS = {"PB": "#3987e5", "TRS": "#d95926", "Collateral upgrade": "#199e70"}
OTHER_COLORS = ["#d55181", "#008300", "#9085e9", "#e66767"]  # slots 5-8
SURFACE = "#1a1a19"
INK = "#ffffff"
INK_2 = "#c3c2b7"
MUTED = "#898781"
GRID = "#2c2c2a"
AXIS = "#383835"
ROUTES = ["PB", "TRS", "Collateral upgrade"]


# --- Page furniture ---------------------------------------------------------------

def page_header(title: str, ctx) -> None:
    st.title(title)
    st.warning(PLACEHOLDER_BANNER, icon=":material/info:")
    x = ctx.fin
    st.caption(
        f"GBP {x.notional / 1e6:,.1f}m {ctx.asset_label} · {ctx.tenor} ({x.tenor_days}d) · "
        f"SONIA {x.sonia * 100:.2f}% (placeholder) · k {x.shadow_cost_k * 100:.2f}% · "
        f"{A.HAIRCUT_REGIMES[ctx.cap.haircut_regime]['label']}"
    )


def explain(title: str, body: str) -> None:
    """The 'How is this calculated' expander under every headline number."""
    with st.expander(f"How is this calculated: {title}"):
        st.markdown(body)


# --- Formatting -------------------------------------------------------------------

def bp(x: float | None) -> str:
    return "n/a" if x is None or x != x else f"{x * 1e4:,.1f} bp"


def pct(x: float | None, d: int = 2) -> str:
    return "n/a" if x is None or x != x else f"{x * 100:,.{d}f}%"


def gbp(x: float | None) -> str:
    return "n/a" if x is None or x != x else f"£{x:,.0f}"


def gbp_m(x: float | None) -> str:
    return "n/a" if x is None or x != x else f"£{x / 1e6:,.2f}m"


def over_sonia_bp(amount: float, x) -> float:
    """Annualised cost per GBP of notional, minus SONIA, in bp."""
    return (amount / (x.notional * x.tenor_days / A.DAYS_IN_YEAR) - x.sonia) * 1e4


# --- Tables -----------------------------------------------------------------------

_FORMATS = {
    "gbp": "localized",  # rounded to whole pounds before display
    "bp": "%.1f",
    "pct": "%.2f%%",
    "m": "%.2f",
    "num": "%.4f",
    "int": "%d",
}


def table(df: pd.DataFrame, formats: dict[str, str] | None = None, height: int | None = None):
    """Dense table. Numbers stay numeric so Streamlit right-aligns them.
    formats: column -> one of gbp, bp, pct, m, num, int (values already in those units)."""
    df = df.copy()
    config = {}
    for col, kind in (formats or {}).items():
        if col not in df:
            continue
        if kind == "gbp":
            df[col] = df[col].astype(float).round(0)
        config[col] = st.column_config.NumberColumn(col, format=_FORMATS[kind])
    kwargs = {"hide_index": True, "width": "stretch", "column_config": config}
    if height:
        kwargs["height"] = height
    st.dataframe(df, **kwargs)


# --- Charts -------------------------------------------------------------------------

def style(fig: go.Figure, title: str, x_title: str | None = None,
          y_title: str | None = None, height: int = 380) -> go.Figure:
    """One look for every chart, always with the 'Illustrative' subtitle."""
    fig.update_layout(
        template="plotly_dark",
        title={"text": title, "subtitle": {"text": SUBTITLE, "font": {"color": MUTED, "size": 12}},
               "font": {"color": INK, "size": 16}, "x": 0, "xanchor": "left"},
        paper_bgcolor=SURFACE,
        plot_bgcolor=SURFACE,
        font={"family": "system-ui, -apple-system, Segoe UI, sans-serif", "color": INK_2,
              "size": 12},
        height=height,
        margin={"l": 60, "r": 20, "t": 80, "b": 50},
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.0, "xanchor": "right", "x": 1,
                "bgcolor": "rgba(0,0,0,0)"},
        hoverlabel={"bgcolor": "#262624", "font": {"color": INK}},
        bargap=0.35,
        barcornerradius=4,
    )
    axis = {"gridcolor": GRID, "zerolinecolor": AXIS, "linecolor": AXIS,
            "tickfont": {"color": MUTED}, "title": {"font": {"color": INK_2}}}
    fig.update_xaxes(**axis, title_text=x_title)
    fig.update_yaxes(**axis, title_text=y_title)
    return fig


def show(fig: go.Figure) -> None:
    st.plotly_chart(fig, width="stretch", config={"displaylogo": False})
