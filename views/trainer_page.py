"""Concept Trainer: flashcards and a multiple-choice quiz drawn from the glossary. Four prompts per
concept; every question and answer is hand-written in content/glossary.py. The score lives in
st.session_state only (nothing is written to disk)."""

import random

import streamlit as st

from content.glossary import PROMPTS, TERMS, by_key, quiz_question

st.caption("Questions and answers are hand-written in code for this app. Your score is kept in "
           "this browser session only and is lost when the session ends.")
terms = by_key()
tab_cards, tab_quiz = st.tabs(["Flashcards", "Quiz"])

# --- Flashcards -------------------------------------------------------------------------------
with tab_cards:
    names = {t.name: t.key for t in TERMS}
    pick = st.selectbox("Concept", list(names), key="tr_card")
    t = terms[names[pick]]
    st.markdown(f"#### {t.name}")
    st.caption("Click a prompt to reveal the answer.")
    for p, question in PROMPTS.items():
        with st.expander(question):
            st.markdown(getattr(t, p))

# --- Quiz -------------------------------------------------------------------------------------
ss = st.session_state
if "tr_order" not in ss:
    ss.tr_seed = random.SystemRandom().randrange(1_000_000)
    order = [(t.key, p) for t in TERMS for p in PROMPTS]
    random.Random(ss.tr_seed).shuffle(order)
    ss.tr_order, ss.tr_pos, ss.tr_score, ss.tr_done, ss.tr_checked = order, 0, 0, 0, False


def reset():
    for k in ("tr_order", "tr_pos", "tr_score", "tr_done", "tr_checked", "tr_choice"):
        ss.pop(k, None)


def next_q():
    ss.tr_pos = (ss.tr_pos + 1) % len(ss.tr_order)
    ss.tr_checked = False
    ss.pop("tr_choice", None)


with tab_quiz:
    total = len(ss.tr_order)
    c1, c2 = st.columns([3, 1])
    c1.markdown(f"**Score: {ss.tr_score} of {ss.tr_done} answered** · question "
                f"{ss.tr_pos + 1} of {total} ({len(TERMS)} concepts × {len(PROMPTS)} prompts)")
    c2.button("Reset score", on_click=reset, key="tr_reset")
    key, prompt = ss.tr_order[ss.tr_pos]
    q = quiz_question(key, prompt, seed=ss.tr_seed + ss.tr_pos)
    st.markdown(f"#### {q['question']}")
    choice = st.radio("Choose one", range(4), format_func=lambda i: q["options"][i], index=None,
                      key="tr_choice", disabled=ss.tr_checked)
    if not ss.tr_checked:
        if st.button("Check answer", key="tr_check", disabled=choice is None):
            ss.tr_checked = True
            ss.tr_done += 1
            ss.tr_score += int(choice == q["answer"])
            st.rerun()
    else:
        if choice == q["answer"]:
            st.success("Correct.")
        else:
            st.error(f"Not quite. The answer is: {q['options'][q['answer']]}")
        st.button("Next question", on_click=next_q, key="tr_next")
