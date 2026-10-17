"""Market data from Yahoo Finance (free, via yfinance). Every number on the site comes from here."""
import logging

log = logging.getLogger(__name__)


def history(symbol, period="3mo"):
    import yfinance as yf
    closes = yf.Ticker(symbol).history(period=period, auto_adjust=False)["Close"].dropna()
    return [(idx.strftime("%Y-%m-%d"), float(v)) for idx, v in closes.items()]


def fetch(cfg):
    """Returns (board, series). board: groups with rows; series: {symbol: [(date, close), ...]}."""
    wanted = {c["symbol"] for c in cfg["charts"]}
    board, series = [], {}
    for g in cfg["markets"]:
        rows = []
        for name, sym in g["items"]:
            row = {"name": name, "symbol": sym, "last": None, "chg": None, "date": None}
            try:
                h = history(sym)
                if len(h) >= 2:
                    (_, prev), (d2, last) = h[-2], h[-1]
                    row.update(last=last, chg=(last / prev - 1) * 100 if prev else None, date=d2)
                if sym in wanted and h:
                    series[sym] = h[-60:]
            except Exception as exc:
                log.warning("No data for %s (%s): %s", name, sym, exc)
            rows.append(row)
        board.append({**g, "rows": rows})
    for c in cfg["charts"]:
        if c["symbol"] not in series:
            try:
                series[c["symbol"]] = history(c["symbol"])[-60:]
            except Exception as exc:
                log.warning("No chart data for %s: %s", c["symbol"], exc)
    try:
        from hb.data_apis import extra_groups
        board.extend(extra_groups())
    except Exception as exc:
        log.warning("Extra data APIs failed: %s", exc)
    return board, series


def big_moves(board, threshold=1.0):
    """Moves that meet the HIGH rule: above 1% for markets, above 2% for the watchlist."""
    out = []
    for g in board:
        limit = 2.0 if g["check"] == "A1" else threshold
        for r in g["rows"]:
            if r["chg"] is not None and r["name"] != "VIX" and abs(r["chg"]) >= limit:
                out.append(f"{r['name']} {r['chg']:+.2f}%")
    return out
