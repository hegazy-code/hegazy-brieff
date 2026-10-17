"""Coverage report: proof of what was checked, what was published, and what wasn't found."""


def report(cfg, board, per_check, sectors):
    used = {u for st in sectors.values() for s in st if s["importance"] in ("HIGH", "MEDIUM", "LOW") for u in s["uses"]}
    market_by_check = {}
    for g in board:
        market_by_check.setdefault(g["check"], []).extend(g["rows"])
    rows = []
    for item in cfg["checklist"]:
        ids = per_check.get(item["id"], [])
        published = sum(1 for i in ids if i in used)
        mrows = market_by_check.get(item["id"], [])
        missing = [r["name"] for r in mrows if r["last"] is None]
        if published:
            status = "COVERED"
        elif ids:
            status = "NOT PUBLISHED"
        elif mrows and len(missing) < len(mrows):
            status = "COVERED"
        else:
            status = "NOT FOUND"
        note = f"{len(ids)} headlines found, {published} used"
        if mrows:
            note += f"; market data {len(mrows) - len(missing)}/{len(mrows)}"
            if missing:
                note += f" (no data: {', '.join(missing)})"
        rows.append({"id": item["id"], "title": item["title"], "status": status, "note": note})
    return rows
