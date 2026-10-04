"""Shared loader for official macro series (Rates & Liquidity, Desk Brief). Load order is live,
then cache, then an error shown on the page; failures are not cached by st.cache_data."""

from concurrent.futures import ThreadPoolExecutor

import streamlit as st

import assumptions as A
from data import macro as MAC


@st.cache_data(ttl=A.MARKETS_CACHE_TTL_HOURS * 3600, show_spinner="Fetching official data...")
def load(key: str) -> MAC.MacroSeries:
    return MAC.load_macro(key)  # MacroDataError propagates (not cached)


def _try(k):
    try:
        return k, load(k), None
    except MAC.MacroDataError as e:
        return k, None, str(e)


def get(keys: list[str]) -> tuple[dict, list[str]]:
    """Load several series in parallel (each source is fetched independently)."""
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(_try, keys))
    return ({k: s for k, s, _ in results if s is not None},
            [e for _, _, e in results if e])
