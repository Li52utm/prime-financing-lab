# Equity Financing Lab

A Streamlit dashboard comparing three ways to finance a long equity position: on-sheet prime brokerage, total return swap (TRS) and collateral upgrade. For each route it shows the client's all-in cost and the dealer's return on balance sheet.

> **Status: step 2 of 5.** The financing engine (`engine/financing.py`) and the capital engine (`engine/capital.py`) are built. This README gets its full version in step 5.

All numbers are illustrative. They use public data and the author's own assumptions. All regulatory treatment is **illustrative and simplified** and is not a regulatory calculation.

## Step 1: financing

- **Static notional.** Price moves and variation margin are ignored. Costs are carry only, over a fixed tenor.
- **Client cost is split three ways.** The headline **financing cost** covers interest, margin opportunity cost, fees and amortised SDRT. The **dividend credit** (dividend or manufactured dividend received) is shown separately. **Net** = financing − dividend credit. The breakeven TRS spread compares net costs, because dividend treatment differs by route.
- **Conventions.** GBP, ACT/365, rates as decimals. Tenors 1M/3M/6M are fixed at 30/91/182 days.
- **Client cost** includes the opportunity cost of the margin or IM the client posts, charged at the client's own funding rate.
- **Dealer cash gap.** A shortfall is funded at SONIA + unsecured spread. A surplus earns SONIA flat.
- **IM remuneration.** The client earns SONIA − `im_remuneration_spread` on its TRS cash IM. The default spread is 0, meaning SONIA flat (own assumption). The dealer's cost equals the client's saving. TRS IM is the only cash margin in the model: PB margin is the client's own equity in the stock, and all other haircuts are posted in securities.
- **Dealer net by component.** Each route breaks dealer net into: SONIA from client, spread income, street funding, cash gap, IM remuneration, dividend pickup, hedge SDRT and gilt borrow.
- **Accounting balance sheet.** `financing.py` still reports accounting ROBS. The collateral upgrade is off the accounting balance sheet (securities for securities), so its accounting ROBS is undefined. The headline balance-sheet metric is now return on leverage exposure (see step 2).
- **SDRT (0.5%)** is a toggle, on by default for the UK large-cap example. AIM shares are exempt. Results are shown both with and without it. SDRT is a one-off charge, amortised over `holding_period_days` (default 365, separate from the tenor): each tenor carries SDRT × min(1, tenor / holding period). The treatment of the dealer's TRS hedge (intermediary relief, so no SDRT) is **UNVERIFIED**.
- **Dividends.** One discrete dividend, counted if the ex-date falls within the tenor. Withholding tax defaults to 0% for UK stocks.

## Step 2: capital (illustrative and simplified)

- **TRS counterparty exposure:** SA-CCR style (PRA Counterparty Credit Risk (CRR) Art 274–280d; Basel CRE52). It supports unmargined or margined trading, a netting set with other equity trades, a mark-to-market input V, and interim resets.
- **PB loan and SFT exposures:** Financial Collateral Comprehensive Method (PRA Credit Risk Mitigation (CRR) Art 223–224; Basel CRE22). A **haircut regime** selector offers:
  - Basel 3.1: 20% / 30%, effective 1 Jan 2027
  - current UK CRR: 15% / 25%
- **Street leg (toggle, on by default):** the dealer repos the stock, or sources gilts, with a street counterparty. That adds CCR and leverage add-ons.
- **Collateral upgrade** leverage exposure and HQLA use depend on `gilt_source` (reverse repo, borrowed, or inventory).
- **Leverage exposure:** PRA Leverage Ratio (CRR) Art 429b, 429c, 429e; Basel LEV30. Surplus cash at the central bank is excluded (Art 429a).
- **Metrics:**
  - Return on leverage exposure (RoLE) is the headline balance-sheet metric. The shadow cost k is charged on leverage exposure and is the RoLE hurdle.
  - Return on RWA is also reported.
  - Both required spreads are shown, and the binding one is flagged.
- **RWA** = EAD × risk weight. Risk weights are inputs.

### Not modelled

- **CVA risk capital: NOT MODELLED.**
- Market risk on the delta-hedged stock
- Default fund and CCP exposures
- Large exposures
- SFT minimum haircut floors
- LCR beyond one illustrative HQLA line (Level 2B at a 50% haircut, **UNVERIFIED**)

## Running the tests

```
.venv\Scripts\python -m pytest
```
