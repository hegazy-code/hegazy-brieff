"""Build today's edition of Hegazy Brief into docs/.

    python build.py           live data (needs internet; GEMINI_API_KEY for written stories)
    python build.py --mock    sample data, no internet, to check the design
"""

import argparse
import json
import logging
import re
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape

from hb.charts import bars, fmt, line


# Market closing times.
CLOSES = [
    ("EGX30", "Cairo", "Africa/Cairo", (14, 30), "egypt", "مؤشر EGX30"),
    ("Saudi TASI", "Riyadh", "Asia/Riyadh", (15, 0), "gulf", "المؤشر السعودي"),
    ("Nikkei 225", "Tokyo", "Asia/Tokyo", (15, 30), "asia", "نيكاي الياباني"),
    ("STOXX 600", "Europe", "Europe/Berlin", (17, 30), "europe", "STOXX 600 الأوروبي"),
    ("Nasdaq", "New York", "America/New_York", (16, 0), "usa", "ناسداك الأمريكي"),
]

ROOT = Path(__file__).parent
DOCS = ROOT / "docs"
DATA = ROOT / "data"

CAIRO = ZoneInfo("Africa/Cairo")

log = logging.getLogger("build")
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s %(message)s",
)


def pretty_date(d):
    """Format dates portably on Windows, macOS, and Linux."""
    return f"{d.strftime('%A,')} {d.day} {d.strftime('%B %Y')}"


def pretty_time_12h(dt):
    """Format time portably without platform-specific strftime modifiers."""
    hour = dt.hour % 12 or 12
    return f"{dt.strftime('%a')} {hour}:{dt.strftime('%M %p')}".upper()


SECTORS = [
    ("markets", "Markets & trading", "الأسواق والتداول"),
    ("economy", "Economy", "الاقتصاد"),
    ("finance", "Finance", "المالية"),
    ("accounting", "Accounting", "المحاسبة"),
    ("politics", "Politics", "السياسة"),
    ("business", "Business & tech", "الأعمال والتكنولوجيا"),
    ("wsj", "Wall Street Journal", "وول ستريت جورنال"),
    ("energy", "Energy", "الطاقة"),
    ("technology", "Technology & AI", "التكنولوجيا والذكاء الاصطناعي"),
    ("cyber", "Cybersecurity", "الأمن السيبراني"),
    ("health", "Health & medicine", "الصحة والطب"),
    ("climate", "Environment & climate", "البيئة والمناخ"),
    ("science", "Science & research", "العلوم والبحث"),
    ("trade", "Trade & supply chains", "التجارة وسلاسل التوريد"),
    ("infrastructure", "Infrastructure", "البنية التحتية"),
    ("law", "Law & regulation", "القانون والتنظيم"),
    ("labor", "Education & labor", "التعليم والعمل"),
    ("sports", "Sports", "الرياضة"),
    ("society", "Society & culture", "المجتمع والثقافة"),
]

REGIONS = [
    ("usa", "USA", "أمريكا"),
    ("europe", "Europe", "أوروبا"),
    ("asia", "Asia", "آسيا"),
    ("egypt", "Egypt", "مصر"),
    ("gulf", "Gulf", "الخليج"),
    ("mena", "Middle East & N. Africa", "الشرق الأوسط وشمال أفريقيا"),
    ("africa", "Africa", "أفريقيا"),
    ("latam", "Latin America", "أمريكا اللاتينية"),
]

REGION_NAMES = {k: en for k, en, _ in REGIONS} | {"global": "Global"}
SECTOR_NAMES = {k: en for k, en, _ in SECTORS}


def typo(s, ar=False):
    """Apply typographic apostrophes and quotation marks."""
    if not s:
        return s or ""

    s = re.sub(r"(\w)'(\w)", "\\1’\\2", s).replace("'", "’")

    opening_quote, closing_quote = (
        ("«", "»") if ar else ("“", "”")
    )

    out = []
    opening = True

    for ch in s:
        if ch == '"':
            out.append(opening_quote if opening else closing_quote)
            opening = not opening
        else:
            out.append(ch)

    return "".join(out)


def _digits(s):
    return re.sub(r"[^0-9.]", "", (s or "").replace("−", "-"))


def stat_ok(stat, texts):
    """Only show a number if it appears in the cited text or market data."""
    d = _digits(stat)

    if not d:
        return False

    blob = " ".join(texts)

    return (
        d in re.sub(r"[^0-9.]", " ", blob).replace(" ", "")
        or d in _digits(blob)
        or d.rstrip("0").rstrip(".") in blob
    )


def stories_view(sectors, headlines, mdata):
    by_id = {h["id"]: h for h in headlines}
    out = []

    for key, sector_stories in sectors.items():
        for story in sector_stories:

            if story.get("importance") not in ("HIGH", "MEDIUM", "LOW"):
                continue

            used_headlines = [
                by_id[uid]
                for uid in story.get("uses", [])
                if uid in by_id
            ]

            texts = [
                h["title"] + " " + h.get("summary", "")
                for h in used_headlines
            ] + [mdata]

            stat = story.get("stat", "")

            if stat and not stat_ok(stat, texts):
                stat = ""

            img = next(
                (h for h in used_headlines if h.get("image")),
                None,
            )

            out.append({
                "kicker": (
                    SECTOR_NAMES[key]
                    + ", "
                    + ", ".join(
                        REGION_NAMES.get(r, r)
                        for r in story["regions"]
                    )
                ),
                "sector": key,
                "sector_name": SECTOR_NAMES[key],
                "importance": story["importance"],
                "impact": story.get("impact", 0),
                "regions": story["regions"],
                "region_str": " ".join(story["regions"]),
                "region_labels": [
                    REGION_NAMES.get(r, r)
                    for r in story["regions"]
                ],
                "stat": stat,
                "label": story.get("stat_label", "") if stat else "",
                "stat_cls": (
                    "up"
                    if stat.startswith("+")
                    else "down"
                    if stat.startswith(("−", "-"))
                    else ""
                ),
                "t_en": typo(story.get("title_en")),
                "t_ar": typo(story.get("title_ar"), True),
                "what_en": typo(story.get("what_en")),
                "why_en": typo(story.get("why_en")),
                "egypt_en": typo(story.get("egypt_en")),
                "what_ar": typo(story.get("what_ar"), True),
                "why_ar": typo(story.get("why_ar"), True),
                "egypt_ar": typo(story.get("egypt_ar"), True),
                "full_en": (
                    [typo(story["body_en"])]
                    if story.get("body_en")
                    and story["importance"] != "LOW"
                    else []
                ),
                "full_ar": (
                    [typo(story["body_ar"], True)]
                    if story.get("body_ar")
                    and story["importance"] != "LOW"
                    else []
                ),
                "chain_en": typo(story.get("chain_en")),
                "chain_ar": typo(story.get("chain_ar"), True),
                "chart_html": "",
                "sources": [
                    (
                        h["source"]
                        + (" (official)" if h.get("official") else ""),
                        h["link"],
                    )
                    for h in used_headlines
                ][:5],
                "image": img["image"] if img else None,
                "image_credit": img["source"] if img else None,
            })

    return out


def timeline_view(board):
    rows = {
        row["name"]: row
        for group in board
        for row in group["rows"]
    }

    stops = []

    for name, place, tz, (hh, mm), region, ar in CLOSES:
        row = rows.get(name)

        if not row or row["chg"] is None or not row["date"]:
            continue

        local = datetime.combine(
            date.fromisoformat(row["date"]),
            datetime.min.time(),
        ).replace(
            hour=hh,
            minute=mm,
            tzinfo=ZoneInfo(tz),
        )

        cairo = local.astimezone(CAIRO)

        sign = (
            "+"
            if row["chg"] > 0
            else "−"
            if row["chg"] < 0
            else ""
        )

        stops.append({
            "when": cairo,
            "time": pretty_time_12h(cairo),
            "place": place,
            "region": region,
            "value": f"{sign}{abs(row['chg']):.2f}%",
            "cls": "up" if row["chg"] >= 0 else "down",
            "en": f"{name} at the close.",
            "ar": f"{ar} عند الإغلاق.",
        })

    stops.sort(key=lambda x: x["when"])

    return stops


def board_view(board):
    out = []

    for group in board:
        rows = [
            {
                "name": row["name"],
                "display": None,
                "last": row["last"],
                "chg": row["chg"],
                "note": "",
            }
            for row in group["rows"]
        ]

        out.append({
            "group": group["group"],
            "region": group["region"],
            "rows": rows,
        })

    return out


def chart_cards(cfg, series, board):
    rows = [
        (row["name"], row["chg"])
        for group in board
        for row in group["rows"]
        if row["chg"] is not None
        and row["name"] != "VIX"
        and group["check"] in (
            "A2.1", "A2.2", "A2.3", "A2.4",
            "A2.5", "A2.6", "A5", "A6",
        )
    ]

    rows.sort(key=lambda x: x[1], reverse=True)

    cards = [{
        "region": "all",
        "title_en": "Today’s moves",
        "title_ar": "حركة اليوم",
        "html": bars(
            rows[:10] + rows[-10:]
            if len(rows) > 20
            else rows
        ),
        "cap_en": "Daily change at last close, %. Source: Yahoo Finance.",
        "cap_ar": "التغير اليومي عند آخر إغلاق %. المصدر: ياهو فاينانس.",
    }]

    for chart in cfg["charts"]:
        points = series.get(chart["symbol"]) or []

        if len(points) < 2:
            continue

        first, last = points[0][1], points[-1][1]
        change = (last / first - 1) * 100 if first else 0

        cls = "up" if change >= 0 else "down"

        sign = (
            "+"
            if change > 0
            else "−"
            if change < 0
            else ""
        )

        html = (
            f'<div class="lc-v num">{fmt(last)}</div>'
            f'<div class="lc-c num {cls}">'
            f'{sign}{abs(change):.2f}% over 60 days</div>'
            f'{line(points)}'
        )

        cards.append({
            "region": chart["region"],
            "title_en": chart["name"],
            "title_ar": "",
            "html": html,
            "cap_en": (
                f"{points[0][0]} to {points[-1][0]}. "
                "Source: Yahoo Finance."
            ),
            "cap_ar": "",
        })

    return cards



def _title_key(title):
    return re.sub(r"\W+", " ", (title or "").lower()).strip()[:90]



def _checks_for(cfg, h):
    """Checklist items a non-RSS headline counts toward: its own check id if it is one,
    otherwise every item with the same sector and an overlapping region."""
    ids = {item["id"] for item in cfg.get("checklist", [])}
    if h.get("check") in ids:
        return [h["check"]]
    regions = set(h.get("regions") or [])
    hits = [item["id"] for item in cfg.get("checklist", [])
            if item["sector"] == h.get("sector") and regions & set(item["regions"])]
    return hits or [h.get("check")]


def collect_sources(cfg):
    """Collect headlines in priority order: official primary sources, then GDELT, then Google News RSS.

    Earlier stages win duplicates, so a CBE press release beats a journalist's write-up of it.
    Every stage is gated by the health registry (data/source_state.json, written by health.yml)
    and isolated, so a dead source costs a log line, never the build.
    Returns (headlines, per_check) with ids renumbered h0..hN, the format the AI prompt expects.
    """
    from hb import gdelt, primary, sources
    from hb.news import collect

    state = sources._load_state()

    def allow(source_id):
        s = state.get(source_id, {})
        if s.get("status") != "down":      # up, unknown or degraded: still try
            return True
        stamps = [t for t in (s.get("last_ok"), s.get("last_fail")) if t]
        try:
            age = datetime.now(ZoneInfo("UTC")) - datetime.fromisoformat(max(stamps))
            if age.total_seconds() > 12 * 3600:   # stale verdict: health.yml hasn't run, so try anyway
                return True
        except ValueError:
            return True
        return "429" in (s.get("last_msg") or "")   # rate-limited is not down

    stages = []
    try:
        stages.append(("primary", primary.collect_all(allow=allow), {}))
    except Exception as exc:
        log.warning("Primary stage failed: %s", exc)
    if allow("gdelt"):
        try:
            stages.append(("gdelt", gdelt.collect_all(cfg), {}))
        except Exception as exc:
            log.warning("GDELT stage failed: %s", exc)
    else:
        log.info("GDELT skipped: marked down in source registry")
    rss, rss_checks = collect(cfg)
    stages.append(("rss", rss, rss_checks))

    headlines, by_key, remap, per_check = [], {}, {}, {}
    counts = {}
    for name, items, checks in stages:
        kept = 0
        for h in items:
            key = _title_key(h.get("title"))
            if not key:
                continue
            old = h.get("id")
            if key in by_key:
                remap[(name, old)] = by_key[key]
                continue
            new = f"h{len(headlines)}"
            by_key[key] = remap[(name, old)] = new
            h = {**h, "id": new}
            h.setdefault("summary", "")
            h.setdefault("regions", ["global"])
            h.setdefault("sector", "economy")
            h.setdefault("check", name.upper())
            headlines.append(h)
            kept += 1
            if name != "rss":
                for check in _checks_for(cfg, h):
                    per_check.setdefault(check, []).append(new)
        counts[name] = (len(items), kept)
        for check, ids in checks.items():
            merged = per_check.setdefault(check, [])
            for old in ids:
                new = remap.get((name, old))
                if new and new not in merged:
                    merged.append(new)
    log.info("Sources: %s", ", ".join(f"{n} {raw} raw / {kept} kept" for n, (raw, kept) in counts.items()))
    return headlines, per_check


def build(mock=False):
    cfg = yaml.safe_load(
        (ROOT / "config.yaml").read_text(encoding="utf-8")
    )

    now = datetime.now(CAIRO)
    today = now.date()

    cfg["_day"] = (
        today - date.fromisoformat(cfg["start_date"])
    ).days + 1

    glossary = yaml.safe_load(
        (ROOT / "glossary.yaml").read_text(encoding="utf-8")
    ) or []

    cfg["_glossary_terms"] = [
        item["term"] for item in glossary
    ]

    if mock:
        sample = json.loads(
            (ROOT / "sample_data.json").read_text(encoding="utf-8")
        )

        (
            board,
            series,
            headlines,
            per_check,
            sectors,
            summary,
        ) = (
            sample[key]
            for key in (
                "board",
                "series",
                "headlines",
                "per_check",
                "sectors",
                "summary",
            )
        )

    else:
        from hb.ai import write
        from hb.markets import big_moves, fetch

        board, series = fetch(cfg)
        headlines, per_check = collect_sources(cfg)

        sectors, summary = write(
            cfg,
            board,
            headlines,
            big_moves(board),
        )

    from hb.ai import market_block
    from hb.coverage import report
    from hb.notify import send

    coverage = report(cfg, board, per_check, sectors)

    payload = {
        "date": today.isoformat(),
        "built": now.strftime("%H:%M"),
        "board": board,
        "series": series,
        "headlines": headlines,
        "sectors": sectors,
        "summary": summary,
    }

    DATA.mkdir(exist_ok=True)

    (DATA / f"{today.isoformat()}.json").write_text(
        json.dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )

    stories = stories_view(
        sectors,
        headlines,
        market_block(board),
    )

    main = sorted(
        [story for story in stories if story["importance"] != "LOW"],
        key=lambda story: (
            story["importance"] != "HIGH",
            -story["impact"],
        ),
    )

    quick = [
        story
        for story in stories
        if story["importance"] == "LOW"
    ]

    lead = main.pop(0) if main else None

    movers = [
        (row["name"], row["chg"])
        for group in board
        for row in group["rows"]
        if row["chg"] is not None and row["name"] != "VIX"
    ]

    movers.sort(key=lambda x: x[1], reverse=True)

    watch = []

    for group in board:
        if group["check"] == "A1":
            for row in group["rows"]:
                if row["last"] is None:
                    value = "no data"
                else:
                    value = fmt(row["last"])

                    if row["chg"] is not None:
                        sign = (
                            "+"
                            if row["chg"] > 0
                            else "−"
                            if row["chg"] < 0
                            else ""
                        )

                        value += (
                            f" ({sign}{abs(row['chg']):.2f}%)"
                        )

                watch.append({
                    "name": row["name"],
                    "value": value,
                    "cls": (
                        ""
                        if row["chg"] is None
                        else "up"
                        if row["chg"] >= 0
                        else "down"
                    ),
                    "note": (
                        "Price not available from Yahoo Finance today."
                        if row["last"] is None
                        else f"Last close {row['date']}."
                    ),
                })

    for item in summary.get("five_minute", []):
        item["en"] = typo(item.get("en"))
        item["ar"] = typo(item.get("ar"), True)

    for item in summary.get("risk_watch", []):
        item["level"] = (
            "esc" if item.get("level") == "esc" else "watch"
        )
        item["level_label"] = (
            "Escalating"
            if item["level"] == "esc"
            else "Watch"
        )
        item.setdefault("regions", ["global"])

    for item in summary.get("calendar", []):
        item.setdefault("regions", ["global"])

    env = Environment(
        loader=FileSystemLoader(ROOT / "templates"),
        autoescape=select_autoescape(),
    )

    env.filters["num"] = (
        lambda value: "no data" if value is None else fmt(value)
    )

    env.filters["pct"] = (
        lambda value: ""
        if value is None
        else (
            f"({'+' if value > 0 else '−' if value < 0 else ''}"
            f"{abs(value):.2f}%)"
        )
    )

    # Add suggested glossary terms only when they appear in today's stories.
    all_text = " ".join(
        story["t_en"]
        + " "
        + story["what_en"]
        + " "
        + story["why_en"]
        + " "
        + story["egypt_en"]
        + " "
        + " ".join(story["full_en"])
        for story in ([lead] if lead else []) + main + quick
    ).lower()

    known = {
        item["term"].lower()
        for item in glossary
    }

    for term in summary.get("new_terms", [])[:12]:
        matches = [
            word
            for word in term.get("match", [])
            if word and word.lower() in all_text
        ]

        if (
            term.get("term")
            and term.get("en")
            and matches
            and term["term"].lower() not in known
        ):
            glossary.append({
                "term": term["term"],
                "match": matches,
                "en": typo(term["en"]),
                "ar": typo(term.get("ar", ""), True),
            })

    def _j(obj):
        return json.dumps(
            obj,
            ensure_ascii=False,
        ).replace("</", "<\\/")

    def _story_text(story):
        parts = [
            story["t_en"],
            story["what_en"],
            story["why_en"],
            story["egypt_en"],
            *story["full_en"],
            story["t_ar"],
        ]

        return (
            " | ".join(part for part in parts if part)
            + " | Sources: "
            + ", ".join(name for name, _ in story["sources"])
        )

    brief = {
        "date": pretty_date(today),
        "markets": [
            group["group"]
            + ": "
            + ", ".join(
                f"{row['name']} {fmt(row['last'])}"
                + (
                    f" ({row['chg']:+.2f}%)"
                    if row["chg"] is not None
                    else ""
                )
                for row in group["rows"]
                if row["last"] is not None
            )
            for group in board
        ],
        "stories": [
            {
                "title": story["t_en"],
                "text": _story_text(story),
            }
            for story in ([lead] if lead else []) + main + quick
        ],
    }

    chain = [
        item
        for item in summary.get("pocket_chain", [])
        if item.get("en")
    ][:5]

    for item in chain:
        item["en"] = typo(item["en"])
        item["ar"] = typo(item.get("ar", ""), True)

    ctx = dict(
        pretty_date=pretty_date(today),
        archive_link=True,
        glossary_json=_j(glossary),
        brief_json=_j(brief),
        chat_endpoint=cfg.get("chat_endpoint") or "",
        timeline=timeline_view(board),
        chain=chain,
        lead=lead,
        stories=main,
        quick=quick,
        summary=summary,
        charts=chart_cards(cfg, series, board),
        board=board_view(board),
        sector_names=SECTORS,
        regions=REGIONS,
        board_note=(
            "Last close from Yahoo Finance, the ECB, CoinGecko and FRED. "
            f"Updated {now.strftime('%H:%M')} Cairo time; may be delayed."
        ),
        fine_print=(
            "For learning, not investment advice."
        ),
    )

    DOCS.mkdir(exist_ok=True)

    page = env.get_template("edition.html").render(**ctx)

    (DOCS / f"{today.isoformat()}.html").write_text(
        page,
        encoding="utf-8",
    )

    (DOCS / "index.html").write_text(
        page,
        encoding="utf-8",
    )

    days = sorted(
        (path.stem for path in DATA.glob("*.json")),
        reverse=True,
    )

    archive = [
        {
            "date": day,
            "pretty": pretty_date(date.fromisoformat(day)),
        }
        for day in days
    ]

    (DOCS / "archive.html").write_text(
        env.get_template("archive.html").render(days=archive),
        encoding="utf-8",
    )

    (DOCS / ".nojekyll").write_text(
        "",
        encoding="utf-8",
    )

    send(today.isoformat(), coverage)

    logging.info(
        "Built %s: %d headlines, %d cards, %d quick hits",
        today,
        len(headlines),
        len(main) + (1 if lead else 0),
        len(quick),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mock", action="store_true")
    build(parser.parse_args().mock)
