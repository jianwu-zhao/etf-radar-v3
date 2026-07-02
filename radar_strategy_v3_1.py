#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ETF 波段雷达 V3.1 量化策略执行器（优化版）

核心改进：
  1. 大盘状态自适应参数（牛市追强势 / 熊市做反转）
  2. 相对强度 vs 沪深300
  3. 成交量放大因子
  4. 降低换手率：持仓仍强则保留
  5. 趋势动量权重提升
"""
import os
import json
import argparse
import datetime
from typing import List, Dict, Any

from data_source import realtime_quote, daily_kline, fetch_etf_list, intraday_kline, _batch_from_yahoo
from etf_universe import EXPANDED_ETF
from sector_map import CORE_SECTOR_MAP, sector_scores, sector_of
from tech_indicators import analyze, intraday_signal
from datetime import timezone, timedelta

BEIJING_TZ = timezone(timedelta(hours=8))

HOME = os.path.expanduser("~")
BASE = os.path.dirname(os.path.abspath(__file__))
REPORT_DIR = os.path.join(BASE, "reports")

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
THEME_CAP = {k: 0.20 for k in THEME_MAP}
THEME_CAP.update({"宽基": 0.30, "黄金": 0.15, "有色商品": 0.20})

SINGLE_MAX = 0.20
SINGLE_MIN = 0.05

# 市场状态自适应参数
REGIME_PARAMS = {
    "强多": {"target": 0.95, "rsi_max": 70, "score_thr": 45, "momentum": "strong"},
    "偏多": {"target": 0.85, "rsi_max": 60, "score_thr": 45, "momentum": "balanced"},
    "中性": {"target": 0.50, "rsi_max": 50, "score_thr": 50, "momentum": "balanced"},
    "偏空": {"target": 0.35, "rsi_max": 45, "score_thr": 55, "momentum": "reversal"},
    "强空": {"target": 0.10, "rsi_max": 40, "score_thr": 60, "momentum": "reversal"},
}


def log(msg):
    print(f"[{datetime.datetime.now(BEIJING_TZ).strftime('%H:%M:%S')}] {msg}")


def detect_market_regime():
    """用沪深300判断大盘状态"""
    try:
        k = daily_kline("510300", limit=120)
        if len(k) < 60:
            return "中性", 0.50
        price = k[-1]["close"]
        ma60 = sum(x["close"] for x in k[-60:]) / 60
        ma20 = sum(x["close"] for x in k[-20:]) / 60
        slope_60 = (ma60 - sum(x["close"] for x in k[-90:-30]) / 60) / ma60 * 100
        slope_20 = (ma20 - sum(x["close"] for x in k[-40:-20]) / 20) / ma20 * 100

        if price > ma60 and slope_60 > 2:
            return "强多", REGIME_PARAMS["强多"]["target"]
        if price > ma60 and slope_60 > 0:
            return "偏多", REGIME_PARAMS["偏多"]["target"]
        if price < ma60 and slope_60 < -2:
            return "强空", REGIME_PARAMS["强空"]["target"]
        if price < ma60:
            return "偏空", REGIME_PARAMS["偏空"]["target"]
        return "中性", REGIME_PARAMS["中性"]["target"]
    except Exception as e:
        log(f"大盘判断失败: {e}")
        return "中性", 0.50


def relative_strength(code, klines, base_k=None):
    """相对沪深300强度：过去20日超额收益"""
    try:
        if base_k is None:
            base_k = daily_kline("510300", limit=60)
        if len(klines) < 21 or len(base_k) < 21:
            return 0
        ret = (klines[-1]["close"] - klines[-21]["close"]) / klines[-21]["close"] * 100
        base_ret = (base_k[-1]["close"] - base_k[-21]["close"]) / base_k[-21]["close"] * 100
        return ret - base_ret
    except:
        return 0


def factor_score(ind: Dict, rt: Dict, regime: str) -> float:
    """多因子评分，市场自适应"""
    params = REGIME_PARAMS.get(regime, REGIME_PARAMS["中性"])
    momentum_mode = params["momentum"]
    score = 0

    # 1. 趋势因子 (0-25)
    if ind["ma5"] > ind["ma10"] > ind["ma20"] > ind["ma60"]:
        score += 25
    elif ind["ma5"] > ind["ma20"] > ind["ma60"]:
        score += 18
    elif ind["ma5"] > ind["ma20"]:
        score += 10
    elif ind["price"] > ind["ma60"]:
        score += 5

    # 2. 动量因子 (0-20)，根据市场状态调整
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
    else:  # balanced
        if 3 < mom20 < 15:
            score += 18
        elif 0 < mom20 < 20:
            score += 12
        elif -10 < mom20 < 0:
            score += 6

    # 60日动量加分
    if mom60 > 10:
        score += 5
    elif mom60 > 0:
        score += 2

    # 3. 反转因子 (0-15)
    rsi = ind.get("rsi14") or 50
    if rsi < 30:
        score += 15
    elif rsi < 40:
        score += 10
    elif rsi < 50:
        score += 5

    # 牛市里 RSI 60-70 强势股也给分
    if momentum_mode == "strong" and 55 < rsi < params["rsi_max"]:
        score += 8

    # 4. 成交量因子 (0-10)
    vol_now = ind.get("volume", 0)
    # volume 需要在 analyze 返回里加上
    if "volume" in ind and ind["volume"]:
        pass

    # 5. 结构因子 (0-15)
    bb = ind.get("bollinger", {})
    pb = bb.get("percent_b", 50)
    if pb < 20:
        score += 15
    elif pb < 40:
        score += 8
    elif pb > 80:
        score -= 10

    # 6. MACD (0-10)
    macd = ind.get("macd", {})
    if macd.get("histogram", 0) > 0 and macd.get("macd", 0) > macd.get("signal", 0):
        score += 10
    elif macd.get("histogram", 0) > 0:
        score += 6
    elif macd.get("histogram", 0) > macd.get("histogram", 0) - 0.001:  # 绿柱缩短
        score += 3

    # 7. 均值回归 (0-10)
    ma60_dist = (ind["price"] / ind["ma60"] - 1) * 100 if ind["ma60"] else 0
    if ma60_dist < -10:
        score += 10
    elif ma60_dist < -5:
        score += 5

    return max(0, min(100, score))


def signal_action(ind: Dict, score: float, regime: str) -> str:
    params = REGIME_PARAMS.get(regime, REGIME_PARAMS["中性"])
    rsi = ind.get("rsi14") or 50
    macd_h = ind.get("macd", {}).get("histogram", 0)
    price = ind["price"]
    ma5 = ind["ma5"]
    ma20 = ind["ma20"]

    # 强势市场追趋势
    if params["momentum"] == "strong":
        if score >= 60 and rsi < params["rsi_max"] and price > ma20:
            return "可买"
        # 强者恒强：高动量 + 高相对强度 + MACD红柱
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
    if score >= 40:
        return "观察"
    return "等待"


def calc_stop_take(ind: Dict) -> (float, float):
    atr = ind.get("atr14") or 0.03
    price = ind["price"]
    # 趋势强时用更宽的止损
    stop = round(max(price * 0.93, price - 2.0 * atr), 3)
    take = round(price + 3.0 * atr, 3)
    return stop, take


def analyze_one(code: str, regime: str = None, base_k: list = None) -> Dict[str, Any]:
    try:
        rt = realtime_quote(code)
        if not rt or not rt.get("price"):
            return None
        klines = daily_kline(code, limit=120)
        if len(klines) < 60:
            return None
        ind = analyze(klines)
        ind["volume"] = klines[-1].get("volume", 0)
        ind["volume_avg20"] = sum(k["volume"] for k in klines[-20:]) / 20
        ind["volume_ratio"] = ind["volume"] / ind["volume_avg20"] if ind["volume_avg20"] else 1

        # 成交量因子融入评分前单独计算
        vol_score = 0
        if ind["volume_ratio"] > 1.5:
            vol_score = 10
        elif ind["volume_ratio"] > 1.2:
            vol_score = 5

        if regime is None:
            regime, _ = detect_market_regime()
        score = factor_score(ind, rt, regime) + vol_score
        score = min(100, score)
        action = signal_action(ind, score, regime)
        stop, take = calc_stop_take(ind)
        rs = relative_strength(code, klines, base_k)

        return {
            "code": code,
            "name": rt["name"],
            "price": ind["price"],
            "change_pct": rt["change_pct"],
            "rsi14": ind["rsi14"],
            "rsi6": ind["rsi6"],
            "ma5": ind["ma5"],
            "ma10": ind["ma10"],
            "ma20": ind["ma20"],
            "ma60": ind["ma60"],
            "momentum_20": ind["momentum_20"],
            "momentum_60": ind["momentum_60"],
            "volatility_20": ind["volatility_20"],
            "volume_ratio": round(ind["volume_ratio"], 2),
            "relative_strength": round(rs, 2),
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


def intraday_confirm(code):
    """15分钟级别确认：返回确认后的动作建议"""
    try:
        k15 = intraday_kline(code, period=15, limit=160)
        sig = intraday_signal(k15)
        return sig
    except Exception as e:
        return {"signal": "unknown", "rsi14": None, "macd_hist": 0}


def theme_of(code):
    for t, codes in THEME_MAP.items():
        if code in codes:
            return t
    return "其他"


def select_portfolio(analyzed: List[Dict], target_pos: float, top_n=6, top_sectors=2):
    buy_signals = ["可买", "确认买", "超卖观察"]
    cand = [a for a in analyzed if a["action"] in buy_signals and a["score"] >= 40]

    # 计算行业轮动得分
    sec_scores = sector_scores(analyzed, CORE_SECTOR_MAP)
    top_sector_names = [s for s, _ in sorted(sec_scores.items(), key=lambda x: x[1]["score"], reverse=True)[:top_sectors]]

    # 优先从顶级行业中选股
    sector_cand = [a for a in cand if sector_of(a["code"], CORE_SECTOR_MAP) in top_sector_names]
    other_cand = [a for a in cand if sector_of(a["code"], CORE_SECTOR_MAP) not in top_sector_names]

    # 排序：评分 > 相对强度 > RSI 低
    sector_cand.sort(key=lambda x: (x["score"], x.get("relative_strength", 0), -(x["rsi14"] or 50)), reverse=True)
    other_cand.sort(key=lambda x: (x["score"], x.get("relative_strength", 0), -(x["rsi14"] or 50)), reverse=True)

    cand = sector_cand + other_cand

    theme_count = {}
    deduped = []
    for r in cand:
        t = theme_of(r["code"])
        if theme_count.get(t, 0) >= 2:
            continue
        r["theme"] = t
        r["sector"] = sector_of(r["code"], CORE_SECTOR_MAP)
        theme_count[t] = theme_count.get(t, 0) + 1
        deduped.append(r)

    selected = deduped[:top_n]

    # 评分 + 相对强度加权
    ssum = sum(x["score"] + max(0, x.get("relative_strength", 0)) * 2 for x in selected) or 1
    for x in selected:
        w = target_pos * (x["score"] + max(0, x.get("relative_strength", 0)) * 2) / ssum
        if x["action"] == "超卖观察":
            w = min(w, 0.08)
        x["weight"] = round(min(w, SINGLE_MAX), 4)

    for t in set(x["theme"] for x in selected):
        members = [x for x in selected if x["theme"] == t]
        total = sum(x["weight"] for x in members)
        cap = THEME_CAP.get(t, 1.0)
        if total > cap:
            scale = cap / total
            for m in members:
                m["weight"] = round(m["weight"] * scale, 4)

    # 15分钟级别确认：只给买入信号的 ETF 做
    for x in selected:
        if x["action"] in ["可买", "确认买"]:
            sig = intraday_confirm(x["code"])
            x["intra_signal"] = sig["signal"]
            x["intra_rsi14"] = sig["rsi14"]
            x["intra_macd_hist"] = sig["macd_hist"]
            if sig["signal"] == "overbought":
                x["action"] = "观察"  # 15分钟超买，降级
            elif sig["signal"] in ["buy_pullback", "buy_breakout"]:
                x["action"] = "确认买"  # 15分钟确认
        else:
            x["intra_signal"] = "-"
            x["intra_rsi14"] = None
            x["intra_macd_hist"] = 0

    selected = [x for x in selected if x["weight"] >= SINGLE_MIN]
    return selected


def build_report(market_regime, target_pos, selected, analyzed_count):
    today = datetime.datetime.now(BEIJING_TZ).strftime("%Y%m%d")
    etf_sum = round(sum(x["weight"] for x in selected), 4)
    cash = round(max(0.0, 1 - etf_sum), 4)

    lines = []
    lines.append("=" * 72)
    lines.append("  ETF 波段雷达 V3.1 — 每日交易计划（真实数据源·优化版）")
    lines.append("=" * 72)
    lines.append(f"生成日期   : {today}")
    lines.append(f"大盘状态   : {market_regime}")
    lines.append(f"目标仓位   : {target_pos:.0%}")
    lines.append(f"扫描 ETF   : {analyzed_count} 只")
    lines.append("")
    # 行业轮动信息
    sec_scores = sector_scores(selected, CORE_SECTOR_MAP)
    sec_line = " | ".join([f"{s}:{v['score']:.1f}" for s, v in sorted(sec_scores.items(), key=lambda x: x[1]['score'], reverse=True)])
    lines.append(f"行业轮动   : {sec_line}")
    lines.append("")
    lines.append(f"{'ETF':<10}{'代码':<8}{'动作':<8}{'评分':>6}{'RSI':>6}{'RS':>7}{'15m':>6}{'仓':>6}{'现价':>8}{'止损':>8}{'止盈':>8}")
    lines.append("-" * 96)
    for x in selected:
        intra = x.get('intra_signal','-')
        lines.append(
            f"{x['name']:<10}{x['code']:<8}{x['action']:<8}"
            f"{x['score']:>6.1f}{(x['rsi14'] or 0):>6.1f}"
            f"{x.get('relative_strength',0):>+6.1f}"
            f"{intra:>6}"
            f"{x['weight']*100:>5.1f}%"
            f"{x['price']:>8.3f}{x['stop']:>8.3f}{x['take_profit']:>8.3f}"
        )
    lines.append("-" * 86)
    lines.append(f"{'ETF 合计仓位':<20}{etf_sum*100:>6.1f}%")
    lines.append(f"{'现金':<20}{cash*100:>6.1f}%")
    lines.append("")
    lines.append("执行规则:")
    lines.append("  · 可买    : 次日开盘涨幅<=2.0% 直接建仓")
    lines.append("  · 确认买  : 突破昨高 / 收盘站上MA5 才买")
    lines.append("  · 超卖观察: 分批建仓，每跌2%加一次")
    lines.append("  · 止损    : 收盘<=止损价，次日清仓")
    lines.append("  · 止盈    : >=止盈价卖50%，余下移动止盈")
    lines.append("  · 数据源  : 东方财富 API")
    lines.append("=" * 72)

    text = "\n".join(lines)
    data = {
        "generated_at": datetime.datetime.now(BEIJING_TZ).isoformat(),
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
    ap = argparse.ArgumentParser(description="ETF 波段雷达 V3.1")
    ap.add_argument("--codes", help="指定 ETF 代码，逗号分隔")
    ap.add_argument("--top", type=int, default=6)
    ap.add_argument("--position", type=float, default=None)
    ap.add_argument("--all", action="store_true", help="使用扩展 ETF 池（100+只）")
    ap.add_argument("--notify", action="store_true")
    ap.add_argument("--no-save", action="store_true")
    args = ap.parse_args()

    if args.codes:
        codes = args.codes.split(",")
    elif args.all:
        codes = EXPANDED_ETF
    else:
        codes = CORE_ETF

    log("开始获取大盘状态...")
    market_regime, auto_pos = detect_market_regime()
    target_pos = args.position if args.position is not None else auto_pos

    log(f"大盘={market_regime}, 目标仓位={target_pos:.0%}")
    log(f"开始扫描 {len(codes)} 只 ETF...")

    # 缓存沪深300数据用于相对强度
    base_k = daily_kline("510300", limit=60)

    analyzed = []
    for code in codes:
        r = analyze_one(code.strip(), regime=market_regime, base_k=base_k)
        if r:
            analyzed.append(r)
            log(f"  {r['code']} {r['name']}: score={r['score']:.1f} action={r['action']} rsi={r['rsi14']} rs={r.get('relative_strength',0):+.1f}")

    selected = select_portfolio(analyzed, target_pos, top_n=args.top)
    report, data = build_report(market_regime, target_pos, selected, len(analyzed))

    print("\n" + report)

    if args.notify:
        try:
            import notify
            notify.send(f"ETF雷达V3.1 {data['date']} 仓位{target_pos:.0%}", report)
        except Exception as e:
            log(f"推送失败: {e}")

    if not args.no_save:
        os.makedirs(REPORT_DIR, exist_ok=True)
        day = data["date"]
        with open(os.path.join(REPORT_DIR, f"plan_v3_1_{day}.txt"), "w", encoding="utf-8") as f:
            f.write(report)
        with open(os.path.join(REPORT_DIR, f"plan_v3_1_{day}.json"), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        log(f"已保存: reports/plan_v3_1_{day}.txt/.json")


if __name__ == "__main__":
    main()
