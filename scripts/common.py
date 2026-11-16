"""Shared helpers: polite HTTP, SEC EDGAR lookups, Google News RSS search.

Only public pages. SEC asks for a User-Agent with contact info and at most
10 requests a second; we stay under 5.
"""

from __future__ import annotations

import email.utils
import hashlib
import html
import json
import os
import re
import time
import urllib.parse
from datetime import UTC, datetime
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
CACHE = Path.home() / "work" / "altdata" / "cache" / "announcement_leaks"
# sites like SEC EDGAR ask for a contact address in the User-Agent
CONTACT = os.environ.get("CONTACT_EMAIL", "contact@example.com")
SEC_UA = f"lawsuit-stock-moves research {CONTACT}"
WEB_UA = f"Mozilla/5.0 (research; {CONTACT})"

_last: dict[str, float] = {}
# CourtListener: about 50 searches/hour without a token, 5,000/hour with one
_CL_GAP = 1.0 if os.environ.get("COURTLISTENER_API_TOKEN") else 6.0
_MIN_GAP = {"sec.gov": 0.22, "news.google.com": 1.5, "courtlistener.com": _CL_GAP}


def _throttle(host: str) -> None:
    for key, gap in _MIN_GAP.items():
        if host.endswith(key):
            wait = _last.get(key, 0) + gap - time.time()
            if wait > 0:
                time.sleep(wait)
            _last[key] = time.time()


def get(url: str, cache: bool = True, tries: int = 3) -> str:
    """GET a URL with caching on disk; returns text ('' on failure)."""
    CACHE.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha1(url.encode()).hexdigest()[:12]
    key = CACHE / (re.sub(r"[^A-Za-z0-9]+", "_", url)[-160:] + "_" + digest + ".txt")
    if cache and key.exists():
        return key.read_text()
    host = urllib.parse.urlparse(url).hostname or ""
    ua = SEC_UA if host.endswith("sec.gov") else WEB_UA
    for i in range(tries):
        _throttle(host)
        try:
            headers = {"User-Agent": ua}
            token = os.environ.get("COURTLISTENER_API_TOKEN")
            if token and host.endswith("courtlistener.com"):
                headers["Authorization"] = f"Token {token}"
            r = requests.get(url, headers=headers, timeout=30)
        except requests.RequestException:
            time.sleep(2 * (i + 1))
            continue
        if r.status_code == 200:
            if cache:
                key.write_text(r.text)
            return r.text
        if r.status_code in (202, 429, 503):
            time.sleep(10 * (i + 1))
            continue
        return ""
    return ""


def efts(q: str, forms: str, start: str, end: str, page: int = 0, **extra) -> dict:
    """SEC EDGAR full-text search (public endpoint behind efts.sec.gov)."""
    params = {
        "q": q,
        "forms": forms,
        "dateRange": "custom",
        "startdt": start,
        "enddt": end,
    }
    if page:
        params["from"] = str(page * 100)
    params.update(extra)
    txt = get(
        "https://efts.sec.gov/LATEST/search-index?" + urllib.parse.urlencode(params)
    )
    return json.loads(txt) if txt else {}


def filing_index_url(cik: str, adsh: str) -> str:
    return f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{adsh.replace('-', '')}/{adsh}-index.htm"


def acceptance_time(cik: str, adsh: str) -> datetime | None:
    """EDGAR 'Accepted' timestamp (US Eastern) from the public filing index page."""
    t = get(filing_index_url(cik, adsh))
    m = re.search(r"Accepted</div>\s*<div class=\"info\">([\d\- :]+)</div>", t)
    if not m:
        return None
    from zoneinfo import ZoneInfo

    return datetime.strptime(m.group(1).strip(), "%Y-%m-%d %H:%M:%S").replace(
        tzinfo=ZoneInfo("America/New_York")
    )


def strip_tags(t: str) -> str:
    t = re.sub(r"(?is)<(script|style).*?</\1>", " ", t)
    t = re.sub(r"<[^>]+>", " ", t)
    return re.sub(r"\s+", " ", html.unescape(t)).strip()


def gnews(query: str) -> list[dict]:
    """Google News RSS search. pubDate is Google's article time (UTC).

    Items whose time is exactly midnight Pacific or Eastern (07:00, 08:00, 04:00,
    05:00 UTC with :00:00) are usually date-only and get exact=False.
    """
    url = "https://news.google.com/rss/search?" + urllib.parse.urlencode(
        {"q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"}
    )
    t = get(url)
    out = []
    for it in re.findall(r"<item>(.*?)</item>", t, re.DOTALL):
        title = html.unescape(
            re.search(r"<title>(.*?)</title>", it, re.DOTALL).group(1)
        )
        pub = re.search(r"<pubDate>(.*?)</pubDate>", it)
        src = re.search(r"<source url=\"([^\"]*)\">(.*?)</source>", it)
        if not pub:
            continue
        dt = email.utils.parsedate_to_datetime(pub.group(1)).astimezone(UTC)
        exact = not (dt.minute == 0 and dt.second == 0 and dt.hour in (4, 5, 7, 8))
        out.append(
            {
                "title": title,
                "time": dt,
                "exact": exact,
                "source_url": src.group(1) if src else "",
                "source": html.unescape(src.group(2)) if src else "",
            }
        )
    return out


def words(s: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", s.lower()) if len(w) > 2}


def similarity(a: str, b: str) -> float:
    wa, wb = words(a), words(b)
    return len(wa & wb) / max(1, min(len(wa), len(wb)))
