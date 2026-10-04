"""Hand-written glossary and Concept Trainer content. Nothing here is generated or copied from
external text. Links point at pages in this app; where the app has no chart for a concept the
entry says so instead of pointing somewhere misleading."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Link:
    page: str  # app page file, e.g. "views/rates_page.py"
    label: str  # page title as shown in the navigation
    chart: str  # chart or section on that page


@dataclass(frozen=True)
class Term:
    key: str
    name: str
    definition: str
    why_financing: str
    links: tuple[Link, ...] = field(default_factory=tuple)
    not_charted: str = ""  # why there is no chart, when links are empty
    # Concept Trainer answers (four prompts per concept)
    what: str = ""
    why_moves: str = ""
    which_chart: str = ""
    desk_action: str = ""


SUMMARY = "views/summary_page.py"
CLIENT = "views/client_page.py"
DESK = "views/desk_page.py"
CAPITAL = "views/capital_page.py"
STRESS = "views/stress_page.py"
MARKETS = "views/markets_page.py"
RATES = "views/rates_page.py"
ASSUMPTIONS = "views/assumptions_page.py"

PAGE_TITLES = {SUMMARY: "Summary", CLIENT: "Client view", DESK: "Desk view", CAPITAL: "Capital",
               STRESS: "Stress lab", MARKETS: "Markets", RATES: "Rates & Liquidity",
               ASSUMPTIONS: "Assumptions"}


def L(page: str, chart: str) -> Link:
    return Link(page, PAGE_TITLES[page], chart)


NO_DATA = "No free official daily series for this was fetched, so this app has no chart for it."

TERMS: list[Term] = [
    Term("qe", "QE (quantitative easing)",
         "A central bank buys government bonds, and sometimes other assets, paying with newly "
         "created reserves.",
         "It adds cash (reserves) to the system and removes bonds from it, so repo rates tend to "
         "sit lower relative to policy rates and some bonds become scarce to borrow.",
         (L(RATES, "BoE reserve balances vs APF gilt holdings"),
          L(RATES, "Liquidity held at the Eurosystem (DF + CA − MLF)")),
         what="Central bank bond buying paid for with new reserves.",
         why_moves="It grows when a central bank decides to ease policy, usually with rates already "
                   "near their lower limit.",
         which_chart="Rates & Liquidity: BoE reserves vs APF gilt holdings (the APF line rises "
                     "during QE).",
         desk_action="Expect plenty of cash and less collateral: secured rates soften against policy, "
                     "so desks focus on sourcing collateral and watch for bonds trading special."),
    Term("qt", "QT (quantitative tightening)",
         "A central bank shrinks its bond holdings, either by not reinvesting bonds as they mature "
         "(passive) or by selling them (active).",
         "It drains reserves and returns bonds to the market, so cash gets scarcer and repo rates "
         "tend to drift up relative to the policy rate.",
         (L(RATES, "BoE reserve balances vs APF gilt holdings"),
          L(RATES, "Excess liquidity (official ECB series)")),
         what="Central bank balance sheet reduction through run-off or sales.",
         why_moves="It follows central bank decisions to reverse QE; the pace is set by maturities "
                   "and any announced sales.",
         which_chart="Rates & Liquidity: BoE reserves vs APF gilt holdings (the APF line falls "
                     "during QT) and the euro area liquidity charts.",
         desk_action="Plan for more collateral supply and dearer cash: watch money market spreads "
                     "and term funding costs, especially into quarter-ends."),
    Term("reserves", "Reserves",
         "Commercial banks' deposits held at the central bank (at the BoE, reserve balances).",
         "Reserves are the most liquid asset banks hold. When they are plentiful, overnight rates "
         "sit near the floor of the policy corridor; when they get scarce, money market rates rise.",
         (L(RATES, "BoE reserve balances vs APF gilt holdings"), L(RATES, "SONIA minus Bank Rate")),
         what="Banks' cash balances at the central bank.",
         why_moves="QE adds reserves, QT and government cash moves drain them, and banks shift "
                   "them around reporting dates.",
         which_chart="Rates & Liquidity: BoE reserve balances (weekly).",
         desk_action="Compare the level with banks' likely demand; as reserves fall, lock in term "
                     "funding earlier and price overnight cash less cheaply."),
    Term("excess_liquidity", "Excess liquidity",
         "In the euro area: banks' current account holdings above their minimum reserve "
         "requirements, plus the deposit facility, minus marginal lending.",
         "While it is large, €STR trades just under the ECB deposit facility rate; as it shrinks, "
         "short-term euro rates can drift upwards.",
         (L(RATES, "Excess liquidity (official ECB series)"),
          L(RATES, "Liquidity held at the Eurosystem (DF + CA − MLF)")),
         what="Central bank money held by banks beyond what rules require.",
         why_moves="It rises with asset purchases and lending operations, and falls with QT, loan "
                   "repayments and growth in banknotes or government deposits.",
         which_chart="Rates & Liquidity: Excess liquidity (official ECB series).",
         desk_action="Track the trend: a steady fall argues for building term euro funding and "
                     "watching €STR against the deposit rate."),
    Term("gc", "GC (general collateral) repo",
         "A repo against any bond from a broad basket of acceptable securities; its rate is the "
         "benchmark rate for secured overnight funding.",
         "It sets the base cost of financing long bond positions and the return on cash lent "
         "against collateral.",
         not_charted=NO_DATA,
         what="Repo against a basket of acceptable bonds rather than a specific one.",
         why_moves="It follows the policy rate and moves with the balance of cash against "
                   "collateral in the market.",
         which_chart="None in this app (no free official GC series was fetched).",
         desk_action="Fund general inventory at GC and earn GC on surplus cash; compare GC with "
                     "SONIA to see how tight secured funding is."),
    Term("specials", "Specials",
         "A specific bond in high demand to borrow trades 'special': its repo rate is below the "
         "GC rate.",
         "Holders of a special bond can fund it cheaply or lend it for a fee; anyone short of it "
         "pays more to borrow it.",
         not_charted=NO_DATA,
         what="A bond whose repo rate is below GC because many want to borrow it.",
         why_moves="Short positions, futures delivery demand and scarce supply after central bank "
                   "buying all make a bond special.",
         which_chart="None in this app.",
         desk_action="Lend specials you own for the extra value; cover shorts early or switch them "
                     "to a cheaper bond."),
    Term("dmo", "DMO (UK Debt Management Office)",
         "The executive agency of HM Treasury that issues gilts and manages the government's cash.",
         "Gilt auctions add collateral and drain cash on settlement days, which affects repo "
         "rates around those dates.",
         not_charted=NO_DATA,
         what="The UK agency that issues gilts.",
         why_moves="Its issuance follows the government's financing plan and auction calendar.",
         which_chart="None in this app (issuance data was not fetched).",
         desk_action="Expect more collateral and less cash around large gilt settlements and "
                     "price repo for those dates accordingly."),
    Term("repo", "Repo",
         "Selling a security with an agreement to buy it back at a set price on a later date; "
         "economically a loan secured on the security.",
         "It is the core funding tool for dealers: positions are financed by repoing them out, "
         "and the haircut decides how much the dealer funds itself.",
         (L(CAPITAL, "Dealer T-accounts (incremental, one trade)"),
          L(SUMMARY, "Break-even balance-sheet charge and required spread")),
         what="A collateralised loan structured as a sale and repurchase.",
         why_moves="Repo rates follow the policy rate and the supply of cash against collateral, "
                   "with spikes over reporting dates.",
         which_chart="Capital: dealer T-accounts (the 'repo from street' liability).",
         desk_action="Fund positions in repo at the cheapest haircut and rate; spread maturities "
                     "so funding does not all roll on one date."),
    Term("reverse_repo", "Reverse repo",
         "The other side of a repo: buying a security with an agreement to sell it back; "
         "economically lending cash against collateral, or borrowing a specific bond.",
         "Dealers use it to source collateral, such as gilts for a collateral upgrade, and to "
         "invest surplus cash; it uses balance sheet.",
         (L(CAPITAL, "Collateral upgrade: how the dealer sources the gilts"),),
         what="Lending cash against a security, or borrowing the security.",
         why_moves="Its rate follows the same funding market as repo; demand rises when specific "
                   "bonds are needed.",
         which_chart="Capital: collateral upgrade gilt sources (reverse repo row).",
         desk_action="Use it to cover short positions or source collateral, and weigh its balance "
                     "sheet use against borrowing securities instead."),
    Term("haircut", "Haircut",
         "The discount applied to the value of collateral: lending 90 against 100 of stock is a "
         "10% haircut.",
         "It sets how much of a position the borrower funds itself and protects the lender if the "
         "borrower defaults and the collateral falls in value.",
         (L(CAPITAL, "PB: RWA against client margin"), L(DESK, "Dealer P&L by component")),
         what="The margin between a loan and the value of the collateral behind it.",
         why_moves="Haircuts rise when the collateral becomes more volatile or less liquid, or the "
                   "borrower looks riskier.",
         which_chart="Capital: PB RWA against client margin (with the supervisory haircut marked).",
         desk_action="Set client haircuts above the supervisory haircut to keep exposure low, and "
                     "raise them when volatility rises."),
    Term("sonia", "SONIA",
         "Sterling Overnight Index Average: the average rate banks pay on unsecured overnight "
         "sterling deposits, published by the Bank of England.",
         "It is the sterling floating benchmark: PB loans and TRS financing legs reset off it, and "
         "this app quotes costs as bp over SONIA.",
         (L(RATES, "SONIA minus Bank Rate"), L(SUMMARY, "All routes")),
         what="The sterling overnight benchmark rate.",
         why_moves="It follows Bank Rate, sitting slightly below it while reserves are plentiful.",
         which_chart="Rates & Liquidity: SONIA minus Bank Rate.",
         desk_action="Price floating legs as SONIA plus a spread and hedge fixed-rate exposure with "
                     "SONIA swaps."),
    Term("estr", "€STR (euro short-term rate)",
         "The ECB-published rate euro area banks pay on unsecured overnight borrowing.",
         "It is the euro floating benchmark for financing legs and swaps.",
         not_charted="€STR is loaded in the data layer (see the Assumptions source audit) but not "
                     "charted on its own page.",
         what="The euro overnight benchmark rate.",
         why_moves="It follows the ECB deposit facility rate, sitting just below it while excess "
                   "liquidity is large.",
         which_chart="None on a chart page; the source is listed in the Assumptions source audit.",
         desk_action="Price euro floating legs as €STR plus a spread and watch it against the "
                     "deposit rate as liquidity falls."),
    Term("ois", "OIS (overnight index swap)",
         "A swap exchanging a fixed rate for the compounded overnight rate (SONIA, €STR) over a "
         "term.",
         "It shows the market's expected average overnight rate and is the benchmark for term "
         "funding and term repo spreads.",
         not_charted=NO_DATA,
         what="A fixed-for-overnight-rate swap.",
         why_moves="It moves with expectations for the policy rate over the swap's term.",
         which_chart="None in this app (no OIS curve was fetched).",
         desk_action="Compare term repo with OIS of the same tenor to judge whether term funding is "
                     "cheap or dear."),
    Term("2s10s", "2s10s",
         "The 10-year government yield minus the 2-year yield.",
         "The curve's steepness affects the carry on financed bond positions and the choice between "
         "short and term funding; inversion often coincides with tight policy.",
         (L(RATES, "Curve slopes: 2s10s (10y minus 2y)"),),
         what="The slope of the yield curve between 2 and 10 years.",
         why_moves="Changing expectations for policy rates move the 2-year; growth, inflation and "
                   "term premium move the 10-year.",
         which_chart="Rates & Liquidity: 2s10s slope (US, euro area AAA, Germany).",
         desk_action="Fund carry trades with an eye on the slope: a steep curve rewards term "
                     "funding of short-dated assets less than a flat one."),
    Term("term_premium", "Term premium",
         "The extra yield investors demand to hold a long bond instead of rolling short ones.",
         "A rising term premium makes long bonds cheaper against expected short rates, changing "
         "the carry and collateral value of financed positions.",
         not_charted="It is not directly observable; model-based estimates were not fetched.",
         what="Compensation for holding duration rather than rolling short debt.",
         why_moves="Uncertainty about inflation and policy, heavy bond supply and reduced central "
                   "bank buying all push it up.",
         which_chart="None in this app.",
         desk_action="Expect long-end collateral values to swing more when term premium is rising, "
                     "and set haircuts with that in mind."),
    Term("ctd", "CTD (cheapest-to-deliver)",
         "The bond in a futures contract's deliverable basket that is cheapest for the seller to "
         "deliver.",
         "Basis traders hold it, so it is often in demand in repo and can trade special.",
         not_charted=NO_DATA,
         what="The cheapest bond to deliver into a bond future.",
         why_moves="It changes with yield levels, curve shape and the bonds' relative prices.",
         which_chart="None in this app.",
         desk_action="Watch repo on the CTD: its specialness changes the economics of basis trades "
                     "the desk finances."),
    Term("basis", "Basis (bond basis)",
         "The difference between a bond's cash price and the price implied by the futures "
         "contract (futures price × conversion factor).",
         "Basis trades (long bond, short future) are financed in repo, so the repo rate decides "
         "whether they make money.",
         not_charted=NO_DATA,
         what="Cash bond price minus the futures-implied price.",
         why_moves="Repo rates, delivery options and supply and demand for the cash bond and "
                   "futures all move it.",
         which_chart="None in this app.",
         desk_action="Finance basis trades in term repo to lock the funding cost and monitor "
                     "margin on the futures leg."),
    Term("implied_repo", "Implied repo rate",
         "The financing rate implied by buying the cash bond now and delivering it into the "
         "futures contract.",
         "If it is above the actual repo rate, a long basis position earns carry; it shows the "
         "funding cost priced into futures.",
         not_charted=NO_DATA,
         what="The funding rate embedded in a cash-and-futures position.",
         why_moves="It moves with the basis and with time to delivery.",
         which_chart="None in this app.",
         desk_action="Compare it with actual repo to decide whether to fund or unwind basis "
                     "positions."),
    Term("balance_sheet", "Balance sheet",
         "A bank's assets and liabilities; in this app, the incremental T-account each financing "
         "route adds.",
         "Balance sheet is scarce and carries a shadow cost (k): routes that add more assets need "
         "more spread to pay for it.",
         (L(CAPITAL, "Dealer T-accounts (incremental, one trade)"),
          L(SUMMARY, "Break-even balance-sheet charge and required spread")),
         what="The bank's assets and liabilities.",
         why_moves="Trades that add assets (loans, hedges, reverse repos) grow it; netting and "
                   "securities-for-securities trades can avoid that.",
         which_chart="Capital: dealer T-accounts.",
         desk_action="Charge each trade for the balance sheet it uses and prefer structures that "
                     "achieve the same economics with less."),
    Term("leverage_ratio", "Leverage ratio",
         "Tier 1 capital divided by total exposure (on-balance-sheet assets plus derivative and "
         "SFT add-ons), without risk weights.",
         "It binds on low-risk, high-volume business such as repo and prime brokerage; this app's "
         "return on leverage exposure (RoLE) is measured against it.",
         (L(CAPITAL, "Leverage exposure by component"), L(SUMMARY, "Break-even balance-sheet charge and required spread")),
         what="Capital as a share of unweighted exposure.",
         why_moves="Exposure grows with gross positions, derivative add-ons and surplus cash not "
                   "parked at the central bank.",
         which_chart="Capital: leverage exposure by component.",
         desk_action="Price trades for leverage use (break-even k) and net or compress where "
                     "possible, especially near reporting dates."),
    Term("rwa", "RWA (risk-weighted assets)",
         "Exposures multiplied by risk weights; capital requirements are a percentage of RWA.",
         "They decide the return on capital of each route; collateral and netting reduce them.",
         (L(CAPITAL, "RWA by counterparty"), L(DESK, "Return on RWA vs target")),
         what="Risk-adjusted exposure that capital is held against.",
         why_moves="Counterparty quality, collateral, margin and netting all change it.",
         which_chart="Capital: RWA by counterparty.",
         desk_action="Collateralise and net exposures to cut RWA, and require a spread that meets "
                     "the return-on-RWA target."),
    Term("sa_ccr", "SA-CCR",
         "The standardised approach to counterparty credit risk: exposure = 1.4 × (replacement cost "
         "+ potential future exposure).",
         "It drives the capital and leverage cost of a TRS; margining and netting lower it.",
         (L(CAPITAL, "TRS SA-CCR detail"), L(DESK, "TRS netting set: three cases"),
          L(STRESS, "Stock price shock: TRS counterparty exposure")),
         what="The standard regulatory formula for derivative counterparty exposure.",
         why_moves="Mark-to-market moves change replacement cost; notional, maturity and margin "
                   "change the potential future exposure.",
         which_chart="Capital: TRS SA-CCR detail (and the Stress lab price shock).",
         desk_action="Margin daily and net trades under one agreement to shrink the exposure."),
    Term("im", "Initial margin (IM)",
         "Collateral posted at the start of a trade to cover potential losses while a defaulted "
         "position is closed out.",
         "It protects the dealer; in this app the TRS IM reduces SA-CCR exposure and, if not paid "
         "interest, earns the dealer SONIA.",
         (L(DESK, "TRS return against IM remuneration"), L(CAPITAL, "TRS SA-CCR detail")),
         what="Up-front collateral against future losses.",
         why_moves="It is set by the asset's volatility and liquidity and by the counterparty's "
                   "credit.",
         which_chart="Desk view: TRS return against IM remuneration.",
         desk_action="Size IM to the asset's risk and agree how it is paid interest; both change "
                     "the trade's economics."),
    Term("vm", "Variation margin (VM)",
         "Collateral exchanged, usually daily, to settle mark-to-market moves on a trade.",
         "It keeps replacement cost near zero; without it, exposure grows with the price move.",
         (L(STRESS, "Stock price shock: TRS counterparty exposure"),),
         what="Daily settlement of mark-to-market changes.",
         why_moves="It moves with the trade's value every day.",
         which_chart="Stress lab: stock price shock (the TRS there is unmargined, so replacement "
                     "cost grows with the move once it exceeds the IM).",
         desk_action="Margin daily and chase calls promptly; unmet calls turn into counterparty "
                     "exposure."),
    Term("rehypothecation", "Rehypothecation",
         "Re-using collateral received from a client, such as prime brokerage client stock, to "
         "raise funding in the market.",
         "It is how a PB desk funds client margin loans; limits on it raise funding costs.",
         (L(CAPITAL, "Dealer T-accounts (incremental, one trade)"),),
         what="Re-using a client's collateral to raise your own funding.",
         why_moves="Client agreements and regulation limit how much can be re-used.",
         which_chart="Capital: dealer T-accounts (PB: client stock re-used in the street repo).",
         desk_action="Fund client loans by re-using their stock within the agreed limits, and "
                     "charge more where re-use is restricted."),
    Term("pb", "Prime brokerage (PB)",
         "A package of services for hedge funds, including margin loans secured on their "
         "securities.",
         "It is the on-balance-sheet route in this app: the dealer lends cash and funds it by "
         "repoing the client's stock.",
         (L(SUMMARY, "All routes"), L(CLIENT, "Cost table"), L(DESK, "Dealer P&L by component")),
         what="Margin lending and services for hedge funds.",
         why_moves="Its economics move with funding spreads, haircuts and the balance-sheet charge.",
         which_chart="Summary and Desk view (PB route).",
         desk_action="Price the margin loan above funding plus the balance-sheet charge and "
                     "re-use client stock to fund it."),
    Term("trs", "TRS (total return swap)",
         "A swap where one side pays an asset's total return and the other pays a floating rate "
         "plus a spread.",
         "It gives the client the exposure synthetically; the dealer holds the hedge, so it uses "
         "the dealer's balance sheet and creates counterparty exposure.",
         (L(SUMMARY, "All routes"), L(CAPITAL, "TRS SA-CCR detail"),
          L(STRESS, "Stock price shock: TRS counterparty exposure")),
         what="A swap of an asset's total return for a floating rate.",
         why_moves="Its value moves one-for-one with the asset; its spread moves with funding and "
                   "balance-sheet costs.",
         which_chart="Summary (TRS route) and Capital (TRS SA-CCR detail).",
         desk_action="Hedge with the physical asset, fund the hedge in repo, and take IM to cover "
                     "the counterparty exposure."),
    Term("delta_one", "Delta-one",
         "Products whose value moves one-for-one with an underlying asset, such as swaps, futures "
         "and exchange-traded funds.",
         "Financing, not volatility, drives the economics: desks compete on spread, balance sheet "
         "and dividend handling.",
         (L(DESK, "Dealer P&L by component"),),
         what="Linear products tracking an underlying one-for-one.",
         why_moves="Their value follows the underlying; their margins follow funding costs.",
         which_chart="Desk view: dealer P&L by component.",
         desk_action="Manage the funding, dividends and balance sheet behind the hedge; the price "
                     "risk is passed through."),
    Term("collateral_upgrade", "Collateral upgrade",
         "A client lends lower-quality collateral (such as equities) and receives higher-quality "
         "collateral (such as gilts) for a fee.",
         "It lets clients raise HQLA or cheap funding; the dealer's cost depends on how it sources "
         "the gilts.",
         (L(CAPITAL, "Collateral upgrade: how the dealer sources the gilts"),
          L(SUMMARY, "All routes")),
         what="Swapping weaker collateral for stronger collateral against a fee.",
         why_moves="Its fee moves with demand for HQLA and the dealer's cost of sourcing it.",
         which_chart="Capital: collateral upgrade gilt sources.",
         desk_action="Choose the cheapest way to source the gilts (borrow, reverse repo or "
                     "inventory) given balance sheet and HQLA limits."),
    Term("sdrt", "SDRT (Stamp Duty Reserve Tax)",
         "A UK tax of 0.5% on purchases of UK shares; AIM shares are exempt.",
         "It is a one-off cost that can dominate short holding periods and favours synthetic "
         "routes (TRS) over physical ones.",
         (L(CLIENT, "Cost table"),),
         what="A 0.5% tax on buying UK shares.",
         why_moves="It is fixed by law; its effect per year shrinks the longer the position is held.",
         which_chart="Client view: cost table (SDRT columns).",
         desk_action="Offer the TRS route where SDRT would dominate the client's cost, and check "
                     "the hedge's treatment."),
    Term("hqla", "HQLA (high-quality liquid assets)",
         "Assets such as central bank reserves and government bonds that count towards the "
         "liquidity coverage ratio.",
         "Banks must hold enough of them; lending them in an upgrade uses the dealer's HQLA.",
         (L(CAPITAL, "Collateral upgrade: how the dealer sources the gilts"),),
         what="Assets that count as liquid under liquidity rules.",
         why_moves="Holdings change with trading, central bank operations and regulation.",
         which_chart="Capital: HQLA change column in the gilt-source table.",
         desk_action="Charge for lending HQLA and avoid structures that drain it near reporting "
                     "dates."),
    Term("lcr", "LCR (liquidity coverage ratio)",
         "HQLA divided by stressed net cash outflows over 30 days; it must be at least 100%.",
         "It drives demand for HQLA and for funding longer than 30 days.",
         (L(CAPITAL, "Collateral upgrade: how the dealer sources the gilts"),),
         what="A rule that liquid assets must cover 30 days of stressed outflows.",
         why_moves="It changes with HQLA holdings and with the maturity of funding.",
         which_chart="Capital: HQLA change (illustrative only; the LCR itself is not modelled).",
         desk_action="Term out funding beyond 30 days and price trades that consume HQLA."),
    Term("turn", "Turn (quarter-end, year-end)",
         "Reporting dates when banks shrink their balance sheets for regulatory snapshots, making "
         "short-term funding over those dates scarcer and dearer.",
         "Repo and FX swap rates can spike over turns, so desks pre-fund or lock term funding.",
         (L(STRESS, "Street funding: lock term or roll through the turn"),),
         what="Funding pressure over quarter- and year-end reporting dates.",
         why_moves="Banks cut balance sheet use for snapshots, so cash over those dates is scarce.",
         which_chart="Stress lab: term vs rolling and the year-end turn preset (hypothetical).",
         desk_action="Lock term funding across the turn when the term premium is below the expected "
                     "spike, and price client trades for it."),
    Term("netting", "Netting",
         "Offsetting exposures to the same counterparty under a legally enforceable agreement.",
         "It reduces SA-CCR exposure and leverage add-ons, but only with a legally enforceable "
         "netting agreement.",
         (L(DESK, "TRS netting set: three cases"),),
         what="Offsetting exposures with one counterparty.",
         why_moves="It depends on the other trades in the netting set and the legal agreement.",
         which_chart="Desk view: TRS netting set, three cases.",
         desk_action="Put trades with a client under one enforceable agreement and pair offsetting "
                     "positions to cut exposure."),
]

PROMPTS = {
    "what": "What is it?",
    "why_moves": "Why does it move?",
    "which_chart": "Which chart in this app shows it?",
    "desk_action": "What does a desk do about it?",
}


def by_key() -> dict[str, Term]:
    return {t.key: t for t in TERMS}


def quiz_question(term_key: str, prompt: str, seed: int) -> dict:
    """Multiple choice: the correct answer plus three other concepts' answers to the same prompt,
    in a deterministic shuffle for the seed."""
    import random
    terms = by_key()
    correct = getattr(terms[term_key], prompt)
    # a "None in this app" answer is never a distractor for another "None" answer (ambiguous)
    others = [getattr(t, prompt) for t in TERMS if t.key != term_key
              and getattr(t, prompt) != correct
              and not (correct.startswith("None") and getattr(t, prompt).startswith("None"))]
    rng = random.Random(seed)
    options = rng.sample(sorted(set(others)), 3) + [correct]
    rng.shuffle(options)
    return {"term": term_key, "prompt": prompt,
            "question": f"{terms[term_key].name}: {PROMPTS[prompt]}",
            "options": options, "answer": options.index(correct)}
