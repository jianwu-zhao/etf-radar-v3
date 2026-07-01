#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ETF 波段雷达 V3 量化策略执行器

数据源升级：
  - 使用东方财富 API 获取 ETF 实时行情 + 历史日K
  - 本地计算 RSI / MA / MACD / 布林带 / ATR / 动量 / 波动率
  - 不再依赖 radar.html 静态页面

因子模型：
  动量 | 反转 | 低波 | 趋势 | 结构 | 风险

输出：
  - 每日交易计划 (TXT + JSON)
  - 详细评分 (CSV)
  - 推送 Telegram
"""
import os
import json
import argparse
import datetime
import urllib.request
from typing import List, Dict, Any

from data_source import realtime_quote, daily_kline, fetch_etf_list
from tech_indicators import analyze

HOME = os.path.expanduser("~")
BASE = os.path.join(HOME, "etf-radar")
REPORT_DIR = os.path.join(BASE, "reports")

# 核心关注的 ETF 代码池（A股常见）
CORE_ETF = [
    # 宽基
    "510300", "510500", "512100", "588000", "510050",
    # 行业
    "512690", "512980", "515210", "512400", "515790",
    "159995", "512760", "512170", "512010", "159928",
    "515030", "159869", "513050", "513180", "518880",
    "159980", "512800", "159915", "159938", "510880",
    # 跨境/商品
    "513500", "513060", "159561", "159920", "513100",
]

# 主题分类：用于限仓
THEME_MAP = {
    "宽基": ["510300", "510500", "512100", "588000", "510050", "159915"],
    "黄金": ["518880", "159937", "518600"],
    "有色商品": ["159980", "512400", "515220", "159930"],
    "新能源链": ["515790", "515030", "159755", "159611"],
    "传媒互联": ["512980", "159869", "513050", "513180"],
    "医药": ["512010", "512170", "159928"],
    "港股": ["513060", "513050", "513180", "159920"],
    "海外": ["513500", "513220", "159561", "513100"],
    "消费": ["512690", "159938"],
    "金融": ["512800", "510880"],
}

THEME_CAP = {
    "宽基": 0.30,
    "黄金": 0.15,
    "有色商品": 0.20,
    "新能源链": 0.20,
    "传媒互联": 0.20,
    "医药": 0.20,
    "港股": 0.20,
    "海外": 0.20,
    "消费": 0.20,
    "金融": 0.20,
}

SINGLE_MAX = 0.20
SINGLE_MIN = 0.05


def log(msg):
    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {msg}")


def detect_market_regime():
    """用沪深300判断大盘状态"""
    try:
        k = daily_kline("510300", limit=120)
        if len(k) < 60:
            return "中性", 0.50
        price = k[-1]["close"]
        ma60 = sum(x["close"] for x in k[-60:]) / 60
        ma20 = sum(x["close"] for x in k[-20:]) / 60
        # 斜率
        slope_60 = (ma60 - sum(x["close"] for x in k[-90:-30]) / 60) / ma60 * 100
        slope_20 = (ma20 - sum(x["close"] for x in k[-40:-20]) / 20) / ma20 * 100

        if price > ma60 and slope_60 > 0:
            return "偏多", 0.80
        elif price < ma60 and slope_60 < -1:
            return "偏空", 0.60
        elif slope_60 < -3:
            return "强空", 0.20
        elif slope_60 > 3:
            return "强多", 1.00
        return "中性", 0.50
    except Exception as e:
        log(f"大盘判断失败: {e}")
        return "中性", 0.50


def factor_score(ind: Dict, rt: Dict) -> float:
    """多因子评分，输出 0~100"""
    score = 0

    # 趋势因子 (20)
    if ind["ma5"] > ind["ma10"] > ind["ma20"]:
        score += 20
    elif ind["ma5"] > ind["ma20"]:
        score += 10

    # 动量因子 (15)
    if ind["momentum_20"] is not None:
        if 0 < ind["momentum_20"] < 15:
            score += 15
        elif -5 < ind["momentum_20"] < 0:
            score += 8
        elif ind["momentum_20"] < -15:
            score += 5  # 超跌也可能反弹

    # 反转因子 (15) - RSI 超卖反弹
    rsi = ind.get("rsi14") or 50
    if rsi < 30:
        score += 15
    elif rsi < 40:
        score += 10
    elif rsi > 70:
        score -= 10

    # 低波因子 (15)
    if ind["volatility_20"] is not None and ind["volatility_20"] < 1.5:
        score += 15
    elif ind["volatility_20"] is not None and ind["volatility_20"] < 2.5:
        score += 8

    # 结构因子 (15) - 布林带位置
    bb = ind.get("bollinger", {})
    if bb.get("percent_b", 50) < 20:
        score += 15
    elif bb.get("percent_b", 50) < 40:
        score += 8
    elif bb.get("percent_b", 50) > 80:
        score -= 8

    # MACD 因子 (10)
    macd = ind.get("macd", {})
    if macd.get("histogram", 0) > 0 and macd.get("macd", 0) > macd.get("signal", 0):
        score += 10
    elif macd.get("histogram", 0) > 0:
        score += 5

    # 价格 vs MA60 (10) - 均值回归
    if ind["price"] < ind["ma60"] * 0.97:
        score += 10
    elif ind["price"] < ind["ma60"]:
        score += 5

    return max(0, score)


def signal_action(ind: Dict, score: float) -> str:
    """生成动作信号"""
    rsi = ind.get("rsi14") or 50
    macd_h = ind.get("macd", {}).get("histogram", 0)
    bb = ind.get("bollinger", {})
    price = ind["price"]
    ma5 = ind["ma5"]

    if score >= 65 and rsi < 45:
        return "可买"
    if score >= 55 and rsi < 45 and macd_h > 0:
        return "可买"
    if score >= 50 and rsi < 40 and price > ma5:
        return "确认买"
    if score >= 45 and rsi < 35:
        return "超卖观察"
    if score >= 40:
        return "观察"
    return "等待"


def calc_stop_take(ind: Dict) -> (float, float):
    """计算止损 / 止盈"""
    atr = ind.get("atr14") or 0.03
    price = ind["price"]
    # 止损：价格 - 1.5xATR 或 前20日低点
    # 止盈：价格 + 2.5xATR
    stop = round(max(price * 0.95, price - 1.5 * atr), 3)
    take = round(price + 2.5 * atr, 3)
    return stop, take


def analyze_one(code: str) -> Dict[str, Any]:
    """分析单个 ETF"""
    try:
        rt = realtime_quote(code)
        if not rt or not rt.get("price"):
            return None
        klines = daily_kline(code, limit=120)
        if len(klines) < 60:
            return None
        ind = analyze(klines)
        score = factor_score(ind, rt)
        action = signal_action(ind, score)
        stop, take = calc_stop_take(ind)

        return {
            "code": code,
            "name": rt["name"],
            "price": ind["price"],
            "change_pct": rt["change_pct"],
            "rsi14": ind["rsi14"],
            "rsi6": ind["rsi6"],
            "ma5": ind["ma5"],
            "ma20": ind["ma20"],
            "ma60": ind["ma60"],
            "momentum_20": ind["momentum_20"],
            "momentum_60": ind["momentum_60"],
            "volatility_20": ind["volatility_20"],
            "macd": ind["macd"],
            "bollinger": ind["bollinger"],
            "atr14": ind["atr14"],
            "score": round(score, 1),
            "action": action,
            "stop": stop,
            "take_profit": take,
        }
    except Exception as e:
        log(f"分析 {code} 失败: {e}")
        return None


def theme_of(code):
    for theme, codes in THEME_MAP.items():
        if code in codes:
            return theme
    return "其他"


def select_portfolio(analyzed: List[Dict], target_pos: float, top_n=6):
    """选池 + 仓位分配"""
    # 过滤可交易信号
    buy_signals = ["可买", "确认买", "超卖观察"]
    cand = [a for a in analyzed if a["action"] in buy_signals and a["score"] >= 45]

    # 排序：评分高、RSI 低优先
    cand.sort(key=lambda x: (x["score"], -(x["rsi14"] or 50)), reverse=True)

    # 同主题去重，最多2只
    theme_count = {}
    deduped = []
    for r in cand:
        t = theme_of(r["code"])
        if theme_count.get(t, 0) >= 2:
            continue
        r["theme"] = t
        theme_count[t] = theme_count.get(t, 0) + 1
        deduped.append(r)

    selected = deduped[:top_n]

    # 评分加权
    ssum = sum(x["score"] for x in selected) or 1
    for x in selected:
        w = target_pos * x["score"] / ssum
        if x["action"] == "超卖观察":
            w = min(w, 0.08)
        x["weight"] = round(min(w, SINGLE_MAX), 4)

    # 主题限仓
    theme_w = {}
    for x in selected:
        theme_w.setdefault(x["theme"], []).append(x)
    for t, members in theme_w.items():
        cap = THEME_CAP.get(t, 1.0)
        total = sum(m["weight"] for m in members)
        if total > cap:
            scale = cap / total
            for m in members:
                m["weight"] = round(m["weight"] * scale, 4)

    selected = [x for x in selected if x["weight"] >= SINGLE_MIN]
    return selected


def build_report(market_regime, target_pos, selected, analyzed_count):
    today = datetime.datetime.now().strftime("%Y%m%d")
    etf_sum = round(sum(x["weight"] for x in selected), 4)
    cash = round(max(0.0, 1 - etf_sum), 4)

    lines = []
    lines.append("=" * 72)
    lines.append("  ETF 波段雷达 V3 — 每日交易计划（真实数据源）")
    lines.append("=" * 72)
    lines.append(f"生成日期   : {today}")
    lines.append(f"大盘状态   : {market_regime}")
    lines.append(f"目标仓位   : {target_pos:.0%}")
    lines.append(f"扫描 ETF   : {analyzed_count} 只")
    lines.append("")
    lines.append(f"{'ETF':<12}{'代码':<8}{'动作':<8}{'评分':>6}{'RSI':>6}{'仓位':>7}{'现价':>8}{'止损':>8}{'止盈':>8}")
    lines.append("-" * 80)
    for x in selected:
        lines.append(
            f"{x['name']:<12}{x['code']:<8}{x['action']:<8}"
            f"{x['score']:>6.1f}{(x['rsi14'] or 0):>6.1f}"
            f"{x['weight']*100:>6.1f}%"
            f"{x['price']:>8.3f}{x['stop']:>8.3f}{x['take_profit']:>8.3f}"
        )
    lines.append("-" * 80)
    lines.append(f"{'ETF 合计仓位':<20}{etf_sum*100:>6.1f}%")
    lines.append(f"{'现金':<20}{cash*100:>6.1f}%")
    lines.append("")
    lines.append("执行规则:")
    lines.append("  · 可买    : 次日开盘涨幅<=1.5% 直接建仓")
    lines.append("  · 确认买  : 突破昨高 / 收盘站上MA5 才买")
    lines.append("  · 超卖观察: 分批建仓，每跌2%加一次")
    lines.append("  · 止损    : 收盘<=止损价 次日清仓")
    lines.append("  · 止盈    : >=止盈价 卖50%，余下移动止盈")
    lines.append("  · 数据源  : 东方财富 API (push2.eastmoney.com)")
    lines.append("=" * 72)

    text = "\n".join(lines)
    data = {
        "generated_at": datetime.datetime.now().isoformat(),
        "date": today,
        "market_regime": market_regime,
        "target_position": target_pos,
        "etf_total": etf_sum,
        "cash": cash,
        "positions": selected,
        "all_scanned": analyzed_count,
    }
    return text, data


def main():
    ap = argparse.ArgumentParser(description="ETF 波段雷达 V3")
    ap.add_argument("--codes", help="指定 ETF 代码，逗号分隔")
    ap.add_argument("--top", type=int, default=6)
    ap.add_argument("--position", type=float, default=None, help="手动目标仓位 0~1")
    ap.add_argument("--notify", action="store_true")
    ap.add_argument("--no-save", action="store_true")
    args = ap.parse_args()

    codes = args.codes.split(",") if args.codes else CORE_ETF

    log("开始获取大盘状态...")
    market_regime, auto_pos = detect_market_regime()
    target_pos = args.position if args.position is not None else auto_pos

    log(f"大盘={market_regime}, 目标仓位={target_pos:.0%}")
    log(f"开始扫描 {len(codes)} 只 ETF...")

    analyzed = []
    for code in codes:
        r = analyze_one(code.strip())
        if r:
            analyzed.append(r)
            log(f"  {r['code']} {r['name']}: score={r['score']:.1f} action={r['action']} rsi={r['rsi14']}")

    selected = select_portfolio(analyzed, target_pos, top_n=args.top)
    report, data = build_report(market_regime, target_pos, selected, len(analyzed))

    print("\n" + report)

    if args.notify:
        try:
            import notify
            sent = notify.send(f"ETF雷达V3 {data['date']} 仓位{target_pos:.0%}", report)
            if sent:
                print(f"\n已推送: {', '.join(sent)}")
        except Exception as e:
            log(f"推送失败: {e}")

    if not args.no_save:
        os.makedirs(REPORT_DIR, exist_ok=True)
        day = data["date"]
        with open(os.path.join(REPORT_DIR, f"plan_v3_{day}.txt"), "w", encoding="utf-8") as f:
            f.write(report)
        with open(os.path.join(REPORT_DIR, f"plan_v3_{day}.json"), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        log(f"已保存: reports/plan_v3_{day}.txt/.json")


if __name__ == "__main__":
    main()
