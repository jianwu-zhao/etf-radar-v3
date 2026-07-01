#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ETF 雷达策略回测

 walk-forward: 从 history[120:] 开始，每天用前 N 天数据计算信号
 每天收盘调仓，持有到次日收盘
 触发止损/止盈则按收盘价执行
"""
import os
import json
import math
import argparse
import datetime
from collections import defaultdict

from data_source import daily_kline
from tech_indicators import analyze

CORE_ETF = [
    "510300", "510500", "512100", "588000", "510050",
    "512690", "512980", "515210", "512400", "515790",
    "159995", "512760", "512170", "512010", "159928",
    "515030", "159869", "513050", "513180", "518880",
    "159980", "512800", "159915", "159938", "510880",
    "513500", "513060", "159561", "159920", "513100",
]

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
THEME_CAP = defaultdict(lambda: 0.20)
THEME_CAP.update({"宽基": 0.30, "黄金": 0.15, "有色商品": 0.20})

SINGLE_MAX = 0.20
SINGLE_MIN = 0.05


def theme_of(code):
    for t, codes in THEME_MAP.items():
        if code in codes:
            return t
    return "其他"


def factor_score(ind):
    score = 0
    if ind["ma5"] > ind["ma10"] > ind["ma20"]:
        score += 20
    elif ind["ma5"] > ind["ma20"]:
        score += 10

    if ind["momentum_20"] is not None:
        if 0 < ind["momentum_20"] < 15:
            score += 15
        elif -5 < ind["momentum_20"] < 0:
            score += 8
        elif ind["momentum_20"] < -15:
            score += 5

    rsi = ind.get("rsi14") or 50
    if rsi < 30:
        score += 15
    elif rsi < 40:
        score += 10
    elif rsi > 70:
        score -= 10

    if ind["volatility_20"] is not None and ind["volatility_20"] < 1.5:
        score += 15
    elif ind["volatility_20"] is not None and ind["volatility_20"] < 2.5:
        score += 8

    bb = ind.get("bollinger", {})
    if bb.get("percent_b", 50) < 20:
        score += 15
    elif bb.get("percent_b", 50) < 40:
        score += 8
    elif bb.get("percent_b", 50) > 80:
        score -= 8

    macd = ind.get("macd", {})
    if macd.get("histogram", 0) > 0 and macd.get("macd", 0) > macd.get("signal", 0):
        score += 10
    elif macd.get("histogram", 0) > 0:
        score += 5

    if ind["price"] < ind["ma60"] * 0.97:
        score += 10
    elif ind["price"] < ind["ma60"]:
        score += 5

    return max(0, score)


def signal_action(score, ind):
    rsi = ind.get("rsi14") or 50
    macd_h = ind.get("macd", {}).get("histogram", 0)
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
    return None  # 不买


def select_portfolio(day_idx, history_map, target_pos=0.8, top_n=6):
    """基于截至 day_idx 的数据选股"""
    cand = []
    for code, k in history_map.items():
        if day_idx < 60:
            continue
        past = k[:day_idx]
        if len(past) < 60:
            continue
        ind = analyze(past)
        score = factor_score(ind)
        action = signal_action(score, ind)
        if action is None or score < 45:
            continue
        cand.append({
            "code": code,
            "score": score,
            "rsi": ind.get("rsi14"),
            "action": action,
        })

    cand.sort(key=lambda x: (x["score"], -(x["rsi"] or 50)), reverse=True)

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
    ssum = sum(x["score"] for x in selected) or 1
    for x in selected:
        w = target_pos * x["score"] / ssum
        if x["action"] == "超卖观察":
            w = min(w, 0.08)
        x["weight"] = min(w, SINGLE_MAX)

    for t in set(x["theme"] for x in selected):
        members = [x for x in selected if x["theme"] == t]
        total = sum(x["weight"] for x in members)
        cap = THEME_CAP[t]
        if total > cap:
            scale = cap / total
            for m in members:
                m["weight"] *= scale

    selected = [x for x in selected if x["weight"] >= SINGLE_MIN]
    for x in selected:
        x["weight"] = round(x["weight"], 4)
    return selected


def run_backtest(codes=CORE_ETF, start_date=None, end_date=None,
                 target_pos=0.8, top_n=6, fee=0.0005):
    """运行回测"""
    import time
    print("加载历史数据...")
    t0 = time.time()
    history_map = {}
    min_len = 9999
    for code in codes:
        try:
            k = daily_kline(code, limit=500)
            if len(k) >= 120:
                history_map[code] = k
                min_len = min(min_len, len(k))
        except Exception as e:
            print(f"  {code} 加载失败: {e}")
    print(f"加载完成: {len(history_map)} 只, 最短 {min_len} 天, 耗时 {time.time()-t0:.1f}s")

    if min_len < 120:
        print("数据不足，无法回测")
        return

    dates = [history_map[c][i]["date"] for c in history_map for i in range(len(history_map[c]))]
    # 以第一个 ETF 的日期序列为基准
    base_code = list(history_map.keys())[0]
    date_list = [k["date"] for k in history_map[base_code]]

    equity = [1.0]
    cash_curve = [1.0]
    trades = []
    positions = {}  # code -> {"weight": w, "entry": price, "stop": s, "take": t}

    for i in range(120, min_len - 1):
        today_k = {code: history_map[code][i] for code in history_map}
        tomorrow_k = {code: history_map[code][i+1] for code in history_map}
        date = date_list[i]

        # 1. 处理持仓（按明天收盘价执行）
        portfolio_ret = 0
        new_positions = {}
        for code, pos in positions.items():
            if code not in tomorrow_k:
                continue
            p_today = today_k[code]["close"]
            p_tomorrow = tomorrow_k[code]["close"]
            ret = (p_tomorrow - p_today) / p_today

            # 止损止盈检查（用明天高低价）
            exited = False
            exit_price = p_tomorrow
            if tomorrow_k[code]["low"] <= pos["stop"]:
                exit_price = pos["stop"]
                exited = True
            elif tomorrow_k[code]["high"] >= pos["take"]:
                exit_price = pos["take"]
                exited = True

            if exited:
                actual_ret = (exit_price - p_today) / p_today - fee
                portfolio_ret += pos["weight"] * actual_ret
                trades.append({
                    "date": date_list[i+1], "code": code, "action": "卖出",
                    "ret": actual_ret, "weight": pos["weight"]
                })
            else:
                portfolio_ret += pos["weight"] * ret
                new_positions[code] = pos

        equity.append(equity[-1] * (1 + portfolio_ret))
        cash_curve.append(cash_curve[-1] * (1 + portfolio_ret))

        # 2. 调仓：收盘后重新选股，按明天收盘调仓（简化）
        selected = select_portfolio(i + 1, history_map, target_pos, top_n)
        positions = {}
        for s in selected:
            code = s["code"]
            if code not in tomorrow_k:
                continue
            p = tomorrow_k[code]["close"]
            ind = analyze(history_map[code][:i+1])
            atr = ind.get("atr14") or 0.03
            stop = max(p * 0.95, p - 1.5 * atr)
            take = p + 2.5 * atr
            positions[code] = {
                "weight": s["weight"],
                "entry": p,
                "stop": round(stop, 3),
                "take": round(take, 3),
            }

    # 计算指标
    returns = [(equity[i] - equity[i-1]) / equity[i-1] for i in range(1, len(equity))]
    total_ret = equity[-1] - 1
    annual_ret = (1 + total_ret) ** (252 / len(returns)) - 1
    volatility = (sum(r**2 for r in returns) / len(returns)) ** 0.5 * math.sqrt(252)
    sharpe = annual_ret / volatility if volatility > 0 else 0

    max_dd = 0
    peak = equity[0]
    for v in equity:
        peak = max(peak, v)
        dd = (peak - v) / peak
        max_dd = max(max_dd, dd)

    # 买入持有基准
    base_returns = []
    for i in range(120, min_len - 1):
        base_today = history_map[base_code][i]["close"]
        base_tomorrow = history_map[base_code][i+1]["close"]
        base_returns.append((base_tomorrow - base_today) / base_tomorrow)
    base_equity = [1.0]
    for r in base_returns:
        base_equity.append(base_equity[-1] * (1 + r))
    base_total = base_equity[-1] - 1

    result = {
        "start_date": date_list[120],
        "end_date": date_list[min_len - 1],
        "trading_days": len(returns),
        "total_return": round(total_ret * 100, 2),
        "annual_return": round(annual_ret * 100, 2),
        "max_drawdown": round(max_dd * 100, 2),
        "sharpe": round(sharpe, 2),
        "volatility": round(volatility * 100, 2),
        "trades": len(trades),
        "final_equity": round(equity[-1], 4),
        "benchmark_300_return": round(base_total * 100, 2),
        "outperform": round((total_ret - base_total) * 100, 2),
    }
    return result, equity, trades


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--position", type=float, default=0.8)
    ap.add_argument("--top", type=int, default=6)
    ap.add_argument("--fee", type=float, default=0.0005)
    args = ap.parse_args()

    import time
    t0 = time.time()
    result, equity, trades = run_backtest(
        target_pos=args.position, top_n=args.top, fee=args.fee
    )
    print(f"\n回测耗时: {time.time()-t0:.1f}s")
    print("\n=== 回测结果 ===")
    for k, v in result.items():
        if k == "trades":
            continue
        print(f"  {k:<25}: {v}")
    print(f"\n交易次数: {result['trades']}")

    # 保存
    os.makedirs("reports", exist_ok=True)
    with open("reports/backtest_result.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print("已保存 reports/backtest_result.json")


if __name__ == "__main__":
    main()
