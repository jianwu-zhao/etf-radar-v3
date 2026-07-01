#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ETF 数据源：Yahoo Finance（适合 GitHub Actions 美国 IP）
"""
import json
import math
import urllib.request
import urllib.parse
from datetime import datetime, timedelta

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"


def _yf_ticker(code):
    if code.startswith("5") or code.startswith("6"):
        return f"{code}.SS"
    return f"{code}.SZ"


def _request(url, timeout=20, retries=3):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for i in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as f:
                return json.loads(f.read().decode())
        except Exception:
            if i == retries - 1:
                raise
            import time
            time.sleep(2 ** i)
    return None


def realtime_quote(code):
    ticker = _yf_ticker(code)
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=1d"
    try:
        data = _request(url)
        result = data["chart"]["result"][0]
        meta = result["meta"]
        price = meta.get("regularMarketPrice") or meta.get("previousClose")
        prev = meta.get("previousClose") or meta.get("regularMarketPrice")
        change_pct = (price - prev) / prev * 100 if price and prev else 0
        return {
            "code": code,
            "name": code,
            "price": round(price, 3) if price else None,
            "open": round(meta.get("regularMarketOpen", price), 3) if price else None,
            "high": round(meta.get("regularMarketDayHigh", price), 3) if price else None,
            "low": round(meta.get("regularMarketDayLow", price), 3) if price else None,
            "pre_close": round(prev, 3) if prev else None,
            "volume": 0,
            "amount": 0,
            "change_pct": round(change_pct, 2),
            "update_time": datetime.now().strftime("%H:%M:%S"),
        }
    except Exception as e:
        raise


def daily_kline(code, limit=500):
    ticker = _yf_ticker(code)
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=2y"
    try:
        data = _request(url)
        result = data["chart"]["result"][0]
        ts = result["timestamp"]
        o = result["indicators"]["quote"][0]["open"]
        h = result["indicators"]["quote"][0]["high"]
        l = result["indicators"]["quote"][0]["low"]
        c = result["indicators"]["quote"][0]["close"]
        v = result["indicators"]["quote"][0]["volume"]
        out = []
        for i in range(len(ts)):
            if c[i] is None:
                continue
            date = datetime.fromtimestamp(ts[i]).strftime("%Y-%m-%d")
            prev_c = c[i-1] if i > 0 and c[i-1] else c[i]
            change_pct = (c[i] - prev_c) / prev_c * 100
            out.append({
                "date": date,
                "open": round(o[i], 3),
                "close": round(c[i], 3),
                "high": round(h[i], 3),
                "low": round(l[i], 3),
                "volume": int(v[i]) if v[i] else 0,
                "amount": 0,
                "amplitude": round((h[i] - l[i]) / prev_c * 100, 2),
                "change_pct": round(change_pct, 2),
            })
        return out[-limit:]
    except Exception as e:
        raise


def fetch_etf_list():
    # 固定列表
    return [
        {"code": c, "name": c} for c in [
            "510300", "510500", "512100", "588000", "510050",
            "512690", "512980", "515210", "512400", "515790",
            "159995", "512760", "512170", "512010", "159928",
            "515030", "159869", "513050", "513180", "518880",
            "159980", "512800", "159915", "159938", "510880",
            "513500", "513060", "159561", "159920", "513100",
        ]
    ]


if __name__ == "__main__":
    import pprint
    pprint.pprint(realtime_quote("515210"))
    k = daily_kline("515210", limit=5)
    pprint.pprint(k)
