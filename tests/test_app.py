"""Smoke tests for the Streamlit app (Prime Financing Lab) using Streamlit's AppTest."""

import json
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from engine.capital import NOT_MODELLED_BANNER
from ui.assumptions_reader import read_assumptions
from ui.common import PLACEHOLDER_BANNER, SUBTITLE

APP = Path(__file__).resolve().parent.parent / "app.py"

PAGES = {
    "Summary": "pages/summary_page.py",
    "Client view": "pages/client_page.py",
    "Desk view": "pages/desk_page.py",
    "Capital": "pages/capital_page.py",
    "Stress lab": "pages/stress_page.py",
    "Assumptions": "pages/assumptions_page.py",
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


@pytest.mark.parametrize("page", list(PAGES))
def test_page_runs_with_banner(page):
    at = open_page(page)
    assert not at.exception, [e.value for e in at.exception]
    assert at.title[0].value == page
    assert any(PLACEHOLDER_BANNER in w.value for w in at.warning)


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
