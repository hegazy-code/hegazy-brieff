"""Free official and open data APIs, added to the market board.

- Frankfurter: exchange rates published by the European Central Bank (no key).
- CoinGecko: total crypto market cap (no key).
- FRED, St. Louis Fed: US Treasury yields, unemployment and the Fed's target rate (free key: FRED_API_KEY).
Every call is optional: if one fails, the board simply shows "no data" for it and the coverage report says so.
"""
import logging
import os
from datetime import date, timedelta

import requests

log = logging.getLogger(__name__)


def _get(url, **params):
    r = requests.get(url, params=params, timeout=30, headers={"User-Agent": "HegazyBrief/1.0"})
    r.raise_for_status()
    return r.json()


def fx_rows():
    start = (date.today() - timedelta(days=10)).isoformat()
    targets = {"EUR": "USD/EUR", "GBP": "USD/GBP", "JPY": "USD/JPY", "CNY": "USD/CNY", "INR": "USD/INR", "TRY": "USD/TRY"}
    for base in ("https://api.frankfurter.dev/v1", "https://api.frankfurter.app"):
        try:
            data = _get(f"{base}/{start}..", **{"from": "USD", "to": ",".join(targets)})
            days = sorted(data["rates"])
            if len(days) < 2:
                break
            prev, last = data["rates"][days[-2]], data["rates"][days[-1]]
            return [{"name": f"{targets[k]} (ECB)", "symbol": k, "last": last[k], "chg": (last[k] / prev[k] - 1) * 100,
                     "date": days[-1]} for k in targets if k in last and k in prev]
        except Exception as exc:
            log.warning("Frankfurter %s failed: %s", base, exc)
    return [{"name": f"{v} (ECB)", "symbol": k, "last": None, "chg": None, "date": None} for k, v in targets.items()]


def crypto_rows():
    try:
        d = _get("https://api.coingecko.com/api/v3/global")["data"]
        return [{"name": "Total crypto market cap (USD bn)", "symbol": "CG-TOTAL",
                 "last": d["total_market_cap"]["usd"] / 1e9, "chg": d.get("market_cap_change_percentage_24h_usd"),
                 "date": date.today().isoformat()}]
    except Exception as exc:
        log.warning("CoinGecko failed: %s", exc)
        return [{"name": "Total crypto market cap (USD bn)", "symbol": "CG-TOTAL", "last": None, "chg": None, "date": None}]


FRED_SERIES = {"DGS2": "US 2-year yield (%)", "DGS10": "US 10-year yield (%, FRED)", "DGS30": "US 30-year yield (%)",
               "DFEDTARU": "Fed funds target, top (%)", "UNRATE": "US unemployment (%)"}


def fred_rows():
    key = os.environ.get("FRED_API_KEY")
    rows = []
    for sid, name in FRED_SERIES.items():
        row = {"name": name, "symbol": sid, "last": None, "chg": None, "date": None}
        if key:
            try:
                obs = _get("https://api.stlouisfed.org/fred/series/observations", series_id=sid, api_key=key,
                           file_type="json", sort_order="desc", limit=10)["observations"]
                vals = [(o["date"], float(o["value"])) for o in obs if o["value"] not in (".", "")]
                if vals:
                    row.update(last=vals[0][1], date=vals[0][0])
                    if len(vals) > 1 and vals[1][1]:
                        row["chg"] = None  # yields and rates change in points, not percent; shown as level only
            except Exception as exc:
                log.warning("FRED %s failed: %s", sid, exc)
        rows.append(row)
    return rows


def extra_groups():
    return [
        {"group": "Currencies (ECB reference rates)", "region": "global", "check": "A4", "rows": fx_rows()},
        {"group": "Crypto market", "region": "global", "check": "A6", "rows": crypto_rows()},
        {"group": "US rates and jobs (FRED)", "region": "usa", "check": "A3", "rows": fred_rows()},
    ]
