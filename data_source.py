#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ETF 数据源：优先 akshare，回退东方财富
"""
import json
import math
import urllib.request
from datetime import datetime

try:
    import yfinance as yf
    YF_AVAILABLE = True
except ImportError:
    YF_AVAILABLE = False

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

AKSHARE_AVAILABLE = False
try:
    import akshare as ak
    AKSHARE_AVAILABLE = True
except ImportError:
    pass


def _request(url, timeout=15, retries=3):
    import random, time
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for i in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as f:
                return json.loads(f.read().decode())
        except Exception:
            if i == retries - 1:
                raise
            time.sleep(2 + i * 2 + random.random())
    return None


def _secid(code):
    if code.startswith("5") or code.startswith("51") or code.startswith("56") or code.startswith("58"):
        return f"1.{code}"
    return f"0.{code}"


def _price(v):
    if v is None or v == "-" or v == 0:
        return None
    return round(float(v) / 1000, 3)


def _pct(v):
    if v is None or v == "-" or v == 0:
        return None
    return round(float(v) / 100, 2)


def realtime_quote(code):
    """实时行情"""
    if AKSHARE_AVAILABLE:
        try:
            df = ak.fund_etf_spot_em()
            row = df[df["代码"] == code]
            if not row.empty:
                r = row.iloc[0]
                return {
                    "code": code,
                    "name": str(r.get("名称", "")).replace("ETF", ""),
                    "price": float(r.get("最新价", 0) or 0),
                    "open": float(r.get("今开", 0) or 0),
                    "high": float(r.get("最高价", 0) or 0),
                    "low": float(r.get("最低价", 0) or 0),
                    "pre_close": float(r.get("昨收", 0) or 0),
                    "volume": int(r.get("成交量", 0) or 0),
                    "amount": float(r.get("成交额", 0) or 0),
                    "change_pct": float(r.get("涨跌幅", 0) or 0),
                    "update_time": datetime.now().strftime("%H:%M:%S"),
                }
        except Exception as e:
            pass

    # fallback: yfinance
    yd = _daily_from_yahoo(code, limit=2)
    if yd and len(yd) >= 1:
        latest = yd[-1]
        prev = yd[-2] if len(yd) >= 2 else latest
        return {
            "code": code,
            "name": code,
            "price": latest["close"],
            "open": latest["open"],
            "high": latest["high"],
            "low": latest["low"],
            "pre_close": prev["close"],
            "volume": latest["volume"],
            "amount": 0,
            "change_pct": round((latest["close"]-prev["close"])/prev["close"]*100, 2),
            "update_time": datetime.now().strftime("%H:%M:%S"),
        }

    secid = _secid(code)
    url = f"https://push2.eastmoney.com/api/qt/stock/get?secid={secid}&fields=f43,f44,f45,f46,f47,f48,f57,f58,f60,f169,f170,f171"
    try:
        data = _request(url)
        d = data.get("data", {})
        if d:
            return {
                "code": code,
                "name": d.get("f58", "").replace("ETF", ""),
                "price": _price(d.get("f43")),
                "open": _price(d.get("f46")),
                "high": _price(d.get("f44")),
                "low": _price(d.get("f45")),
                "pre_close": _price(d.get("f60")),
                "volume": d.get("f47", 0),
                "amount": d.get("f48", 0),
                "change_pct": _pct(d.get("f170")),
                "update_time": datetime.now().strftime("%H:%M:%S"),
            }
    except:
        pass
    return None


def daily_kline(code, limit=500):
    """日K线"""
    # 优先 Yahoo Finance（GitHub Actions 可用）
    yd = _daily_from_yahoo(code, limit)
    if yd:
        return yd

    if AKSHARE_AVAILABLE:
        try:
            end = datetime.now().strftime("%Y%m%d")
            start = "20200101"
            df = ak.fund_etf_hist_em(symbol=code, period="daily", start_date=start, end_date=end, adjust="qfq")
            if df is not None and len(df) > 0:
                out = []
                for _, row in df.iterrows():
                    out.append({
                        "date": row["日期"],
                        "open": round(float(row["开盘"]), 3),
                        "close": round(float(row["收盘"]), 3),
                        "high": round(float(row["最高"]), 3),
                        "low": round(float(row["最低"]), 3),
                        "volume": int(row["成交量"]),
                        "amount": float(row.get("成交额", 0)),
                        "amplitude": float(row.get("振幅", 0)),
                        "change_pct": float(row.get("涨跌幅", 0)),
                    })
                return out[-limit:]
        except Exception as e:
            pass

    secid = _secid(code)
    url = (f"https://push2his.eastmoney.com/api/qt/stock/kline/get?secid={secid}"
           f"&fields1=f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,f13"
           f"&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61"
           f"&klt=101&fqt=1&end=20500101&lmt={limit}")
    data = _request(url)
    klines = data.get("data", {}).get("klines", [])
    out = []
    for k in klines:
        parts = k.split(",")
        if len(parts) >= 6:
            out.append({
                "date": parts[0],
                "open": round(float(parts[1]), 3),
                "close": round(float(parts[2]), 3),
                "high": round(float(parts[3]), 3),
                "low": round(float(parts[4]), 3),
                "volume": int(parts[5]),
                "amount": float(parts[6]) if len(parts) > 6 else 0,
                "amplitude": float(parts[7]) if len(parts) > 7 else 0,
                "change_pct": float(parts[8]) if len(parts) > 8 else 0,
            })
    return out


def _yahoo_symbol(code):
    """A股 ETF 转 Yahoo 代码"""
    if code.startswith(("51", "58", "56", "50", "52")):
        return f"{code}.SS"
    return f"{code}.SZ"


def _daily_from_yahoo(code, limit=500):
    """从 Yahoo Finance 获取日K线"""
    if not YF_AVAILABLE:
        return None
    symbol = _yahoo_symbol(code)
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period="2y")
        if df is None or len(df) == 0:
            return None
        df = df.reset_index()
        out = []
        for _, row in df.iterrows():
            out.append({
                "date": row["Date"].strftime("%Y-%m-%d"),
                "open": round(float(row["Open"]), 3),
                "close": round(float(row["Close"]), 3),
                "high": round(float(row["High"]), 3),
                "low": round(float(row["Low"]), 3),
                "volume": int(row["Volume"]),
                "amount": 0,
            })
        return out[-limit:]
    except Exception as e:
        print(f"Yahoo fallback error: {e}")
        return None


def intraday_kline(code, period=15, limit=160):
    """获取 15/60 分钟 K 线（东财）"""
    secid = _secid(code)
    klt = "15" if period == 15 else "60"
    url = (f"https://push2his.eastmoney.com/api/qt/stock/kline/get?secid={secid}"
           f"&fields1=f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,f13"
           f"&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61"
           f"&klt={klt}&fqt=1&end=20500101&lmt={limit}")
    try:
        data = _request(url, timeout=20, retries=3)
        klines = data.get("data", {}).get("klines", [])
        out = []
        for k in klines:
            parts = k.split(",")
            if len(parts) >= 6:
                out.append({
                    "date": parts[0],
                    "open": round(float(parts[1]), 3),
                    "close": round(float(parts[2]), 3),
                    "high": round(float(parts[3]), 3),
                    "low": round(float(parts[4]), 3),
                    "volume": int(parts[5]),
                })
        return out
    except:
        return []


def fetch_etf_list(min_amount=10000000):
    """获取 ETF 列表，按成交额过滤"""
    if AKSHARE_AVAILABLE:
        try:
            df = ak.fund_etf_spot_em()
            out = []
            for _, row in df.iterrows():
                amt = float(row.get("成交额", 0) or 0)
                if amt >= min_amount:
                    out.append({"code": row["代码"], "name": row["名称"], "amount": amt})
            return out
        except:
            pass
    url = ("http://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=5000&po=1&np=1"
           "&fltt=2&invt=2&fid=f6&fs=b:MK0021,b:MK0022,b:MK0023,b:MK0024"
           "&fields=f12,f14,f5,f6,f3")
    data = _request(url)
    rows = data.get("data", {}).get("diff", [])
    out = []
    for r in rows:
        amt = r.get("f6") or 0
        try:
            amt = float(amt)
        except:
            amt = 0
        if amt >= min_amount:
            out.append({"code": r.get("f12"), "name": r.get("f14"), "amount": amt, "volume": r.get("f5", 0)})
    return out


if __name__ == "__main__":
    import pprint
    print(f"akshare: {AKSHARE_AVAILABLE}")
    pprint.pprint(realtime_quote("515210"))
