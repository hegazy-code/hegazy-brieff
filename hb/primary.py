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
from html import unescape as html_unescape
import time
from datetime import datetime, timezone
from typing import Optional

import requests

log = logging.getLogger(__name__)
TIMEOUT = 25
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0 Safari/537.36 HegazyBrief/2.0")


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

CBE_PRESS_URL = "https://www.cbe.org.eg/en/news-publications/news"   # verified live 2026-10-20
CBE_BASE = "https://www.cbe.org.eg"
CBE_LINK = re.compile(r'href="(/en/news-publications/news/(\d{4})/(\d{2})/(\d{2})/[^"?#]+)"[^>]*>(.*?)</a>', re.S)


def _cbe_check(title: str) -> str:
    t = title.lower()
    if "mpc" in t or "monetary policy" in t or "interest rate" in t:
        return "A7"      # central banks
    if any(k in t for k in ("cpi", "inflation", "reserves", "balance of payments", "remittances", "external debt")):
        return "A8"      # economic data
    return "A13"         # Egypt deep check


def parse_cbe() -> list[dict]:
    """CBE news & press releases. Links carry their date in the path: /news/YYYY/MM/DD/..."""
    r = _get(CBE_PRESS_URL)
    if not r:
        return []
    seen, headlines = set(), []
    for href, y, m, d, inner in CBE_LINK.findall(r.text):
        title = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", inner)).strip()
        if len(title) < 15 or href in seen:      # image links repeat the URL with no text
            continue
        seen.add(href)
        headlines.append(_headline(
            title=title, url=CBE_BASE + href, source="Central Bank of Egypt",
            when=f"{y}-{m}-{d}T00:00:00+02:00", sector="economy", regions=["egypt"],
            check=_cbe_check(title)))
    log.info("CBE: %d headlines", len(headlines))
    return headlines[:10]


# ── EGX — Egyptian Exchange ───────────────────────────────────────────────────

EGX_HOME_URL = "https://www.egx.com.eg/en/homepage.aspx"   # verified live 2026-10-20
EGX_BASE = "https://www.egx.com.eg/en/"
EGX_LINK = re.compile(r'<a[^>]+href="([^"]*NewsDetails\.aspx\?NewsID=\d+[^"]*)"[^>]*>(.*?)</a>', re.S | re.I)


def parse_egx() -> list[dict]:
    """Latest EGX company disclosures and exchange news, from the homepage news tabs."""
    from urllib.parse import urljoin
    r = _get(EGX_HOME_URL)
    if not r:
        return []
    seen, headlines = set(), []
    for href, inner in EGX_LINK.findall(r.text):
        title = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", inner)).strip()
        url = urljoin(EGX_BASE, html_unescape(href))
        if len(title) < 15 or url in seen:
            continue
        seen.add(url)
        exchange_news = title.startswith(("EGX", "The Egyptian Exchange"))
        headlines.append(_headline(
            title=title, url=url, source="Egyptian Exchange",
            sector="markets" if exchange_news else "finance", regions=["egypt"],
            check="A2.5" if exchange_news else "A10"))
    log.info("EGX: %d headlines", len(headlines))
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

SCA_URL = "https://www.suezcanal.gov.eg/English/MediaCenter/News/Pages/default.aspx"   # verified live 2026-10-20
SCA_BASE = "https://www.suezcanal.gov.eg"
SCA_LINK = re.compile(r'<a[^>]+href="([^"]*/MediaCenter/News/Pages/([^"/]+)\.aspx)"[^>]*>(.*?)</a>', re.S | re.I)
SCA_DATE = re.compile(r"(\d{1,2})-(\d{1,2})-(\d{4})")


def parse_sca() -> list[dict]:
    """Suez Canal Authority news: traffic, revenue, tolls, agreements."""
    r = _get(SCA_URL)
    if not r:
        return []
    seen, headlines = set(), []
    for href, slug, inner in SCA_LINK.findall(r.text):
        title = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", inner)).strip()
        if len(title) < 15 or slug.lower() == "default" or href in seen:
            continue
        seen.add(href)
        m = SCA_DATE.search(slug)
        when = f"{m[3]}-{int(m[2]):02d}-{int(m[1]):02d}T00:00:00+02:00" if m else None
        headlines.append(_headline(
            title=title, url=href if href.startswith("http") else SCA_BASE + href,
            source="Suez Canal Authority", when=when, sector="trade",
            regions=["egypt"], check="B7"))
    log.info("SCA: %d headlines", len(headlines))
    return headlines[:8]


def collect_all(allow=None) -> list[dict]:
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
    registry_ids = {"CBE": "cbe", "EGX": "egx", "CAPMAS": "capmas", "MOF": "mof_egypt", "SCA": "sca"}

    for name, fn in parsers:
        if allow and not allow(registry_ids[name]):
            log.info("Primary %s skipped: marked down in source registry", name)
            continue
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
