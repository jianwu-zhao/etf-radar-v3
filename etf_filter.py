#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ETF 筛选器：从全市场筛选出高质量的 100+ 只 ETF
"""
import re
from collections import defaultdict
from data_source import fetch_etf_list, daily_kline

try:
    import akshare as ak
    AKSHARE_AVAILABLE = True
except ImportError:
    AKSHARE_AVAILABLE = False

# 排除关键词
EXCLUDE_KEYWORDS = [
    "货币", "添益", "日利", "国债", "国开债", "政金债", "可转债",
    "逆回购", "华宝现金", "银华日利", "财富宝", "保证金", "理财",
    "短融", "公司债", "企业债", "地方债", "金融债", "中期票据"
]

# 排除代码段（货币基金、债券基金常见）
EXCLUDE_CODE_PREFIX = ["5118", "5119", "5110", "5112", "5113", "5115", "5116", "5117"]

# 主题归类（用于去重）
THEME_KEYWORDS = {
    "沪深300": ["沪深300"],
    "中证500": ["中证500"],
    "中证1000": ["中证1000"],
    "上证50": ["上证50"],
    "创业板": ["创业板", "创业板50"],
    "科创板": ["科创", "科创50", "科创100", "科创芯片"],
    "中证A500": ["A500"],
    "半导体芯片": ["半导体", "芯片", "集成电路"],
    "医药医疗": ["医药", "医疗", "创新药", "生物医药", "疫苗", "医疗器械", "恒生医疗"],
    "新能源": ["新能源", "光伏", "新能源车", "电池", "储能", "碳中和"],
    "白酒消费": ["酒", "食品", "消费", "家电", "旅游"],
    "传媒游戏": ["传媒", "游戏", "影视", "动漫"],
    "中概互联": ["中概", "互联", "恒生科技", "恒生互联网"],
    "金融科技": ["证券", "银行", "保险", "金融科技", "地产"],
    "资源有色": ["黄金", "有色", "稀土", "煤炭", "钢铁", "石油", "矿产", "资源"],
    "通信AI": ["通信", "5G", "AI", "人工智能", "云计算", "大数据", "算力", "机器人"],
    "军工": ["军工", "国防"],
    "农业": ["农业", "畜牧", "养殖", "粮食"],
    "海外": ["标普", "纳指", "道指", "德国", "日本", "越南", "印度", "法国"],
    "红利": ["红利", "股息", "低波"],
}


def classify_theme(name):
    """根据名称归类主题"""
    for theme, keywords in THEME_KEYWORDS.items():
        if any(k in name for k in keywords):
            return theme
    return "其他"


def filter_etfs(min_amount=20_000_000, min_history_days=300, verbose=True):
    """筛选 ETF"""
    print("获取 ETF 列表...")
    if AKSHARE_AVAILABLE:
        try:
            df = ak.fund_etf_spot_em()
            all_etfs = []
            for _, row in df.iterrows():
                all_etfs.append({
                    "code": row["代码"],
                    "name": row["名称"],
                    "amount": float(row.get("成交额", 0) or 0),
                })
            print(f"akshare 总数: {len(all_etfs)}")
        except Exception as e:
            print(f"akshare 失败: {e}, 使用东财")
            all_etfs = fetch_etf_list(min_amount=0)
    else:
        all_etfs = fetch_etf_list(min_amount=0)
    print(f"总数: {len(all_etfs)}")

    # 第一层：名称/代码过滤
    candidates = []
    for e in all_etfs:
        code = e["code"]
        name = e.get("name", "")
        amount = e.get("amount", 0) or 0

        if any(k in name for k in EXCLUDE_KEYWORDS):
            continue
        if any(code.startswith(p) for p in EXCLUDE_CODE_PREFIX):
            continue
        if amount < min_amount:
            continue
        candidates.append(e)

    print(f"名称/成交额过滤后: {len(candidates)}")

    # 第二层：历史数据长度过滤
    qualified = []
    for i, e in enumerate(candidates):
        code = e["code"]
        try:
            k = daily_kline(code, limit=400)
            if len(k) >= min_history_days:
                e["history_days"] = len(k)
                e["avg_amount"] = sum(x.get("amount", 0) for x in k[-20:]) / 20
                e["avg_volume"] = sum(x.get("volume", 0) for x in k[-20:]) / 20
                e["volatility_20"] = (sum(((x["high"]-x["low"])/x["close"]*100)**2 for x in k[-20:]) / 20) ** 0.5
                e["momentum_60"] = (k[-1]["close"] - k[-60]["close"]) / k[-60]["close"] * 100
                qualified.append(e)
            if verbose and (i+1) % 20 == 0:
                print(f"  已检查 {i+1}/{len(candidates)}, 通过 {len(qualified)}")
        except Exception as ex:
            if verbose:
                print(f"  {code} 获取失败: {ex}")

    print(f"历史数据过滤后: {len(qualified)}")

    # 第三层：同主题去重，保留成交额最大/流动性最好的一只
    theme_groups = defaultdict(list)
    for e in qualified:
        theme = classify_theme(e["name"])
        e["theme"] = theme
        theme_groups[theme].append(e)

    final = []
    for theme, items in theme_groups.items():
        # 按成交额排序，保留 top 3 每个主题
        items.sort(key=lambda x: (x.get("amount", 0), x.get("avg_amount", 0)), reverse=True)
        # 重要主题保留更多
        if theme in ["半导体芯片", "医药医疗", "新能源", "白酒消费", "金融科技", "资源有色", "通信AI", "科创板", "创业板", "沪深300", "中证500"]:
            keep = items[:4]
        else:
            keep = items[:2]
        final.extend(keep)

    # 按成交额排序
    final.sort(key=lambda x: x.get("amount", 0), reverse=True)

    print(f"最终: {len(final)}")
    return final


def export_universe(filename="etf_universe.py", min_amount=10_000_000, min_history_days=300):
    etfs = filter_etfs(min_amount=min_amount, min_history_days=min_history_days, verbose=False)
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
    etfs = filter_etfs(min_amount=10_000_000, min_history_days=300)
    print("\n前20:")
    for e in etfs[:20]:
        print(f"  {e['code']} {e['name']} 主题:{e['theme']} 历史:{e['history_days']}天 成交额:{e.get('amount',0):.0f}")
    export_universe()
