#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ETF 数据源：优先 akshare，回退东方财富
"""
import json
import math
import urllib.request
from datetime import datetime

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

AKSHARE_AVAILABLE = False
try:
    import akshare as ak
    AKSHARE_AVAILABLE = True
except ImportError:
    pass


def _request(url, timeout=15, retries=3):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for i in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as f:
                return json.loads(f.read().decode())
        except Exception:
            if i == retries - 1:
                raise
            import time
            time.sleep(1 + i)
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
            df = ak.fund_etf_hist_em(symbol=code, period="daily", start_date="20990101", end_date="20990101", adjust="qfq")
            return None  # 历史接口不适合实时
        except:
            pass

    secid = _secid(code)
    url = f"https://push2.eastmoney.com/api/qt/stock/get?secid={secid}&fields=f43,f44,f45,f46,f47,f48,f57,f58,f60,f169,f170,f171"
    data = _request(url)
    d = data.get("data", {})
    if not d:
        return None
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


def daily_kline(code, limit=500):
    """日K线"""
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


def fetch_etf_list():
    if AKSHARE_AVAILABLE:
        try:
            df = ak.fund_etf_spot_em()
            return [{"code": row["代码"], "name": row["名称"]} for _, row in df.iterrows()]
        except:
            pass
    url = ("http://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=5000&po=1&np=1"
           "&fltt=2&invt=2&fid=f3&fs=b:MK0021,b:MK0022,b:MK0023,b:MK0024"
           "&fields=f12,f14")
    data = _request(url)
    rows = data.get("data", {}).get("diff", [])
    return [{"code": r.get("f12"), "name": r.get("f14")} for r in rows if r.get("f12")]


if __name__ == "__main__":
    import pprint
    print(f"akshare: {AKSHARE_AVAILABLE}")
    pprint.pprint(realtime_quote("515210"))
