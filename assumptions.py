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
        "pb_margin": 0.20,
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
        "pb_margin": 0.30,
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
TRS_PASS_THROUGH = 1.00  # own assumption: 100% of gross dividend passed to TRS client
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

# Own assumption: shadow cost of balance sheet (annual, per GBP of balance sheet).
# It is also the hurdle for return on balance sheet (ROBS).
SHADOW_COST_K = 0.020
SHADOW_COST_K_MIN = 0.0  # slider bounds (own assumption)
SHADOW_COST_K_MAX = 0.060
