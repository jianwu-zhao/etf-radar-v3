#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
回测 ETF 雷达 V3.1 策略
"""
import os
import json
import math
import argparse
from collections import defaultdict

from data_source import daily_kline
from etf_universe import EXPANDED_ETF, EXPANDED_ETF_TOP50
from sector_map import CORE_SECTOR_MAP, sector_of
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
SINGLE_MIN = 0.03

REGIME_PARAMS = {
    "强多": {"target": 1.00, "rsi_max": 75, "score_thr": 35, "momentum": "strong", "stop_mul": 2.5, "take_mul": 5.0},
    "偏多": {"target": 0.95, "rsi_max": 65, "score_thr": 40, "momentum": "balanced", "stop_mul": 2.2, "take_mul": 4.0},
    "中性": {"target": 0.70, "rsi_max": 55, "score_thr": 45, "momentum": "balanced", "stop_mul": 2.0, "take_mul": 3.5},
    "偏空": {"target": 0.40, "rsi_max": 45, "score_thr": 50, "momentum": "reversal", "stop_mul": 1.8, "take_mul": 3.0},
    "强空": {"target": 0.15, "rsi_max": 40, "score_thr": 55, "momentum": "reversal", "stop_mul": 1.8, "take_mul": 3.0},
}

TARGET_VOL = 0.15  # 目标年化波动率 15%


def theme_of(code):
    for t, codes in THEME_MAP.items():
        if code in codes:
            return t
    return "其他"


def detect_regime(base_k, day_idx):
    if day_idx < 90:
        return "中性"
    price = base_k[day_idx]["close"]
    ma60 = sum(base_k[i]["close"] for i in range(day_idx-59, day_idx+1)) / 60
    ma20 = sum(base_k[i]["close"] for i in range(day_idx-19, day_idx+1)) / 20
    slope_60 = (ma60 - sum(base_k[i]["close"] for i in range(day_idx-89, day_idx-29)) / 60) / ma60 * 100
    slope_20 = (ma20 - sum(base_k[i]["close"] for i in range(day_idx-39, day_idx-19)) / 20) / ma20 * 100

    if price > ma60 and slope_60 > 2:
        return "强多"
    if price > ma60 and slope_60 > 0:
        return "偏多"
    if price < ma60 and slope_60 < -2:
        return "强空"
    if price < ma60:
        return "偏空"
    return "中性"


def factor_score(ind, regime):
    params = REGIME_PARAMS.get(regime, REGIME_PARAMS["中性"])
    momentum_mode = params["momentum"]
    score = 0

    if ind["ma5"] > ind["ma10"] > ind["ma20"] > ind["ma60"]:
        score += 25
    elif ind["ma5"] > ind["ma20"] > ind["ma60"]:
        score += 18
    elif ind["ma5"] > ind["ma20"]:
        score += 10
    elif ind["price"] > ind["ma60"]:
        score += 5

    mom20 = ind.get("momentum_20") or 0
    mom60 = ind.get("momentum_60") or 0
    if momentum_mode == "strong":
        if mom20 > 15:
            score += 20
        elif mom20 > 8:
            score += 15
        elif mom20 > 0:
            score += 8
        elif mom20 > -5:
            score += 3
    elif momentum_mode == "reversal":
        if -15 < mom20 < -5:
            score += 15
        elif mom20 < -15:
            score += 10
        elif 0 < mom20 < 10:
            score += 8
    else:
        if 3 < mom20 < 15:
            score += 18
        elif 0 < mom20 < 20:
            score += 12
        elif -10 < mom20 < 0:
            score += 6

    if mom60 > 10:
        score += 5
    elif mom60 > 0:
        score += 2

    rsi = ind.get("rsi14") or 50
    if rsi < 30:
        score += 15
    elif rsi < 40:
        score += 10
    elif rsi < 50:
        score += 5

    if momentum_mode == "strong" and 55 < rsi < params["rsi_max"]:
        score += 8

    bb = ind.get("bollinger", {})
    pb = bb.get("percent_b", 50)
    if pb < 20:
        score += 15
    elif pb < 40:
        score += 8
    elif pb > 80:
        score -= 10

    macd = ind.get("macd", {})
    if macd.get("histogram", 0) > 0 and macd.get("macd", 0) > macd.get("signal", 0):
        score += 10
    elif macd.get("histogram", 0) > 0:
        score += 6

    ma60_dist = (ind["price"] / ind["ma60"] - 1) * 100 if ind["ma60"] else 0
    if ma60_dist < -10:
        score += 10
    elif ma60_dist < -5:
        score += 5

    # 成交量
    vol_ratio = ind.get("volume_ratio", 1)
    if vol_ratio > 1.5:
        score += 10
    elif vol_ratio > 1.2:
        score += 5

    return max(0, min(100, score))


def signal_action(ind, score, regime):
    params = REGIME_PARAMS.get(regime, REGIME_PARAMS["中性"])
    rsi = ind.get("rsi14") or 50
    macd_h = ind.get("macd", {}).get("histogram", 0)
    price = ind["price"]
    ma5 = ind["ma5"]
    ma20 = ind["ma20"]

    if params["momentum"] == "strong":
        if score >= 60 and rsi < params["rsi_max"] and price > ma20:
            return "可买"
        rs = ind.get("relative_strength") or 0
        mom20 = ind.get("momentum_20") or 0
        if mom20 > 15 and rs > 20 and rsi < 80 and price > ma20 and macd_h > 0:
            return "可买"
        if score >= 55 and price > ma5 and macd_h > 0:
            return "确认买"
    else:
        if score >= 65 and rsi < 45:
            return "可买"
        if score >= 55 and rsi < 45 and macd_h > 0:
            return "可买"
        if score >= 50 and rsi < 40 and price > ma5:
            return "确认买"

    if score >= params["score_thr"] and rsi < 40:
        return "超卖观察"
    return None


def calc_stop_take(ind):
    atr = ind.get("atr14") or 0.03
    price = ind["price"]
    stop = round(max(price * 0.93, price - 2.0 * atr), 3)
    take = round(price + 3.0 * atr), 3
    if isinstance(take, tuple):
        take = take[0]
    return stop, take


def select_portfolio(day_idx, history_map, base_k, target_pos, top_n=10, top_sectors=2):
    regime = detect_regime(base_k, day_idx)
    params = REGIME_PARAMS.get(regime, REGIME_PARAMS["中性"])

    # 计算相对强度
    base_ret20 = None
    if day_idx >= 20:
        base_ret20 = (base_k[day_idx]["close"] - base_k[day_idx-20]["close"]) / base_k[day_idx-20]["close"] * 100

    cand = []
    for code, k in history_map.items():
        if day_idx < 60:
            continue
        past = k[:day_idx+1]
        if len(past) < 60:
            continue
        ind = analyze(past)
        ind["volume_ratio"] = past[-1]["volume"] / (sum(x["volume"] for x in past[-20:]) / 20) if day_idx >= 20 else 1
        score = factor_score(ind, regime)
        action = signal_action(ind, score, regime)
        if action is None:
            continue

        rs = 0
        if base_ret20 is not None and day_idx >= 20:
            ret20 = (past[-1]["close"] - past[-21]["close"]) / past[-21]["close"] * 100
            rs = ret20 - base_ret20

        cand.append({
            "code": code,
            "score": score,
            "rsi": ind.get("rsi14"),
            "action": action,
            "relative_strength": rs,
        })

    # 行业轮动：顶级行业加分
    sector_scores_map = {}
    sector_items = {}
    for c in cand:
        s = sector_of(c["code"], CORE_SECTOR_MAP)
        sector_items.setdefault(s, []).append(c)
    for s, items in sector_items.items():
        avg_score = sum(x["score"] for x in items) / len(items)
        avg_rs = sum(x["relative_strength"] for x in items) / len(items)
        sector_scores_map[s] = avg_score + max(0, avg_rs) * 0.5
    top_sector_names = [s for s, _ in sorted(sector_scores_map.items(), key=lambda x: x[1], reverse=True)[:top_sectors]]

    # 给顶级行业内的 ETF 加分
    for c in cand:
        if sector_of(c["code"], CORE_SECTOR_MAP) in top_sector_names:
            c["score"] += 5

    cand.sort(key=lambda x: (x["score"], x["relative_strength"], -(x["rsi"] or 50)), reverse=True)

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
    ssum = sum(x["score"] + max(0, x["relative_strength"]) * 2 for x in selected) or 1
    for x in selected:
        w = target_pos * (x["score"] + max(0, x["relative_strength"]) * 2) / ssum
        if x["action"] == "超卖观察":
            w = min(w, 0.08)
        # 波动率缩放：高波动 ETF 降权
        vol = x.get("volatility_20", 0.15)
        if vol > 0:
            vol_factor = min(2.0, TARGET_VOL / vol)
            w *= vol_factor
        x["weight"] = min(w, SINGLE_MAX)

    for t in set(x["theme"] for x in selected):
        members = [x for x in selected if x["theme"] == t]
        total = sum(x["weight"] for x in members)
        cap = THEME_CAP.get(t, 1.0)
        if total > cap:
            scale = cap / total
            for m in members:
                m["weight"] *= scale

    selected = [x for x in selected if x["weight"] >= SINGLE_MIN]
    return selected


def run_backtest(codes=EXPANDED_ETF, top_n=6, fee=0.0005):
    import time
    print("加载历史数据...")
    t0 = time.time()
    history_map = {}
    base_k = daily_kline("510300", limit=500)
    min_len = len(base_k)
    for code in codes:
        try:
            k = daily_kline(code, limit=500)
            if len(k) >= 300:
                history_map[code] = k
                min_len = min(min_len, len(k))
            else:
                print(f"  {code} 历史数据不足: {len(k)} 天，跳过")
        except Exception as e:
            print(f"  {code} 加载失败: {e}")
    print(f"加载完成: {len(history_map)} 只, 最短 {min_len} 天, 耗时 {time.time()-t0:.1f}s")

    if min_len < 120:
        print("数据不足")
        return

    date_list = [k["date"] for k in base_k]
    equity = [1.0]
    trades = []
    positions = {}

    for i in range(120, min_len - 1):
        today_k = {code: history_map[code][i] for code in history_map}
        tomorrow_k = {code: history_map[code][i+1] for code in history_map}
        regime = detect_regime(base_k, i)
        target_pos = REGIME_PARAMS.get(regime, REGIME_PARAMS["中性"])["target"]

        # 处理持仓
        portfolio_ret = 0
        new_positions = {}
        params = REGIME_PARAMS.get(regime, REGIME_PARAMS["中性"])
        for code, pos in positions.items():
            if code not in tomorrow_k:
                continue
            p_today = today_k[code]["close"]
            p_tomorrow = tomorrow_k[code]["close"]
            atr = pos.get("atr", 0.03)

            # 更新最高价，做移动止损
            pos["high"] = max(pos.get("high", pos["entry"]), p_today)
            trailing_stop = max(pos["stop"], pos["high"] - params["stop_mul"] * atr)
            pos["stop"] = round(trailing_stop, 3)

            exited = False
            exit_price = p_tomorrow
            if tomorrow_k[code]["low"] <= pos["stop"]:
                exit_price = pos["stop"]
                exited = True
            elif tomorrow_k[code]["high"] >= pos["take"]:
                # 分批止盈：第一次触及目标止盈 50%，余下移动止盈
                if pos.get("stage", 0) == 0:
                    actual_ret = (pos["take"] - p_today) / p_today - fee
                    portfolio_ret += pos["weight"] * 0.5 * actual_ret
                    trades.append({"date": date_list[i+1], "code": code, "action": "止盈半仓", "ret": actual_ret})
                    pos["weight"] *= 0.5
                    pos["stage"] = 1
                    pos["stop"] = max(pos["entry"] * 1.005, pos["stop"])  # 保本
                    exited = False
                else:
                    exit_price = pos["take"]
                    exited = True

            if exited:
                actual_ret = (exit_price - p_today) / p_today - fee
                portfolio_ret += pos["weight"] * actual_ret
                trades.append({"date": date_list[i+1], "code": code, "action": "卖出", "ret": actual_ret})
            else:
                ret = (p_tomorrow - p_today) / p_today
                portfolio_ret += pos["weight"] * ret
                new_positions[code] = pos

        equity.append(equity[-1] * (1 + portfolio_ret))

        # 调仓：持有仍强的标的，减少换手
        selected = select_portfolio(i, history_map, base_k, target_pos, top_n, top_sectors=2)

        # 保留当前仍在前 top_n*1.5 的持仓，降低摩擦
        hold_codes = {x["code"] for x in selected}
        for code, pos in new_positions.items():
            if code not in hold_codes:
                # 旧持仓不在新选中池，但还盈利就保留一天
                continue
        positions = {}
        for s in selected:
            code = s["code"]
            if code not in tomorrow_k:
                continue
            p = tomorrow_k[code]["close"]
            ind = analyze(history_map[code][:i+2])
            atr = ind.get("atr14") or 0.03
            stop = max(p * 0.93, p - params["stop_mul"] * atr)
            take = p + params["take_mul"] * atr
            positions[code] = {
                "weight": s["weight"],
                "entry": p,
                "stop": round(stop, 3),
                "take": round(take, 3),
                "atr": atr,
                "high": p,
                "stage": 0,
            }

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

    base_returns = []
    for i in range(120, min_len - 1):
        base_returns.append((base_k[i+1]["close"] - base_k[i]["close"]) / base_k[i]["close"])
    base_equity = [1.0]
    for r in base_returns:
        base_equity.append(base_equity[-1] * (1 + r))
    base_total = base_equity[-1] - 1

    # 每日净值曲线（每5日采样一次，避免数据过大）
    equity_curve = []
    benchmark_curve = []
    dates_curve = []
    for j in range(0, len(equity), 5):
        if j < len(date_list) - 120:
            dates_curve.append(date_list[120 + j])
            equity_curve.append(round(equity[j], 6))
            if j < len(base_equity):
                benchmark_curve.append(round(base_equity[j], 6))

    return {
        "start_date": date_list[120],
        "end_date": date_list[min_len-1],
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
        "equity_curve": equity_curve,
        "benchmark_curve": benchmark_curve,
        "dates_curve": dates_curve,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=6)
    ap.add_argument("--fee", type=float, default=0.0005)
    ap.add_argument("--all", action="store_true", help="使用扩展 ETF 池")
    ap.add_argument("--top50", action="store_true", help="使用扩展 ETF 池 Top 50")
    ap.add_argument("--grid", action="store_true", help="网格搜索止损止盈参数")
    args = ap.parse_args()

    codes = CORE_ETF
    if args.all:
        codes = EXPANDED_ETF
    if args.top50:
        codes = EXPANDED_ETF_TOP50
    print(f"使用 {'扩展池Top50' if args.top50 else '扩展池' if args.all else '核心池'} {len(codes)} 只 ETF")

    import time

    if args.grid:
        best = None
        best_score = -999
        for stop_mul in [1.8, 2.0, 2.2]:
            for take_mul in [3.0, 3.5, 4.0]:
                for r in REGIME_PARAMS:
                    REGIME_PARAMS[r]["stop_mul"] = stop_mul
                    REGIME_PARAMS[r]["take_mul"] = take_mul
                t0 = time.time()
                result = run_backtest(codes=codes, top_n=args.top, fee=args.fee)
                score = result["total_return"] - result["max_drawdown"] * 0.5
                print(f"stop={stop_mul} take={take_mul}: 收益{result['total_return']}% 回撤{result['max_drawdown']}% 夏普{result['sharpe']} 得分{score:.2f} 耗时{time.time()-t0:.0f}s")
                if score > best_score:
                    best_score = score
                    best = (stop_mul, take_mul, result)
        print(f"\n最优: stop={best[0]} take={best[1]} 得分{best_score:.2f}")
        for k, v in best[2].items():
            print(f"  {k:<25}: {v}")
        return

    t0 = time.time()
    result = run_backtest(codes=codes, top_n=args.top, fee=args.fee)
    print(f"\n回测耗时: {time.time()-t0:.1f}s")
    print("\n=== V3.2 回测结果 ===")
    for k, v in result.items():
        print(f"  {k:<25}: {v}")

    os.makedirs("reports", exist_ok=True)
    with open("reports/backtest_v3_2_result.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print("已保存 reports/backtest_v3_2_result.json")


if __name__ == "__main__":
    main()
