"""Reusable time-series section: stats table, chart with optional SD bands and dated events,
source stamps. Used by Rates & Liquidity, Desk Brief and the bring-your-own-data page."""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from analytics import series_stats as S
from ui.common import MUTED, show, style, table

LINE_COLORS = ["#3ddc84", "#ffc247", "#6dd3ff", "#d77ee8"]  # validated palette roles
LINE_DASHES = ["solid", "dash", "dot", "dashdot"]
BAND_MODES = ["None", "Mean ±1 SD", "Mean ±1 and ±2 SD"]
NEWLINE = chr(10)


def stats_table(lines: list[tuple[str, pd.Series]], frequency: str) -> pd.DataFrame:
    """One row per series, values in the chart's unit. Change statistics use the series' own
    frequency (the header names it: day, week or month)."""
    noun = S.PERIOD_NOUN[frequency]
    rows = []
    for label, s in lines:
        st_ = S.series_stats(s, frequency)
        rows.append({
            "Series": label, "As of": st_["as_of"].isoformat(), "Obs": st_["n"],
            "Last": st_["last"], "Min": st_["min"], "Max": st_["max"], "Mean": st_["mean"],
            "SD": st_["sd"], f"Chg ({noun})": st_["change"], f"Chg z ({noun})": st_["change_z"],
            "Pctile": st_["level_pct"],
        })
    return pd.DataFrame(rows)


def show_stats(lines, frequency, unit):
    df = stats_table(lines, frequency)
    noun = S.PERIOD_NOUN[frequency]
    starts = ", ".join(f"{lbl} from {s.index[0]:%d %b %Y}" for lbl, s in lines)
    st.caption(f"Statistics over the range shown, {frequency} data, values in {unit}: {starts}. "
               f"Chg = latest {noun}-on-{noun} change; Chg z = its z-score; Pctile = percentile "
               "of the latest level.")
    table(df, {"Obs": "int", "Last": "num2", "Min": "num2", "Max": "num2", "Mean": "num2",
               "SD": "num2", f"Chg ({noun})": "num2", f"Chg z ({noun})": "num2", "Pctile": "pct"})
    return df


def series_figure(title: str, unit: str, lines: list[tuple[str, pd.Series]], band_mode: str,
                  events: list[dict], height: int = 460, subtitle: str | None = None) -> go.Figure:
    fig = go.Figure()
    for i, (label, s) in enumerate(lines):
        color = LINE_COLORS[i % 4]
        fig.add_scatter(x=s.index, y=s.values, name=label, mode="lines",
                        line={"color": color, "width": 2.5, "dash": LINE_DASHES[i % 4]},
                        hovertemplate="%{x|%d %b %Y}<br>%{y:,.2f} " + unit + "<extra>" + label
                        + "</extra>")
        if band_mode != "None" and len(s) > 2:
            b = S.bands(s)
            levels = [("mean", "mean")] + [("+1sd", "+1 SD"), ("-1sd", "-1 SD")]
            if band_mode == BAND_MODES[2]:
                levels += [("+2sd", "+2 SD"), ("-2sd", "-2 SD")]
            for k, name in levels:
                fig.add_scatter(x=[s.index[0], s.index[-1]], y=[b[k], b[k]], mode="lines",
                                name=f"{label} {name}", showlegend=False,
                                line={"color": color, "width": 1.2,
                                      "dash": "dot" if "1" in k else "dash" if "2" in k else "solid"},
                                opacity=0.7,
                                hovertemplate=f"{label} {name}: " + "%{y:,.2f}<extra></extra>")
    for n, e in enumerate(events, start=1):
        fig.add_vline(x=pd.Timestamp(e["day"]).value / 1e6, line={"color": MUTED, "width": 1.5,
                                                                 "dash": "dot"},
                      annotation_text=str(n),
                      # alternate sides so labels of events a few days apart do not overlap
                      annotation_position="top left" if n % 2 else "top right")
    if subtitle:
        style(fig, title, y_title=unit, height=height, subtitle=subtitle)
    else:
        style(fig, title, y_title=unit, height=height)
    return fig


def events_in_range(events: list[dict], start, end) -> list[dict]:
    lo, hi = pd.Timestamp(start), pd.Timestamp(end)
    return [e for e in events if lo <= pd.Timestamp(e["day"]) <= hi]


def show_events(events: list[dict]):
    if not events:
        st.caption("No verified events in this date range.")
        return
    st.markdown("\n".join(f"{n}. **{e['day']}** ({e['region']}): {e['label']}. "
                          f"[Source]({e['url']})" for n, e in enumerate(events, start=1)))


def section(title: str, unit: str, frequency: str, lines: list[tuple[str, pd.Series]],
            stamps: list[str], band_mode: str, events: list[dict], note: str | None = None,
            height: int = 460, sources: str | None = None, as_of: str | None = None):
    """Stats table, chart, events list and stamps for one set of same-unit, same-frequency lines.
    sources/as_of feed the chart subtitle; full stamps sit in an expander under the chart."""
    lines = [(lbl, s.dropna()) for lbl, s in lines if len(s.dropna()) > 2]
    if not lines:
        st.error(f"{title}: no data in the selected range.")
        return
    start = min(s.index[0] for _, s in lines)
    end = max(s.index[-1] for _, s in lines)
    ev = events_in_range(events, start, end)
    show_stats(lines, frequency, unit)
    subtitle = None
    if sources:
        subtitle = f"{frequency.capitalize()} · {sources}" + (f" · as of {as_of}" if as_of else "")
    show(series_figure(title, unit, lines, band_mode, ev, height, subtitle))
    st.caption(f"Sources: {sources or '; '.join(stamps)}" + (f" · as of {as_of}" if as_of else ""))
    if note:
        st.caption(note)
    with st.expander("Source details (series, frequency, as of, live or cached, fetch time)"):
        st.markdown(NEWLINE.join(f"- {s_}" for s_ in stamps))
    if events is not None and ev:
        with st.expander(f"Dated events on this chart ({len(ev)}), each with its official source"):
            show_events(ev)
