"""Write and rank the stories with Gemini's free tier. Without a key, the site still builds from headlines.

Safety rules built in:
- The AI only sees headlines the site collected and must cite them by id (h12). Links and photos are
  attached by code from those ids, so the AI can't invent a source.
- Every number on the market board and in the charts comes from Yahoo Finance, not from the AI.
- The ranking caps (max HIGH stories, max radar lines) are enforced by code, not trusted to the AI.
"""
import json
import logging
import os
import time

import requests

log = logging.getLogger(__name__)
API = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
REGIONS = "usa, europe, asia, egypt, gulf, mena, africa, latam, global"
REGION_SET = set(REGIONS.split(", "))

RULES = f"""You are the editor of "The Hegazy Brief", a daily world-intelligence site for one reader:
a university student in Cairo learning finance, economics, accounting, trading and politics,
with special focus on the USA and Egypt.

Strict rules:
1. Use ONLY the headlines and market data given below. Never invent events, numbers or quotes.
   If something is unclear from the data, say so plainly.
2. Every story must list the ids of the headlines it uses in "uses" (for example ["h3","h17"]).
3. Market numbers must come from the MARKET DATA block. Don't use numbers that aren't in the
   headlines or the market data.
4. Politics: neutral facts only, no opinions about politicians or parties. Separate announced,
   proposed, enacted and implemented decisions. Separate verified facts from claims by parties to a conflict.
5. Simple, specific English that a beginner understands. Explain jargon the first time.
   Give a faithful Modern Standard Arabic translation in every *_ar field.
6. Rank every story:
   HIGH only if at least one is true: it moved a major index, currency, bond or commodity more
   than 1%; it directly affects Egypt's dollar sources, the pound, the EGX, inflation or interest
   rates; it is a central bank decision or a major data surprise; a war escalating or calming,
   or a major sanction or tariff; a watchlist stock moving more than 2%.
   MEDIUM: affects a whole sector or country, or is likely to matter within a week.
   LOW: useful context, no clear market or Egypt impact today. Write LOW items as one line only.
7. Lengths: HIGH body 150-250 words, MEDIUM 60-100 words, LOW body is one sentence.
8. For HIGH and MEDIUM, "chain" traces: cause -> investor reaction -> who won and lost ->
   what it means for Egypt -> what to watch next. Only connections supported by the data.
9. "regions" uses only: {REGIONS}.
10. "impact" is a number 1-10 for how much the story matters to world markets and Egypt.
12. "stat" is the single most important number in the story, copied exactly from the headlines or
    market data, with its sign or unit (for example "−2.1%", "$109.88", "11.2×"). Empty string if
    there is no reliable number. "stat_label" says in 2-5 words what the number is (e.g. "Nasdaq, Friday").
13. "what_en", "why_en", "egypt_en": one short sentence each: what happened, why it happened, and
    what it means for Egypt. These are what the reader sees first, so make them punchy and concrete.
    "body_en" holds the full explanation for readers who open the story.
11. Respond with JSON only.
14. Headlines marked [OFFICIAL] come from central banks, governments, regulators, exchanges or
    international organizations. When an official headline and a media headline cover the same fact,
    base the fact on the official one and cite it first."""

STORY_SCHEMA = ('{"stories": [{"importance": "HIGH|MEDIUM|LOW", "impact": 1-10, "regions": [str], '
                '"stat": str, "stat_label": str, "title_en": str, "title_ar": str, '
                '"what_en": str, "why_en": str, "egypt_en": str, "what_ar": str, "why_ar": str, "egypt_ar": str, '
                '"body_en": str, "body_ar": str, "chain_en": str, "chain_ar": str, "uses": [str]}]}')

SUMMARY_SCHEMA = ('{"five_minute": [{"en": str, "ar": str}], "pocket_chain": [{"en": str, "ar": str}], "new_terms": [{"term": str, "match": [str], "en": str, "ar": str}], '
                  '"risk_watch": [{"level": "esc|watch", "situation_en": str, "situation_ar": str, "status_en": str, "status_ar": str, '
                  '"next_en": str, "next_ar": str, "watch_en": str, "watch_ar": str, "regions": [str]}], '
                  '"calendar": [{"when": str, "en": str, "ar": str, "regions": [str], "uses": [str]}], '
                  '"terms": [{"term_en": str, "term_ar": str, "explain_en": str, "explain_ar": str, '
                  '"example_en": str, "example_ar": str}]}')

SECTOR_TASK = {
    "markets": "Markets and trading: stocks in every region, bonds, currencies, commodities, crypto, and the watchlist.",
    "economy": "The economy: central banks, economic data, Egypt's economy and dollar sources, and next week's events.",
    "finance": "Finance: company earnings, deals, IPOs, banks, defaults and investment flows.",
    "accounting": "Accounting: reported vs adjusted profits, write-downs, restatements, audits, new rules, regulators.",
    "politics": "Politics and geopolitics in every region, especially the USA, Egypt, the Gulf and the wider Middle East. Publish only events with real consequences; the rest stays out.",
    "business": "Business and technology across every industry: tech and AI, banks, energy, healthcare, real estate, autos, consumer, defense, shipping, travel, telecom, food, mining.",
    "wsj": "Wall Street Journal stories. You only see headlines and snippets: summarize in your own words, never copy, and say 'headline only' if the snippet is too thin to explain the story.",
}


def gemini(prompt):
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        return None
    model = os.environ.get("GEMINI_MODEL") or "gemini-2.5-flash"
    body = {"contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseMimeType": "application/json", "temperature": 0.2}}
    for attempt in range(4):
        try:
            r = requests.post(API.format(model=model), params={"key": key}, json=body, timeout=180)
            if r.status_code == 429:
                time.sleep(30 * (attempt + 1))
                continue
            r.raise_for_status()
            return json.loads(r.json()["candidates"][0]["content"]["parts"][0]["text"])
        except Exception as exc:
            log.warning("Gemini call failed (attempt %d): %s", attempt + 1, exc)
            time.sleep(8)
    return None


def market_block(board):
    lines = []
    for g in board:
        for r in g["rows"]:
            if r["last"] is not None:
                lines.append(f"{g['group']} | {r['name']}: {r['last']:,.2f} ({r['chg']:+.2f}%) on {r['date']}")
    return "\n".join(lines) or "No market data."


def headline_block(items):
    return "\n".join(f"{h['id']} {'[OFFICIAL] ' if h.get('official') else ''}[{h['source']}] {h['title']} | {h['summary'][:220]}" for h in items)


def fallback_stories(items, limit):
    return [{"importance": "LOW", "impact": 1, "regions": h["regions"], "title_en": h["title"], "title_ar": "",
             "stat": "", "stat_label": "", "what_en": "", "why_en": "", "egypt_en": "", "what_ar": "", "why_ar": "",
             "egypt_ar": "", "body_en": "", "body_ar": "", "chain_en": "", "chain_ar": "", "uses": [h["id"]]}
            for h in items[:limit]]


def write(cfg, board, headlines, big):
    by_id = {h["id"]: h for h in headlines}
    mdata = market_block(board)
    moves = ", ".join(big) or "none"
    sectors = {}
    for sector, task in SECTOR_TASK.items():
        items = sorted([h for h in headlines if h["sector"] == sector], key=lambda h: not h.get("official"))[:120]
        if not items:
            sectors[sector] = []
            continue
        prompt = (f"{RULES}\n\nSECTOR: {task}\nMoves above the HIGH threshold today: {moves}\n"
                  f"Schema: {STORY_SCHEMA}\n\nMARKET DATA:\n{mdata}\n\nHEADLINES:\n{headline_block(items)}")
        res = gemini(prompt)
        stories = res.get("stories", []) if isinstance(res, dict) else fallback_stories(items, cfg["max_radar"])
        clean_stories = []
        for s in stories:
            uses = [u for u in s.get("uses", []) if u in by_id]
            if not uses:  # no valid source: drop it, never publish an unsourced story
                continue
            s["uses"] = uses
            s["importance"] = s.get("importance", "LOW").upper()
            if s["importance"] not in ("HIGH", "MEDIUM", "LOW"):
                s["importance"] = "LOW"
            s["regions"] = [r for r in s.get("regions", []) if r in REGION_SET] or by_id[uses[0]]["regions"]
            clean_stories.append(s)
        sectors[sector] = clean_stories
        if os.environ.get("GEMINI_API_KEY"):
            time.sleep(7)

    # Enforce caps in code.
    highs = sorted([s for st in sectors.values() for s in st if s["importance"] == "HIGH"],
                   key=lambda s: s.get("impact", 0), reverse=True)
    for s in highs[cfg["max_high"]:]:
        s["importance"] = "MEDIUM"
    for sector, st in sectors.items():
        lows = [s for s in st if s["importance"] == "LOW"]
        for s in lows[cfg["max_radar"]:]:
            s["importance"] = "DROPPED"

    published = [s for st in sectors.values() for s in st if s["importance"] in ("HIGH", "MEDIUM")]
    titles = "\n".join(f"[{s['importance']}] {s['title_en']}" for s in published) or "No major stories."
    cal_items = [h for h in headlines if h["check"] in ("A16", "A7", "A10")][:60]
    n = cfg["_day"]
    term = cfg["curriculum"][(n - 1) % len(cfg["curriculum"])]
    prompt = (f"{RULES}\n\nTasks:\n"
              f"1. five_minute: at most 7 one-sentence bullets, the most important things today, most important first.\n"
              f"1b. pocket_chain: 4-5 very short steps (3-6 words each) showing how today's biggest world event reaches "
              f"prices or jobs in Egypt, e.g. 'Attacks near Hormuz', 'Oil near $110', 'Egypt's energy bill rises', "
              f"'Pound weakens', 'Pricier fuel and wheat'. Only steps the headlines or market data support.\n"
              f"2. risk_watch: the 3-6 biggest ongoing political or geopolitical situations in these stories: level "
              f"(esc if getting worse, watch otherwise), current status, next deadline or decision, and what to watch. "
              f"Use only what the headlines support.\n"
              f"3. calendar: events in the next 7 days that the headlines explicitly mention, with ids in uses. "
              f"Never invent dates.\n4. terms: explain '{term}' plus two terms from today's stories, each in 3 simple "
              f"sentences with a concrete Egyptian example.\nSchema: {SUMMARY_SCHEMA}\n\nMARKET DATA:\n{mdata}\n\n"
              f"TODAY'S STORIES:\n{titles}\n\nCALENDAR HEADLINES:\n{headline_block(cal_items)}")
    summary = gemini(prompt)
    if not isinstance(summary, dict):
        summary = {"five_minute": [{"en": m, "ar": ""} for m in big[:7]] or [{"en": "Add a GEMINI_API_KEY to get the written brief.", "ar": ""}],
                   "risk_watch": [], "calendar": [],
                   "terms": [{"term_en": term, "term_ar": "", "explain_en": "Add a GEMINI_API_KEY to get explanations.",
                              "explain_ar": "", "example_en": "", "example_ar": ""}]}
    summary["calendar"] = [c for c in summary.get("calendar", []) if any(u in by_id for u in c.get("uses", []))]
    summary["term"] = term
    return sectors, summary
