#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""预加载 Yahoo 数据到缓存文件"""
import json
import os
from data_source import _batch_from_yahoo, _YAHOO_CACHE
from etf_universe import CORE_ETF

CORE_ETF = [
    "510300", "510500", "512100", "588000", "510050",
    "512690", "512980", "515210", "512400", "515790",
    "159995", "512760", "512170", "512010", "159928",
    "515030", "159869", "513050", "513180", "518880",
    "159980", "512800", "159915", "159938", "510880",
    "513500", "513060", "159561", "159920", "513100",
]

def main():
    os.makedirs("data_cache", exist_ok=True)
    try:
        data = _batch_from_yahoo(CORE_ETF, limit=500)
        cache = {}
        for code, rows in data.items():
            cache[code] = rows
        with open("data_cache/yahoo_cache.json", "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False)
        print(f"缓存 {len(cache)} 只 ETF 数据")
    except Exception as e:
        print(f"预加载失败: {e}")

if __name__ == "__main__":
    main()
