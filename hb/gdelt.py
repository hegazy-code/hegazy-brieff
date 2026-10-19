"""
GDELT integration — international news discovery across 100+ languages and 65+ countries.

GDELT DOC 2.0 API: https://api.gdeltproject.org/api/v2/doc/doc
Free, no key needed. Returns articles matching a query sorted by relevance or date.

We use it to discover stories that English-language RSS feeds miss:
- Arabic, French, Swahili, Chinese, Hindi, Turkish coverage
- African, Latin American, Southeast Asian events
- Secondary regional stories that Reuters/AP don't lead with

The output is normalized into the same headline format used by hb/news.py
so stories slot into the existing pipeline without changes.
"""
from __future__ import annotations
import logging
import time
from datetime import datetime, timezone
from typing import Optional
import requests

log = logging.getLogger(__name__)

BASE = "https://api.gdeltproject.org/api/v2/doc/doc"
TIMEOUT = 30
RETRY_WAIT = 10
MIN_GAP = 5.5          # GDELT DOC API limit is one request every 5 seconds

# Sector → GDELT themes (from GDELT's official theme taxonomy)
SECTOR_THEMES: dict[str, list[str]] = {
    "politics":      ["GOV_LEADERSHIP", "GOV_ELECTIONS", "UNGROUPED", "CRISISLEX_CRISISLEXREC"],
    "economy":       ["ECON_BANKRUPTCY", "ECON_DEBTBURDEN", "ECON_REFORM", "ECON_INFLATION"],
    "finance":       ["ECON_STOCKMARKET", "ECON_BANKSFC", "ECON_REMITTANCE"],
    "energy":        ["ENV_OIL", "ENV_GAS", "ENV_ENERGYRESOURCES", "ENV_NUCLEARPOWER"],
    "trade":         ["ECON_TRADE", "WB_1747_TRADE_FACILITATION", "TRANS_SHIPPING"],
    "health":        ["HEALTH_PANDEMIC", "HEALTH_VACCINATION", "HEALTH_DISEASE"],
    "climate":       ["ENV_CLIMATECHANGE", "ENV_DEFORESTATION", "ENV_WATERWAYS", "ENV_FLOODING"],
    "technology":    ["CYBER_ATTACK", "SOC_COMPUTERTECHNOLOGY", "SOC_MEDIA"],
    "cyber":         ["CYBER_ATTACK", "CYBER_DATA_BREACH", "CYBER_RANSOMWARE"],
    "society":       ["UNGROUPED", "SOC_CENSORSHIP", "MIGRATION", "DEMO_ETHNICITY"],
    "infrastructure":["TRANS_AIR_TRANSPORT", "TRANS_SHIPPING", "TRANS_RAILWAY"],
    "labor":         ["ECON_EMPLOYMENT", "ECON_LABORMARKET", "SOC_LABOR"],
}

# Egypt-specific searches
EGYPT_QUERIES = [
    "Egypt economy",
    "Egypt pound inflation",
    "Egypt CBE interest rate",
    "Suez Canal shipping",
    "Egypt IMF",
    "Egypt investment",
    "EGX Egyptian Exchange",
    "مصر اقتصاد",        # Egypt economy (Arabic)
    "البنك المركزي المصري",  # Central Bank of Egypt (Arabic)
    "قناة السويس",          # Suez Canal (Arabic)
]

# Non-English regions that need GDELT (English RSS misses these)
REGION_QUERIES: dict[str, list[str]] = {
    "africa":   ["Africa election", "Africa economy IMF", "sub-Saharan Africa"],
    "latam":    ["Brazil economy", "Mexico peso", "Argentina peso IMF", "Colombia Venezuela"],
    "mena":     ["Arab League", "Gulf economy", "Saudi Arabia oil", "Iraq Syria Lebanon"],
    "asia":     ["ASEAN economy", "India rupee", "Indonesia economy", "Vietnam exports"],
}


def _fetch(query: str, mode: str = "artlist", max_records: int = 10,
           timespan: str = "24h", source_lang: Optional[str] = None) -> list[dict]:
    """
    Call the GDELT DOC API and return normalized headline dicts.

    mode: artlist (article list) or timelinevol (volume over time)
    timespan: 15min, 1h, 6h, 24h, 3d, 7d
    """
    params = {
        "query": query,
        "mode": mode,
        "maxrecords": max_records,
        "timespan": timespan,
        "format": "json",
        "sort": "DateDesc",
    }
    if source_lang:
        params["sourcelang"] = source_lang

    for attempt in range(3):
        try:
            r = requests.get(BASE, params=params, timeout=TIMEOUT,
                             headers={"User-Agent": "HegazyBrief/2.0 GDELT"})
            if r.status_code == 429:
                log.warning("GDELT rate limited — waiting %ds", RETRY_WAIT)
                time.sleep(RETRY_WAIT)
                continue
            r.raise_for_status()
            data = r.json()
            articles = data.get("articles") or []
            return [_normalize(a, query) for a in articles]
        except Exception as exc:
            log.warning("GDELT attempt %d failed for %r: %s", attempt + 1, query, exc)
            if attempt < 2:
                time.sleep(RETRY_WAIT)
    return []


def _normalize(article: dict, query: str) -> dict:
    """Convert a GDELT article record to the headline format used by hb/news.py."""
    title = (article.get("title") or "").strip()
    url = article.get("url") or ""
    source = article.get("domain") or article.get("sourcecountry") or "GDELT"
    lang = (article.get("language") or "en").lower()
    published = article.get("seendate") or article.get("socialimage") or None

    # Parse GDELT date format: YYYYMMDDTHHMMSSZ
    when = None
    if published and len(published) >= 15:
        try:
            when = datetime.strptime(published[:15], "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc).isoformat()
        except ValueError:
            pass

    return {
        "title": title,
        "summary": "",          # GDELT doesn't provide summaries
        "link": url,
        "source": source,
        "source_domain": source,
        "image": article.get("socialimage") or None,
        "published": when,
        "official": False,
        "gdelt": True,
        "language": lang,
        "gdelt_query": query,
    }


def collect_egypt(max_per_query: int = 5, timespan: str = "24h") -> list[dict]:
    """
    Run all Egypt-specific GDELT queries and return deduplicated headlines.
    Called during the daily build to supplement CBE/EGX/CAPMAS direct feeds.
    """
    seen_urls: set[str] = set()
    results: list[dict] = []
    for query in EGYPT_QUERIES:
        lang = "ara" if any(ord(c) > 127 for c in query) else None
        items = _fetch(query, max_records=max_per_query, timespan=timespan, source_lang=lang)
        for item in items:
            if item["link"] not in seen_urls and item["title"]:
                seen_urls.add(item["link"])
                item["sector"] = "economy"
                item["regions"] = ["egypt"]
                item["check"] = "GDELT_EG"
                results.append(item)
        time.sleep(MIN_GAP)
    log.info("GDELT Egypt: %d headlines from %d queries", len(results), len(EGYPT_QUERIES))
    return results


def collect_by_sector(sector: str, max_per_query: int = 5,
                      timespan: str = "24h") -> list[dict]:
    """
    Collect GDELT headlines for a given sector using theme-based queries.
    Falls back to keyword search if no themes defined for the sector.
    """
    themes = SECTOR_THEMES.get(sector, [])
    if not themes:
        return []

    seen_urls: set[str] = set()
    results: list[dict] = []
    for theme in themes[:4]:           # cap at 4 theme queries per sector
        query = f"(sourcecountry:EG OR theme:{theme}) theme:{theme}"
        items = _fetch(query, max_records=max_per_query, timespan=timespan)
        for item in items:
            if item["link"] not in seen_urls and item["title"]:
                seen_urls.add(item["link"])
                item["sector"] = sector
                item["regions"] = ["global"]
                item["check"] = f"GDELT_{sector.upper()}"
                results.append(item)
        time.sleep(MIN_GAP)
    log.info("GDELT %s: %d headlines from %d theme queries", sector, len(results), len(themes[:4]))
    return results



_ECON_WORDS = ("economy", "peso", "rupee", "imf", "exports", "inflation", "currency")
_ENERGY_WORDS = ("oil", "gas", "opec", "energy")


def _region_sector(query: str) -> str:
    q = query.lower()
    if any(w in q for w in _ENERGY_WORDS):
        return "energy"
    if any(w in q for w in _ECON_WORDS):
        return "economy"
    return "politics"


def collect_region_gaps(max_per_query: int = 5, timespan: str = "24h") -> list[dict]:
    """
    Collect GDELT headlines for regions that English RSS feeds under-cover:
    Africa, Latin America, MENA (non-Egypt), Southeast Asia.
    """
    seen_urls: set[str] = set()
    results: list[dict] = []
    for region, queries in REGION_QUERIES.items():
        for query in queries[:2]:       # 2 queries per region max
            items = _fetch(query, max_records=max_per_query, timespan=timespan)
            for item in items:
                if item["link"] not in seen_urls and item["title"]:
                    seen_urls.add(item["link"])
                    item["sector"] = _region_sector(query)
                    item["regions"] = [region]
                    item["check"] = f"GDELT_{region.upper()}"
                    results.append(item)
            time.sleep(MIN_GAP)
    log.info("GDELT region gaps: %d headlines", len(results))
    return results


def collect_all(cfg: dict) -> list[dict]:
    """
    Main entry point. Run all GDELT queries and return combined headlines.
    Respects cfg["gdelt_enabled"] = False to skip entirely.
    """
    if not cfg.get("gdelt_enabled", True):
        log.info("GDELT disabled in config, skipping")
        return []

    timespan = cfg.get("gdelt_timespan", "24h")
    max_per = cfg.get("gdelt_per_query", 5)

    all_headlines: list[dict] = []
    all_headlines.extend(collect_egypt(max_per, timespan))
    all_headlines.extend(collect_region_gaps(max_per, timespan))

    # Sector-level GDELT for gaps not covered by RSS
    for sector in ["health", "climate", "cyber", "trade"]:
        all_headlines.extend(collect_by_sector(sector, max_per, timespan))

    # Assign sequential IDs (will be re-numbered in the main pipeline)
    for i, h in enumerate(all_headlines):
        h["id"] = f"g{i}"

    log.info("GDELT total: %d headlines", len(all_headlines))
    return all_headlines


if __name__ == "__main__":
    import json
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    results = collect_egypt(max_per_query=3, timespan="6h")
    print(json.dumps(results[:3], indent=2, ensure_ascii=False))
