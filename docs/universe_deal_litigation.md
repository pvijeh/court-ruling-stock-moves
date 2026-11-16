# Deal and shareholder lawsuits, 2021 to Oct 2026: what happened to the stock

**What this is**
- A list of lawsuits over company deals and shareholder rights, decided or filed from 2021-01-01 to 2026-10-14, where a US-listed company was a party and a ruling could block, force or reprice a deal, or move at least $100M (or 2% of the company's market value).
- For each ruling it records the outcome, the stock move on the filing day and on the ruling day, the company's size when the suit was filed, and when the ruling first became public.
- Data: `data/universe/deal_litigation/cases.csv`. Code: `scripts/universe_deal_litigation.py`.
- This is historical research, not investment advice.

**Why it matters**
- The goal is to estimate, when a suit is filed or a trial ends, how much the stock will move when the judge rules. That needs ordinary cases too (dismissals, settlements, rulings that barely moved the stock), not just the famous ones.

**Headline**
- 48 distinct lawsuits, 64 rulings or case events, 72 company rows, 49 different tickers.
- Most rulings barely moved the stock: the median abnormal move on the ruling day was 1.3%. Only 7 of 57 measurable rows moved more than 5%.
- 23 rows (21 rulings) came out while the market was open, on a day nobody knew in advance.
- Coverage is good for written Delaware opinions and weak for New York and federal courts (see "How complete").

## Terms used

- **Delaware Court of Chancery**: the business court where most US companies are incorporated, so most deal fights land there. Judges rule alone (no jury) and post written opinions on no fixed date.
- **Delaware Supreme Court**: hears appeals from Chancery.
- **Specific performance**: a court order forcing a party to close a deal it signed, instead of paying damages.
- **Earnout**: extra money a buyer promised to pay sellers later if milestones are hit; a common source of suits.
- **Appraisal**: a suit where shareholders who were bought out ask the court to set a higher fair price.
- **Controlling shareholder (controller)**: an owner who effectively runs the company. Deals with a controller get stricter court review.
- **Derivative suit**: shareholders sue directors on the company's behalf; any money goes to the company. The company is a "nominal defendant".
- **Caremark claim**: a derivative claim that directors ignored red flags (oversight failure).
- **Motion to dismiss**: an early request to throw the case out before evidence is heard.
- **Post-trial opinion**: the judge's written decision after a trial.
- **Abnormal return**: the stock's close-to-close return minus the return of a benchmark fund over the same days (SPY for the market; XBI for drug and biotech companies). It strips out the market's own move.
- **Market cap**: shares outstanding (from the company's SEC data) times the share price.

## What was counted and how

**Where the cases came from**
- The Delaware courts' public opinion list (courts.delaware.gov/opinions): 4,488 Chancery and Supreme Court opinion entries for 2021 to 2026, of which 2,380 came from the Court of Chancery.
- Case names were matched to current and former listed-company names, which gave several hundred candidate opinions.
- About 400 opinion PDFs were downloaded and their conclusions read to decide what each ruling did.
- A handful of non-Delaware matters came from company 8-K filings found with EDGAR full-text search.

**What was kept**
- Cases with a listed party where the ruling could block, force or reprice a deal, rescind pay, or move at least $100M or 2% of market cap: merger-agreement enforcement, earnout and merger-damages suits, controller buyouts, executive pay, large oversight (Caremark) suits, a poison-pill injunction and one federal deal-block challenge.
- Each ruling that changed the outcome or the money is its own row (main ruling, then any remand or appeal), marked by the case_id suffix (`-appeal`, `-remand`, `-damages`).
- If both sides are listed (for example Williams and Energy Transfer), there are two rows, each scored from that company's side.

**What was left out**
- Government merger challenges (FTC/DOJ) and securities-fraud class actions; other parts of this project cover them.
- Books-and-records (Section 220) fights, lead-plaintiff and fee-only rulings, governance-only suits, and buyouts where no party was still listed (e.g. Pattern Energy, Mindbody, Anaplan).

**How each row was checked**
- Every row's outcome was checked against the conclusion of the opinion it cites. Rows are "high" confidence only where the opinion clearly states the result and the company match is certain (29 rows). "Medium" (36) means the outcome is clear but a date or amount came from memory or a nearby document; "low" (7) means the docket number, filing date or outcome is partly estimated, as the notes say.

**How the numbers were built**
- Prices: Yahoo daily closes. Ruling time: the opinion PDF's "last saved" stamp when it falls on the ruling date. This is an estimate: posting normally follows within minutes, but not always.
- If the ruling came after 4:00 pm ET, the next trading day counts as the ruling day. If the time is unknown, the ruling-day return covers two trading days (the day and the next), as the notes say.
- Market cap and trailing 12-month revenue at filing come from SEC XBRL data (`dei:EntityCommonStockSharesOutstanding` times a split-corrected price).
- revenue_at_stake and implied_move_before_decision are blank: deal suits rarely tie to a product's revenue, and no free option data exists for these past dates.

## How complete the list is

- **Good:** written Delaware opinions from 2021 to Oct 2026 involving well-known listed companies.
- **Missing or thin:**
  - New York Commercial Division and federal deal suits. Only one (U.S. Steel's challenge to the Nippon Steel block) is included. A known gap is the federal suit over Bristol-Myers Squibb's $6.4B Celgene contingent value rights.
  - Cases settled before any written opinion, and rulings given orally from the bench (transcripts are not on the opinion list).
  - Former listed companies whose names changed or which were acquired, where the name match failed.
  - CourtListener was barely used, because its free quota (50 per hour, 125 per day) is shared across several projects. That is the main reason non-Delaware coverage is thin.
- **Missing prices:** Yahoo has no history for delisted tickers (Twitter, Hill-Rom, Desktop Metal, Ebix, Endeavor, Walgreens, Skechers and others), and Energy Transfer's history restarts in July 2026. Those rows have blank returns, which is why 57 of 72 rows have a ruling-day move.

## Counts

**Rows by ruling year**
- 2021: 16
- 2022: 9
- 2023: 15
- 2024: 12
- 2025: 9
- 2026: 6
- Pending, no ruling yet: 5 (Albertsons v. Kroger, Endeavor, Skechers, WWE/TKO)

**Listed companies**
- Every one of the 48 lawsuits has at least one listed party (by design); 49 tickers in total.

**Outcomes (rows)**
- Win: 15, loss: 16, split: 16, dismissed: 13, settled: 6, withdrawn: 1, pending: 5
- For the listed company: good 27, bad 21, mixed 5, unknown 19. "Unknown" is mostly derivative suits, where the company is a nominal defendant and a plaintiff's win sends money to it.

**Size of the ruling-day move (abnormal, 57 rows with prices)**
- More than 5%: 7
- More than 10%: 3
- More than 25%: 1
- Median absolute move: 1.3%

**The 10 biggest ruling-day moves (abnormal)**
- AMC, Aug 11 2023: court approves the AMC settlement letting preferred units convert to common: -32.4% (two-day; time unknown)
- Nano Dimension, Mar 24 2025: ordered to close its Desktop Metal purchase: -17.1%
- Trump Media (DJT), Sep 16 2024: wins against its SPAC sponsor's claim for more shares: -10.4% (two-day)
- AMC, May 20 2024: Supreme Court affirms the settlement: +9.7%
- BridgeBio, Dec 29 2022: Eidos buyout suit dismissed: +7.8% (two-day)
- Oracle, Jan 21 2025: Supreme Court affirms the NetSuite judgment for Ellison: +6.3%
- Carvana, Jun 30 2022: suit over the Garcia direct offering survives dismissal: -5.6% (two-day)
- Match Group, Apr 4 2024: Supreme Court partly revives the IAC separation suit: -4.5%
- Yatra, Aug 30 2021: its suit against Ebix dismissed: -4.1%
- Tesla, Jan 30 2026: fee opinion on directors returning about $277M: +3.6%
- Some of these moves may not be caused by the ruling: AMC and DJT were very volatile stocks, and other news on the same day was not checked. The ruling-day number measures timing only.

## Which outcomes can be traded on fast

**The question**
- Peter's model is Liquidia: a court order posted at 11:15 ET, a company press release about two hours later, and a 57% fall. Which deal rulings look like that: published during market hours (9:30 to 16:00 ET), with no date set in advance?

**Answer**
- 23 rows (21 rulings) came out during market hours on an unscheduled day. That covers every Chancery and Supreme Court opinion in the list; none had a preset date. Another 15 came out before the open or after the close, and 29 have no time.
- Median lead over the company's own release: about 2,400 minutes (40 hours), from only 2 rows. Companies rarely file an 8-K about these rulings, and the 8-K match (one mentioning a court within three days) was not checked by hand, so treat this as weak.
- Median minutes to half move: 51 minutes, from 7 rows with 1-minute bars (Polygon, only about the last two years). It is noisy because most moves were small.
- In this case type, rulings that come out during trading hours almost never move the stock much. The same court-site alert idea that works for drug-patent rulings has little to trade on here.

**The 10 best examples (largest abnormal move, during market hours, no preset date)**
- AMC, May 20 2024, about 14:10: Supreme Court affirms the stock-conversion settlement: +9.7%
- Oracle, Jan 21 2025, about 09:34: NetSuite judgment affirmed: +6.3%; 8-K next day; half the move in 194 minutes
- Yatra, Aug 30 2021, about 12:54: suit against Ebix dismissed: -4.1%
- Tesla, Jan 30 2026, about 10:47: director-pay settlement fee opinion: +3.6%; half the move in 82 minutes
- AstraZeneca (Alexion), Sep 5 2024, about 10:35: liable for breaching the Syntimmune earnout: -2.8%
- Edwards Lifesciences, Jul 31 2024, about 11:24: dismissal of Valtech earnout suit affirmed: -2.6%
- Edwards Lifesciences, Dec 12 2023, about 15:07: Valtech earnout suit dismissed: +2.2%
- Tesla, Jun 6 2023, about 09:37: SolarCity judgment for Musk affirmed: +1.5%
- Brookfield, Jul 19 2022, about 14:11: GGP buyout dismissal affirmed: +1.5%
- Brookfield, Sep 20 2021, about 12:52: TerraForm dilution claims thrown out: -1.3%
- Close behind: Charter/Liberty Broadband (Jul 19 2023, 15:52, +1.3%) and the Supreme Court's Tornetta reversal reinstating Musk's pay (Dec 19 2025, 12:43, -1.1%, half the move in 24 minutes).
- Times are estimates from the PDF save stamp, so they may come before the public posting.

## Judgment

- The list is a solid base for Delaware deal and shareholder rulings since 2021 and includes the dull cases the earlier hand-picked study missed. It is not complete for New York or federal courts.
- Deal and shareholder rulings rarely move the stock much: a typical ruling moved it about 1%, and big moves came from small or meme-driven companies or from rulings that forced a deal (Nano Dimension).
- For fast trading, this case type looks weak: rulings come out in market hours with no warning, but the price moves are usually too small for a fast alert to matter.
- Next steps if worth it: add the New York and federal deal suits through CourtListener over several days within its quota, and add filing dates for rows still marked estimated.
