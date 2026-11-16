# Prior research: how stocks react to court rulings, and how fast

This is research, not investment advice. Nothing here recommends buying or selling any security.

**Who this is for:** someone who has never seen this repo and wants to know what is already known before we claim anything new.

## Summary

- **What this is:** a review of published studies, data vendors and trading strategies related to this repo's question. The question is how US stock prices move when a lawsuit outcome becomes public, and how fast.
- **Why it matters:** on Sept 30, 2025 a district-court order against Liquidia was posted on the court docket at 11:15 ET. The company's press release came about two hours later and the stock fell 57%. If the docket is often first, a fast public alert could be tradable. We want to say honestly whether anyone has measured that.
- **Where we looked:** Crossref, OpenAlex and Semantic Scholar (citation databases), SSRN and NBER (working-paper sites), arXiv, and the public websites of 16 legal-data and catalyst-calendar vendors. Every paper listed was checked to exist in Crossref. The 53 papers are in `data/prior_research/papers.csv`.
- **What we found:** stock reactions to lawsuits are well studied, going back to the 1970s. Almost all of those studies use daily prices and newspaper or court dates. We found one verified court-ruling study with intraday prices: Supreme Court decisions, where prices adjusted over hours and days, not minutes.
- **Still open:** we found no verified study that times when district-court, PTAB or ITC outcomes first become public during the trading day, or compares that time with the company's own release. That is the gap this repo can fill.

## Terms used below

- **Event study:** measures how a stock moved around a dated event, compared with what it would normally have done.
- **Abnormal return:** the part of a stock's move not explained by the overall market that day (or minute).
- **Intraday:** within a single trading day, using minute or trade-by-trade prices instead of one closing price per day.
- **Docket:** the court's running list of everything filed in a case. In federal courts it is kept in **PACER** (the paid public website) and **ECF** (the electronic filing system that feeds it).
- **Hatch-Waxman / Paragraph IV:** the 1984 law that lets a generic drug maker challenge a brand drug's patent before launching. A "Paragraph IV" filing is the generic's claim that the patent is invalid or not infringed. It usually leads to a district-court trial with no jury.
- **PTAB / IPR:** the Patent Trial and Appeal Board, part of the US patent office. An inter partes review (IPR) is a cheaper way to ask the board to cancel a patent.
- **ITC Section 337:** a trade law that lets the US International Trade Commission ban imports of products that infringe US patents.
- **Merger challenge:** a lawsuit by the Justice Department, the FTC or a state to block a merger.
- **Delaware deal litigation:** suits in the Delaware Court of Chancery (the state court where most US companies are incorporated) over mergers and board conduct.
- **Settlement:** the parties agree to end the case before a ruling.
- **Risk or merger arbitrage:** buying a takeover target after the deal is announced and betting it closes.
- **Litigation arbitrage:** any strategy that profits from mispriced legal outcomes. Used below only where a source uses the term.

## Lawsuits in general

**Main result: defendants lose, and the loss is bigger than the money at stake.**

- Bhagat, Brickley & Coles (1994) and Bhagat, Bizjak & Coles (1998) are the standard references. Using Wall Street Journal announcement dates, they report that defendants lose value when sued and plaintiffs gain less than defendants lose. UNVERIFIED: we could not retrieve either abstract, so the exact sizes (about 1% for defendants in the 1998 paper) are from general knowledge.
- Haslem (2005) finds that shareholders prefer a court decision to a settlement, even when the firm loses, and treats settling as a sign managers are protecting themselves.
- Cutler & Summers (1988) followed one case, Texaco v. Pennzoil. The dispute cut the two firms' combined value by over $3 billion, and the 1987 settlement restored about two-thirds of it.
- Securities class actions, where shareholders sue the company, are well covered by Griffin, Grundfest & Perino (2004) and Gande & Lewis (2009). Part of the drop is priced in before the suit is filed.
- Penalty studies find market losses much larger than legal penalties. Karpoff, Lee & Martin (2008) count 585 firms charged by the SEC for false accounting, with legal penalties averaging $23.5 million per firm. Karpoff, Lott & Wehrly (2005) found environmental losses about equal to the penalties.

## Patent and drug-patent rulings

**Main result: rulings move stocks by about 1% on average in broad samples; drug-patent rulings can move one stock by half.**

- Marco (2006) is the earliest verified study of patent-case outcomes, using patents litigated from 1977 to 1997. Resolving validity is worth about 1 to 1.5% of firm value, about as much as the patent grant itself. The author calls it the first study of its kind.
- Bessen & Meurer (2007) use stock drops at filing to estimate that a patent suit costs a defendant $28.7 million on average (median $2.9 million), far above legal fees.
- Henry (2013) finds firms lose 0.85% when a patent is ruled invalid and gain 0.7% when it is upheld and infringed. The journal is minor, so treat with care.
- Other filing-date studies cover IT (Raghu et al. 2008), smartphones (Nam et al. 2015), Taiwan (Shih et al. 2020) and defendants' cash (Tan & Yang 2014).
- **Drug patents:** Panattoni (2011) built a dataset of all Paragraph IV court decisions and studied the brand company's stock reaction. It is the closest prior work to Liquidia-style cases. It uses daily prices.
- Settlements in which the brand pays the generic to delay launch ("pay-for-delay") have their own event-study literature: Helland & Seabury (2016), Hartman et al. (2019) and Drake & McGuire (2025). These measure settlement announcements, not rulings.
- Branstetter, Chatterjee & Higgins (2016) show the stakes: early generic entry in blood-pressure drugs gained consumers $42 billion from 2000 to 2008.

## PTAB and ITC

**Main result: almost no stock-price research found.**

- Kruppert (2017), "Dispute the patent, short the stock," studies IPR petitions filed by a hedge-fund group (the Coalition for Affordable Drugs, linked to Kyle Bass) against drug patents. It is the only verified PTAB stock study we found, and it covers petition filings, not board decisions. UNVERIFIED: abstract not retrieved; our reading is that effects were mostly small.
- Mahaseth (2018) counts 412 IPRs against 230 drug patents from 2012 to 2018 and compares outcomes with district court. It has no stock prices.
- **ITC:** no verified Section 337 stock-reaction study found in this search. The ITC's statistics page (updated Feb 3, 2026) lists 48 complaints filed in fiscal 2025, which gives a sense of the yearly volume.

## Antitrust and merger challenges

**Main result: the most studied area, but almost all of it is about filings, indictments and agency decisions.**

- US merger challenges: Ellert (1976), Eckbo (1983), Stillman (1983), Eckbo & Wier (1985) and Eckbo (1992). These mostly use rival firms' stocks to ask whether blocked mergers were really anti-competitive. UNVERIFIED for most: abstracts not retrieved.
- Antitrust suits and indictments: Garbade, Silber & White (1982) on suit filings; Bosch & Eckard (1991) on price-fixing indictments; Bittlingmayer (1993) on early-1900s trust-busting; Bittlingmayer & Hazlett (1998) on the Microsoft case.
- Europe: Aguzzoni et al. (2013) find a surprise EU raid cuts a share price 2.89% and an infringement decision 3.57%, but later court judgments have no significant effect. Duso, Neven & Röller (2007) cover 167 EU merger decisions from 1990 to 2002. Günster & van Dijk (2016) cover EU cartel decisions.

## Jury verdicts

**Main result: big awards often barely move the stock.**

- Palmer & Sanders (2010) study 17 jury awards of $100 million or more. Their title states the result: most are ignored by the stock market.
- Karpoff & Lott (1999) study punitive damages. Cox & Means (1999) and Koku, Qureshi & Akhigbe (2001) cover lawsuit news and settlements more generally.

## Delaware deal litigation

**Main result: studied with full dockets, but with daily prices.**

- Badawi & Chen (2017) collected every docket entry in hundreds of Delaware derivative and merger cases filed from 2004 to 2011 and measured the stock reaction to each type of event. This is the closest prior work to a "complete docket" approach.
- Krishnan, Masulis & Thomas (2010) study merger lawsuits and deal outcomes.
- Jiang, Li, Mei & Thomas (2016) study appraisal petitions, where shareholders ask the court to set a higher buyout price (see Funds below).

## Supreme Court rulings: the closest intraday work

**Main result: prices took hours to days to absorb Supreme Court decisions.**

- Katz, Bommarito, Soellinger & Chen (2015) used both daily and intraday prices across more than 15 years. 79 of 211 cases (37%) showed an average 4.4% abnormal return over two trading sessions. They report that these moves "materialize over the span of hours and days, not minutes."
- Davis, Govindaraj & Suslava (2024) cover over 500 cases from 1948 to 2018. They find reactions both when the Court agrees to hear a case and at the decision, and no sign of leaks before decisions. They use daily data.
- **Why this differs from our cases:** the Supreme Court releases opinions on days it announces in advance, and reporters wait for them. A district-court order can appear on the docket at any minute with no notice.

## How fast prices absorb public news

**Main result: wire and TV news is priced within minutes; feeds that arrive early are profitable.**

- Patell & Wolfson (1984) found most of the reaction to earnings stories on the Dow Jones wire within 5 to 10 minutes. Busse & Green (2002) found prices react within seconds to a few minutes of CNBC segments. UNVERIFIED: both exact speeds from general knowledge, abstracts not retrieved.
- Rogers, Skinner & Zechman (2017) showed that SEC filings reached paying feed subscribers before the public website, and that the head start was profitable. Bolandnazar, Jackson, Jiang & Mitts (2020) study a period when the SEC accidentally sent filings to some investors early. These are the best published examples of "the primary source comes out before most investors see it," but they are about the SEC, not courts.
- Cuñat & Groen-Xu (2025) show firms time hard-to-read filings around the SEC's daily filing cutoff.
- **PACER/ECF timing:** no verified study found in this search that measures how long a federal court order takes from the judge's entry to public visibility on PACER, RECAP or a news wire.

## Vendors that sell litigation data or alerts

**Main result: many sell fast alerts to lawyers; none we found publishes its latency, and few publish prices.** All facts are from public pages read on Oct 14, 2026, with no login. "Not public" means we did not find a price.

- **PACER (the courts):** official source. $0.10 per page, most documents capped at $3, no fee under $30 a quarter. Many courts also publish feeds of new filings. UNVERIFIED: the PACER help page on these feeds returned "not found."
- **CourtListener / RECAP (Free Law Project, non-profit):** free archive of PACER material with docket alerts and an API. Its API docs say requests to fetch documents from PACER are usually done "within seconds" and that alerts can be sent by webhook. Speed of its alerts after a court posts an order: not public.
- **Docket Navigator:** US district patent cases, ITC and PTAB, with orders coded by hand into up to 29 fields, and a daily docket report. Price not public.
- **Lex Machina (LexisNexis):** all 94 federal district courts, 13 appeals courts, PTAB and some state courts. It claims over 10 million cases. Analytics product, not marketed for speed. Price not public.
- **UniCourt:** federal and state case search and monitoring. $59, $199 or $399 a month for its three plans ($590, $1,990 or $3,990 a year). API and enterprise pricing are custom.
- **Docket Alarm:** free plan of 5 actions a week. Pay-as-you-go is $39.99 a month plus $4 a document and $3 a day per case alert. A flat plan is $99 a user per month.
- **DocketBird:** says it delivers real-time filings with PDFs and webhooks. About $35 to $40 a month, billed yearly, for small plans.
- **PacerPro:** says it offers real-time federal and state dockets and documents. Price not public.
- **Law360:** says it offers real-time news on high-stakes cases and covers 62,000+ companies. It is journalism, so its timing is after the docket. Price not public.
- **Law.com Radar:** says it offers real-time litigation alerts covering federal courts and 2,600+ county courts. Price not public.
- **Patexia:** PACER, PTAB, USPTO and ITC data. Price not public.
- **Unified Patents:** free daily patent-litigation alerts and PTAB tools.
- **Courtroom View Network:** video of trials, over 1,000 trials archived. $99 a month for one person, $399 a month for up to six.
- **Bloomberg Law dockets and Trellis:** pages blocked our browser (HTTP 403). Not verified.
- **BioPharmCatalyst:** a daily-updated calendar of FDA dates for biotech stocks. Court coverage not verified. Price not verified. **Evaluate:** page not reviewed.
- **What none of them publish:** how many minutes after a court posts an order the alert arrives, or how that compares with the company's press release.

## Funds and strategies that trade legal outcomes

**Main result: documented examples exist, but none publishes a court-docket speed strategy.**

- **Short-and-challenge:** a group linked to hedge-fund manager Kyle Bass filed IPR petitions against drug patents, and the paper studies whether this let a fund profit by shorting the patent owners (Kruppert 2017). It is the best documented case of a fund trading a patent-office proceeding. UNVERIFIED: abstract not retrieved, so filing years and results are not checked here.
- **Appraisal arbitrage:** Jiang et al. (2016) report that shareholders filing appraisal petitions in Delaware earned an average 32.9% a year before costs (median 19.3%) over 2000 to 2014. The paper's title uses the phrase "litigation arbitrage."
- **Merger arbitrage:** Mitchell & Pulvino (2001) studied 4,750 deals from 1963 to 1998. Merger challenges are one of the main risks these funds price.
- **Litigation-outcome contracts:** Hughes (2026) proposes exchange-traded contracts that pay out on court events such as rulings or settlements. This is a proposal, not an existing fund.
- UNVERIFIED: event-driven hedge funds and litigation-finance firms are widely reported to trade around court cases. We found no public document describing a strategy built on reading court dockets before the company's release.

## How we checked, and limits

- Every paper in the CSV resolved in Crossref by DOI. Titles, authors, years and journals come from Crossref.
- The `main_finding` column says "Abstract:" when it paraphrases the abstract. It is marked UNVERIFIED when we could not retrieve one; that applies to 23 of the 53 papers.
- Semantic Scholar's search API rate-limited us, so we may have missed recent working papers. Law-review articles without DOIs are under-covered.
- Negative findings mean "no verified study found in this search," not "no one has done it."

## What our study would add

- **Full case list instead of picked cases:** past work uses newspaper-reported cases, single famous cases or one case type. This repo starts from court records for every ruling in scope (drug patents, PTAB, ITC, merger challenges, jury verdicts, antitrust, Delaware) so that small and ignored cases count too.
- **Minute the outcome first became public:** past ruling studies use the day. We record the docket entry's time and line it up with minute-level prices.
- **Lead over the company's release:** we measure how many minutes the court record came before the first press release or 8-K, and how much of the move had happened by then. No verified study found does this for courts. The closest are the SEC feed studies.
- **How much of the move was left:** the README's early sample shows 6 of 7 large moves still had at least 66% of the move left one minute after filing. A full sample tests whether that holds.
- **Rulings that land during market hours with no set date:** past intraday court work covers the Supreme Court, which releases on announced days. District-court, PTAB and ITC orders arrive unannounced.
- **PTAB decisions and ITC rulings:** no verified stock study found for either. This would be new data, not a repeat.
- **Alert speed:** time how long free sources (PACER feeds, CourtListener) take to show an order. No vendor publishes this.

## Already done by others

- Average stock reaction to being sued, settling or losing, with daily prices: Bhagat and co-authors, Haslem, Gande & Lewis, Griffin et al.
- Patent-ruling and patent-filing reactions with daily prices: Marco, Bessen & Meurer, Henry.
- Paragraph IV decision reactions for brand drug makers with daily prices: Panattoni. Pay-for-delay settlement studies: Helland & Seabury, Drake & McGuire.
- Merger-challenge and antitrust filing reactions, US and EU: Eckbo, Stillman, Ellert, Aguzzoni et al., Duso et al.
- Jury verdict reactions for $100M+ awards: Palmer & Sanders.
- Delaware docket-level event study: Badawi & Chen.
- Supreme Court reactions, including intraday: Katz et al., Davis et al.
- Proof that an early primary-source feed is profitable, for SEC filings: Rogers et al., Bolandnazar et al.
- Returns to appraisal arbitrage and merger arbitrage: Jiang et al., Mitchell & Pulvino.

We should cite these and not repeat them. The claim we can defend is narrower than "first" or "biggest": a complete, minute-timed record of when court and patent-office outcomes first became public, and how far ahead of the company's own release that was.
