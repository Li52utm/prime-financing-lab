"""Keep every test offline and deterministic.

Each test gets a SONIA fetch that fails and an empty temporary cache, so the app falls back
to the assumptions.py placeholder (4.00%) unless a test opts into live or cached mode.
Market data fetches fail too and use an empty temporary cache (the Markets page shows its
error state unless a test opts in). The Streamlit data cache is cleared so one test cannot
leak into another.
"""

import pytest
import streamlit as st

from data import macro, markets, sonia


def _no_network(*args, **kwargs):
    raise sonia.SoniaFetchError("network disabled in tests")


def _no_market_network(key, *args, **kwargs):
    raise ConnectionError("network disabled in tests")


@pytest.fixture(autouse=True)
def offline_sonia(monkeypatch, tmp_path):
    monkeypatch.setattr(sonia, "fetch_latest_sonia", _no_network)
    monkeypatch.setattr(sonia, "http_get", _no_network)
    monkeypatch.setattr(sonia, "CACHE_PATH", tmp_path / "cache" / "sonia.json")
    st.cache_data.clear()
    yield
    st.cache_data.clear()


@pytest.fixture(autouse=True)
def offline_markets(monkeypatch, tmp_path):
    monkeypatch.setattr(markets, "fetch_live", _no_market_network)
    monkeypatch.setattr(markets, "_get", _no_market_network)
    monkeypatch.setattr(markets, "_yahoo_history", _no_market_network)
    monkeypatch.setattr(markets, "CACHE_DIR", tmp_path / "cache" / "markets")
    yield


@pytest.fixture(autouse=True)
def offline_macro(monkeypatch, tmp_path):
    monkeypatch.setattr(macro, "fetch_live", _no_market_network)
    monkeypatch.setattr(macro, "_get", _no_market_network)
    monkeypatch.setattr(macro, "CACHE_DIR", tmp_path / "cache" / "macro")
    yield
