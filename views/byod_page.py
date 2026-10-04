"""Bring your own data: a user-supplied CSV through the same stats strip, bands, z-scores and Desk
Brief rules as the official series, plus a spread builder (A minus B).

Everything uploaded or pasted stays in this browser session's memory (st.session_state). Nothing is
written to disk, cached or committed. Display analytics only: none of this feeds the engine."""

import pandas as pd
import streamlit as st

import assumptions as A
from analytics import desk_brief as B
from analytics import user_data as U
from ui.common import TABLE_ROW_PX, explain, table
from ui.series_chart import BAND_MODES, NEWLINE, section

STORE = "byod_store"
RANGES = {"1Y": 12, "5Y": 60, "10Y": 120, "Max": None}

st.warning(f"**{U.USER_LABEL} DATA.** Files and pasted text are held in this session's memory "
           "only: never written to disk, cached or committed, and gone when the session ends. "
           "**Do not upload confidential or client data to a hosted copy of this app**; run it "
           "locally for anything sensitive (see the README).")
st.caption("The statistics and sentences below describe the data you supply against its own "
           "history. They are not forecasts and do not feed the financing engine.")

store: dict[str, U.UserSeries] = st.session_state.setdefault(STORE, {})

# --- 1. Load and map ---------------------------------------------------------------------------
st.subheader("1. Load a CSV and map its columns")
how = st.radio("Input", ["Upload a CSV file", "Paste CSV text"], horizontal=True, key="byod_how")
content, origin = None, None
if how == "Upload a CSV file":
    up = st.file_uploader("CSV file (one date column, one or more value columns)", type=["csv", "txt"],
                          key="byod_file")
    if up is not None:
        content, origin = up.getvalue(), up.name
else:
    pasted = st.text_area("Paste CSV text (first row = column names)", height=160, key="byod_paste",
                          placeholder="date,value" + NEWLINE + "2024-01-02,4.21" + NEWLINE + "...")
    if pasted.strip():
        content, origin = pasted.encode("utf-8"), "pasted text"

if content is not None:
    try:
        df = U.read_csv(content)
    except U.UserDataError as e:
        st.error(str(e))
        df = None
    if df is not None:
        st.caption(f"{origin}: {len(df):,} rows, {df.shape[1]} columns. First rows as read "
                   "(all text, before parsing):")
        table(df.head(5))
        cols = list(df.columns)
        c1, c2, c3 = st.columns(3)
        date_col = c1.selectbox("Date column", cols, index=cols.index(U.guess_date_column(df)),
                                key="byod_date_col")
        fmt = c2.selectbox("Date format", list(U.DATE_FORMATS), key="byod_fmt")
        freq_choice = c3.selectbox("Frequency", ["Auto (from date spacing)", "daily", "weekly",
                                                 "monthly"], key="byod_freq")
        c4, c5 = st.columns([2, 1])
        value_cols = c4.multiselect("Value column(s)", [c for c in cols if c != date_col],
                                    default=[c for c in cols if c != date_col][:1],
                                    key="byod_values")
        unit = c5.text_input("Unit of the values (e.g. %, bp, GBP m)", value="", key="byod_unit")
        if st.button("Add to session", key="byod_add", type="primary"):
            for vc in value_cols:
                try:
                    s, report = U.build_series(df, date_col, vc, fmt)
                except U.UserDataError as e:
                    st.error(f"{vc}: {e}")
                    continue
                freq = U.infer_frequency(s.index) if freq_choice.startswith("Auto") else freq_choice
                if freq is None:
                    st.error(f"{vc}: the dates are not evenly daily, weekly or monthly (median gap "
                             "outside the ranges in assumptions.py). Choose the frequency, or "
                             "supply a regular series; nothing is resampled.")
                    continue
                label = vc
                n = 2
                while label in store:
                    label, n = f"{vc} ({n})", n + 1
                store[label] = U.UserSeries(label, unit.strip() or "units", freq, s, origin)
                st.success(f"Added {label} ({freq}, {s.index[0]:%d %b %Y} to "
                           f"{s.index[-1]:%d %b %Y}). {report.sentence()}")

if not store:
    st.info("No user series in this session yet. Upload or paste a CSV above.")
    st.stop()

# --- 2. Session series and spread builder ------------------------------------------------------
st.subheader("2. Series in this session")
table(pd.DataFrame([{"Series": u.label, "Unit": u.unit, "Frequency": u.frequency,
                     "From": f"{u.data.index[0]:%d %b %Y}", "To": f"{u.data.index[-1]:%d %b %Y}",
                     "Obs": len(u.data), "Origin": u.origin} for u in store.values()]),
      {"Obs": "int"})
k1, k2 = st.columns([3, 1])
drop = k1.multiselect("Remove series", list(store), key="byod_drop")
if k2.button("Remove selected", key="byod_remove") and drop:
    for lbl in drop:
        store.pop(lbl, None)
    st.rerun()

with st.expander("Spread builder (A minus B)", expanded=False):
    labels = list(store)
    s1, s2, s3, s4 = st.columns([3, 3, 2, 2])
    a = s1.selectbox("A", labels, key="byod_sp_a")
    b = s2.selectbox("B", labels, index=min(1, len(labels) - 1), key="byod_sp_b")
    scale_label = s3.radio("Scale", ["x1 (same unit)", "x100 (% to bp)"], key="byod_sp_scale")
    x100 = scale_label.startswith("x100")
    # keyed per scale so the suggested unit follows the scale choice
    sp_unit = s4.text_input("Result unit", value="bp" if x100 else store[a].unit,
                            key=f"byod_sp_unit_{'x100' if x100 else 'x1'}")
    st.caption("Computed only on dates where both series have a value; nothing is filled or "
               "resampled. Both must have the same frequency.")
    if st.button("Add spread", key="byod_sp_add"):
        if a == b:
            st.error("Pick two different series.")
        else:
            try:
                u = U.spread(store[a], store[b], 100.0 if x100 else 1.0,
                             sp_unit.strip() or "units")
                store[u.label] = u
                st.rerun()
            except U.UserDataError as e:
                st.error(str(e))

# --- 3. Chart with stats strip and bands --------------------------------------------------------
st.subheader("3. Stats strip, chart and bands")
c1, c2 = st.columns([3, 3])
rng = c1.radio("Range (back from each series' last date)", list(RANGES), index=3,
               horizontal=True, key="byod_range")
band_mode = c2.selectbox("Bands (over the selected range)", BAND_MODES, index=0, key="byod_bands")
chosen = st.multiselect("Series to chart", list(store), default=list(store)[:1], key="byod_chart")
groups: dict[tuple[str, str], list[U.UserSeries]] = {}
for lbl in chosen:
    u = store[lbl]
    groups.setdefault((u.unit, u.frequency), []).append(u)
if len(groups) > 1:
    st.caption("Series with different units or frequencies are charted separately.")
for (unit, freq), members in groups.items():
    if len(members) > A.BYOD_MAX_LINES:
        st.warning(f"Only the first {A.BYOD_MAX_LINES} {unit} / {freq} series are charted.")
        members = members[:A.BYOD_MAX_LINES]
    lines = []
    for u in members:
        start = U.range_start(u.data, RANGES[rng])
        lines.append((u.label, u.data if start is None else u.data[u.data.index >= start]))
    as_of = max(s.index[-1] for _, s in lines)
    names = ", ".join(u.label for u in members)
    section(f"{U.USER_LABEL}: {names}, {unit}, {freq}", unit, freq, lines,
            [f"{u.label}: {U.USER_LABEL}, from {u.origin}, {u.frequency}, unit {u.unit}, "
             f"held in session memory only" for u in members],
            band_mode, [], sources=f"{U.USER_LABEL} ({', '.join(dict.fromkeys(u.origin for u in members))})",
            as_of=f"{as_of:%d %b %Y}")

# --- 4. Desk Brief rules ---------------------------------------------------------------------
st.subheader("4. Desk Brief rules on your series")
st.info("**RULES-BASED, NOT A FORECAST.** The same fixed rules as the Desk Brief page: each "
        "sentence quotes the numbers it was built from and describes the data against its own "
        "history only.")
rows, skipped = U.brief_rows(list(store.values()), RANGES[rng])
if rows.empty:
    st.error("No user series has 3 or more observations in the selected range.")
else:
    st.markdown(f"**Stretched: beyond {A.BRIEF_STRETCH_Z:g} SD**")
    hot = rows[(rows["Level status"] == "stretched") | (rows["Move status"] == "stretched")]
    st.markdown(NEWLINE.join(f"- {B.row_sentence(r)}" for r in hot.to_dict("records")) if len(hot)
                else f"No user series has a level or latest change beyond {A.BRIEF_STRETCH_Z:g} SD "
                     "of its window.")
    st.markdown(f"**Largest movers (top {A.BRIEF_TOP_MOVERS} by |change z|)**")
    st.markdown(NEWLINE.join(f"{i}. {B.mover_sentence(r)}" for i, r in
                             enumerate(B.movers(rows).to_dict("records"), start=1)))
    st.markdown("**Every series**")
    st.markdown(NEWLINE.join(f"- {B.row_sentence(r)}" for r in rows.to_dict("records")))
    compact = pd.DataFrame([{
        "Series": r["Series"], "Freq": r["Frequency"][0].upper(), "As of": f"{r['As of']}",
        "Last": B._num(r["Last"], r["Unit"]), "Chg": B._chg(r["Change"], r["Change unit"]),
        "Chg z": f"{r['Change z']:+.2f}", "Lvl z": f"{r['Level z']:+.2f}",
        "Pctile": f"{r['Percentile']:.0f}", "Status": (
            "STRETCHED" if "stretched" in (r["Level status"], r["Move status"]) else "normal")}
        for r in rows.to_dict("records")])
    table(compact, height=(len(compact) + 1) * TABLE_ROW_PX + 3)
    export = rows.drop(columns="key").astype({"As of": str, "From": str})
    st.download_button("Export these rows to CSV (generated in memory)",
                       export.to_csv(index=False).encode("utf-8"),
                       file_name="user_series_brief.csv", mime="text/csv", key="byod_csv")
if skipped:
    st.caption("Skipped: " + " ".join(skipped))

if st.button("Clear all user data from this session", key="byod_clear"):
    st.session_state[STORE] = {}
    st.rerun()

explain("the user-data rules", f"""
- **Parsing:** dates use the format you pick; rows whose date or value does not parse are dropped
  and counted, never filled. Thousands separators and a trailing % are stripped. For repeated
  dates the last row is kept.
- **Frequency:** inferred from the median gap between dates (daily {A.BYOD_FREQ_GAP_DAYS['daily']},
  weekly {A.BYOD_FREQ_GAP_DAYS['weekly']}, monthly {A.BYOD_FREQ_GAP_DAYS['monthly']} calendar
  days), or chosen by you. Changes are observation-to-observation at that frequency.
- **Statistics:** as on Rates & Liquidity: sample SD, change z-score, percentile of the level,
  mean ±1/±2 SD bands over the range shown.
- **Brief rules:** stretched = |z| > {A.BRIEF_STRETCH_Z:g}; movers ranked by |change z|.
- **Spreads:** (A − B) × scale on common dates only.
- **Storage:** session memory only (st.session_state). Nothing is written to disk.
""")
