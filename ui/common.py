"""Shared UI pieces: banners, formatting, dense tables, explainers, chart styling."""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import assumptions as A

SUBTITLE = "Illustrative, not a regulatory calculation"
# Readability (display only): chart text >= 14px, hover 15px, thicker lines, larger markers.
CHART_TEXT_PX = 14
CHART_TITLE_PX = 17
CHART_HOVER_PX = 15
LINE_WIDTH = 3
MARKER_PX = 10
TABLE_ROW_PX = 38  # dense but legible at 14px table text
PLACEHOLDER_BANNER = (
    "Default spreads and the balance-sheet charge k are placeholder assumptions, "
    "not market levels."
)

# Terminal desk palette (all on a near-black page). CVD-checked with Machado (2009) simulation
# and OKLab Delta E x100: every route pair >= 14.6 under protan / deutan / tritan, >= 24.5
# normal; contrast on the panel colour >= 6:1. Routes also differ by marker and dash.
PAGE = "#0b0c0b"
SURFACE = "#151715"  # panels and chart background
PANEL_2 = "#1c1f1c"
INK = "#e4e6e1"
INK_2 = "#b9bdb5"
MUTED = "#a1a69c"  # >= 6.4:1 on every panel background
GRID = "#232723"
AXIS = "#343934"
ACCENT = "#3ddc84"  # UI accent: headings, key metrics, active states (not used for series)
ROUTES = ["PB", "TRS", "Collateral upgrade"]
ROUTE_COLORS = {"PB": "#25a85c", "TRS": "#ffc247", "Collateral upgrade": "#6dd3ff"}
ROUTE_SYMBOLS = {"PB": "circle", "TRS": "square", "Collateral upgrade": "diamond"}
ROUTE_DASHES = {"PB": "solid", "TRS": "dash", "Collateral upgrade": "dot"}
ROUTE_PATTERNS = {"PB": "", "TRS": "/", "Collateral upgrade": "."}  # bar fills
# Non-route series (components, stress lines): violet, light grey, coral, steel.
# All pairs pass CVD checks (worst 8.4 tritan, violet/coral).
OTHER_COLORS = ["#d77ee8", "#c9ccc6", "#ff8a5c", "#4f7fae"]
OTHER_SYMBOLS = ["triangle-up", "x", "star", "hexagon"]
OTHER_DASHES = ["solid", "dash", "dot", "dashdot"]
# Diverging scale for RoLE - k: misses magenta-violet, clears green, neutral dark midpoint.
# Lightness rises away from zero on both arms; a bold contour marks zero. CVD-checked: worst
# pair (mid steps, deuteranopia) Delta E 14.8. Deliberately not red versus green.
DIVERGING = [[0.0, "#d77ee8"], [0.25, "#8a45a6"], [0.5, "#2a2d2a"], [0.75, "#2c7a4b"],
             [1.0, "#4fe08f"]]


# Markets page roles (same palette; up/down candles are green/violet, not red/green).
MKT = {
    "up": ACCENT, "down": OTHER_COLORS[0], "band": "#6dd3ff", "band_fill": "rgba(109,211,255,0.07)",
    "ma_fast": "#ffc247", "ma_slow": OTHER_COLORS[1], "above": OTHER_COLORS[2], "below": "#4fe08f",
    "vol": "#ffc247", "dd": OTHER_COLORS[0], "dd_fill": "rgba(215,126,232,0.18)",
    "marker_edge": PAGE,
}


def route_line(route: str, width: float = LINE_WIDTH) -> dict:
    """Line and marker styling for a route series: colour + dash + marker shape."""
    return {"line": {"color": ROUTE_COLORS[route], "width": width, "dash": ROUTE_DASHES[route]},
            "marker": {"color": ROUTE_COLORS[route], "symbol": ROUTE_SYMBOLS[route],
                       "size": MARKER_PX}}


def other_line(i: int, width: float = LINE_WIDTH) -> dict:
    return {"line": {"color": OTHER_COLORS[i], "width": width, "dash": OTHER_DASHES[i]},
            "marker": {"color": OTHER_COLORS[i], "symbol": OTHER_SYMBOLS[i], "size": MARKER_PX}}


_ACRONYMS = {"sonia": "SONIA", "sdrt": "SDRT", "im": "IM", "pb": "PB", "trs": "TRS",
             "rwa": "RWA", "sft": "SFT"}


def label(key: str) -> str:
    """'sonia_from_client' -> 'SONIA from client' (sentence case, acronyms kept)."""
    words = key.split("_")
    out = [_ACRONYMS.get(w, w) for w in words]
    if out and out[0] == words[0]:
        out[0] = out[0].capitalize()
    return " ".join(out)


def tag(clears: bool) -> str:
    """Text tag for clears / misses (no emoji; meaning carried by the word)."""
    return ":green[**[CLEARS]**]" if clears else ":violet[**[MISSES]**]"


def clearance_sentence(route: str, row, k: float) -> str:
    """One line from capital_comparison data: spread needed at the current k, and the k
    up to which the route clears at its quoted spread."""
    lever = "fee" if route == "Collateral upgrade" else "spread"
    if row["role"] is None or row["role"] != row["role"]:
        return f"{route}: RoLE undefined (no leverage exposure)."
    be = row["break_even_k"]
    clears_at = (f"at its quoted {lever} it clears for k up to {be * 1e4:.0f} bp" if be > 0
                 else f"at its quoted {lever} it clears at no k ≥ 0")
    return (f"{route} needs {row['required_spread_role'] * 1e4:.0f} bp to clear k = "
            f"{k * 1e4:.0f} bp (quoted {row['current_spread'] * 1e4:.0f} bp); {clears_at}.")


# --- Page furniture ---------------------------------------------------------------

FALLBACK_SONIA_NOTE = (" SONIA is also a placeholder: the live value and the cache are "
                       "unavailable.")


def sonia_label(ctx) -> str:
    """'SONIA 3.7329% as of 30 Sep 2026 (Bank of England IADB (IUDSOIA), live)'."""
    q = ctx.sonia_quote
    if ctx.sonia_overridden:
        return f"SONIA {ctx.fin.sonia * 100:.4f}% (manual override)"
    as_of = q.as_of.strftime("%d %b %Y") if q.as_of else "no date"
    return f"SONIA {q.rate * 100:.4f}% as of {as_of} ({q.source}, {q.status})"


def page_header(title: str, ctx) -> None:
    """Placeholder notice and trade context. The page name sits in the top banner (ui.theme)."""
    fallback = ctx.sonia_quote.status == "fallback" and not ctx.sonia_overridden
    st.warning(PLACEHOLDER_BANNER + (FALLBACK_SONIA_NOTE if fallback else ""))
    x = ctx.fin
    st.caption(
        f"GBP {x.notional / 1e6:,.1f}m {ctx.asset_label} · {ctx.tenor} ({x.tenor_days}d) · "
        f"{sonia_label(ctx)} · k {x.shadow_cost_k * 100:.2f}% · "
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
    "num2": "%.2f",
    "int": "%d",
}


def table(df: pd.DataFrame, formats: dict[str, str] | None = None, height: int | None = None):
    """Dense table. Numbers stay numeric so Streamlit right-aligns them.
    formats: column -> one of gbp, bp, pct, m, num, num2, int (values already in those units)."""
    df = df.copy()
    config = {}
    for col, kind in (formats or {}).items():
        if col not in df:
            continue
        if kind == "gbp":
            df[col] = df[col].astype(float).round(0)
        config[col] = st.column_config.NumberColumn(col, format=_FORMATS[kind])
    kwargs = {"hide_index": True, "width": "stretch", "column_config": config,
              "row_height": TABLE_ROW_PX}
    if height:
        kwargs["height"] = height
    st.dataframe(df, **kwargs)


# --- Charts -------------------------------------------------------------------------

MONO = ('ui-monospace, "Cascadia Mono", "Cascadia Code", Consolas, "SFMono-Regular", Menlo, '
        '"Liberation Mono", monospace')


def style(fig: go.Figure, title: str, x_title: str | None = None,
          y_title: str | None = None, height: int = 460, subtitle: str = SUBTITLE) -> go.Figure:
    """One look for every chart: terminal palette, monospace, the 'Illustrative' subtitle,
    legend below the plot so it never collides with the title block."""
    fig.update_layout(
        template="plotly_dark",
        title={"text": title.upper(), "subtitle": {"text": subtitle,
                                                  "font": {"color": MUTED,
                                                           "size": CHART_TEXT_PX}},
               "font": {"color": ACCENT, "size": CHART_TITLE_PX}, "x": 0, "xanchor": "left",
               "y": 0.97, "yanchor": "top"},
        paper_bgcolor=SURFACE,
        plot_bgcolor=SURFACE,
        font={"family": MONO, "color": INK_2, "size": CHART_TEXT_PX},
        height=height,
        margin={"l": 76, "r": 28, "t": 92, "b": 132},
        # Legend sits at the bottom of the figure container (in the margin), so it cannot
        # collide with the x-axis title however many rows it wraps to.
        legend={"orientation": "h", "yref": "container", "yanchor": "bottom", "y": 0.01,
                "xanchor": "left", "x": 0,
                "bgcolor": "rgba(0,0,0,0)", "font": {"color": INK_2, "size": CHART_TEXT_PX},
                "itemwidth": 40},
        hoverlabel={"bgcolor": PANEL_2, "bordercolor": ACCENT,
                    "font": {"color": INK, "family": MONO, "size": CHART_HOVER_PX}},
        bargap=0.35,
        barcornerradius=0,
    )
    axis = {"gridcolor": GRID, "zerolinecolor": AXIS, "linecolor": AXIS, "showline": True,
            "tickfont": {"color": MUTED, "size": CHART_TEXT_PX},
            "title": {"font": {"color": INK_2, "size": CHART_TEXT_PX}}}
    fig.update_xaxes(**axis, title_text=x_title)
    fig.update_yaxes(**axis, title_text=y_title)
    fig.update_annotations(font={"color": INK_2, "family": MONO, "size": CHART_TEXT_PX})
    # Reserve bottom space for the legend only when one is drawn (more than one listed trace)
    listed = [tr for tr in fig.data if tr.showlegend is not False]
    if len(listed) <= 1 or fig.layout.showlegend is False:
        fig.update_layout(margin={"b": 72})
    return fig


def show(fig: go.Figure) -> None:
    st.plotly_chart(fig, width="stretch", config={"displaylogo": False})
