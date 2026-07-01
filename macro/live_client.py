import json
import os
from datetime import datetime, timedelta, timezone

import yfinance as yf

from config.trading_params import LIVE_CACHE_TTL_MINUTES
from monitoring.logger import log

CACHE_PATH = os.path.join("cache", "live_cache.json")

LIVE_TICKERS = {
    "vix": "^VIX",
    "skew": "^SKEW",
}


def get_live_snapshot() -> dict | None:
    cached = _get_cached()
    if cached is not None:
        return cached

    try:
        data = _fetch_live()
    except Exception as e:
        log.warning(f"Live market fetch failed: {e} — proceeding without VIX/SKEW")
        return None

    _save_cache(data)
    return data


def _get_cached() -> dict | None:
    if not os.path.exists(CACHE_PATH):
        return None
    try:
        with open(CACHE_PATH, "r", encoding="utf-8") as f:
            payload = json.load(f)
        fetched_at = datetime.fromisoformat(payload["fetched_at"])
        if datetime.now(timezone.utc) - fetched_at > timedelta(minutes=LIVE_CACHE_TTL_MINUTES):
            return None
        return payload["data"]
    except (json.JSONDecodeError, KeyError, ValueError, OSError) as e:
        log.warning(f"Live cache unreadable, refetching: {e}")
        return None


def _save_cache(data: dict) -> None:
    os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
    payload = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "data": data,
    }
    tmp_path = CACHE_PATH + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    os.replace(tmp_path, CACHE_PATH)


def _fetch_live() -> dict:
    result = {}
    for key, ticker_sym in LIVE_TICKERS.items():
        try:
            price = yf.Ticker(ticker_sym).fast_info.last_price
            result[key] = round(float(price), 2) if price and price > 0 else None
        except Exception as e:
            log.warning(f"Live fetch {ticker_sym}: {e}")
            result[key] = None
    return result
