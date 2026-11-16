# Patent office trials (PTAB) since 2021: the complete list and the stock moves

**Summary**
- **What this is:** every patent office trial with a US-listed company on either side that was decided, settled or still open from 2021-01-01 to 2026-10-14. That is 5,074 trials, 6,597 company rows and 478 tickers, in `data/universe/ptab/cases.csv`.
- **Why it matters:** to estimate how much a stock moves when a patent trial ends, you need every trial, including the ones where nothing happened, not a list of famous ones.
- **Where we looked:** the US Patent and Trademark Office's public trial system (P-TACTS), the decision documents themselves, SEC filings for company size and revenue, and Polygon for prices.
- **What we found:** the median decision-day move, after taking out the market's move, is 1.2%. Only 30 of 1,746 measured rows moved more than 10%.
- **Speed:** 958 Board decisions were posted while the market was open, on a day nobody announced. Where 1-minute prices exist, the stock made half its move in a median 48 minutes.
- **Still open:** prices only go back to 2024-10 (see below), so older decisions have no move.

**Terms used here**
- **PTAB** (Patent Trial and Appeal Board): the patent office's court. Anyone can ask it to cancel a patent.
- **IPR** (inter partes review) and **PGR** (post-grant review): the two kinds of PTAB trial. A PGR must be filed within 9 months of the patent being granted and can use more grounds.
- **Petitioner:** the side asking to cancel the patent, usually a company that has been sued over it. **Patent owner:** the side defending it.
- **Institution:** the Board's decision, about 6 months after filing, on whether to hold a trial at all. **Institution denied** means no trial and the patent survives.
- **Final written decision:** the ruling at the end of a trial, due by law about 12 months after institution. The Board does not announce the day or the time.
- **Adverse judgment:** the patent owner gives up the challenged claims, which counts as a petitioner win.
- **Abnormal return:** the stock's close-to-close return minus the benchmark's (the S&P 500 fund SPY, or the biotech fund XBI for drug and biotech companies). It strips out the market's move that day.

**What was counted and how**
- Every IPR and PGR filed from 2019 on was pulled from the public P-TACTS search; trials that ended before 2021 were dropped. The USPTO's official data API needs a key we don't have (it returns 401).
- Party names were matched to SEC lists of exchange-listed companies, plus subsidiaries and former names ("Google LLC" counts as Alphabet). Matches that looked wrong on reading were removed, for example Biofrontera AG (the German former parent) is not Biofrontera Inc.
- One row per trial per listed company. Both sides are listed in 961 trials, so they have two rows.
- Final written decisions were read from the decision PDF: the line under the title says whether all, some or none of the challenged claims were cancelled.
- The posting time is the minute the Board's document appeared in P-TACTS. A document posted after 4pm or on a weekend counts against the next trading day. Where only the date is known, the move is the 2-day return, and the notes say so.

**How complete the list is**
- The trial list itself should be complete for IPR and PGR: the search returns every trial number by year.
- The company matching is not complete. Private companies and patent-holding firms are correctly left out, but a listed company filing under an unusual subsidiary name can be missed. 295 rows are marked low confidence; the notes say why.
- Outcomes are blank for 63 rows: the code could not read a result from the decision document or the trial status.
- Prices: Yahoo, the planned source, refused every request for the whole run (HTTP 429), so prices come from Polygon's free tier, which goes back about 2 years. 1,746 of 6,266 decided rows have a decision-day move. Market value at filing is filled only where the filing date is inside that window.
- Company press releases: listed companies almost never file an 8-K (the SEC form for material news) about a PTAB decision, so the company release time is nearly always blank.

**Counts per year (trials, by the year the trial ended)**
- 2021: 851
- 2022: 783
- 2023: 850
- 2024: 742
- 2025: 1,078
- 2026: 529
- Still pending: 241

**How the trials ended**
- final written decision: 1,719 trials
- institution denied (Board refused to hold a trial): 1,652 trials
- terminated on settlement: 1,252 trials
- pending: 240 trials
- dismissed: 119 trials
- adverse judgment (patent owner gave up the challenged claims): 92 trials

**Outcome split (company rows)**
- Petitioner rows: win means the patent's claims were cancelled; patent owner rows: win means the patent survived.
- loss: 2,280
- win: 1,804
- settled: 1,570
- split: 401
- pending: 327
- dismissed: 152
- blank: 63
- For the listed company: good 1,804, bad 2,280, mixed 401, unknown 2,112 (settlements and dismissals are unknown).

**Stock moves on the decision day (abnormal, close to close)**
- Measured rows: 1,746. Median absolute move: 1.2%.
- More than 5%: 128. More than 10%: 30. More than 25%: 1.
- A move on the decision day does not prove the decision caused it. For large companies (Ford, Micron, Ericsson) a big move that day is almost certainly other news, such as earnings.

**The 10 biggest moves**
- **Cerence Inc. (CRNC)**, patent owner vs Samsung Electronics Co., Ltd.: IPR2024-01267, terminated on settlement, outcome for the company unknown. Posted 2025-11-20; abnormal move +29.0%.
- **DISH Network L.L.C. (SATS)**, petitioner vs SafeCast Limited LLC: IPR2023-01116, terminated on settlement, outcome for the company unknown. Posted 2025-06-05; abnormal move +17.9%.
- **Biofrontera Inc. (BFRI)**, petitioner vs Sun Pharmaceutical Industries, Inc.: IPR2024-00874, institution denied (Board refused to hold a trial), outcome for the company bad. Posted 2024-11-12; abnormal move +17.8%.
- **AppLovin Corp (APP)**, petitioner vs Intent IQ, LLC: IPR2026-00330, institution denied (Board refused to hold a trial), outcome for the company bad. Posted 2026-08-06; abnormal move -17.4%.
- **ERICSSON LM TELEPHONE CO (ERIC)**, petitioner vs Innovative Sonic Limited: IPR2024-01145, institution denied (Board refused to hold a trial), outcome for the company bad. Posted 2025-01-24; abnormal move -14.1%.
- **Fossil Group, Inc. (FOSL)**, petitioner vs OMNI MEDSCI, INC.: IPR2025-01249 (3 trials decided that day), institution denied (Board refused to hold a trial), outcome for the company bad. Posted 2025-12-01; abnormal move +13.9%.
- **FORD MOTOR CO (F)**, petitioner vs AutoConnect Holdings LLC: IPR2025-01342 (3 trials decided that day), institution denied (Board refused to hold a trial), outcome for the company bad. Posted 2026-05-12; abnormal move +12.6%.
- **FORD MOTOR CO (F)**, petitioner vs AutoConnect Holdings LLC: IPR2026-00171 (3 trials decided that day), institution denied (Board refused to hold a trial), outcome for the company bad. Posted 2026-05-13; abnormal move +12.6%.
- **Cytek Biosciences, Inc. (CTKB)**, petitioner vs Beckman Coulter, Inc.: IPR2025-01319, institution denied (Board refused to hold a trial), outcome for the company bad. Posted 2025-11-20; abnormal move +12.3%.
- **CommScope Technologies LLC (COMM)**, petitioner vs Belden, Inc.: IPR2023-01061 (2 trials decided that day), final written decision, outcome for the company good. Posted 2024-12-18; abnormal move +12.2%.

**Which outcomes can be traded on fast**
- Only the Board's own decisions count here (final written decisions, institution denials, adverse judgments). Settlements and dismissals are filed by the parties, who know the outcome first.
- 958 of 4,548 Board-decision rows were posted while the market was open (9:30 to 16:00 ET) on a day nobody announced in advance. 3,751 of those 4,548 have a posting minute.
- Median lead over the company's own release: not measurable; no company in these rows filed an 8-K with a time on the decision day.
- Median minutes to half the day's move: 48 minutes, over 418 rows with 1-minute prices (938 rows had minute data; a move too small to time leaves it blank).
- 43 of the 751 market-hours rows with a price moved more than 5%.

**The 10 best examples (largest moves among market-hours Board decisions)**
- **Biofrontera Inc. (BFRI)**, petitioner vs Sun Pharmaceutical Industries, Inc.: IPR2024-00874, institution denied (Board refused to hold a trial), outcome for the company bad. Posted 2024-11-12 13:19; abnormal move +17.8%.
- **ERICSSON LM TELEPHONE CO (ERIC)**, petitioner vs Innovative Sonic Limited: IPR2024-01145, institution denied (Board refused to hold a trial), outcome for the company bad. Posted 2025-01-24 11:26; abnormal move -14.1%, half the day's move within 23 minutes.
- **FORD MOTOR CO (F)**, petitioner vs AutoConnect Holdings LLC: IPR2026-00171 (3 trials decided that day), institution denied (Board refused to hold a trial), outcome for the company bad. Posted 2026-05-13 09:46; abnormal move +12.6%, half the day's move within 75 minutes.
- **CommScope Technologies LLC (COMM)**, petitioner vs Belden, Inc.: IPR2023-01061 (2 trials decided that day), final written decision, outcome for the company good. Posted 2024-12-18 14:03; abnormal move +12.2%, half the day's move within 4 minutes.
- **Hesai Group (HSAI)**, petitioner vs Ouster, Inc.: IPR2023-01456, final written decision, outcome for the company good. Posted 2025-03-17 14:40; abnormal move +11.9%, half the day's move within 17 minutes.
- **MICRON TECHNOLOGY INC (MU)**, petitioner vs Yangtze Memory Technologies Company, Ltd: IPR2025-00190, final written decision, outcome for the company bad. Posted 2026-07-21 14:27; abnormal move +11.3%.
- **ROKU, INC (ROKU)**, petitioner vs Dolby International AB: IPR2024-01354, institution denied (Board refused to hold a trial), outcome for the company bad. Posted 2025-04-03 12:40; abnormal move -10.7%, half the day's move within 94 minutes.
- **Shoals Technologies Group, Inc. (SHLS)**, patent owner vs Voltage, LLC: IPR2024-00877, institution denied (Board refused to hold a trial), outcome for the company good. Posted 2024-11-22 12:58; abnormal move +9.5%, half the day's move within 110 minutes.
- **MICRON TECHNOLOGY INC (MU)**, petitioner vs Yangtze Memory Technologies Company, Ltd: IPR2024-00792, final written decision, outcome for the company bad. Posted 2025-11-05 13:28; abnormal move +8.6%.
- **Genius Sports Ltd (GENI)**, petitioner vs SportsCastr Inc.: IPR2024-01308 (2 trials decided that day), final written decision, outcome for the company good. Posted 2026-03-04 09:30; abnormal move -7.3%.

**Hand-check**
- "Material" means the patent likely covers a product that is a large share of the company's revenue. It is a rule, not a reading of each patent: a patent owner with under $500M revenue, or a drug or device company with under $2B (petitioners under $1B). 399 rows are flagged.
- All flagged rows plus a fixed random 50 of the rest (449 rows) were checked: party name against the company, and the outcome against a second reading of the PTAB record. 448 agree and are marked high confidence; the rest say so in the notes.
- Revenue at stake (the product's own revenue) is not filled: it needs reading each 10-K by hand.

**Reproduce**
- `python scripts/universe_ptab.py artifacts pdfs prices facts minutes releases` downloads (slow: the USPTO and Polygon rate limits make it hours); `python scripts/universe_ptab.py` rebuilds the CSV and this page from the cache in `data/universe/ptab/raw/`.

This is historical research, not investment advice.
