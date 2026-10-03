"""Keep every test offline and deterministic.

Each test gets a SONIA fetch that fails and an empty temporary cache, so the app falls back
to the assumptions.py placeholder (4.00%) unless a test opts into live or cached mode.
The Streamlit data cache (6-hour SONIA TTL) is cleared so one test cannot leak into another.
"""

import pytest
import streamlit as st

from data import sonia


def _no_network(*args, **kwargs):
    raise sonia.SoniaFetchError("network disabled in tests")


@pytest.fixture(autouse=True)
def offline_sonia(monkeypatch, tmp_path):
    monkeypatch.setattr(sonia, "fetch_latest_sonia", _no_network)
    monkeypatch.setattr(sonia, "http_get", _no_network)
    monkeypatch.setattr(sonia, "CACHE_PATH", tmp_path / "cache" / "sonia.json")
    st.cache_data.clear()
    yield
    st.cache_data.clear()
