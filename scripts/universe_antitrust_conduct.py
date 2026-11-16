"""Complete list of government antitrust conduct suits (not mergers), 2021-today.

Covers DOJ, FTC and state attorney general suits about business conduct
(monopolization, exclusive deals, price fixing, no-poach, app-store and ad-tech
practices) against US-listed companies, plus private antitrust cases with a
listed defendant that reached a liability ruling or verdict.

Steps:
1. Discovery (cached under data/universe/antitrust_conduct/raw/):
   - FTC competition case list (ftc.gov legal library, mission=Competition,
     2021-01-01 to today). ftc.gov answers curl with 404, so the pages were
     saved from a normal Chrome visit; the saved HTML is in raw/ftc/.
   - DOJ Antitrust Division case list: justice.gov returns HTTP 401 to this
     machine (curl and Chrome), so the case slugs come from the Internet
     Archive's public capture index of justice.gov/atr/case/* (raw/doj_slugs.txt).
   - Google News RSS sweeps, two-month windows 2021-2026, for DOJ/FTC/AG
     antitrust suits, verdicts, rulings and settlements (raw/gnews/).
   The case and event list below (EVENTS) is the hand-checked result.
2. Price join: Yahoo daily closes (stock and SPY/XBI), SEC XBRL companyfacts
   (shares outstanding, revenue), Polygon 1-minute bars for events in the last
   ~2 years.

Output: data/universe/antitrust_conduct/cases.csv
Secrets (POLYGON_API_KEY, COURTLISTENER_API_TOKEN) are read from the
environment and never written anywhere.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import statistics
import time
import urllib.parse
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data" / "universe" / "antitrust_conduct"
RAW = OUT_DIR / "raw"
ET = ZoneInfo("America/New_York")
# sites like SEC EDGAR ask for a contact address in the User-Agent
CONTACT = os.environ.get("CONTACT_EMAIL", "contact@example.com")
SEC_UA = f"lawsuit-stock-moves research {CONTACT}"
WEB_UA = "Mozilla/5.0"  # Yahoo answers 429 to a full Chrome UA string from this box
GAP = {"sec.gov": 0.15, "polygon.io": 12.5, "yahoo.com": 0.5, "news.google.com": 1.5}
_last: dict[str, float] = {}


def _throttle(host: str) -> None:
    for key, gap in GAP.items():
        if host.endswith(key):
            wait = _last.get(key, 0) + gap - time.time()
            if wait > 0:
                time.sleep(wait)
            _last[key] = time.time()


def get(url: str, sub: str = "http", secret_param: str | None = None) -> str:
    """Cached GET. secret_param names a query parameter added at request time
    (from the environment) and left out of the cache key."""
    folder = RAW / sub
    folder.mkdir(parents=True, exist_ok=True)
    key = folder / (hashlib.sha1(url.encode()).hexdigest()[:20] + ".txt")
    if key.exists():
        return key.read_text()
    host = urllib.parse.urlparse(url).hostname or ""
    ua = SEC_UA if host.endswith("sec.gov") else WEB_UA
    full = url
    if secret_param:
        sep = "&" if "?" in url else "?"
        full = f"{url}{sep}{secret_param}={os.environ.get('POLYGON_API_KEY', '')}"
    for i in range(4):
        _throttle(host)
        try:
            r = requests.get(full, headers={"User-Agent": ua}, timeout=60)
        except requests.RequestException:
            time.sleep(3 * (i + 1))
            continue
        if r.status_code == 200:
            key.write_text(r.text)
            return r.text
        if r.status_code in (429, 503, 502):
            time.sleep(15 * (i + 1))
            continue
        return ""
    return ""


# ---------------------------------------------------------------------------
# Hand-checked case list. Parties: TICKER:Company:role, separated by ';'.
# kind: gov (DOJ/FTC/state AG) or private (private suit that reached a
# liability ruling or verdict).
# ---------------------------------------------------------------------------
CL = "https://www.courtlistener.com/docket/"
FTC = "https://www.ftc.gov/legal-library/browse/cases-proceedings/"
CASES_TXT = """
doj_google_search|gov|United States v. Google LLC (search)|D.D.C.|1:20-cv-03010|{CL}18552824/united-states-of-america-v-google-llc/|2020-10-20|2023-09-12|2023-11-16|GOOGL:Alphabet Inc.:defendant|U.S. DOJ and states||yes
doj_google_adtech|gov|United States v. Google LLC (ad tech)|E.D. Va.|1:23-cv-00108|{CL}66753787/united-states-v-google-llc/|2023-01-24|2024-09-09|2024-09-27|GOOGL:Alphabet Inc.:defendant|U.S. DOJ and states||yes
doj_apple|gov|United States v. Apple Inc. (smartphones)|D.N.J.|2:24-cv-04055||2024-03-21|||AAPL:Apple Inc.:defendant|U.S. DOJ and states||yes
doj_visa|gov|United States v. Visa Inc. (debit)|S.D.N.Y.|1:24-cv-07214||2024-09-24|||V:Visa Inc.:defendant|U.S. DOJ||yes
doj_live_nation|gov|United States et al. v. Live Nation Entertainment|S.D.N.Y.|1:24-cv-03973||2024-05-23|2026-03-02|2026-04-15|LYV:Live Nation Entertainment:defendant|U.S. DOJ and states||no
doj_realpage_landlords|gov|United States et al. v. RealPage (amended to add landlords)|M.D.N.C.|1:24-cv-00710||2025-01-07|||CPT:Camden Property Trust:defendant;CWK:Cushman & Wakefield (Pinnacle):defendant;BX:Blackstone (LivCor):defendant|U.S. DOJ and states||yes
doj_aa_jetblue_nea|gov|United States v. American Airlines Group and JetBlue (Northeast Alliance)|D. Mass.|1:21-cv-11558||2021-09-21|2022-09-27|2022-11-18|AAL:American Airlines Group:defendant;JBLU:JetBlue Airways:defendant|U.S. DOJ and states||yes
doj_davita|gov|United States v. DaVita Inc. and Kent Thiry (criminal no-poach)|D. Colo.|1:21-cr-00229||2021-07-15|2022-03-28|2022-04-15|DVA:DaVita Inc.:defendant|U.S. DOJ||no
doj_sca|gov|United States v. Surgical Care Affiliates (criminal no-poach; UnitedHealth unit)|N.D. Tex.|3:21-cr-00011||2021-01-07|||UNH:UnitedHealth Group (Surgical Care Affiliates):defendant|U.S. DOJ||yes
doj_pilgrims|gov|United States v. Pilgrim's Pride (criminal chicken price fixing)|D. Colo.|1:20-cr-00330||2020-10-14|||PPC:Pilgrim's Pride:defendant|U.S. DOJ||yes
doj_teva|gov|United States v. Teva Pharmaceuticals USA (criminal generic-drug price fixing)|E.D. Pa.|2:20-cr-00200||2020-08-25|||TEVA:Teva Pharmaceutical Industries:defendant|U.S. DOJ||yes
doj_eggs|gov|United States et al. v. Cal-Maine Foods et al. (egg prices)|D.D.C. (consent filing)|||2026-06-30|||CALM:Cal-Maine Foods:defendant|U.S. DOJ and 17 states||yes
ftc_meta|gov|FTC v. Meta Platforms (Instagram/WhatsApp monopolization)|D.D.C.|1:20-cv-03590|{CL}18735353/federal-trade-commission-v-meta-platforms-inc/|2020-12-09|2025-04-14|2025-05-27|META:Meta Platforms:defendant|FTC||yes
states_facebook|gov|New York et al. v. Facebook (state AGs)|D.D.C.|1:20-cv-03589||2020-12-09|||META:Meta Platforms:defendant|48 state and territory AGs||yes
ftc_amazon|gov|FTC et al. v. Amazon.com (marketplace monopolization)|W.D. Wash.|2:23-cv-01495||2023-09-26|||AMZN:Amazon.com:defendant|FTC and states||yes
ftc_amazon_ads|gov|FTC et al. v. Amazon.com (advertising auction prices)|W.D. Wash.|||2026-09-01|||AMZN:Amazon.com:defendant|FTC and 22 states||yes
dc_amazon|gov|District of Columbia v. Amazon.com (price parity)|D.C. Superior Court|2021 CA 001775 B||2021-05-25|||AMZN:Amazon.com:defendant|D.C. Attorney General||yes
ca_amazon|gov|California v. Amazon.com (price parity)|San Francisco Superior Court|CGC-22-601826||2022-09-14|||AMZN:Amazon.com:defendant|California Attorney General||yes
ftc_broadcom|gov|In the Matter of Broadcom Inc. (exclusive dealing)|FTC administrative|C-4750|{FTC}181-0205-broadcom-incorporated-matter|2021-07-02|||AVGO:Broadcom Inc.:respondent|FTC||yes
ftc_syngenta_corteva|gov|FTC et al. v. Syngenta and Corteva (pesticide loyalty programs)|M.D.N.C.|1:22-cv-00828|{FTC}191-0031-syngenta-corteva-ftc-v|2022-09-29|||CTVA:Corteva Inc.:defendant|FTC and states||yes
ftc_deere|gov|FTC et al. v. Deere & Company (right to repair)|N.D. Ill.|3:25-cv-50017|{FTC}211-0191-deere-company-ftc-v|2025-01-15|||DE:Deere & Company:defendant|FTC and states||yes
ftc_pepsico|gov|FTC v. PepsiCo (Robinson-Patman price discrimination)|C.D. Cal.|2:25-cv-00664|{FTC}221-0158-pepsico-inc-ftc-v|2025-01-17|||PEP:PepsiCo Inc.:defendant|FTC||yes
ftc_insulin_pbms|gov|In the Matter of Caremark Rx, Express Scripts and OptumRx (insulin rebates)|FTC administrative|9437|{FTC}221-0114-caremark-rx-zinc-health-services-et-al-matter-insulin|2024-09-20|||CVS:CVS Health (Caremark):respondent;CI:Cigna Group (Express Scripts):respondent;UNH:UnitedHealth Group (OptumRx):respondent|FTC||yes
ftc_zillow_redfin|gov|FTC v. Zillow Group and Redfin (rental listings agreement)|E.D. Va.|||2025-09-30|||Z:Zillow Group:defendant;RKT:Rocket Companies (Redfin):defendant|FTC and states||yes
ftc_ad_holdcos|gov|FTC et al. v. Dentsu, WPP Media and Publicis (ad boycott)|FTC with states (stipulated order)||{FTC}251-0061-dentsuwpp-mediapublicis-ftc-et-al-v|2026-04-15|||WPP:WPP plc:defendant|FTC and states||yes
ftc_mastercard|gov|In the Matter of Mastercard Inc. (debit routing)|FTC administrative|C-4795|{FTC}mastercard-inc-matter|2022-12-23|||MA:Mastercard Inc.:respondent|FTC||yes
ftc_oi_glass|gov|In the Matter of O-I Glass (worker noncompetes)|FTC administrative||{FTC}2110182-o-i-glass-inc-matter|2023-01-04|||OI:O-I Glass Inc.:respondent|FTC||yes
ftc_rollins|gov|In the Matter of Rollins Inc. (worker noncompetes)|FTC administrative||{FTC}251-0011-rollins-inc-matter|2026-04-15|||ROL:Rollins Inc.:respondent|FTC||yes
tx_blackrock|gov|Texas et al. v. BlackRock, State Street and Vanguard (coal output)|E.D. Tex.|6:24-cv-00437||2024-11-27|||BLK:BlackRock Inc.:defendant;STT:State Street Corp.:defendant|Texas and 12 states||yes
states_google_play|gov|Utah et al. v. Google (Play Store, state AGs)|N.D. Cal.|3:21-cv-05227||2021-07-07|||GOOGL:Alphabet Inc.:defendant|36 states and D.C.||yes
epic_apple|private|Epic Games v. Apple|N.D. Cal.|4:20-cv-05640|{CL}17442392/epic-games-inc-v-apple-inc/|2020-08-13|2021-05-03|2021-05-24|AAPL:Apple Inc.:defendant|Epic Games (private)||yes
epic_google|private|Epic Games v. Google (Play Store)|N.D. Cal.|3:20-cv-05671||2020-08-13|2023-11-06|2023-12-11|GOOGL:Alphabet Inc.:defendant|Epic Games (private)||no
sis_intuitive|private|Surgical Instrument Service Co. v. Intuitive Surgical|N.D. Cal.|3:21-cv-03496||2021-05-10|2025-01-13|2025-01-27|ISRG:Intuitive Surgical:defendant|Surgical Instrument Service (private)||no
regeneron_amgen|private|Regeneron v. Amgen (Praluent/Repatha bundling)|D. Del.|1:22-cv-00697||2022-05-27|2025-05-05|2025-05-14|AMGN:Amgen Inc.:defendant;REGN:Regeneron Pharmaceuticals:plaintiff|Regeneron / Amgen|REGN/AMGN|no
applied_medtronic|private|Applied Medical v. Medtronic (surgical sealers)|C.D. Cal.|8:23-cv-00268||2023-02-13|2026-01-20|2026-02-04|MDT:Medtronic plc:defendant|Applied Medical (private)||no
burnett_nar|private|Burnett v. National Association of Realtors (commissions)|W.D. Mo.|4:19-cv-00332||2019-04-29|2023-10-16|2023-10-31|BRK-B:Berkshire Hathaway (HomeServices):defendant|home sellers class (private)||no
kraft_eggs|private|Kraft Foods v. United Egg Producers / Cal-Maine (egg prices)|N.D. Ill.|1:11-cv-08808||2011-12-13|2023-10-23|2023-11-21|CALM:Cal-Maine Foods:defendant|Kraft, Kellogg, General Mills, Nestle (plaintiffs)||no
staley_gilead|private|Staley v. Gilead Sciences (HIV drug pay-for-delay)|N.D. Cal.|3:19-cv-02573||2019-05-14|2023-05-15|2023-06-30|GILD:Gilead Sciences:defendant;TEVA:Teva Pharmaceutical Industries:defendant|HIV patients and health plans (private)||no
""".replace("{CL}", CL).replace("{FTC}", FTC)

# Events. date = day the outcome first became public. time = ET clock time,
# only where a primary source gives it. ofc = outcome for company per ticker.
# known = decision date scheduled in advance. conf = high only where the
# primary document was checked in this repo's earlier hand review.
EVENTS_TXT = """
doj_google_search|liability ruling|2024-08-05|14:42|no|loss|GOOGL=bad|||high|{CL}18552824/1034/united-states-of-america-v-google-llc/|Google search monopoly ruling Mehta|Opinion ECF 1033 with redactions order ECF 1034 (time from RECAP entry 1034).
doj_google_search|remedies ruling|2025-09-02|16:05|no|split|GOOGL=good|||high|{CL}18552824/1437/united-states-of-america-v-google-llc/|Google search remedies ruling Chrome Mehta|Opinion ECF 1436 filed 16:05, after the close; no Chrome sale ordered.
doj_google_adtech|complaint|2023-01-24||no|pending|GOOGL=bad|||medium||Justice Department sues Google ad tech|DOJ complaint, E.D. Va.
doj_google_adtech|liability ruling|2025-04-17||no|loss|GOOGL=bad|||high|{CL}66753787/1411/united-states-v-google-llc/|Google ad tech monopoly ruling Brinkema|Opinion; clock time not checked (CourtListener quota spent).
doj_google_adtech|remedies ruling|2026-09-02||no|split|GOOGL=good|||medium||Google ad tech remedies Brinkema breakup|Judge refused to order AdX sale; decision unsealed Sept 16 2026.
doj_apple|complaint|2024-03-21||no|pending|AAPL=bad|||medium||Justice Department sues Apple smartphone monopoly|DOJ and 15 states plus D.C. complaint.
doj_apple|motion to dismiss ruling|2025-06-30||no|loss|AAPL=bad|||medium||Apple loses bid to dismiss Justice Department antitrust|Motion to dismiss denied; case pending.
doj_visa|complaint|2024-09-24||no|pending|V=bad|||medium||Justice Department sues Visa debit monopoly|DOJ complaint (news on Sept 23 evening said a suit was coming).
doj_visa|motion to dismiss ruling|2025-06-24||no|loss|V=bad|||medium||judge rejects Visa bid to dismiss debit card antitrust|Motion to dismiss denied; trial pending.
doj_live_nation|complaint|2024-05-23||no|pending|LYV=bad|||medium||Justice Department sues Live Nation Ticketmaster|DOJ and 30 states plus D.C.
doj_live_nation|summary judgment ruling|2026-02-18||no|split|LYV=mixed|||medium||judge Live Nation summary judgment trial pares claims|Some DOJ claims cut; case sent to a March jury trial.
doj_live_nation|settlement|2026-03-09||no|settled|LYV=good|||medium||Justice Department Live Nation settlement|DOJ settled one week into the jury trial; most states refused and kept trying the case.
doj_live_nation|jury verdict|2026-04-15||yes|loss|LYV=bad|||medium||Live Nation jury verdict monopoly states|Jury verdict for the states after deliberations began about Apr 10; post-trial motions pending.
doj_realpage_landlords|complaint|2025-01-07||no|pending|CPT=bad;CWK=bad;BX=bad|||medium||Justice Department sues landlords RealPage Camden Cushman|Amended complaint adding six landlords; LivCor is a Blackstone portfolio company and Pinnacle is a Cushman & Wakefield affiliate.
doj_realpage_landlords|settlement|2026-04-13||no|settled|CPT=good||53000000|low||Camden settles RealPage lawsuit|Camden settlement reported at $53M; not checked whether this is the DOJ case or the private class case.
doj_realpage_landlords|settlement|2026-06-18||no|settled|BX=good||7000000|low||LivCor settlement RealPage attorney general|LivCor $7M settlement announced by state AGs who are co-plaintiffs.
doj_realpage_landlords|settlement|2026-09-08||no|settled|CWK=good|||low||Pinnacle DOJ RealPage settlement|DOJ settlement with Pinnacle (Cushman & Wakefield affiliate).
doj_aa_jetblue_nea|complaint|2021-09-21||no|pending|AAL=bad;JBLU=bad|||medium||Justice Department sues American Airlines JetBlue alliance|Northeast Alliance complaint.
doj_aa_jetblue_nea|liability ruling|2023-05-19||no|loss|AAL=bad;JBLU=bad|||medium||judge American JetBlue alliance ruling|Bench ruling ordering the alliance ended.
doj_davita|indictment|2021-07-15||no|pending|DVA=bad|||medium||DaVita indicted no-poach Thiry|Criminal indictment for no-poach agreements.
doj_davita|motion to dismiss ruling|2022-01-28||no|loss|DVA=bad|||medium||DaVita Thiry lose bid to dismiss criminal antitrust|Motion to dismiss denied.
doj_davita|jury verdict|2022-04-15||yes|win|DVA=good|||medium||DaVita Thiry acquitted jury no-poach|Jury acquitted DaVita and Thiry.
doj_sca|indictment|2021-01-07||no|pending|UNH=bad|||low||Surgical Care Affiliates indicted no-poach|First criminal no-poach indictment; SCA is part of UnitedHealth's Optum.
doj_sca|dismissal|2023-11-28||no|dismissed|UNH=good|||low||Surgical Care Affiliates no-poach charges dismissed|DOJ moved to dismiss its last criminal no-poach case; exact date not checked against the docket.
doj_pilgrims|sentencing (plea accepted)|2021-02-23||no|settled|PPC=mixed||107900000|medium||Pilgrim's Pride sentenced price-fixing fine|Guilty plea accepted; $107.9M criminal fine.
doj_teva|deferred prosecution agreement|2023-08-21||no|settled|TEVA=mixed||225000000|medium||Teva deferred prosecution agreement price-fixing|DPA with $225M penalty and a pravastatin divestiture.
doj_eggs|complaint and settlement|2026-06-30||no|settled|CALM=good||3300000|medium||Justice Department egg producers Cal-Maine settlement|Complaint and settlement filed together; $3.3M is the total across three producers plus egg donations.
ftc_meta|motion to dismiss ruling|2021-06-28||no|dismissed|META=good|||medium||judge dismisses FTC Facebook antitrust complaint|Boasberg dismissed the FTC complaint with leave to amend, and the states' suit, the same day.
ftc_meta|motion to dismiss ruling|2022-01-11||no|loss|META=bad|||medium||judge FTC amended complaint Facebook proceed|Amended complaint allowed to proceed.
ftc_meta|summary judgment ruling|2024-11-13||no|split|META=mixed|||medium||judge Meta FTC summary judgment trial|Summary judgment denied in most part; trial ordered.
ftc_meta|liability ruling|2025-11-18|12:43|no|win|META=good|||high|{CL}18735353/694/federal-trade-commission-v-meta-platforms-inc/|Meta wins FTC antitrust trial|Judgment for Meta (ECF 694, 12:43 ET).
states_facebook|dismissal|2021-06-28||no|dismissed|META=good|||medium||states Facebook antitrust lawsuit dismissed|Same day as the FTC dismissal; stock move is shared with that row.
states_facebook|appeal ruling|2023-04-27||no|win|META=good|||medium||appeals court states Facebook antitrust dismissal upheld|D.C. Circuit affirmed dismissal.
ftc_amazon|complaint|2023-09-26||no|pending|AMZN=bad|||medium|{FTC}1910129-1910130-amazoncom-inc-amazon-ecommerce|FTC sues Amazon monopoly|FTC and 17 states.
ftc_amazon|motion to dismiss ruling|2024-09-30||no|split|AMZN=mixed|||medium|{FTC}1910129-1910130-amazoncom-inc-amazon-ecommerce|Amazon motion to dismiss FTC antitrust judge Chun|Mostly denied (some state claims dismissed); trial now set for 2027.
ftc_amazon_ads|complaint|2026-09-01||no|pending|AMZN=bad|||medium||FTC sues Amazon advertising auction states|FTC and 22 states.
dc_amazon|complaint|2021-05-25||no|pending|AMZN=bad|||medium||D.C. attorney general sues Amazon antitrust|
dc_amazon|dismissal|2022-03-18||no|dismissed|AMZN=good|||low||judge dismisses D.C. Amazon antitrust lawsuit|Trial-court dismissal; date not checked against the court record.
dc_amazon|appeal ruling|2024-08-22||no|loss|AMZN=bad|||low||appeals court revives D.C. Amazon antitrust lawsuit|D.C. Court of Appeals reinstated the case; date not checked against the court record.
ca_amazon|complaint|2022-09-14||no|pending|AMZN=bad|||medium||California sues Amazon antitrust|
ca_amazon|motion to dismiss ruling|2023-03-30||no|loss|AMZN=bad|||low||judge California Amazon antitrust lawsuit proceed demurrer|Demurrer overruled; date not checked against the court record.
ftc_broadcom|complaint and consent order|2021-07-02||no|settled|AVGO=mixed|||medium|{FTC}181-0205-broadcom-incorporated-matter|FTC Broadcom settle exclusive dealing|Proposed consent; final order Nov 4 2021.
ftc_syngenta_corteva|complaint|2022-09-29||no|pending|CTVA=bad|||medium|{FTC}191-0031-syngenta-corteva-ftc-v|FTC sues Syngenta Corteva|Syngenta is owned by ChemChina, not US-listed.
ftc_syngenta_corteva|motion to dismiss ruling|2024-01-12||no|loss|CTVA=bad|||medium|{FTC}191-0031-syngenta-corteva-ftc-v|judge Syngenta Corteva motion to dismiss FTC|Order denying motions to dismiss.
ftc_syngenta_corteva|settlement|2026-09-28||no|settled|CTVA=good||35000000|medium|{FTC}191-0031-syngenta-corteva-ftc-v|Corteva FTC settlement|Stipulated order; $35M payment. Syngenta still litigating.
ftc_deere|complaint|2025-01-15||no|pending|DE=bad|||medium|{FTC}211-0191-deere-company-ftc-v|FTC sues Deere repair|
ftc_deere|motion ruling|2025-06-09||no|loss|DE=bad|||medium|{FTC}211-0191-deere-company-ftc-v|Deere must face FTC lawsuit judge|Motion for judgment on the pleadings denied.
ftc_deere|settlement|2026-07-08||no|settled|DE=mixed|||medium|{FTC}211-0191-deere-company-ftc-v|Deere FTC settlement right to repair|Stipulated order; 10-year repair-software access.
ftc_pepsico|complaint|2025-01-17||no|pending|PEP=bad|||medium|{FTC}221-0158-pepsico-inc-ftc-v|FTC sues PepsiCo Walmart pricing|
ftc_pepsico|withdrawal|2025-05-22||no|withdrawn|PEP=good|||medium|{FTC}221-0158-pepsico-inc-ftc-v|FTC drops PepsiCo lawsuit|FTC voted to dismiss.
ftc_insulin_pbms|complaint|2024-09-20||no|pending|CVS=bad;CI=bad;UNH=bad|||medium|{FTC}221-0114-caremark-rx-zinc-health-services-et-al-matter-insulin|FTC sues pharmacy benefit managers insulin|Administrative complaint.
ftc_insulin_pbms|settlement|2026-02-04||no|settled|CI=mixed|||medium|{FTC}221-0114-caremark-rx-zinc-health-services-et-al-matter-insulin|Cigna Express Scripts settles FTC insulin|Express Scripts consent.
ftc_insulin_pbms|settlement|2026-03-24||no|settled|CVS=mixed|||low|{FTC}221-0114-caremark-rx-zinc-health-services-et-al-matter-insulin|CVS FTC insulin settlement|Proposed settlement first reported Mar 24 2026; FTC posted the consent order Jul 14 2026.
ftc_insulin_pbms|withdrawn for settlement|2026-06-12||no|settled|UNH=mixed|||low|{FTC}221-0114-caremark-rx-zinc-health-services-et-al-matter-insulin|OptumRx FTC insulin settlement|Order withdrawing the Optum respondents from adjudication to consider a settlement; final terms not checked.
ftc_zillow_redfin|complaint|2025-09-30||no|pending|Z=bad;RKT=bad|||medium|https://www.ftc.gov/legal-library/browse/cases-proceedings/zillow-groupredfin-corp|FTC sues Zillow Redfin|Redfin was owned by Rocket Companies by then.
ftc_zillow_redfin|settlement|2026-08-24||yes|settled|Z=mixed;RKT=mixed|||medium|https://www.ftc.gov/legal-library/browse/cases-proceedings/zillow-groupredfin-corp|Zillow Redfin FTC settlement|Settled hours before a scheduled trial.
ftc_ad_holdcos|complaint and settlement|2026-04-15||no|settled|WPP=mixed|||medium|{FTC}251-0061-dentsuwpp-mediapublicis-ftc-et-al-v|FTC WPP Publicis Dentsu|Complaint and stipulated order filed together. Publicis and Dentsu are not US-listed.
ftc_mastercard|consent order|2022-12-23||no|settled|MA=mixed|||medium|{FTC}mastercard-inc-matter|FTC Mastercard debit|Proposed consent; final May 30 2023.
ftc_oi_glass|consent order|2023-01-04||no|settled|OI=mixed|||medium|{FTC}2110182-o-i-glass-inc-matter|FTC noncompete O-I Glass|Worker noncompete consent order.
ftc_rollins|consent order|2026-04-15||no|settled|ROL=mixed|||medium|{FTC}251-0011-rollins-inc-matter|FTC Rollins noncompete|Consent agreement; final order Jun 22 2026.
tx_blackrock|complaint|2024-11-27||no|pending|BLK=bad;STT=bad|||medium||Texas sues BlackRock State Street Vanguard coal|Vanguard is private.
tx_blackrock|motion to dismiss ruling|2025-08-01||no|loss|BLK=bad;STT=bad|||medium||BlackRock lose bid to dismiss Texas climate lawsuit|Mostly denied.
states_google_play|complaint|2021-07-07||no|pending|GOOGL=bad|||medium||states sue Google Play Store|
states_google_play|settlement|2023-12-18||no|settled|GOOGL=mixed||700000000|medium||Google Play $700 million settlement states|Terms made public after the Epic verdict.
epic_apple|liability ruling|2021-09-10||no|split|AAPL=mixed|||medium||Epic Apple ruling Gonzalez Rogers|Apple won on federal antitrust claims, lost on California anti-steering claim.
epic_apple|appeal ruling|2023-04-24||no|split|AAPL=mixed|||medium||Ninth Circuit Epic Apple ruling|Ninth Circuit affirmed.
epic_apple|contempt ruling|2025-04-30||no|loss|AAPL=bad|||medium||Apple contempt Epic Gonzalez Rogers|Contempt order on anti-steering compliance.
epic_google|jury verdict|2023-12-11||yes|loss|GOOGL=bad|||medium||Epic Google jury verdict|Jury verdict at end of a scheduled trial.
epic_google|remedies ruling|2024-10-07||no|loss|GOOGL=bad|||medium||Google Play injunction Donato Epic|Permanent injunction opening Play Store.
epic_google|settlement|2025-11-04||no|settled|GOOGL=mixed|||low||Google Epic settlement Play Store|Comprehensive settlement filed; date not checked against the docket.
sis_intuitive|jury verdict|2025-01-27||yes|win|ISRG=good|||low||Intuitive Surgical antitrust jury Surgical Instrument Service|Verdict date from law-firm and trade-press reports.
sis_intuitive|appeal ruling|2026-08-13||no|loss|ISRG=bad|||low||Surgical robot monopoly suit revived jury instructions|Ninth Circuit revived the claims.
regeneron_amgen|jury verdict|2025-05-14||yes|loss|AMGN=bad;REGN=good||406800000|low||Regeneron Amgen jury verdict antitrust|$406.8M verdict for Regeneron (damages before any trebling).
applied_medtronic|jury verdict|2026-02-04||yes|loss|MDT=bad||382000000|low||Applied Medical Medtronic jury|$382M verdict.
burnett_nar|jury verdict|2023-10-31||yes|loss|BRK-B=bad||1785000000|medium||Realtors jury verdict commissions Burnett|$1.78B verdict against NAR, HomeServices and Keller Williams. Anywhere and RE/MAX settled before trial.
kraft_eggs|jury verdict|2023-11-21||yes|loss|CALM=bad||17700000|medium||Kraft egg price-fixing verdict Cal-Maine|Liability verdict Nov 21; $17.7M damages Dec 1 2023.
staley_gilead|jury verdict|2023-06-30||yes|win|GILD=good;TEVA=good|||medium||Gilead Teva HIV antitrust trial verdict|Jury verdict for defendants.
""".replace("{CL}", CL).replace("{FTC}", FTC)

PHARMA = {"TEVA", "GILD", "AMGN", "REGN"}

# 8-Ks matched by full-text search whose item text was read: False = the
# filing is about something else (shelf offering, credit deal, acquisition).
RELEASE_ABOUT_EVENT = {
    ("doj_google_search", "GOOGL", "2024-08-05"): True,
    ("doj_google_search", "GOOGL", "2025-09-02"): True,
    ("doj_google_adtech", "GOOGL", "2023-01-24"): True,
    ("doj_google_adtech", "GOOGL", "2025-04-17"): True,
    ("doj_live_nation", "LYV", "2024-05-23"): True,
    ("doj_aa_jetblue_nea", "AAL", "2021-09-21"): True,
    ("doj_aa_jetblue_nea", "JBLU", "2021-09-21"): True,
    ("doj_eggs", "CALM", "2026-06-30"): True,
    ("ftc_deere", "DE", "2025-01-15"): False,
    ("ftc_pepsico", "PEP", "2025-05-22"): False,
    ("ftc_zillow_redfin", "RKT", "2025-09-30"): False,
    ("ftc_zillow_redfin", "Z", "2026-08-24"): True,
    ("states_google_play", "GOOGL", "2021-07-07"): True,
    ("epic_google", "GOOGL", "2025-11-04"): False,
    ("kraft_eggs", "CALM", "2023-11-21"): True,
}

# Where the company's own 8-K came out before any other timed source.
FIRST_PUBLIC_OVERRIDE = {
    ("ftc_zillow_redfin", "2026-08-24"): (
        "company 8-K (Zillow, SEC EDGAR acceptance time; order signed Sat Aug 22)",
        "2026-08-24 09:04",
    ),
}

# Other news in the same return window, found by reading the day's headlines.
CONFOUNDS = {
    (
        "states_facebook",
        "2023-04-27",
    ): "CONFOUNDED: Meta reported Q1 2023 earnings after the close on Apr 26; the move is earnings, not the ruling",
    (
        "ftc_insulin_pbms",
        "2026-02-04",
    ): "CONFOUNDED: Cigna reported Q4 2025 earnings on Feb 5, inside the 2-day window",
    (
        "ftc_meta",
        "2021-06-28",
    ): "same day as the states' dismissal (states_facebook); one move, two rows",
    (
        "states_facebook",
        "2021-06-28",
    ): "same day as the FTC dismissal (ftc_meta); one move, two rows",
    (
        "ftc_oi_glass",
        "2023-01-04",
    ): "no news about the consent order found on Google News; the 2-day move is probably not about this order (not checked)",
    (
        "doj_google_search",
        "2024-08-05",
    ): "Aug 5 2024 was a market-wide sell-off; SPY -3%",
}

COLUMNS = [
    "case_id",
    "case_type",
    "case_name",
    "court",
    "docket_number",
    "docket_url",
    "ticker",
    "company",
    "company_role",
    "counterparty",
    "counterparty_ticker",
    "filed_date",
    "trial_start_date",
    "trial_end_date",
    "decision_date",
    "decision_time_et",
    "decision_known_in_advance",
    "decision_source_url",
    "outcome",
    "outcome_for_company",
    "days_filed_to_decision",
    "market_cap_usd_at_filing",
    "revenue_ttm_usd_at_filing",
    "revenue_at_stake_usd",
    "revenue_at_stake_share",
    "ret_filing_day",
    "abn_ret_filing_day",
    "ret_decision_day",
    "abn_ret_decision_day",
    "ret_decision_plus5",
    "adv_usd_20d_before_decision",
    "implied_move_before_decision",
    "settlement_amount_usd",
    "confidence",
    "sources",
    "notes",
    "first_public_source",
    "first_public_time_et",
    "time_precision",
    "during_market_hours",
    "company_release_time_et",
    "lead_minutes_vs_company_release",
    "minutes_to_half_move",
    "minute_data_available",
]


def load_tables() -> tuple[dict, list]:
    keys = [
        "id",
        "kind",
        "name",
        "court",
        "docket",
        "url",
        "filed",
        "trial_start",
        "trial_end",
        "parties",
        "cp",
        "cp_ticker",
        "bench",
    ]
    cases = {}
    for line in CASES_TXT.strip().splitlines():
        c = dict(zip(keys, line.split("|")))
        c["parties"] = [p.split(":") for p in c["parties"].split(";")]
        cases[c["id"]] = c
    ekeys = [
        "case",
        "label",
        "date",
        "time",
        "known",
        "outcome",
        "ofc",
        "unused",
        "settle",
        "conf",
        "src",
        "query",
        "note",
    ]
    events = [
        dict(zip(ekeys, line.split("|"))) for line in EVENTS_TXT.strip().splitlines()
    ]
    for e in events:
        e["ofc"] = dict(x.split("=") for x in e["ofc"].split(";"))
    return cases, events


# ---- Google News: corroborate the event date and find the earliest report ----
def gnews(query: str, day: date) -> list[tuple[datetime, str, str]]:
    q = f"{query} after:{day - timedelta(days=2)} before:{day + timedelta(days=4)}"
    url = "https://news.google.com/rss/search?" + urllib.parse.urlencode(
        {"q": q, "hl": "en-US", "gl": "US", "ceid": "US:en"}
    )
    out = []
    for item in re.findall(r"<item>(.*?)</item>", get(url, "gnews"), re.DOTALL):
        title = re.search(r"<title>(.*?)</title>", item, re.DOTALL)
        link = re.search(r"<link>(.*?)</link>", item, re.DOTALL)
        pub = re.search(r"<pubDate>(.*?)</pubDate>", item)
        if not (title and pub):
            continue
        from email.utils import parsedate_to_datetime

        out.append(
            (
                parsedate_to_datetime(pub.group(1)).astimezone(ET),
                title.group(1),
                link.group(1) if link else "",
            )
        )
    return sorted(out)


def news_check(e: dict) -> dict:
    """Count reports on the event day or the day after, and take the earliest one
    whose time stamp carries a clock time (Google gives date-only items a fixed
    07:00/08:00 UTC stamp, i.e. 02:00-04:00 ET)."""
    day = date.fromisoformat(e["date"])
    items = gnews(e["query"], day)
    near = [x for x in items if 0 <= (x[0].date() - day).days <= 1]
    before = [x for x in items if (x[0].date() - day).days < 0]
    timed = [
        x for x in near if not (x[0].minute == 0 and x[0].hour in (2, 3, 4, 19, 20))
    ]
    first = timed[0] if timed and timed[0][0].date() == day else None
    return {
        "n_near": len(near),
        "n_before": len(before),
        "first": first,
        "items": items,
    }


# ---- SEC ----
_tickers: dict[str, int] = {}


def cik(ticker: str) -> int | None:
    if not _tickers:
        data = json.loads(get("https://www.sec.gov/files/company_tickers.json", "sec"))
        for row in data.values():
            _tickers.setdefault(row["ticker"].upper(), int(row["cik_str"]))
    return _tickers.get(ticker.replace("-", "-").upper())


def companyfacts(c: int) -> dict:
    txt = get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{c:010d}.json", "sec")
    return json.loads(txt) if txt else {}


def shares_outstanding(facts: dict, asof: date) -> float | None:
    units = (
        facts.get("facts", {})
        .get("dei", {})
        .get("EntityCommonStockSharesOutstanding", {})
        .get("units", {})
    )
    vals = units.get("shares", [])
    best: dict[str, float] = {}
    for v in vals:
        if date.fromisoformat(v["end"]) <= asof and date.fromisoformat(
            v["filed"]
        ) <= asof + timedelta(days=1):
            best.setdefault(v["end"], 0)
    if not best:
        # multi-class issuers tag dei shares by class, which companyfacts drops;
        # fall back to the latest basic weighted-average share count
        gaap = facts.get("facts", {}).get("us-gaap", {})
        wa = (
            gaap.get("WeightedAverageNumberOfSharesOutstandingBasic", {})
            .get("units", {})
            .get("shares", [])
        )
        wa = [v for v in wa if date.fromisoformat(v["filed"]) <= asof]
        return (
            float(max(wa, key=lambda v: (v["end"], v["filed"]))["val"]) if wa else None
        )
    end = max(best)
    # sum share classes reported for the same date (deduplicated by value)
    seen = {v["val"] for v in vals if v["end"] == end}
    return float(sum(seen))


REV_TAGS = [
    ("us-gaap", "RevenueFromContractWithCustomerExcludingAssessedTax"),
    ("us-gaap", "Revenues"),
    ("us-gaap", "RevenueFromContractWithCustomerIncludingAssessedTax"),
    ("us-gaap", "SalesRevenueNet"),
    ("us-gaap", "RevenuesNetOfInterestExpense"),
    ("ifrs-full", "Revenue"),
]


def revenue_ttm(facts: dict, asof: date) -> tuple[float | None, str]:
    """Latest reported 12-month revenue (annual report or a 4-quarter sum
    from the most recent quarter) filed on or before asof."""
    best = None
    for ns, tag in REV_TAGS:
        units = facts.get("facts", {}).get(ns, {}).get(tag, {}).get("units", {})
        for cur, vals in units.items():
            if cur != "USD":
                continue
            for v in vals:
                if "start" not in v or date.fromisoformat(v["filed"]) > asof:
                    continue
                span = (
                    date.fromisoformat(v["end"]) - date.fromisoformat(v["start"])
                ).days
                if 350 <= span <= 380:
                    cand = (v["end"], v["val"], f"{tag} 12 months to {v['end']}")
                    if best is None or cand[0] > best[0]:
                        best = cand
    return (float(best[1]), best[2]) if best else (None, "no USD revenue tag in XBRL")


def efts_8k(c: int, start: date, end: date) -> list[dict]:
    q = urllib.parse.urlencode(
        {
            "q": '"antitrust" OR "Federal Trade Commission" OR "Department of Justice" OR "jury" OR "court"',
            "forms": "8-K",
            "dateRange": "custom",
            "startdt": str(start),
            "enddt": str(end),
            "ciks": f"{c:010d}",
        }
    )
    txt = get(f"https://efts.sec.gov/LATEST/search-index?{q}", "sec")
    try:
        return json.loads(txt).get("hits", {}).get("hits", [])
    except json.JSONDecodeError:
        return []


def acceptance_time(c: int, adsh: str) -> datetime | None:
    url = f"https://www.sec.gov/Archives/edgar/data/{c}/{adsh.replace('-', '')}/{adsh}-index.htm"
    m = re.search(
        r"Accepted</div>\s*<div class=\"info\">([\d\- :]+)</div>", get(url, "sec")
    )
    return (
        datetime.strptime(m.group(1).strip(), "%Y-%m-%d %H:%M:%S").replace(tzinfo=ET)
        if m
        else None
    )


# ---- prices ----
_px: dict[str, dict] = {}


def daily(sym: str) -> dict:
    if sym in _px:
        return _px[sym]
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?period1=1262304000"
        f"&period2=1792000000&interval=1d&events=div%2Csplit"
    )
    txt = get(url, "yahoo")
    out: dict = {"dates": [], "close": [], "vol": []}
    try:
        r = json.loads(txt)["chart"]["result"][0]
        q = r["indicators"]["quote"][0]
        adj = r["indicators"].get("adjclose", [{}])[0].get("adjclose") or q["close"]
        for t, c, v, a in zip(r["timestamp"], q["close"], q["volume"], adj):
            if c is None or a is None:
                continue
            out["dates"].append(datetime.fromtimestamp(t, ET).date())
            out["close"].append(a)
            out["vol"].append((v or 0) * c)
    except (KeyError, TypeError, IndexError, json.JSONDecodeError):
        pass
    _px[sym] = out
    return out


def trading_index(px: dict, d: date, after_close: bool) -> int | None:
    for i, x in enumerate(px["dates"]):
        if x > d or (x == d and not after_close):
            return i
    return None


def ret(px: dict, i: int | None, n: int) -> float | None:
    if i is None or i < 1 or i + n - 1 >= len(px["close"]):
        return None
    return px["close"][i + n - 1] / px["close"][i - 1] - 1


def price_on(px: dict, d: date) -> float | None:
    idx = [i for i, x in enumerate(px["dates"]) if x <= d]
    return px["close"][idx[-1]] if idx else None


# ---- Polygon 1-minute bars (key from env, never cached in the URL) ----
def minute_bars(sym: str, d: date) -> list[dict]:
    if not os.environ.get("POLYGON_API_KEY"):
        return []
    url = (
        f"https://api.polygon.io/v2/aggs/ticker/{sym.replace('-', '.')}/range/1/minute/{d}/{d}"
        "?adjusted=true&sort=asc&limit=50000"
    )
    txt = get(url, "polygon", secret_param="apiKey")
    try:
        return json.loads(txt).get("results", [])
    except json.JSONDecodeError:
        return []


def half_move_minutes(sym: str, t0: datetime) -> int | None:
    """Minutes from t0 until the price first covered half of the move from the
    last pre-t0 trade to the regular-session close."""
    bars = minute_bars(sym, t0.date())
    if not bars:
        return None
    t0_ms = t0.timestamp() * 1000
    close_ms = (
        datetime.combine(t0.date(), datetime.min.time(), ET)
        .replace(hour=16)
        .timestamp()
        * 1000
    )
    pre = [b for b in bars if b["t"] < t0_ms]
    post = [b for b in bars if t0_ms <= b["t"] < close_ms]
    if not pre or not post:
        return None
    p0, pc = pre[-1]["c"], post[-1]["c"]
    move = pc - p0
    if abs(move) / p0 < 0.002:
        return None
    for b in post:
        if (b["c"] - p0) / move >= 0.5:
            return int((b["t"] - t0_ms) // 60000)
    return None


def fmt(x: float | None, nd: int = 4) -> str:
    return "" if x is None else f"{x:.{nd}f}"


def build() -> list[dict]:
    cases, events = load_tables()
    today = date.today()
    rows = []
    for e in events:
        c = cases[e["case"]]
        d = date.fromisoformat(e["date"])
        filed = date.fromisoformat(c["filed"])
        nc = news_check(e)
        for ticker, company, role in c["parties"]:
            if ticker not in e["ofc"]:
                continue
            notes = [f"event_label={e['label']}"]
            if e["note"]:
                notes.append(e["note"])
            if (c["id"], e["date"]) in CONFOUNDS:
                notes.append(CONFOUNDS[(c["id"], e["date"])])
            bench = "XBI" if ticker in PHARMA else "SPY"
            px, bx = daily(ticker), daily(bench)
            if not px["dates"]:
                notes.append(f"no Yahoo price history for {ticker}")
            # filing-day return: filing times are not collected, so use 2 days
            fi = trading_index(px, filed, False) if px["dates"] else None
            bfi = trading_index(bx, filed, False)
            rf, bf = ret(px, fi, 2), ret(bx, bfi, 2)
            # decision-day return
            t = e["time"]
            if t:
                after = t >= "16:00"
                di, bdi, n = trading_index(px, d, after), trading_index(bx, d, after), 1
            else:
                di, bdi, n = trading_index(px, d, False), trading_index(bx, d, False), 2
                notes.append(
                    "decision time unknown: decision-day returns are 2-day (day of plus next trading day)"
                )
            rd, bd = ret(px, di, n), ret(bx, bdi, n)
            r5 = ret(px, di, 5)
            adv = None
            if di is not None and di >= 20:
                adv = statistics.mean(px["vol"][di - 20 : di])
            # fundamentals at filing
            mcap = rev = None
            ck = cik(ticker)
            if ck and ticker not in ("BRK-B", "WPP"):
                facts = companyfacts(ck)
                sh = shares_outstanding(facts, filed)
                p = price_on(px, filed) if px["dates"] else None
                if sh and p:
                    mcap = sh * p
                rev, revnote = revenue_ttm(facts, filed)
                if rev is None:
                    notes.append(revnote)
                if ticker in ("GOOGL", "Z", "RKT"):
                    notes.append(
                        "market cap = all share classes x this class's price (approximate)"
                    )
            elif ticker in ("BRK-B", "WPP"):
                notes.append(
                    "market cap/revenue not computed: share classes or ADR ratio make dei shares x price wrong"
                )
            else:
                notes.append("ticker not in SEC current ticker map")
            if not px["dates"]:
                mcap = None
            notes.append(
                "revenue_at_stake not filled: product revenue at issue not collected from segment notes"
            )
            # timing columns
            fps, fpt, prec, mh = "", "", "day", "unknown"
            if t:
                fps = "court docket (CourtListener RECAP entry time)"
                fpt, prec = f"{d} {t}", "minute"
            elif nc["first"]:
                fps = "news report (earliest time-stamped Google News item, an upper bound)"
                fpt, prec = nc["first"][0].strftime("%Y-%m-%d %H:%M"), "hour"
            else:
                fps = "agency/court page or news (date only)"
                fpt = str(d)
            if (c["id"], e["date"]) in FIRST_PUBLIC_OVERRIDE:
                fps, fpt = FIRST_PUBLIC_OVERRIDE[(c["id"], e["date"])]
                prec = "minute"
            trading_day = bool(bx["dates"]) and d in bx["dates"]
            if prec in ("minute", "hour"):
                hhmm = fpt[11:]
                mh = "yes" if trading_day and "09:30" <= hhmm < "16:00" else "no"
                if prec == "hour" and mh == "no" and hhmm >= "16:00":
                    mh = "unknown"  # the item could be a late write-up of a daytime event
            elif not trading_day:
                mh = "no"
            rel, lead = "", ""
            if ck:
                accepted = [
                    acceptance_time(ck, h["_source"]["adsh"])
                    for h in efts_8k(ck, d, d + timedelta(days=2))[:3]
                    if "_source" in h
                ]
                accepted = sorted(a for a in accepted if a)
                about = RELEASE_ABOUT_EVENT.get((c["id"], ticker, e["date"]))
                if accepted and about is False:
                    notes.append(
                        "the only 8-K found near this date is about something else (item text read); company_release_time left blank"
                    )
                    accepted = []
                if accepted and about is None:
                    accepted = []
                if accepted:
                    rel = accepted[0].strftime("%Y-%m-%d %H:%M")
                    notes.append(
                        "company_release_time = acceptance time of the company's 8-K about this event (item text read)"
                    )
                    if prec == "minute":
                        lead = str(
                            int(
                                (
                                    accepted[0]
                                    - datetime.strptime(fpt, "%Y-%m-%d %H:%M").replace(
                                        tzinfo=ET
                                    )
                                ).total_seconds()
                                // 60
                            )
                        )
            mdav = "no"
            half = ""
            if (today - d).days <= 730 and os.environ.get("POLYGON_API_KEY"):
                if prec == "minute" and mh == "yes":
                    t0 = datetime.strptime(fpt, "%Y-%m-%d %H:%M").replace(tzinfo=ET)
                    if minute_bars(ticker, d):
                        mdav = "yes"
                        h = half_move_minutes(ticker, t0)
                        half = "" if h is None else str(h)
                elif prec in ("minute", "hour") or di is not None:
                    pass
            conf = e["conf"]
            if nc["n_near"] == 0 and conf != "high":
                notes.append(
                    "no news item found within a day of this date (date not corroborated)"
                )
                conf = "low"
            outcome = e["outcome"]
            rows.append(
                {
                    "case_id": c["id"],
                    "case_type": "antitrust_conduct_" + c["kind"],
                    "case_name": c["name"],
                    "court": c["court"],
                    "docket_number": c["docket"],
                    "docket_url": c["url"],
                    "ticker": ticker,
                    "company": company,
                    "company_role": role,
                    "counterparty": c["cp"],
                    "counterparty_ticker": next(
                        (p[0] for p in c["parties"] if p[0] != ticker and p[2] != role),
                        c["cp_ticker"] if "/" not in c["cp_ticker"] else "",
                    ),
                    "filed_date": c["filed"],
                    "trial_start_date": c["trial_start"],
                    "trial_end_date": c["trial_end"],
                    "decision_date": e["date"],
                    "decision_time_et": t,
                    "decision_known_in_advance": e["known"],
                    "decision_source_url": e["src"]
                    or (
                        nc["first"][2]
                        if nc["first"]
                        else (nc["items"][0][2] if nc["items"] else "")
                    ),
                    "outcome": outcome,
                    "outcome_for_company": e["ofc"][ticker],
                    "days_filed_to_decision": (d - filed).days,
                    "market_cap_usd_at_filing": fmt(mcap, 0),
                    "revenue_ttm_usd_at_filing": fmt(rev, 0),
                    "revenue_at_stake_usd": "",
                    "revenue_at_stake_share": "",
                    "ret_filing_day": fmt(rf),
                    "abn_ret_filing_day": fmt(
                        None if rf is None or bf is None else rf - bf
                    ),
                    "ret_decision_day": fmt(rd),
                    "abn_ret_decision_day": fmt(
                        None if rd is None or bd is None else rd - bd
                    ),
                    "ret_decision_plus5": fmt(r5),
                    "adv_usd_20d_before_decision": fmt(adv, 0),
                    "implied_move_before_decision": "",
                    "settlement_amount_usd": e["settle"],
                    "confidence": conf,
                    "sources": " ; ".join(
                        x
                        for x in [c["url"], e["src"]] + [i[2] for i in nc["items"][:2]]
                        if x
                    ),
                    "notes": "; ".join(
                        notes
                        + [
                            "filing-day returns are 2-day (filing time not collected); benchmark "
                            + bench,
                            f"{nc['n_near']} news items within a day",
                        ]
                    ),
                    "first_public_source": fps,
                    "first_public_time_et": fpt,
                    "time_precision": prec,
                    "during_market_hours": mh,
                    "company_release_time_et": rel,
                    "lead_minutes_vs_company_release": lead,
                    "minutes_to_half_move": half,
                    "minute_data_available": mdav,
                }
            )
    return rows


def main() -> None:
    rows = build()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUT_DIR / "cases.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {len(rows)} rows for {len({r['case_id'] for r in rows})} cases")


if __name__ == "__main__":
    main()
