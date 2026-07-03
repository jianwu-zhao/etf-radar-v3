#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""预加载 Yahoo 数据到缓存文件"""
import json
import os
from data_source import _batch_from_yahoo, _YAHOO_CACHE

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
        # 先删除旧缓存，强制重新下载
        cache_path = "data_cache/yahoo_cache.json"
        if os.path.exists(cache_path):
            with open(cache_path) as f:
                old_cache = json.load(f)
            old_latest = ""
            for code, rows in old_cache.items():
                if rows:
                    d = rows[-1].get("date", "")
                    if d > old_latest:
                        old_latest = d
            print(f"旧缓存最新日期: {old_latest}")
        
        data = _batch_from_yahoo(CORE_ETF, limit=500)
        cache = {}
        for code, rows in data.items():
            cache[code] = rows
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False)
        
        # 检查最新日期
        latest = ""
        for code, rows in data.items():
            if rows:
                d = rows[-1].get("date", "")
                if d > latest:
                    latest = d
        print(f"缓存 {len(cache)} 只 ETF 数据，最新日期: {latest}")
    except Exception as e:
        print(f"预加载失败: {e}")

if __name__ == "__main__":
    main()
