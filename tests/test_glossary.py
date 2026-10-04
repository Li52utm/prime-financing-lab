"""Glossary and Concept Trainer content: every required term, four hand-written prompts each,
links that point at real pages and real chart/section names, and a well-formed quiz."""

import pathlib
import re

import pytest

from content import glossary as G

ROOT = pathlib.Path(__file__).resolve().parents[1]
REQUIRED = ["QE", "QT", "Reserves", "Excess liquidity", "GC", "Specials", "DMO", "Repo",
            "Reverse repo", "Haircut", "SONIA", "€STR", "OIS", "2s10s", "Term premium", "CTD",
            "Basis", "Implied repo rate", "Balance sheet", "Leverage ratio", "RWA", "SA-CCR",
            "Initial margin", "Variation margin", "Rehypothecation", "Prime brokerage", "TRS",
            "Delta-one", "Collateral upgrade", "SDRT", "HQLA", "LCR", "Turn", "Netting"]


def test_every_required_term_present_once():
    names = [t.name for t in G.TERMS]
    for r in REQUIRED:
        hits = [n for n in names if n.startswith(r)]
        assert len(hits) == 1, (r, hits)
    assert len({t.key for t in G.TERMS}) == len(G.TERMS) == len(REQUIRED)


@pytest.mark.parametrize("term", G.TERMS, ids=lambda t: t.key)
def test_term_complete(term):
    assert term.definition and term.why_financing
    for p in G.PROMPTS:  # four prompts per concept
        assert getattr(term, p).strip(), (term.key, p)
    assert term.links or term.not_charted  # either a link or an explanation of why not


@pytest.mark.parametrize("link", sorted({ln for t in G.TERMS for ln in t.links}, key=str),
                         ids=lambda ln: f"{ln.label}:{ln.chart}")
def test_link_targets_exist(link):
    """The page file exists, is registered in app.py, and the chart/section name appears in it."""
    src = (ROOT / link.page).read_text(encoding="utf-8")
    assert link.page in (ROOT / "app.py").read_text(encoding="utf-8")
    assert f'title="{link.label}"' in (ROOT / "app.py").read_text(encoding="utf-8")
    assert link.chart in src, link


def test_quiz_question_shape_and_determinism():
    q = G.quiz_question("repo", "what", seed=7)
    assert len(q["options"]) == 4 == len(set(q["options"]))
    assert q["options"][q["answer"]] == G.by_key()["repo"].what
    assert q == G.quiz_question("repo", "what", seed=7)


def test_none_answers_never_distract_each_other():
    """For uncharted concepts the correct 'which chart' answer starts with 'None'; no other
    option may also start with 'None', or two options would both be right."""
    for t in G.TERMS:
        if t.which_chart.startswith("None"):
            q = G.quiz_question(t.key, "which_chart", seed=1)
            assert sum(o.startswith("None") for o in q["options"]) == 1


def test_no_external_text_markers():
    """Hand-written content: no URLs or citation brackets pasted in."""
    src = (ROOT / "content" / "glossary.py").read_text(encoding="utf-8")
    assert not re.search(r"https?://", src)
