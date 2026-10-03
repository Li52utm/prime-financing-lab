# Equity Financing Lab

A Streamlit dashboard comparing three ways to finance a long equity position: on-sheet prime brokerage, total return swap (TRS) and collateral upgrade. For each route it shows the client's all-in cost and the dealer's return on balance sheet.

> **Status: step 4 of 5.** The engines (`engine/financing.py`, `engine/capital.py`, `engine/stress.py`) and the Streamlit app are built. This README gets its full version in step 5.

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

## Step 3: stress lab (hypothetical)

All presets and shocks are **hypothetical own assumptions** in `assumptions.py`. They are not forecasts.

- **Price shock:** a stock move m sets the TRS mark-to-market V = −N·m. It also scales three things by (1 + m):
  - the hedge stock value
  - the street repo collateral
  - the SA-CCR adjusted notional. Under PRA CCR (CRR) Art 279b(1)(c), an equity adjusted notional is market price × number of units. A TRS expressed as a fixed GBP notional keeps its notional; this is a toggle, and the default is a TRS on a number of shares.

  The street repo cash and the client's IM stay at their original amounts. The page shows RC, multiplier, EAD, RWA and leverage exposure.
- **Presets:** `quarter_end_squeeze`, `year_end_turn` and `collateral_shortage`. There are three views. The k, street haircut and gilt borrow shocks always apply for the whole tenor. The street spread shock and the client repricing apply for the horizon set by the view, and both are costed with the term-vs-rolling formula:
  - **"If the shock persisted for the whole tenor"**: street shock and client repricing both apply for the tenor.
  - **"Shock for the turn days only (street and client)"**: both apply only for the preset's turn days, so both sides of the dealer's P&L use the same horizon.
  - **"Client reprices and stays repriced"**: the street shock applies for the turn days and the client repricing for the whole tenor.

  In every view, the required spread is the flat spread over the tenor, excluding client-repricing income, so it's comparable across the three.

  Each preset shocks:
  - the client spread
  - the street spread
  - the shadow cost k
  - the street haircut
  - the gilt borrow fee
- **Pass-through lag:** the shock persists for the whole path. The TRS spread reprices fully at once. The on-sheet PB spread reprices by a fraction per month (default 25%, capped at 100%). The dealer's street costs are hit immediately. The page shows the month-by-month client cost gap (PB − TRS) and the dealer's PB shortfall.
  - After PB has fully repriced, the gap does **not** return to its pre-shock level. PB reprices on its loan L = N(1 − margin) and the TRS on the full N, so the gap = base gap − (N − L) × client shock × τ.
- **Term vs rolling:** the dealer's street funding either locks a term spread (base + term premium) or rolls and pays the shock for the turn days. The page shows the breakeven term premium = shock × turn days / horizon.

## Collateral upgrade dealer P&L

The upgrade's dealer P&L matches the capital model's gilt source.
- **`reverse_repo`:** the dealer earns the fee; pays street funding on the repo of the client's equities; earns the gilt reverse-repo rate on R = G(1 − gilt haircut); and earns SONIA on any surplus cash (or pays for a shortfall). **Own assumption:** no gilt borrow fee by default (`GILT_BORROW_FEE_REVERSE_REPO = 0`). The gilts are sourced at the reverse repo rate, so a fee would double count. It remains an input.
- **`borrowed` / `inventory`:** fee minus gilt borrow fee (`GILT_BORROW_FEE`). The preset gilt borrow shock applies to this fee only.

## Hurdle clearance

**Break-even k** is the lead metric: the balance-sheet charge at which the route just clears, equal to its gross RoLE. Each route also reports whether its gross RoLE clears the hurdle k, and by how many bp of spread (current spread − required spread). The Summary page names a "best for desk" route only among routes that clear. If none clears, it says so.

## Not modelled

- **CVA risk capital: NOT MODELLED.**
- Market risk on the delta-hedged stock
- Default fund and CCP exposures
- Large exposures
- SFT minimum haircut floors
- LCR beyond one illustrative HQLA line (Level 2B at a 50% haircut, **UNVERIFIED**)

## The app: Prime Financing Lab

```
.venv\Scripts\python -m streamlit run app.py
```

It opens at http://localhost:8501. The sidebar holds the trade ticket, with an Advanced expander for the haircut regime, street leg, surplus cash placement, PB holding period, risk weights, TRS unit notional and resets.

| Page | What it shows |
|---|---|
| Summary | Break-even k and required vs quoted spread per route, hurdle clearance (no winner is named if none clears), one table of all three routes, and the k sensitivity |
| Client view | Financing and net cost in bp over SONIA, with and without SDRT; a cost waterfall; the breakeven TRS spread |
| Desk view | Dealer P&L by component, RoLE and RoRWA against hurdles, quoted vs required spread, TRS return vs IM remuneration, and three netting cases |
| Capital | NOT MODELLED banner, RWA and leverage by component, T-accounts, gilt source comparison, PB RWA vs margin, SA-CCR detail |
| Stress lab | Hypothetical presets under three horizon views, the price shock, the repricing lag, term vs rolling |
| Assumptions | Every value in `assumptions.py`, read live, with its source and a VERIFIED / UNVERIFIED tag (n/a for own assumptions and hypothetical values) |

Every page carries a banner saying the default spreads and k are placeholder assumptions, not market levels. Every chart carries the subtitle "Illustrative, not a regulatory calculation". Every headline number has a "How is this calculated" expander.

## Live SONIA

The app loads SONIA live. The engine never calls the network: SONIA is an input to every engine function.

- **Sources:**
  - **Bank of England IADB** (first choice), series IUDSOIA, via its CSV endpoint (`_iadb-fromshowcolumns.asp?...&SeriesCodes=IUDSOIA&CSVF=TN...`). The response is `DATE,IUDSOIA` followed by rows like `30 Sep 2026,3.7329` (percent).
  - **FRED** (fallback), `fredgraph.csv?id=IUDSOIA`. The response is `observation_date,IUDSOIA` followed by rows like `2026-09-30,3.7329`; UK holidays appear with an empty value.
  - Both formats were verified by fetching them on 2026-10-03. FRED did not respond from the development network, so expect the fallback to time out there.
- **Rules:**
  - A browser-like User-Agent and a 10-second timeout per source.
  - The value used is the most recent observation that has a value. Weekends and holidays have none.
  - Values outside 0% to 15% are rejected.
- **Load order:**
  1. live fetch, BoE then FRED;
  2. the last good value cached in `data/cache/sonia.json` (git-ignored);
  3. the `SONIA` placeholder in `assumptions.py`.

  The status is shown as **live**, **cached** or **fallback**, with the as-of date and its age.
- **In the app:**
  - The value is fetched through `st.cache_data` with a 6-hour TTL.
  - The sidebar shows the value, as-of date, source and status.
  - A warning appears if the status is cached or fallback, or if the as-of date is more than 5 business days old. Weekdays are counted with no UK holiday calendar.
  - The page header shows the SONIA in use. The placeholder banner mentions SONIA only in fallback mode.
- **Manual override:** the sidebar toggle "Manual SONIA override" replaces the loaded value with a slider value (0% to 15%). The header then says "manual override", and the IM remuneration slider's range follows the SONIA in use.
- **Tests run offline:** `tests/conftest.py` disables the fetch and uses a temporary cache for every test.

## Running the tests

```
.venv\Scripts\python -m pytest
```

`tests/test_app.py` smoke-tests every page with Streamlit's AppTest.
