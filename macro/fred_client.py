import json
import os
from datetime import datetime, timedelta, timezone

import requests

from config.settings import settings
from config.trading_params import MACRO_CACHE_TTL_HOURS
from monitoring.logger import log

FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"
CACHE_PATH = os.path.join("cache", "macro_cache.json")
HTTP_TIMEOUT = 15

SERIES = {
    "fed_funds_rate": "DFF",
    "fed_funds_target_upper": "DFEDTARU",
    "fed_funds_target_lower": "DFEDTARL",
    "ten_year_yield": "DGS10",
    "cpi": "CPIAUCSL",
    "core_cpi": "CPILFESL",
    "unemployment_rate": "UNRATE",
    "hy_spread": "BAMLH0A0HYM2",
    "yield_curve": "T10Y2Y",
    "real_10y": "DFII10",
}


class FREDFetchError(RuntimeError):
    pass


def get_macro_snapshot() -> dict | None:
    if not settings.fred_api_key:
        return None

    cached = _get_cached()
    if cached is not None:
        return cached

    try:
        data = _fetch_from_fred()
    except FREDFetchError as e:
        log.warning(f"FRED fetch failed: {e} — proceeding without macro context")
        return None
    except Exception as e:
        log.warning(f"FRED unexpected error: {e} — proceeding without macro context")
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
        if datetime.now(timezone.utc) - fetched_at > timedelta(hours=MACRO_CACHE_TTL_HOURS):
            return None
        return payload["data"]
    except (json.JSONDecodeError, KeyError, ValueError, OSError) as e:
        log.warning(f"Macro cache unreadable, refetching: {e}")
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


def _fetch_from_fred() -> dict:
    fed_funds = _latest_value(SERIES["fed_funds_rate"])
    target_upper = _latest_value(SERIES["fed_funds_target_upper"])
    target_lower = _latest_value(SERIES["fed_funds_target_lower"])
    ten_year = _latest_value(SERIES["ten_year_yield"])
    unemployment = _latest_value(SERIES["unemployment_rate"])
    cpi_yoy = _compute_cpi_yoy()
    core_cpi_yoy = _compute_yoy(SERIES["core_cpi"])
    hy_spread_pct = _latest_value(SERIES["hy_spread"])
    hy_spread = round(hy_spread_pct * 100, 1) if hy_spread_pct is not None else None
    yield_curve = _latest_value(SERIES["yield_curve"])
    real_10y = _latest_value(SERIES["real_10y"])

    return {
        "fed_funds_rate": fed_funds,
        "fed_funds_target_upper": target_upper,
        "fed_funds_target_lower": target_lower,
        "ten_year_yield": ten_year,
        "real_10y": real_10y,
        "yield_curve": yield_curve,
        "cpi_yoy": cpi_yoy,
        "core_cpi_yoy": core_cpi_yoy,
        "unemployment_rate": unemployment,
        "hy_spread": hy_spread,
    }


def _latest_value(series_id: str) -> float | None:
    obs = _fetch_series(series_id, limit=10)
    return obs[0]["value"] if obs else None


def _compute_cpi_yoy() -> float | None:
    return _compute_yoy(SERIES["cpi"])


def _compute_yoy(series_id: str) -> float | None:
    obs = _fetch_series(series_id, limit=14)
    if len(obs) < 13:
        return None
    now = obs[0]["value"]
    year_ago = obs[12]["value"]
    if year_ago == 0:
        return None
    return round((now - year_ago) / year_ago * 100, 2)


def _fetch_series(series_id: str, limit: int = 10) -> list[dict]:
    params = {
        "series_id": series_id,
        "api_key": settings.fred_api_key,
        "file_type": "json",
        "sort_order": "desc",
        "limit": limit,
    }
    try:
        resp = requests.get(FRED_BASE, params=params, timeout=HTTP_TIMEOUT)
    except requests.RequestException as e:
        raise FREDFetchError(f"{series_id}: {e}") from e

    if resp.status_code != 200:
        raise FREDFetchError(f"{series_id}: HTTP {resp.status_code}")

    out = []
    for o in resp.json().get("observations", []):
        raw = o.get("value")
        if raw in (None, ".", ""):
            continue
        try:
            out.append({"value": float(raw), "date": o.get("date", "")})
        except (TypeError, ValueError):
            continue
    return out
