#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ETF 筛选器：两步筛选，先按成交额/名称过滤，再检查历史数据
"""
import re
from collections import defaultdict
from data_source import fetch_etf_list, daily_kline

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
        try:
            df = ak.fund_etf_spot_em()
            etfs = []
            for _, row in df.iterrows():
                etfs.append({
                    "code": str(row["代码"]),
                    "name": str(row["名称"]),
                    "amount": float(row.get("成交额", 0) or 0),
                })
            print(f"akshare 获取 {len(etfs)} 只")
            return etfs
        except Exception as e:
            print(f"akshare 失败: {e}")
    return fetch_etf_list(min_amount=0)


def filter_etfs(min_amount=10_000_000, min_history_days=300, max_etfs=120, verbose=True):
    print("获取 ETF 列表...")
    all_etfs = get_all_etfs()
    print(f"总数: {len(all_etfs)}")

    # 第一层：名称/代码/成交额过滤
    # 如果 amount 全为 0（市场关闭），则跳过成交额过滤
    has_amount = any((e.get("amount") or 0) > 0 for e in all_etfs)
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
        if has_amount and amount < min_amount:
            continue
        e["theme"] = classify_theme(name)
        candidates.append(e)

    print(f"名称/成交额过滤后: {len(candidates)}")

    # 同主题保留流动性 top N，避免过度集中
    theme_groups = defaultdict(list)
    for e in candidates:
        theme_groups[e["theme"]].append(e)

    pre_selected = []
    for theme, items in theme_groups.items():
        items.sort(key=lambda x: x.get("amount", 0), reverse=True)
        cap = 5 if theme in ["半导体芯片", "医药医疗", "金融科技", "通信AI", "科创板"] else 3
        pre_selected.extend(items[:cap])

    pre_selected.sort(key=lambda x: x.get("amount", 0), reverse=True)
    pre_selected = pre_selected[:max_etfs * 2]
    print(f"预选 {len(pre_selected)} 只，开始检查历史数据...")

    # 第二层：历史数据过滤
    qualified = []
    for i, e in enumerate(pre_selected):
        code = e["code"]
        try:
            k = daily_kline(code, limit=min_history_days + 20)
            if len(k) >= min_history_days:
                e["history_days"] = len(k)
                e["avg_amount_20"] = sum(x.get("amount", 0) for x in k[-20:]) / 20
                qualified.append(e)
            if verbose and (i+1) % 30 == 0:
                print(f"  已检查 {i+1}/{len(pre_selected)}, 通过 {len(qualified)}")
        except Exception as ex:
            if verbose:
                print(f"  {code} 失败")

    print(f"历史数据过滤后: {len(qualified)}")

    # 最终排序并限制数量
    qualified.sort(key=lambda x: x.get("amount", 0), reverse=True)
    final = qualified[:max_etfs]
    print(f"最终: {len(final)}")
    return final


def export_universe(filename="etf_universe.py", min_amount=10_000_000, min_history_days=300, max_etfs=120):
    etfs = filter_etfs(min_amount=min_amount, min_history_days=min_history_days, max_etfs=max_etfs, verbose=False)
    codes = [e["code"] for e in etfs]
    with open(filename, "w", encoding="utf-8") as f:
        f.write("# -*- coding: utf-8 -*-\n")
        f.write(f"# 扩展 ETF 池（按成交额/历史/主题过滤，共 {len(codes)} 只）\n")
        f.write("EXPANDED_ETF = [\n")
        for code in codes:
            f.write(f'    "{code}",\n')
        f.write("]\n")
    print(f"已导出 {filename}，共 {len(codes)} 只")
    return etfs


if __name__ == "__main__":
    etfs = filter_etfs(min_amount=10_000_000, min_history_days=300, max_etfs=120)
    print("\n前20:")
    for e in etfs[:20]:
        print(f"  {e['code']} {e['name']} 主题:{e['theme']} 历史:{e['history_days']}天 成交额:{e.get('amount',0):.0f}")
    export_universe()
