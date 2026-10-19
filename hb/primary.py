"""
Direct primary source parsers for Egypt's three most important official sources:
CBE, EGX, and CAPMAS. These bypass Google News entirely and pull straight
from the official pages — so a CBE rate decision shows up immediately,
not when a news site decides to write about it.

Each parser returns normalized headline dicts matching the format from hb/news.py.
Failed parsers log a warning and return [] — they never crash the build.
"""
from __future__ import annotations
import logging
import re
import time
from datetime import datetime, timezone
from typing import Optional

import requests

log = logging.getLogger(__name__)
TIMEOUT = 25
UA = "HegazyBrief/2.0 primary-source-parser"


def _get(url: str) -> Optional[requests.Response]:
    try:
        r = requests.get(url, timeout=TIMEOUT, headers={"User-Agent": UA})
        r.raise_for_status()
        return r
    except requests.exceptions.Timeout:
        log.warning("Timeout fetching %s", url)
    except requests.exceptions.HTTPError as e:
        log.warning("HTTP %s for %s", e.response.status_code, url)
    except Exception as e:
        log.warning("Failed to fetch %s: %s", url, e)
    return None


def _headline(title: str, url: str, source: str,
              when: Optional[str] = None, sector: str = "economy",
              regions: Optional[list] = None, check: str = "PRIMARY",
              official: bool = True) -> dict:
    return {
        "title": title.strip(),
        "summary": "",
        "link": url,
        "source": source,
        "source_domain": url.split("/")[2] if url.startswith("http") else source,
        "image": None,
        "published": when,
        "official": official,
        "primary": True,
        "sector": sector,
        "regions": regions or ["egypt"],
        "check": check,
    }


# ── CBE — Central Bank of Egypt ──────────────────────────────────────────────

CBE_PRESS_URL = "https://www.cbe.org.eg/en/EconomicResearch/Publications/Pages/Pressrelease.aspx"
CBE_BASE = "https://www.cbe.org.eg"

def parse_cbe() -> list[dict]:
    """
    Parse CBE press releases page. Returns latest press releases.
    The page is ASP.NET so we look for the list items with release titles.
    """
    r = _get(CBE_PRESS_URL)
    if not r:
        return []
    html = r.text

    # CBE press releases appear in divs with class containing "ms-rtestate-field"
    # or in table cells. Try multiple patterns.
    headlines = []

    # Pattern 1: links with /en/ in the href pointing to press releases
    pattern = r'<a[^>]+href="(/en/[^"]*(?:press|release|decision|rate|inflation)[^"]*)"[^>]*>([^<]{20,200})</a>'
    for href, title in re.findall(pattern, html, re.IGNORECASE):
        title = re.sub(r'\s+', ' ', title).strip()
        if len(title) > 15:
            url = CBE_BASE + href if href.startswith("/") else href
            headlines.append(_headline(
                title=title, url=url, source="Central Bank of Egypt",
                sector="economy", regions=["egypt"], check="A7"
            ))

    # Pattern 2: anchor tags with Arabic press release content
    ar_pattern = r'<a[^>]+href="(/ar/[^"]*)"[^>]*>([\u0600-\u06FF\s،,.-]{15,200})</a>'
    for href, title in re.findall(ar_pattern, html):
        title = re.sub(r'\s+', ' ', title).strip()
        if len(title) > 10:
            url = CBE_BASE + href if href.startswith("/") else href
            headlines.append(_headline(
                title=f"[CBE Arabic] {title}", url=url,
                source="البنك المركزي المصري",
                sector="economy", regions=["egypt"], check="A7"
            ))

    if not headlines:
        # Fallback: look for any substantial links on the page
        fallback = r'<a[^>]+href="([^"]+)"[^>]*>([^<]{30,150})</a>'
        for href, title in re.findall(fallback, html)[:5]:
            title = re.sub(r'\s+', ' ', title).strip()
            if len(title) > 20 and "cbe.org.eg" in href or href.startswith("/"):
                url = CBE_BASE + href if href.startswith("/") else href
                headlines.append(_headline(
                    title=title, url=url, source="Central Bank of Egypt",
                    sector="economy", regions=["egypt"], check="A7"
                ))

    log.info("CBE: %d headlines", len(headlines))
    return headlines[:10]


# ── EGX — Egyptian Exchange ───────────────────────────────────────────────────

EGX_DISCLOSURES_URL = "https://www.egx.com.eg/en/Disclosure.aspx"
EGX_BASE = "https://www.egx.com.eg"

def parse_egx() -> list[dict]:
    """
    Parse EGX market disclosures. These are company announcements
    that bypass the press entirely — earnings, dividends, board decisions.
    """
    r = _get(EGX_DISCLOSURES_URL)
    if not r:
        return []
    html = r.text
    headlines = []

    # EGX disclosures are typically in table rows
    row_pattern = r'<tr[^>]*>.*?<td[^>]*>(.*?)</td>.*?<td[^>]*>(.*?)</td>.*?</tr>'
    for row_match in re.finditer(row_pattern, html, re.DOTALL)[:20]:
        cell1 = re.sub(r'<[^>]+>', '', row_match.group(1)).strip()
        cell2 = re.sub(r'<[^>]+>', '', row_match.group(2)).strip()
        if len(cell1) > 5 and len(cell2) > 5:
            title = f"{cell1} — {cell2}" if cell2 != cell1 else cell1
            if len(title) > 15:
                headlines.append(_headline(
                    title=title, url=EGX_DISCLOSURES_URL,
                    source="Egyptian Exchange",
                    sector="markets", regions=["egypt"], check="A2.5"
                ))

    # Also look for anchor links with disclosure titles
    link_pattern = r'<a[^>]+href="([^"]*(?:Disclosure|disclosure|company|Company)[^"]*)"[^>]*>([^<]{10,150})</a>'
    for href, title in re.findall(link_pattern, html, re.IGNORECASE):
        title = re.sub(r'\s+', ' ', title).strip()
        if len(title) > 10:
            url = EGX_BASE + href if href.startswith("/") else href
            if not any(h["link"] == url for h in headlines):
                headlines.append(_headline(
                    title=title, url=url, source="Egyptian Exchange",
                    sector="markets", regions=["egypt"], check="A2.5"
                ))

    log.info("EGX: %d disclosures", len(headlines))
    return headlines[:10]


# ── CAPMAS — Central Agency for Public Mobilization and Statistics ────────────

CAPMAS_NEWS_URL = "https://www.capmas.gov.eg/Pages/pressreleases.aspx"
CAPMAS_BASE = "https://www.capmas.gov.eg"

def parse_capmas() -> list[dict]:
    """
    Parse CAPMAS press releases: CPI, unemployment, population, trade stats.
    CAPMAS is the primary source for Egypt inflation data — more authoritative
    than any news article.
    """
    r = _get(CAPMAS_NEWS_URL)
    if not r:
        return []
    html = r.text
    headlines = []

    # CAPMAS pages have SharePoint-style structure
    patterns = [
        r'<a[^>]+href="(/Pages/[^"]+\.aspx[^"]*)"[^>]*>([^<]{15,200})</a>',
        r'<a[^>]+href="(/en/[^"]+)"[^>]*>([^<]{15,200})</a>',
        r'class="ms-rtestate-field"[^>]*>(.*?)</div>',
    ]

    for pattern in patterns:
        for match in re.findall(pattern, html, re.IGNORECASE | re.DOTALL)[:10]:
            if isinstance(match, tuple):
                href, title = match
                title = re.sub(r'<[^>]+>', '', title).strip()
                title = re.sub(r'\s+', ' ', title)
                if len(title) > 15:
                    url = CAPMAS_BASE + href if href.startswith("/") else href
                    headlines.append(_headline(
                        title=title, url=url,
                        source="CAPMAS",
                        sector="economy", regions=["egypt"], check="A8"
                    ))
            else:
                text = re.sub(r'<[^>]+>', '', match).strip()
                if len(text) > 20:
                    headlines.append(_headline(
                        title=text[:200], url=CAPMAS_NEWS_URL,
                        source="CAPMAS",
                        sector="economy", regions=["egypt"], check="A8"
                    ))

    log.info("CAPMAS: %d headlines", len(headlines))
    return headlines[:8]


# ── MOF — Ministry of Finance ────────────────────────────────────────────────

MOF_URL = "https://www.mof.gov.eg/en/Pages/latestnews.aspx"
MOF_BASE = "https://www.mof.gov.eg"

def parse_mof() -> list[dict]:
    """Parse Egypt Ministry of Finance news — budget, debt, fiscal policy."""
    r = _get(MOF_URL)
    if not r:
        return []
    html = r.text

    headlines = []
    pattern = r'<a[^>]+href="(/en/Pages/[^"]+)"[^>]*>([^<]{15,200})</a>'
    for href, title in re.findall(pattern, html, re.IGNORECASE)[:10]:
        title = re.sub(r'\s+', ' ', title).strip()
        if len(title) > 15:
            url = MOF_BASE + href
            headlines.append(_headline(
                title=title, url=url, source="Egyptian Ministry of Finance",
                sector="economy", regions=["egypt"], check="A13"
            ))

    log.info("MOF: %d headlines", len(headlines))
    return headlines[:8]


# ── SCA — Suez Canal Authority ────────────────────────────────────────────────

SCA_URL = "https://www.sca.gov.eg/en/news"
SCA_BASE = "https://www.sca.gov.eg"

def parse_sca() -> list[dict]:
    """Parse Suez Canal Authority news — transit stats, revenue, incidents."""
    r = _get(SCA_URL)
    if not r:
        return []
    html = r.text

    headlines = []
    patterns = [
        r'<a[^>]+href="(/en/news/[^"]+)"[^>]*>([^<]{15,200})</a>',
        r'<h[2-4][^>]*>([^<]{20,200})</h[2-4]>',
    ]
    for pattern in patterns:
        for match in re.findall(pattern, html, re.IGNORECASE)[:8]:
            if isinstance(match, tuple):
                href, title = match
            else:
                href, title = SCA_URL, match
            title = re.sub(r'\s+', ' ', title).strip()
            if len(title) > 15:
                url = SCA_BASE + href if href.startswith("/") else href
                headlines.append(_headline(
                    title=title, url=url, source="Suez Canal Authority",
                    sector="trade", regions=["egypt"], check="A13"
                ))

    log.info("SCA: %d headlines", len(headlines))
    return headlines[:8]


# ── Main collector ────────────────────────────────────────────────────────────

def collect_all() -> list[dict]:
    """
    Run all primary source parsers and return combined headlines.
    Each parser is isolated — one failure doesn't stop the others.
    """
    all_headlines: list[dict] = []

    parsers = [
        ("CBE",    parse_cbe),
        ("EGX",    parse_egx),
        ("CAPMAS", parse_capmas),
        ("MOF",    parse_mof),
        ("SCA",    parse_sca),
    ]

    for name, fn in parsers:
        try:
            items = fn()
            for i, h in enumerate(items):
                h["id"] = f"p_{name.lower()}_{i}"
            all_headlines.extend(items)
            time.sleep(1)           # be polite to official servers
        except Exception as exc:
            log.warning("Primary parser %s crashed: %s", name, exc)

    log.info("Primary sources total: %d headlines", len(all_headlines))
    return all_headlines


if __name__ == "__main__":
    import json
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    results = collect_all()
    print(json.dumps(results[:5], indent=2, ensure_ascii=False))
    print(f"\nTotal: {len(results)}")
