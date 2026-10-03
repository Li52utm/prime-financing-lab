"""Every numeric default used by the engine and the app.

Conventions: GBP, ACT/365, all rates and spreads are decimals (0.0050 = 50 bp).
Each value says where it comes from: "public" (with source) or "own assumption".
Values tagged UNVERIFIED have not been checked against the cited source.
"""

# --- Day count and tenors -------------------------------------------------

DAYS_IN_YEAR = 365  # ACT/365 day count (GBP money-market convention)

TENOR_DAYS = {  # own assumption: fixed day counts rather than calendar months
    "1M": 30,
    "3M": 91,
    "6M": 182,
}
DEFAULT_TENOR = "3M"  # own assumption

# --- Position ---------------------------------------------------------------

DEFAULT_NOTIONAL = 10_000_000.0  # own assumption: GBP 10m long equity position

# Own assumption: how long the client expects to hold the position, rolling the
# financing tenor as needed. One-off SDRT is amortised over this period.
HOLDING_PERIOD_DAYS = 365

# --- Market rates -----------------------------------------------------------

# UNVERIFIED: offline placeholder only. The app loads live SONIA from the Bank of England IADB
# (series IUDSOIA; fallback FRED IUDSOIA) via data/sonia.py, caches the last good value in
# data/cache/sonia.json, and uses this value only when both fail. Engine functions take SONIA as
# an input; this default is used by tests and when no live or cached value exists.
SONIA = 0.0400

# Own assumption: the client's own cost of funding the margin / IM / shortfall it
# puts up (hedge-fund style unsecured funding or cost of capital).
CLIENT_FUNDING_RATE = 0.0600

# Own assumption: dealer unsecured funding spread over SONIA, paid only when the
# dealer is short cash. A cash surplus earns SONIA flat (see engine.funding_gap_cost).
DEALER_UNSECURED_SPREAD = 0.0080

# Own assumption: the client earns SONIA minus this spread on its TRS cash IM, paid by the
# dealer. 0 = IM remunerated at SONIA flat. Slider range 0 to SONIA (SONIA = unremunerated).
# TRS IM is the only cash margin in the model: PB margin is the client's own equity in the
# stock, and every other haircut or over-collateralisation is posted in securities.
IM_REMUNERATION_SPREAD = 0.0
IM_REMUNERATION_SPREAD_MIN = 0.0  # own assumption: slider lower bound (SONIA flat)
IM_REMUNERATION_SPREAD_MAX = SONIA  # own assumption: slider upper bound (IM earns nothing)

# --- Asset-class presets (all own assumptions, illustrative) --------------
# pb_margin          client margin on the PB loan (fraction of notional)
# trs_im             client initial margin on the TRS (cash, unremunerated)
# street_haircut     haircut the dealer suffers repoing the stock in the street
# pb_spread          PB loan spread over SONIA charged to client
# trs_spread         TRS floating-leg spread over SONIA charged to client
# street_repo_spread dealer's equity repo spread over SONIA
# upgrade_haircut    equity-vs-gilt over-collateralisation in the upgrade
# upgrade_fee        annual fee on equity notional for the collateral upgrade
# aim_listed         True -> exempt from SDRT (AIM / recognised growth market)
ASSET_CLASSES = {
    "large_cap": {  # FTSE 100-style main-market stock
        # 18%: deliberately not equal to either supervisory haircut (20% Basel 3.1, 15% UK CRR)
        "pb_margin": 0.18,
        "trs_im": 0.15,
        "street_haircut": 0.10,
        "pb_spread": 0.0050,
        "trs_spread": 0.0040,
        "street_repo_spread": 0.0030,
        "upgrade_haircut": 0.10,
        "upgrade_fee": 0.0030,
        "aim_listed": False,
    },
    "small_cap": {  # AIM-listed small cap, so the default is SDRT-exempt
        "pb_margin": 0.35,
        "trs_im": 0.30,
        "street_haircut": 0.25,
        "pb_spread": 0.0100,
        "trs_spread": 0.0085,
        "street_repo_spread": 0.0070,
        "upgrade_haircut": 0.25,
        "upgrade_fee": 0.0060,
        "aim_listed": True,
    },
    "convertible_style": {  # main-market equity with convertible-like risk (gap / credit)
        # 28%: deliberately not equal to either supervisory haircut (30% Basel 3.1, 25% UK CRR)
        "pb_margin": 0.28,
        "trs_im": 0.25,
        "street_haircut": 0.20,
        "pb_spread": 0.0080,
        "trs_spread": 0.0070,
        "street_repo_spread": 0.0060,
        "upgrade_haircut": 0.20,
        "upgrade_fee": 0.0050,
        "aim_listed": False,
    },
}
DEFAULT_ASSET_CLASS = "large_cap"  # own assumption: the UK large-cap example

# --- Collateral upgrade: gilt leg -----------------------------------------

GILT_REPO_SPREAD = 0.0000  # own assumption: gilt repo at roughly SONIA flat
GILT_HAIRCUT = 0.02  # own assumption: haircut when client repos the gilts it received
# Own assumption: dealer's annual fee for borrowing the gilts (borrowed source) or the
# opportunity cost of lending its own (inventory source).
GILT_BORROW_FEE = 0.0010
# Own assumption: no separate borrow fee when the gilts are reversed in (reverse_repo
# source). They are sourced at the reverse repo rate, so a fee would double count.
GILT_BORROW_FEE_REVERSE_REPO = 0.0

# --- Dividends and tax ------------------------------------------------------

DIVIDEND = 0.015  # own assumption: one discrete gross dividend = 1.5% of notional
EX_DIV_DAY = 45  # own assumption: ex-date 45 days after trade start
# Own assumption: 100% of the gross dividend is passed to the TRS client, the norm for UK
# stocks with no withholding tax. For foreign stocks, a pass-through below 100%, or a
# dealer WHT rate below the rate implied by the pass-through (e.g. treaty relief), leaves
# the dealer a dividend pickup: gross x (1 - wht_dealer - pass_through).
TRS_PASS_THROUGH = 1.00
MANUFACTURED_PASS_THROUGH = 1.00  # own assumption: 100% manufactured dividend on lent stock
WHT_CLIENT = 0.00  # public: the UK levies no withholding tax on dividends (HMRC)
WHT_DEALER = 0.00  # public: as above, for UK stocks

INCLUDE_SDRT = True  # own assumption: default on for the UK large-cap example
# public: SDRT on UK share purchases is 0.5% (Finance Act 1986 s.87; HMRC guidance).
# AIM / recognised-growth-market shares are exempt (Finance Act 2014).
SDRT_RATE = 0.005
# UNVERIFIED: assumes the dealer's TRS hedge purchase qualifies for intermediary
# relief (FA 1986 s.88A), so the hedge pays no SDRT. Not checked against HMRC guidance.
DEALER_HEDGE_SDRT_RATE = 0.0

# --- Balance sheet ----------------------------------------------------------

# Own assumption: shadow cost of balance sheet (annual, per GBP). From step 2 it is
# charged on leverage exposure and is the hurdle for return on leverage exposure.
# 0.5% (was 2% on accounting balance sheet in step 1).
SHADOW_COST_K = 0.005
SHADOW_COST_K_MIN = 0.0  # slider bounds (own assumption)
SHADOW_COST_K_MAX = 0.030  # own assumption: slider upper bound
SHADOW_COST_K_STEP = 0.0025  # own assumption: slider step and sensitivity grid spacing


# =============================================================================
# Step 2: capital. ILLUSTRATIVE AND SIMPLIFIED. Not a regulatory calculation.
# "Verified" means checked on 2026-09-30 against the text quoted in the source.
# =============================================================================

# --- Supervisory volatility adjustments (Financial Collateral Comprehensive Method)
# 10-day liquidation-period haircuts for equities.
# Verified: PRA Rulebook, Credit Risk Mitigation (CRR) Part, Art 224(1) Table 3
#   (version effective 01/01/2027): Main Index Equities 20; Other Equities listed on a
#   recognised exchange 30.
# Verified: UK CRR (legislation.gov.uk, eur/2013/575 Art 224 Table 3, version in force
#   before 01/01/2027): Main Index Equities 15; Other Equities 25.
HAIRCUT_REGIMES = {
    "basel_3_1": {
        "label": "Basel 3.1 (PRA, effective 1 Jan 2027)",
        "main_index": 0.20,
        "other_listed": 0.30,
    },
    "uk_crr_current": {
        "label": "UK CRR (in force before 1 Jan 2027)",
        "main_index": 0.15,
        "other_listed": 0.25,
    },
}
DEFAULT_HAIRCUT_REGIME = "basel_3_1"  # own assumption: the regime in force from 1 Jan 2027

# Credit quality step 1 (AA- or better) central government debt, 10-day haircuts.
# Verified: PRA CRM (CRR) Art 224(1) Table 1 (01/01/2027): <=1y 0.5, >1<=3y 2, >3<=5y 2,
#   >5<=10y 4, >10y 4. Identical in both regimes.
GILT_HAIRCUTS_10D = {"<=1y": 0.005, "1-3y": 0.02, "3-5y": 0.02, "5-10y": 0.04, ">10y": 0.04}
DEFAULT_GILT_BAND = "1-3y"  # own assumption: the gilt delivered in the upgrade

FX_MISMATCH_HAIRCUT_10D = 0.08  # Verified: PRA CRM (CRR) Art 224(1) Table 4. Unused (all GBP)

# Liquidation periods. Verified: PRA CRM (CRR) Art 224(2): (a) secured lending 20 business
# days; (b) repurchase and securities lending/borrowing 5; (c) other capital-market-driven
# transactions 10. Haircuts scale with sqrt(days/10) (the Table 3 5-day column is 14.142
# for 20 at 10 days).
REPO_LIQUIDATION_DAYS = 5
# PB margin lending is capital-market-driven, so 10 days under Art 224(2)(c).
# UNVERIFIED interpretation: the last paragraph of Art 224(2) aligns the period with the
# Art 285(2) MPOR, and Art 285(2)(a) gives 5 business days for netting sets consisting only
# of margin lending, so a daily-margined PB book might use 5. Kept at 10 (conservative).
PB_LIQUIDATION_DAYS = 10

# --- SA-CCR ---------------------------------------------------------------------
# Verified: PRA Counterparty Credit Risk (CRR) Part Art 274(2): alpha = 1.4, unless the
#   counterparty is non-financial or a pension scheme arrangement (then 1). Client is a fund.
SACCR_ALPHA = 1.4
# Verified: PRA CCR (CRR) Art 278(3): multiplier = 1 if z >= 0, else
#   min{1, Floor_m + (1 - Floor_m) * exp(z / y)}, Floor_m = 5%, y = 2(1 - Floor_m)AggAddOn,
#   z = CMV - NICA (unmargined) or CMV - VM - NICA (margined). Same as Basel CRE52.
SACCR_MULTIPLIER_FLOOR = 0.05
# Verified: PRA CCR (CRR) Art 280d(3)-(4): single-name SF 32%, rho 50%; multi-name SF 20%,
#   rho 80%. (The plan cited 280c; the equity add-on is Art 280d in the PRA text.)
SACCR_EQUITY_SF = {"single": 0.32, "index": 0.20}
SACCR_EQUITY_RHO = {"single": 0.50, "index": 0.80}  # Verified: PRA CCR (CRR) Art 280d(3)
# Verified: PRA CCR (CRR) Art 279c(1): unmargined MF = sqrt(min{max{M, 10/OneBusinessYear}, 1});
#   margined MF = 1.5 * sqrt(MPOR / OneBusinessYear). M is in business-day years.
SACCR_MIN_MATURITY_BD = 10
# Own convention: 250 business days per year, as in Basel CRE52.
ONE_BUSINESS_YEAR = 250
# Verified: PRA CCR (CRR) Art 285(2)(b): MPOR at least 10 business days for netting sets
#   other than pure SFT netting sets.
SACCR_MPOR_DAYS = 10

# --- Risk weights (inputs) --------------------------------------------------------
# UNVERIFIED: own assumption based on the standardised treatment of unrated corporates
#   (Basel CRE20). Not checked against the PRA Credit Risk: Standardised Approach (CRR) Part.
RW_CLIENT = 1.00  # hedge-fund client, unrated
RW_STREET = 0.40  # own assumption: street bank / repo counterparty

# --- Asset-class mapping for capital (own assumptions) ------------------------------
# haircut_class: which Art 224 Table 3 row applies.
# lcr_level2b: whether the stock counts as Level 2B HQLA when received by the dealer.
# UNVERIFIED: treating convertible-style as "other listed" and not Level 2B eligible.
CAPITAL_ASSET_CLASSES = {
    "large_cap": {"haircut_class": "main_index", "saccr_type": "single", "lcr_level2b": True},
    "small_cap": {"haircut_class": "other_listed", "saccr_type": "single", "lcr_level2b": False},
    "convertible_style": {"haircut_class": "other_listed", "saccr_type": "single",
                          "lcr_level2b": False},
}

# --- Liquidity (illustrative) ----------------------------------------------------------
# UNVERIFIED: Level 2B equity haircut of 50% (Basel LCR, from secondary sources only; the
#   PRA Liquidity Coverage Ratio (CRR) Part has not been checked). Caps are ignored.
LCR_LEVEL2B_EQUITY_HAIRCUT = 0.50

# --- Trade structure defaults (own assumptions) -----------------------------------------
INCLUDE_STREET_LEG = True  # own assumption: include the street counterparty leg
DEFAULT_GILT_SOURCE = "reverse_repo"  # one of reverse_repo, borrowed, inventory
# Where surplus cash from the street repo sits. "central_bank": BoE reserves, netted
#   against a same-currency liability under PRA Leverage Ratio (CRR) Art 429a
#   (verified text), so it adds no leverage exposure. "counted": placed elsewhere.
DEFAULT_SURPLUS_CASH_PLACEMENT = "central_bank"
TRS_MARGINED = False  # unmargined by default; IM held as NICA
TRS_MTM = 0.0  # dealer-side mark-to-market V at the calculation date
# Own assumption: the TRS references a number of shares, so its SA-CCR adjusted notional
# moves with the price (PRA CCR (CRR) Art 279b(1)(c)). False = fixed GBP notional.
TRS_NOTIONAL_IN_UNITS = True

# --- Targets ------------------------------------------------------------------------
# Own assumption: gross annual return on RWA the desk needs.
TARGET_RORWA = 0.015
# Return on leverage exposure hurdle = SHADOW_COST_K (above).


# =============================================================================
# Step 3: stress. Every value below is HYPOTHETICAL and an own assumption, chosen
# only to illustrate the mechanics. None is a forecast or taken from any private source.
# =============================================================================

# Stock price moves for the TRS mark-to-market grid (hypothetical).
PRICE_SHOCK_GRID = [-0.30, -0.20, -0.10, 0.0, 0.10, 0.20]

# Stress presets (all HYPOTHETICAL own assumptions).
# client_spread_shock    market repricing of client spreads (PB spread, TRS spread, upgrade fee)
# street_spread_shock    rise in the dealer's street repo spread, hits the dealer immediately
# k_shock                rise in the shadow cost of balance sheet k
# street_haircut_change  change in the street repo haircut on equities
# turn_days              how long a roller pays the street spread shock (term vs rolling)
# term_premium           extra spread a term lender charges over the whole horizon to lock
# gilt_borrow_shock      rise in the dealer's gilt borrow fee (collateral upgrade sourcing)
STRESS_PRESETS = {
    "quarter_end_squeeze": {
        "label": "Quarter-end squeeze (hypothetical)",
        "client_spread_shock": 0.0010,
        "street_spread_shock": 0.0025,
        "k_shock": 0.0025,
        "street_haircut_change": 0.00,
        "turn_days": 5,
        "term_premium": 0.0002,
        "gilt_borrow_shock": 0.0005,
    },
    "year_end_turn": {
        "label": "Year-end turn (hypothetical)",
        "client_spread_shock": 0.0025,
        "street_spread_shock": 0.0060,
        "k_shock": 0.0050,
        "street_haircut_change": 0.02,
        "turn_days": 10,
        "term_premium": 0.0006,
        "gilt_borrow_shock": 0.0015,
    },
    "collateral_shortage": {
        "label": "Collateral shortage (hypothetical)",
        "client_spread_shock": 0.0015,
        "street_spread_shock": 0.0040,
        "k_shock": 0.0010,
        "street_haircut_change": 0.05,
        "turn_days": 30,
        "term_premium": 0.0010,
        "gilt_borrow_shock": 0.0030,
    },
}

# Pass-through lag (hypothetical own assumptions).
# The TRS spread reprices fully at once. The on-sheet PB spread reprices by this fraction
# of the client spread shock per month, cumulative and capped at 100% (0.25 = full in 4 months).
PB_REPRICING_FRACTION_PER_MONTH = 0.25
# Own assumption: the upgrade fee reprices fully at once, like the TRS.
UPGRADE_REPRICING_FRACTION = 1.0
MONTH_DAYS = 30  # own assumption: one month = 30 days (ACT/365), as the 1M tenor
REPRICING_HORIZON_MONTHS = 6  # own assumption: months shown on the repricing chart

# Term vs rolling (own assumption): horizon over which a term spread is locked.
TERM_HORIZON_DAYS = 91


# =============================================================================
# App (Prime Financing Lab)
# =============================================================================

# HYPOTHETICAL own assumption: the client's other trade used to illustrate SA-CCR netting.
# The client is short a TRS (the dealer receives the equity return, so the dealer's signed
# notional is positive). Recognising it requires a legally enforceable netting agreement.
NETTING_OTHER_NOTIONAL = 5_000_000.0
NETTING_DEFAULT_CASE = "different_name"  # "different_name" or "same_name"

# Own assumption: upper end of the TRS spread axis on the client breakeven chart (decimal).
BREAKEVEN_CHART_MAX_SPREAD = 0.03

# Own assumptions (display only): default axes of the Summary "Spread vs k" heatmaps, in bp.
HEATMAP_SPREAD_MIN_BP = 0.0  # x axis: client spread / upgrade fee
HEATMAP_SPREAD_MAX_BP = 150.0  # x axis upper end
HEATMAP_K_MIN_BP = 0.0  # y axis: balance-sheet charge k
HEATMAP_K_MAX_BP = 100.0  # y axis upper end
HEATMAP_STEP_BP = 5.0  # cell size on both axes


# =============================================================================
# Markets page (display analytics only; nothing here feeds the financing engine)
# =============================================================================

MARKETS_BB_WINDOW = 20  # Bollinger window (days); standard default, adjustable in the app
MARKETS_BB_WIDTH = 2.0  # Bollinger width in standard deviations; standard default
MARKETS_MA_FAST = 50  # moving averages (days), conventional desk choices
MARKETS_MA_SLOW = 200  # slow moving average (days), conventional desk choice
MARKETS_RSI_WINDOW = 14  # Wilder's original RSI window
MARKETS_VOL_WINDOW = 20  # rolling realised volatility window (days)
MARKETS_TRADING_DAYS = 252  # annualisation factor for daily volatility (own convention)
MARKETS_FORWARD_DAYS = (5, 20)  # horizons for "what happened after a band breach"
MARKETS_CANDLE_MAX_BARS = 1500  # above this many daily bars, candles are drawn weekly
MARKETS_CACHE_TTL_HOURS = 6  # in-app cache lifetime for fetched series
MARKETS_RANGES_MONTHS = {"1M": 1, "6M": 6, "1Y": 12, "5Y": 60, "10Y": 120, "Max": None}  # presets
MARKETS_DEFAULT_RANGE = "1Y"  # own assumption: range shown on first load
MARKETS_RSI_LEVELS = (30, 70)  # conventional oversold / overbought guides on the RSI panel
