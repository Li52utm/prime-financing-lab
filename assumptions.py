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

# UNVERIFIED: placeholder level. Update from the Bank of England IADB (series IUDSOIA).
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
IM_REMUNERATION_SPREAD_MIN = 0.0
IM_REMUNERATION_SPREAD_MAX = SONIA

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
DEFAULT_ASSET_CLASS = "large_cap"

# --- Collateral upgrade: gilt leg -----------------------------------------

GILT_REPO_SPREAD = 0.0000  # own assumption: gilt repo at roughly SONIA flat
GILT_HAIRCUT = 0.02  # own assumption: haircut when client repos the gilts it received
GILT_BORROW_FEE = 0.0010  # own assumption: dealer's annual cost of sourcing the gilts

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
SHADOW_COST_K_MAX = 0.030
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
DEFAULT_HAIRCUT_REGIME = "basel_3_1"

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
SACCR_EQUITY_RHO = {"single": 0.50, "index": 0.80}
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
INCLUDE_STREET_LEG = True
DEFAULT_GILT_SOURCE = "reverse_repo"  # one of reverse_repo, borrowed, inventory
# Where surplus cash from the street repo sits. "central_bank": BoE reserves, netted
#   against a same-currency liability under PRA Leverage Ratio (CRR) Art 429a
#   (verified text), so it adds no leverage exposure. "counted": placed elsewhere.
DEFAULT_SURPLUS_CASH_PLACEMENT = "central_bank"
TRS_MARGINED = False  # unmargined by default; IM held as NICA
TRS_MTM = 0.0  # dealer-side mark-to-market V at the calculation date

# --- Targets ------------------------------------------------------------------------
# Own assumption: gross annual return on RWA the desk needs.
TARGET_RORWA = 0.015
# Return on leverage exposure hurdle = SHADOW_COST_K (above).
