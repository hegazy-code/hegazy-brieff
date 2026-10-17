"""Collect headlines for every checklist line, with photos from feeds that provide them."""
import html
import logging
import re
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import quote_plus

log = logging.getLogger(__name__)
TAG = re.compile(r"<[^>]+>")


def gnews(q, arabic=False):
    q = quote_plus(f"{q} when:2d")
    if arabic:
        return f"https://news.google.com/rss/search?q={q}&hl=ar&gl=EG&ceid=EG:ar"
    return f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"


def clean(s):
    return re.sub(r"\s+", " ", html.unescape(TAG.sub(" ", s or ""))).strip()


def image_of(entry):
    for key in ("media_thumbnail", "media_content"):
        for m in entry.get(key) or []:
            url = m.get("url") or ""
            if url.startswith("https://"):
                return url
    for link in entry.get("links") or []:
        href = link.get("href") or ""
        if link.get("rel") == "enclosure" and (link.get("type") or "").startswith("image") and href.startswith("https://"):
            return href
    return None


def domain_of(url):
    try:
        host = url.split("/")[2].lower()
        return host[4:] if host.startswith("www.") else host
    except IndexError:
        return ""


def parse(url, cutoff, limit):
    import feedparser
    try:
        feed = feedparser.parse(url)
    except Exception as exc:
        log.warning("Feed failed %s: %s", url, exc)
        return []
    default_src = clean(feed.feed.get("title", "")) or url.split("/")[2]
    out = []
    for e in feed.entries[:limit]:
        title = clean(e.get("title"))
        if not title:
            continue
        p = e.get("published_parsed") or e.get("updated_parsed")
        when = datetime.fromtimestamp(time.mktime(p), tz=timezone.utc) if p else None
        if when and when < cutoff:
            continue
        source = clean((e.get("source") or {}).get("title", "")) or default_src
        source_domain = domain_of((e.get("source") or {}).get("href", "") or e.get("link", "") or url)
        if source and title.endswith(" - " + source):  # Google News appends " - Source"
            title = title[: -len(source) - 3]
        out.append({"title": title, "summary": clean(e.get("summary"))[:300], "link": e.get("link", ""),
                    "source": source, "source_domain": source_domain, "image": image_of(e), "published": when.isoformat() if when else None})
    return out


def collect(cfg):
    """Returns (headlines, per_check). Each headline gets an id like h12 so the AI can cite it."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=cfg["max_age_hours"])
    limit = cfg["per_query"]
    seen, headlines, per_check = {}, [], {}
    for item in cfg["checklist"]:
        urls = [gnews(q) for q in item.get("queries", [])]
        urls += [gnews(q, arabic=True) for q in item.get("ar_queries", [])]
        urls += [cfg["feeds"][f] for f in item.get("feeds", [])]
        official_urls = {cfg["feeds"][f] for f in cfg.get("official_feeds", []) if f in cfg["feeds"]}
        official_domains = tuple(cfg.get("official_domains", []))
        ids = []
        for url in urls:
            for h in parse(url, cutoff, limit):
                d = h.get("source_domain", "")
                h["official"] = url in official_urls or any(d == od or d.endswith("." + od) for od in official_domains)
                key = h["title"].lower()[:90]
                hid = seen.get(key)
                if hid is None:
                    hid = f"h{len(headlines)}"
                    seen[key] = hid
                    headlines.append({**h, "id": hid, "check": item["id"], "sector": item["sector"],
                                      "regions": item["regions"]})
                if hid not in ids:
                    ids.append(hid)
        per_check[item["id"]] = ids
        log.info("%s %s: %d headlines", item["id"], item["title"], len(ids))
    return headlines, per_check
