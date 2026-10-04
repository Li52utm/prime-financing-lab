"""Smoke tests for the Streamlit app (Prime Financing Lab) using Streamlit's AppTest."""

import html
import json
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from engine.capital import NOT_MODELLED_BANNER
from ui.assumptions_reader import read_assumptions
from ui.common import PLACEHOLDER_BANNER, SUBTITLE
from ui.theme import THEME_MARKER

APP = Path(__file__).resolve().parent.parent / "app.py"

PAGES = {
    "Summary": "views/summary_page.py",
    "Client view": "views/client_page.py",
    "Desk view": "views/desk_page.py",
    "Capital": "views/capital_page.py",
    "Stress lab": "views/stress_page.py",
    "Assumptions": "views/assumptions_page.py",
    "Markets": "views/markets_page.py",
    "Rates & Liquidity": "views/rates_page.py",
    "Desk Brief": "views/brief_page.py",
    "Glossary": "views/glossary_page.py",
    "Concept Trainer": "views/trainer_page.py",
}
PAGES_WITH_HEADLINES = ["Summary", "Client view", "Desk view", "Capital", "Stress lab"]


def open_page(page: str, widgets: dict | None = None) -> AppTest:
    """Run the entry point (sidebar ticket), set any ticket widgets, re-run so the ticket is
    stored in session state, then switch to the page. After a switch AppTest renders the page
    script with the stored ticket; the sidebar is not in its element tree."""
    at = AppTest.from_file(APP, default_timeout=90)
    at.run()
    for (kind, key), value in (widgets or {}).items():
        getattr(at, kind)(key=key).set_value(value)
    if widgets:
        at.run()
    at.switch_page(PAGES[page])
    at.run()
    return at


def chart_specs(at: AppTest) -> list[str]:
    return [el.proto.spec for el in at.get("plotly_chart")]


NO_TICKET_PAGES = {"Markets", "Rates & Liquidity", "Desk Brief", "Glossary", "Concept Trainer"}  # no trade-context banner


@pytest.mark.parametrize("page", [p for p in PAGES if p not in NO_TICKET_PAGES])
def test_page_runs_with_banner(page):
    at = open_page(page)
    assert not at.exception, [e.value for e in at.exception]
    assert any(PLACEHOLDER_BANNER in w.value for w in at.warning)


@pytest.mark.parametrize("page", list(PAGES))
def test_banner_and_theme_on_every_page(page):
    """The entry script injects the theme CSS and the top banner on every page."""
    at = open_page(page)
    md = [m.value for m in at.markdown]
    assert sum(THEME_MARKER in v for v in md) == 1  # CSS injected exactly once
    banners = [v for v in md if 'data-testid="pfl-banner"' in v]
    assert len(banners) == 1
    b = banners[0]
    assert "PRIME FINANCING LAB" in b and f"/ {html.escape(page.upper())}" in b
    assert "SONIA 4.0000%" in b and "FALLBACK" in b  # conftest: offline -> placeholder
    assert not at.title  # page headers replaced by the banner
    for text in md + [w.value for w in at.warning] + [i.value for i in at.info]:
        assert "✅" not in text and "❌" not in text  # no emojis


@pytest.mark.parametrize("page", list(PAGES))
def test_every_chart_has_illustrative_subtitle(page):
    for spec in chart_specs(open_page(page)):
        assert json.loads(spec)["layout"]["title"]["subtitle"]["text"] == SUBTITLE


@pytest.mark.parametrize("page", PAGES_WITH_HEADLINES)
def test_headlines_have_explainers(page):
    at = open_page(page)
    labels = [e.label for e in at.expander]
    assert any(l.startswith("How is this calculated") for l in labels)
    # every metric sits in a page that explains it; at least as many explainers as metric groups
    assert len([l for l in labels if l.startswith("How is this calculated")]) >= 3


def test_capital_opens_with_not_modelled_banner():
    at = open_page("Capital")
    assert at.error[0].value == NOT_MODELLED_BANNER
    assert "CVA" in at.error[0].value


def test_summary_names_no_winner_when_none_clears():
    at = open_page("Summary")  # default k 0.5%: no route clears
    assert any("No route clears" in i.value for i in at.info)
    assert not at.success


def test_summary_names_winner_when_k_zero():
    at = open_page("Summary", {("slider", "k_pct"): 0.0})
    assert not at.exception
    assert any("PB" in s.value for s in at.success)


def test_desk_shows_three_netting_cases():
    at = open_page("Desk view")
    frames = [d.value for d in at.dataframe if "Case" in d.value.columns]
    assert len(frames) == 1
    assert list(frames[0]["Case"]) == [
        "Standalone", "Netted: short on a different name", "Netted: short on the same name"]
    # a = 0.32 x 10m x sqrt(91/365) = 1,597,806.72 (standalone)
    # same name: dealer -10m + 5m = -5m in one entity -> a / 2 = 798,903.36
    # different name: sqrt((0.5(-a) + 0.5(a/2))^2 + 0.75 a^2 + 0.75 (a/2)^2)
    #   = sqrt(0.0625 + 0.75 + 0.1875) a = a (no change at this size)
    addons = list(frames[0]["Equity add-on (GBP)"])
    assert addons == pytest.approx([1_597_807, 1_597_807, 798_903], abs=1)


@pytest.mark.parametrize("page", list(PAGES))
def test_pages_run_with_non_default_ticket(page):
    at = open_page(page, {
        ("toggle", "netting"): True,
        ("toggle", "margined"): True,
        ("toggle", "sdrt"): False,
        ("selectbox", "gilt_source"): "borrowed",
        ("selectbox", "asset_class"): "small_cap",
        ("radio", "tenor"): "1M",
        ("slider", "im_spread_bp"): 400.0,
    })
    assert not at.exception, [e.value for e in at.exception]


@pytest.mark.parametrize("page", ["Capital", "Stress lab", "Summary"])
def test_pages_run_with_advanced_settings(page):
    at = open_page(page, {
        ("selectbox", "regime"): "uk_crr_current",
        ("toggle", "street_leg"): False,
        ("selectbox", "surplus"): "counted",
        ("toggle", "resets"): True,
        ("toggle", "units"): False,
        ("selectbox", "gilt_source"): "inventory",
    })
    assert not at.exception, [e.value for e in at.exception]


def test_stress_lab_views_run():
    at = open_page("Stress lab")
    for view in ("full_tenor", "turn_only", "client_stays_repriced"):
        at.radio(key="view").set_value(view).run()
        assert not at.exception, [e.value for e in at.exception]
        assert at.radio(key="view").value == view
    at.selectbox(key="preset").set_value("collateral_shortage").run()
    at.slider(key="pb_per_month").set_value(50).run()
    assert not at.exception, [e.value for e in at.exception]


def test_assumptions_reader_tags():
    d = read_assumptions().set_index("Name")
    assert d.loc["SONIA", "Status"] == "UNVERIFIED"
    assert d.loc["HAIRCUT_REGIMES", "Status"] == "VERIFIED"
    assert d.loc["SACCR_EQUITY_RHO", "Status"] == "VERIFIED"
    assert d.loc["STRESS_PRESETS", "Type"] == "Hypothetical"
    assert d.loc["SDRT_RATE", "Status"] == "UNVERIFIED"
    assert (d["Source / comment"].str.strip() != "").all()  # every default has a comment


# --- Summary: Spread vs k heatmaps ------------------------------------------------------------

def heatmap_spec(at: AppTest) -> dict:
    specs = [json.loads(s) for s in chart_specs(at)]
    hm = [s for s in specs if any(t["type"] == "heatmap" for t in s["data"])]
    assert len(hm) == 1
    return hm[0]


def test_heatmaps_three_panels_shared_scale():
    at = open_page("Summary")
    spec = heatmap_spec(at)
    types = [t["type"] for t in spec["data"]]
    assert types.count("heatmap") == 3
    assert all(t.get("coloraxis") == "coloraxis" for t in spec["data"] if t["type"] == "heatmap")
    ca = spec["layout"]["coloraxis"]
    assert ca["cmid"] == 0 and ca["cmin"] == -ca["cmax"]  # one symmetric scale centred on 0
    contours = [t for t in spec["data"] if t["type"] == "contour"]
    assert len(contours) == 3
    assert all(t["contours"]["start"] == 0 and t["line"]["width"] >= 3 for t in contours)
    # one current-position marker per route at quoted spread and current k (default 50 bp)
    markers = [t for t in spec["data"] if t["type"] == "scatter"]
    assert [m["x"][0] for m in markers] == pytest.approx([50.0, 40.0, 30.0])
    assert all(m["y"][0] == pytest.approx(50.0) for m in markers)
    # default axes 0-150 bp spread, 0-100 bp k
    assert spec["layout"]["xaxis"]["range"] == [0, 150]
    assert spec["layout"]["yaxis"]["range"] == [0, 100]
    assert spec["layout"]["title"]["subtitle"]["text"] == SUBTITLE
    hover = [t["hovertemplate"] for t in spec["data"] if t["type"] == "heatmap"][0]
    for word in ("spread", "k ", "RoLE", "RoLE − k", "customdata[1]"):
        assert word in hover


def test_heatmap_caption_and_explainer():
    at = open_page("Summary")
    caption = " ".join(c.value for c in at.caption)
    assert "PB needs 89 bp to clear k = 50 bp (quoted 50 bp); at its quoted spread it clears " \
           "for k up to 15 bp." in caption
    assert "TRS needs 93 bp" in caption and "Collateral upgrade needs 76 bp" in caption
    assert any(e.label == "How is this calculated: spread vs k heatmaps" for e in at.expander)


def test_heatmap_axis_ranges_adjustable():
    at = open_page("Summary")
    at.number_input(key="hm_s_max").set_value(300.0)
    at.number_input(key="hm_k_max").set_value(200.0)
    at.run()
    assert not at.exception
    spec = heatmap_spec(at)
    assert spec["layout"]["xaxis"]["range"] == [0, 300]
    assert spec["layout"]["yaxis"]["range"] == [0, 200]
    # invalid range falls back to defaults with a warning
    at.number_input(key="hm_s_min").set_value(400.0).run()
    assert not at.exception
    assert any("showing the defaults" in w.value for w in at.warning)
    assert heatmap_spec(at)["layout"]["xaxis"]["range"] == [0, 150]


def test_heatmap_runs_with_zero_leverage_upgrade():
    at = open_page("Summary", {("selectbox", "gilt_source"): "inventory"})
    assert not at.exception, [e.value for e in at.exception]
    assert "Collateral upgrade: RoLE undefined" in " ".join(c.value for c in at.caption)
    assert [t["type"] for t in heatmap_spec(at)["data"]].count("contour") == 2


def test_clearance_sentence_never_clears():
    from ui.common import clearance_sentence
    row = {"role": -0.0006, "break_even_k": -0.0006, "required_spread_role": 0.0085,
           "current_spread": 0.003}
    s = clearance_sentence("Collateral upgrade", row, 0.005)
    assert s == ("Collateral upgrade needs 85 bp to clear k = 50 bp (quoted 30 bp); at its quoted "
                 "fee it clears at no k ≥ 0.")


# --- Live SONIA in the sidebar (network mocked by conftest / per test) -----------------------

from datetime import date, timedelta  # noqa: E402

from data import sonia as sonia_mod  # noqa: E402
from ui.common import FALLBACK_SONIA_NOTE  # noqa: E402


def sidebar_text(at: AppTest) -> str:
    return " ".join(m.value for m in at.sidebar.markdown)


def sidebar_warnings(at: AppTest) -> list[str]:
    return [w.value for w in at.sidebar.warning]


def header_caption(at: AppTest) -> str:
    return " ".join(c.value for c in at.caption)


def test_sidebar_sonia_live(monkeypatch):
    as_of = date.today()
    monkeypatch.setattr(sonia_mod, "fetch_latest_sonia",
                        lambda **kw: (0.037329, as_of, sonia_mod.BOE_SOURCE))
    at = AppTest.from_file(APP, default_timeout=90)
    at.run()
    assert not at.exception
    text = sidebar_text(at)
    assert "**3.7329%**" in text
    assert f"As of: {as_of.strftime('%d %b %Y')}" in text
    assert "Source: Bank of England IADB (IUDSOIA)" in text
    assert "Status: **live**" in text
    assert not sidebar_warnings(at)  # fresh live value: no warning
    assert f"SONIA 3.7329% as of {as_of.strftime('%d %b %Y')} (Bank of England IADB (IUDSOIA), " \
           "live)" in header_caption(at)
    assert not any(FALLBACK_SONIA_NOTE in w.value for w in at.warning)
    assert sonia_mod.read_cache(sonia_mod.CACHE_PATH)[0] == pytest.approx(0.037329)


def test_sidebar_sonia_live_but_stale_warns(monkeypatch):
    as_of = date.today() - timedelta(days=21)
    monkeypatch.setattr(sonia_mod, "fetch_latest_sonia",
                        lambda **kw: (0.0373, as_of, sonia_mod.BOE_SOURCE))
    at = AppTest.from_file(APP, default_timeout=90)
    at.run()
    assert "Status: **live**" in sidebar_text(at)
    assert any("more than 5 business days old" in w for w in sidebar_warnings(at))


def test_sidebar_sonia_cached():
    sonia_mod.write_cache(0.0372, date(2026, 9, 21), sonia_mod.FRED_SOURCE, sonia_mod.CACHE_PATH)
    at = AppTest.from_file(APP, default_timeout=90)
    at.run()  # conftest: live fetch fails
    assert not at.exception
    text = sidebar_text(at)
    assert "**3.7200%**" in text and "As of: 21 Sep 2026" in text
    assert "Source: FRED (IUDSOIA)" in text and "Status: **cached**" in text
    assert any("Live SONIA fetch failed" in w for w in sidebar_warnings(at))
    assert "(FRED (IUDSOIA), cached)" in header_caption(at)


def test_sidebar_sonia_fallback():
    at = AppTest.from_file(APP, default_timeout=90)
    at.run()  # no live, no cache
    assert not at.exception
    text = sidebar_text(at)
    assert "**4.0000%**" in text and "As of: n/a" in text
    assert "Source: assumptions.py placeholder" in text and "Status: **fallback**" in text
    assert any("placeholder in assumptions.py" in w for w in sidebar_warnings(at))
    assert any(FALLBACK_SONIA_NOTE in w.value for w in at.warning)  # banner names SONIA too


def test_sidebar_sonia_manual_override(monkeypatch):
    monkeypatch.setattr(sonia_mod, "fetch_latest_sonia",
                        lambda **kw: (0.037329, date.today(), sonia_mod.BOE_SOURCE))
    at = AppTest.from_file(APP, default_timeout=90)
    at.run()
    at.toggle(key="sonia_override").set_value(True).run()
    at.slider(key="sonia_override_pct").set_value(3.0).run()
    assert not at.exception
    assert "SONIA 3.0000% (manual override)" in header_caption(at)
    assert at.slider(key="im_spread_bp").max == 300.0  # IM slider follows the SONIA in use
    assert at.session_state["ctx"].fin.sonia == pytest.approx(0.03)


# --- Markets page: live, cached and error modes (network mocked) ---------------------------

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from data import markets as markets_mod  # noqa: E402


def synthetic(key: str, n: int = 600) -> pd.DataFrame:
    """Deterministic daily series in the shape fetch_live returns."""
    idx = pd.bdate_range(end="2026-10-02", periods=n)
    rng = np.random.default_rng(11)
    if markets_mod.SERIES[key].is_yield:
        return pd.DataFrame({"close": 3.5 + np.cumsum(rng.normal(0, 0.03, n))}, index=idx)
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, n)))
    df = pd.DataFrame({"close": close}, index=idx)
    if markets_mod.SERIES[key].has_ohlc:
        df = df.assign(open=close * 0.999, high=close * 1.01, low=close * 0.99,
                       volume=1e6)[["open", "high", "low", "close", "volume"]]
    return df


def markets_text(at: AppTest) -> str:
    return " ".join([c.value for c in at.caption] + [m.value for m in at.markdown]
                    + [w.value for w in at.warning] + [e.value for e in at.error])


def test_markets_live_mode(monkeypatch):
    monkeypatch.setattr(markets_mod, "fetch_live", synthetic)
    at = open_page("Markets")
    assert not at.exception, [e.value for e in at.exception]
    labels = [m.label for m in at.metric]
    assert labels == ["Last", "Daily change", "1Y return", "1Y volatility", "Max drawdown",
                      "Band position"]
    assert any(c.value.startswith("Last in index points. Max drawdown over the selected range (1Y)")
               for c in at.caption)
    stamps = [c.value for c in at.caption if c.value.startswith("Source:")]
    assert len(stamps) == 3 and all("status live" in s and "as of 02 Oct 2026" in s for s in stamps)
    spec = json.loads(chart_specs(at)[0])
    types = [tr["type"] for tr in spec["data"]]
    assert "candlestick" in types and "bar" in types  # OHLC series with volume
    names = [tr.get("name") for tr in spec["data"]]
    for n in ("MA 50", "MA 200", "Close above upper band", "Close below lower band"):
        assert n in names
    assert spec["layout"]["title"]["subtitle"]["text"] == SUBTITLE
    assert "Bands describe range, not direction." in markets_text(at)
    assert not at.error
    # the only warning is the sidebar's offline SONIA notice, not a Markets cache warning
    assert not any("Live fetch failed" in w.value for w in at.warning)


def test_markets_live_yield_series_and_controls(monkeypatch):
    monkeypatch.setattr(markets_mod, "fetch_live", synthetic)
    at = open_page("Markets")
    at.selectbox(key="mkt_asset").set_value("uk10y")
    at.radio(key="mkt_range").set_value("Max")
    at.number_input(key="mkt_bb_window").set_value(30)
    at.number_input(key="mkt_bb_width").set_value(2.5)
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    assert [m.label for m in at.metric][2] == "1Y change"  # yields: change in bp, not a return
    spec = json.loads(chart_specs(at)[0])
    types = [tr["type"] for tr in spec["data"]]
    assert "candlestick" not in types and "bar" not in types  # line, no volume
    assert any(tr.get("name") == "Bollinger 30, ±2.5σ" for tr in spec["data"])


def test_markets_cached_mode():
    markets_mod.write_cache("ftse100", synthetic("ftse100"), "2026-10-01T08:30:00")
    at = open_page("Markets")  # conftest: live fetch fails
    assert not at.exception, [e.value for e in at.exception]
    assert any("Live fetch failed. Showing the cached copy fetched 2026-10-01 08:30" in w.value
               for w in at.warning)
    stamps = [c.value for c in at.caption if c.value.startswith("Source:")]
    assert stamps and all("status cached" in s for s in stamps)


def test_markets_error_mode():
    at = open_page("Markets")  # no live, no cache
    assert not at.exception, [e.value for e in at.exception]
    assert len(at.error) == 1
    assert "No data for FTSE 100" in at.error[0].value and "no cached copy" in at.error[0].value
    assert not at.metric and not chart_specs(at)


# --- Rates & Liquidity: live, cached and error modes (network mocked) ---------------------

from data import macro as macro_mod  # noqa: E402


def synthetic_macro(key: str) -> pd.Series:
    spec = macro_mod.SERIES[key]
    freq = {"daily": "B", "weekly": "W-WED", "monthly": "MS"}[spec.frequency]
    n = {"daily": 900, "weekly": 260, "monthly": 120}[spec.frequency]
    idx = pd.date_range(end="2026-10-01", periods=n, freq=freq)
    rng = np.random.default_rng(abs(hash(key)) % 2**32)
    if spec.unit == "%":
        return pd.Series(3.0 + np.cumsum(rng.normal(0, 0.02, n)), index=idx)
    return pd.Series(500_000 + np.cumsum(rng.normal(0, 2_000, n)), index=idx)


def rates_open(monkeypatch=None, mode="live"):
    if mode == "live":
        monkeypatch.setattr(macro_mod, "fetch_live", synthetic_macro)
    elif mode == "cached":
        for key in macro_mod.SERIES:
            if key not in ("brent", "gbpusd"):
                macro_mod.write_cache(key, synthetic_macro(key), "2026-10-02T07:00:00")
    return open_page("Rates & Liquidity")


def test_rates_live_mode(monkeypatch):
    at = rates_open(monkeypatch, "live")
    assert not at.exception, [e.value for e in at.exception]
    assert not at.error
    specs = [json.loads(s) for s in chart_specs(at)]
    titles = [sp["layout"]["title"]["text"] for sp in specs]
    assert len(specs) == 6
    for needle in ("2S10S SLOPE", "SPREAD TO GERMANY, BP, MONTHLY", "EXCESS LIQUIDITY",
                   "DF + CA", "WEEKLY", "SONIA MINUS BANK RATE"):
        assert any(needle in t for t in titles), needle
    for sp in specs:  # every chart states frequency, sources and as-of in its subtitle
        sub = sp["layout"]["title"]["subtitle"]["text"]
        assert sub.split(" · ")[0] in ("Daily", "Weekly", "Monthly") and "as of" in sub
    captions = " ".join(c.value for c in at.caption)
    assert "Chg = latest month-on-month change" in captions  # no daily stats on monthly data
    assert "Chg = latest week-on-week change" in captions
    assert "UK, France and Italy 2s10s are not shown" in captions
    headers = [list(d.value.columns) for d in at.dataframe]
    assert any("Chg z (month)" in h for h in headers) and any("Chg z (week)" in h for h in headers)


def test_rates_bands_and_events_toggle(monkeypatch):
    at = rates_open(monkeypatch, "live")
    at.selectbox(key="rl_bands").set_value("Mean ±1 and ±2 SD").run()
    assert not at.exception
    spec = json.loads(chart_specs(at)[0])
    assert sum("+2 SD" in (t.get("name") or "") for t in spec["data"]) == 3  # one per slope line
    at.toggle(key="rl_events").set_value(False).run()
    assert not any("Dated events on this chart" in e.label for e in at.expander)


def test_rates_cached_mode():
    at = rates_open(mode="cached")
    assert not at.exception, [e.value for e in at.exception]
    assert any("live fetch failed; showing the cached copy fetched 2026-10-02 07:00" in w.value
               for w in at.warning)
    assert len(chart_specs(at)) == 6


def test_rates_error_mode():
    at = rates_open(mode="error")  # no live, no cache
    assert not at.exception, [e.value for e in at.exception]
    assert len(at.error) >= 5 and all("no cached copy" in e.value for e in at.error)
    assert not chart_specs(at)


# --- Phase 3: Glossary and Concept Trainer ----------------------------------------------------

def test_glossary_lists_every_term_with_links():
    from content.glossary import TERMS
    at = open_page("Glossary")
    assert not at.exception, [e.value for e in at.exception]
    text = " ".join(m.value for m in at.markdown)
    for t in TERMS:
        assert t.name in text
    at.text_input(key="gl_filter").set_value("repo").run()
    assert not at.exception
    shown = " ".join(m.value for m in at.markdown)
    assert "Reverse repo" in shown and "Haircut" not in shown


def test_trainer_flashcards_and_quiz_score():
    at = open_page("Concept Trainer")
    assert not at.exception, [e.value for e in at.exception]
    from content.glossary import PROMPTS
    assert [e.label for e in at.expander if e.label in PROMPTS.values()] == list(PROMPTS.values())
    at.selectbox(key="tr_card").set_value("SONIA").run()
    assert not at.exception
    ss = at.session_state
    from content.glossary import quiz_question
    key, prompt = ss.tr_order[ss.tr_pos]
    q = quiz_question(key, prompt, seed=ss.tr_seed + ss.tr_pos)
    at.radio(key="tr_choice").set_value(q["answer"]).run()
    at.button(key="tr_check").click().run()
    assert not at.exception
    assert at.session_state.tr_score == 1 and at.session_state.tr_done == 1
    assert any("Correct" in s.value for s in at.success)
    at.button(key="tr_next").click().run()
    assert at.session_state.tr_pos == 1 and not at.session_state.tr_checked
    key, prompt = at.session_state.tr_order[1]
    q = quiz_question(key, prompt, seed=at.session_state.tr_seed + 1)
    at.radio(key="tr_choice").set_value((q["answer"] + 1) % 4).run()
    at.button(key="tr_check").click().run()
    assert at.session_state.tr_score == 1 and at.session_state.tr_done == 2
    assert at.error
    at.button(key="tr_reset").click().run()
    assert at.session_state.tr_done == 0


# --- Phase 4: Desk Brief ----------------------------------------------------------------------

def macro_open(page, monkeypatch=None, mode="live"):
    if mode == "live":
        monkeypatch.setattr(macro_mod, "fetch_live", synthetic_macro)
    elif mode == "cached":
        for key in macro_mod.SERIES:
            if key not in ("brent", "gbpusd"):
                macro_mod.write_cache(key, synthetic_macro(key), "2026-10-02T07:00:00")
    return open_page(page)


def test_brief_live_mode(monkeypatch):
    at = macro_open("Desk Brief", monkeypatch, "live")
    assert not at.exception, [e.value for e in at.exception]
    assert not at.error
    assert not [w for w in at.warning if "SONIA" not in w.value]  # sidebar ticket SONIA aside
    assert "RULES-BASED, NOT A FORECAST" in at.info[0].value
    md = " ".join(m.value for m in at.markdown)
    assert "SONIA − Bank Rate stood at" in md and "change z" in md
    assert [s.value for s in at.subheader][:3] == ["Funding conditions", "Largest movers",
                                                    "Stretched: beyond 2 SD"]
    assert len(at.get("download_button")) == 2


def test_brief_printable_view(monkeypatch):
    at = macro_open("Desk Brief", monkeypatch, "live")
    at.toggle(key="db_print").set_value(True).run()
    assert not at.exception
    assert [s.value for s in at.subheader] == ["SONIA"]  # sidebar only: compact view
    assert any("Printable view" in c.value for c in at.caption)


def test_brief_cached_mode():
    at = macro_open("Desk Brief", mode="cached")
    assert not at.exception, [e.value for e in at.exception]
    assert any("cached copy used" in w.value and "2026-10-02 07:00" in w.value for w in at.warning)
    assert any("Not available" in e.label for e in at.expander)  # Brent and GBP/USD


def test_brief_error_mode():
    at = macro_open("Desk Brief", mode="error")
    assert not at.exception, [e.value for e in at.exception]
    assert at.error and "No series could be loaded" in at.error[0].value


# --- Phase 5: Markets upgrades ----------------------------------------------------------------

def synthetic_varied(key: str, n: int = 900) -> pd.DataFrame:
    """Like synthetic() but each series gets its own path (so correlations are not all 1)."""
    idx = pd.bdate_range(end="2026-10-02", periods=n)
    rng = np.random.default_rng(sorted(markets_mod.SERIES).index(key) + 1)
    if markets_mod.SERIES[key].is_yield:
        return pd.DataFrame({"close": 3.5 + np.cumsum(rng.normal(0, 0.03, n))}, index=idx)
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, n)))
    df = pd.DataFrame({"close": close}, index=idx)
    if markets_mod.SERIES[key].has_ohlc:
        df = df.assign(open=close * 0.999, high=close * 1.01, low=close * 0.99,
                       volume=1e6)[["open", "high", "low", "close", "volume"]]
    return df


MARKET_SECTIONS = ["Cross-asset correlation", "Rolling correlation and beta for a pair",
                   "Volatility regimes: FTSE 100", "Daily change distribution: FTSE 100",
                   "Seasonality by calendar month: FTSE 100"]


def test_markets_upgrades_live(monkeypatch):
    monkeypatch.setattr(markets_mod, "fetch_live", synthetic_varied)
    at = open_page("Markets")
    assert not at.exception, [e.value for e in at.exception]
    subs = [s.value for s in at.subheader]
    for s in MARKET_SECTIONS:
        assert s in subs
    specs = [json.loads(s) for s in chart_specs(at)]
    titles = [sp["layout"]["title"]["text"] for sp in specs]
    assert "CORRELATION OF DAILY CHANGES, LAST 1Y" in titles
    import base64
    heat = next(sp for sp in specs if sp["data"][0]["type"] == "heatmap")["data"][0]["z"]
    if isinstance(heat, dict):  # plotly's binary array encoding
        z = np.frombuffer(base64.b64decode(heat["bdata"]), dtype=heat["dtype"]).reshape(
            [int(v) for v in heat["shape"].split(",")])
    else:
        z = np.array(heat, dtype=float)
    assert z.shape == (6, 6) and np.allclose(np.diag(z), 1) and np.allclose(z, z.T, equal_nan=True)
    # every new chart carries frequency, source and as-of (or date span) in its subtitle
    for sp in specs[1:]:
        sub_ = sp["layout"]["title"]["subtitle"]["text"]
        assert sub_.startswith(("Daily · ", "Monthly ")), sub_
    assert any("Small samples" in c.value for c in at.caption)
    assert any("observed against" in c.value for c in at.caption)


def test_markets_upgrades_controls(monkeypatch):
    monkeypatch.setattr(markets_mod, "fetch_live", synthetic_varied)
    at = open_page("Markets")
    at.radio(key="mkt_corr_win").set_value("3M")
    at.selectbox(key="mkt_pair_a").set_value("uk10y")
    at.selectbox(key="mkt_roll").set_value(20)
    at.radio(key="mkt_range").set_value("Max")
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    titles = [json.loads(s)["layout"]["title"]["text"] for s in chart_specs(at)]
    assert "CORRELATION OF DAILY CHANGES, LAST 3M" in titles
    assert any(t.startswith("UK 10-YEAR GILT YIELD VS") for t in titles)
    assert any("bp of A per 1" in c.value for c in at.caption)
