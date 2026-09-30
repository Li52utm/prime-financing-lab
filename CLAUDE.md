# Equity Financing Lab

## Purpose
A Streamlit dashboard that compares three ways to finance a long equity position:
1. On-sheet prime brokerage (PB margin loan)
2. Total return swap (TRS)
3. Collateral upgrade (equities lent against HQLA / gilts)

For each route it shows the **client's all-in cost** and the **dealer's return on balance sheet**. The audience is a repo / equity-finance desk.

## Data and confidentiality
- Use only public data and the user's own assumptions.
- **Never read, reference, quote or infer from anything in `notes_private/`.** It is git-ignored and off-limits.

## Regulatory treatment
- All regulatory numbers (RWA, SA-CCR-style add-ons, leverage exposure) are **illustrative and simplified**. Label them that way in code comments, chart titles and captions, the app UI and the README.
- Give every regulatory formula a comment citing its source (PRA Rulebook part/article, CRR article, or Basel framework paragraph such as CRE52 or LEV30).
- If a citation or parameter has not been checked against the source, mark it `# UNVERIFIED:` with a short reason.

## Assumptions
- Every numeric default lives in `assumptions.py` with a comment explaining it (source or "own assumption").
- No magic numbers in `engine/` or `pages/`.
- Label stress presets as **hypothetical** in code and UI.

## Testing
- Every engine function has at least one pytest test against a hand-worked number. Show the working in the test's docstring or comments.
- Run with `.venv\Scripts\python -m pytest`.

## Conventions
- Currency is GBP. Day count is ACT/365 (`days / 365`).
- Rates are decimals (`0.05` means 5%). Spreads are decimals too (`0.0035` means 35 bp). Convert to bp only for display.
- Tenors are `1M`, `3M` and `6M`, mapped to day counts in `assumptions.py`.

## Features
- Compare all three routes side by side.
- Dividend mechanics: ex-dividend timing within the tenor, pass-through % on the TRS, and withholding tax.
- Asset-class toggle: large-cap, small-cap, convertible-style (drives haircuts, spreads, borrow and risk weights).
- Shadow cost of balance sheet slider.
- Stress lab: hypothetical presets; the TRS reprices fast while on-sheet reprices slowly; term vs rolling funding.
- Breakeven TRS spread (the spread at which the client is indifferent to PB, and the spread at which the dealer hits its hurdle).

## Build order
1. `assumptions.py` + `engine/financing.py`
2. `engine/capital.py`
3. `engine/stress.py`
4. Streamlit app (`app.py`) + `pages/`
5. `README.md`

## Workflow
- Plan before building. Build one module at a time and **stop for user review after each** before starting the next.
