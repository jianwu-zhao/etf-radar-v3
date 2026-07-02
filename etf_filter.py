#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ETF 筛选器：基于 akshare 实时数据快速筛选，不拉取历史 K 线
"""
import datetime
from collections import defaultdict

try:
    import akshare as ak
    AKSHARE_AVAILABLE = True
except ImportError:
    AKSHARE_AVAILABLE = False

EXCLUDE_KEYWORDS = [
    "货币", "添益", "日利", "国债", "国开债", "政金债", "可转债",
    "逆回购", "华宝现金", "银华日利", "财富宝", "保证金", "理财",
    "短融", "公司债", "企业债", "地方债", "金融债", "中期票据"
]

EXCLUDE_CODE_PREFIX = ["5118", "5119", "5110", "5112", "5113", "5115", "5116", "5117"]

THEME_KEYWORDS = {
    "沪深300": ["沪深300"],
    "中证500": ["中证500"],
    "中证1000": ["中证1000"],
    "上证50": ["上证50"],
    "创业板": ["创业板", "创业板50"],
    "科创板": ["科创50", "科创100", "科创芯片", "科创半导体"],
    "中证A500": ["A500"],
    "半导体芯片": ["半导体", "芯片", "集成电路"],
    "医药医疗": ["医药", "医疗", "创新药", "生物医药", "疫苗", "医疗器械", "恒生医疗"],
    "新能源": ["新能源", "光伏", "新能源车", "电池", "储能", "碳中和"],
    "白酒消费": ["酒", "食品", "消费", "家电", "旅游"],
    "传媒游戏": ["传媒", "游戏", "影视", "动漫"],
    "中概互联": ["中概", "互联", "恒生科技", "恒生互联网"],
    "金融科技": ["证券", "券商", "银行", "保险", "金融科技", "地产"],
    "资源有色": ["黄金", "有色", "稀土", "煤炭", "钢铁", "石油", "矿产", "资源"],
    "通信AI": ["通信", "5G", "AI", "人工智能", "云计算", "大数据", "算力", "机器人"],
    "军工": ["军工", "国防"],
    "农业": ["农业", "畜牧", "养殖", "粮食"],
    "海外": ["标普", "纳指", "道指", "德国", "日本", "越南", "印度", "法国"],
    "红利": ["红利", "股息", "低波"],
}


def classify_theme(name):
    for theme, keywords in THEME_KEYWORDS.items():
        if any(k in name for k in keywords):
            return theme
    return "其他"


def get_all_etfs():
    if AKSHARE_AVAILABLE:
        df = ak.fund_etf_spot_em()
        etfs = []
        for _, row in df.iterrows():
            etfs.append({
                "code": str(row["代码"]),
                "name": str(row["名称"]),
                "amount": float(row.get("成交额", 0) or 0),
            })
        return etfs
    # fallback 空
    return []


def filter_etfs(min_amount=5_000_000, max_etfs=150):
    print("获取 ETF 列表...")
    all_etfs = get_all_etfs()
    print(f"akshare 总数: {len(all_etfs)}")

    candidates = []
    for e in all_etfs:
        code = e["code"]
        name = e.get("name", "")
        amount = e.get("amount", 0) or 0

        if not code or not name:
            continue
        if any(k in name for k in EXCLUDE_KEYWORDS):
            continue
        if any(code.startswith(p) for p in EXCLUDE_CODE_PREFIX):
            continue
        if amount < min_amount:
            continue
        e["theme"] = classify_theme(name)
        candidates.append(e)

    print(f"名称/成交额过滤后: {len(candidates)}")

    # 同主题保留流动性 top
    theme_groups = defaultdict(list)
    for e in candidates:
        theme_groups[e["theme"]].append(e)

    pre_selected = []
    for theme, items in theme_groups.items():
        items.sort(key=lambda x: x.get("amount", 0), reverse=True)
        cap = 6 if theme in ["半导体芯片", "医药医疗", "金融科技", "通信AI", "科创板", "创业板", "沪深300", "中证500"] else 3
        pre_selected.extend(items[:cap])

    # 按成交额排序，保留 max_etfs
    pre_selected.sort(key=lambda x: x.get("amount", 0), reverse=True)
    final = pre_selected[:max_etfs]
    print(f"最终: {len(final)}")
    return final


def export_universe(filename="etf_universe.py", min_amount=5_000_000, max_etfs=150, log_file="reports/universe_filter.log"):
    etfs = filter_etfs(min_amount=min_amount, max_etfs=max_etfs)
    codes = [e["code"] for e in etfs]
    with open(filename, "w", encoding="utf-8") as f:
        f.write("# -*- coding: utf-8 -*-\n")
        f.write(f"# 扩展 ETF 池（按成交额/名称/主题过滤，共 {len(codes)} 只）\n")
        f.write("EXPANDED_ETF = [\n")
        for code in codes:
            f.write(f'    "{code}",\n')
        f.write("]\n")

    import os
    os.makedirs(os.path.dirname(log_file) or ".", exist_ok=True)
    with open(log_file, "w", encoding="utf-8") as f:
        f.write(f"# ETF 筛选日志 {datetime.datetime.now()}\n")
        f.write(f"min_amount={min_amount}, max_etfs={max_etfs}, akshare_count={len(get_all_etfs())}\n")
        f.write(f"导出数量: {len(codes)}\n\n")
        f.write("code|name|theme|amount\n")
        f.write("---|---|---|---\n")
        for e in etfs:
            f.write(f"{e['code']}|{e['name']}|{e['theme']}|{e.get('amount',0):.0f}\n")

    print(f"已导出 {filename}，共 {len(codes)} 只")
    return etfs


if __name__ == "__main__":
    try:
        export_universe()
    except Exception as e:
        import traceback
        print("ERROR:", e)
        traceback.print_exc()
        raise
