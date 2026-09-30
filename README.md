# Equity Financing Lab

A Streamlit dashboard comparing three ways to finance a long equity position: on-sheet prime brokerage, total return swap (TRS) and collateral upgrade. For each route it shows the client's all-in cost and the dealer's return on balance sheet.

> **Status: step 1 of 5.** Only the financing engine (`assumptions.py`, `engine/financing.py`) is built. This README gets its full version in step 5.

All numbers are illustrative. They use public data and the author's own assumptions. Any regulatory treatment (step 2 onwards) is **illustrative and simplified** and is not a regulatory calculation.

## Step 1 scope and simplifications

- **Static notional.** Price moves and variation margin are ignored. Costs are carry only, over a fixed tenor.
- **Client cost is split three ways.** The headline **financing cost** covers interest, margin opportunity cost, fees and amortised SDRT. The **dividend credit** (dividend or manufactured dividend received) is shown separately. **Net** = financing − dividend credit. The breakeven TRS spread compares net costs, because dividend treatment differs by route.
- **Conventions.** GBP, ACT/365, rates as decimals. Tenors 1M/3M/6M are fixed at 30/91/182 days.
- **Client cost** includes the opportunity cost of the margin or IM the client posts, charged at the client's own funding rate.
- **Dealer cash gap.** A shortfall is funded at SONIA + unsecured spread. A surplus earns SONIA flat.
- **ROBS** is gross: dealer net / (balance sheet × τ), annualised. The shadow cost of balance sheet is shown separately and is **not** deducted. Each route also reports the dealer spread needed for gross ROBS to equal the hurdle k.
- **Collateral upgrade balance sheet = 0 is a PLACEHOLDER.** A securities-for-securities trade is treated as off the accounting balance sheet for now, so its ROBS and required fee show as undefined. Step 2 replaces this with an illustrative leverage exposure.
- **SDRT (0.5%)** is a toggle, on by default for the UK large-cap example. AIM shares are exempt. Results are shown both with and without it. SDRT is a one-off charge, amortised over `holding_period_days` (default 365, separate from the tenor): each tenor carries SDRT × min(1, tenor / holding period). The treatment of the dealer's TRS hedge (intermediary relief, so no SDRT) is **UNVERIFIED**.
- **Dividends.** One discrete dividend, counted if the ex-date falls within the tenor. Withholding tax defaults to 0% for UK stocks.

## Running the tests

```
.venv\Scripts\python -m pytest
```
