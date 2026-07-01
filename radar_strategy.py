#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ETF 波段雷达 V2 量化策略执行器

数据源: https://jianwu-zhao.github.io/aggregator/radar.html

功能:
  1. 抓取 radar.html 并解析全部 ETF 因子数据
  2. 解析大盘/市场状态, 计算目标总仓位
  3. 按多因子规则分层(强信号/观察买/等待)并过滤排除项
  4. 同主题去重 + 评分加权分配单票仓位
  5. 输出每日交易计划(买入池/仓位/止损/止盈)
  6. 保存 JSON + 文本报告到 ~/etf-radar/reports/

注意: 本工具仅做策略信号计算, 不构成投资建议, 不自动下单。
"""

import re
import os
import json
import html
import argparse
import datetime
import urllib.request
import gzip

URL = "https://jianwu-zhao.github.io/aggregator/radar.html"
HOME = os.path.expanduser("~")
BASE = os.path.join(HOME, "etf-radar")
REPORT_DIR = os.path.join(BASE, "reports")

# ---------------------------------------------------------------------------
# 主题分类: 用于同主题去重/限仓
# ---------------------------------------------------------------------------
THEME_MAP = {
    "黄金": ["518880", "159937", "518600"],
    "有色商品": ["159980", "512400", "515220", "159930"],
    "新能源链": ["515790", "515030", "159755", "159611"],
    "传媒互联": ["512980", "159869", "513050", "513180"],
    "港股": ["513060", "513050", "513180"],
    "海外": ["513500", "513220", "159561"],
}

THEME_CAP = {  # 同主题合并仓位上限
    "黄金": 0.15,
    "有色商品": 0.25,
    "新能源链": 0.25,
    "传媒互联": 0.20,
    "港股": 0.20,
    "海外": 0.20,
}

SINGLE_MAX = 0.15   # 单票最高
SINGLE_MIN = 0.05   # 单票最低(低于此则不建仓)


def fetch(url=URL):
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0",
        "Accept-Encoding": "gzip",
    })
    with urllib.request.urlopen(req, timeout=30) as r:
        data = r.read()
        if r.headers.get("Content-Encoding") == "gzip":
            data = gzip.decompress(data)
    return data.decode("utf-8", "replace")


def parse_market(text):
    """解析大盘/市场/建议仓位/宽度/多空比"""
    m = re.search(r'更新：(\d+).*?大盘：<span[^>]*>([^<]+)</span>', text, re.S)
    upd = m.group(1) if m else ""
    regime = m.group(2).strip() if m else ""

    def grab(pat):
        mm = re.search(pat, text)
        return mm.group(1).strip() if mm else ""

    market = grab(r'市场：([^　<]+)')
    suggest = grab(r'建议仓位：([\d.]+)%')
    width = grab(r'宽度：([\d.]+)%')
    ratio = grab(r'多空比：([\d.]+)')

    return {
        "update": upd,
        "regime": regime,
        "market": market,
        "suggest_position": float(suggest) / 100 if suggest else 0.5,
        "width": float(width) if width else None,
        "long_short_ratio": float(ratio) if ratio else None,
    }


def parse_rows(text):
    rows = []
    for m in re.finditer(r'<tr class="[^"]*"([^>]*)>(.*?)</tr>', text, re.S):
        attrs, body = m.group(1), m.group(2)

        def attr(k):
            mm = re.search(r'data-' + k + r'="([^"]*)"', attrs)
            return html.unescape(mm.group(1)) if mm else ""

        code = attr("code")
        if not code:
            continue

        score_m = re.search(r'<td class="score-cell[^"]*"><b>([+-]?[\d.]+)</b>', body)
        rsi_m = re.search(r'RSI(\d+)', body)
        grade_m = re.search(r'grade-([SABC])', body)

        rows.append({
            "code": code,
            "name": attr("name").replace(code, "").strip(),
            "action": attr("action"),
            "price": float(attr("price") or 0),
            "stop": float(attr("stop") or 0),
            "take_profit": float(attr("tp") or 0),
            "score": float(score_m.group(1)) if score_m else 0.0,
            "rsi": int(rsi_m.group(1)) if rsi_m else None,
            "grade": grade_m.group(1) if grade_m else "",
            "excluded": attr("excluded") == "true",
        })
    return rows


def rank_action(action):
    if "关注" in action:
        return 4
    if "超卖" in action:
        return 3
    if "观察" in action:
        return 2
    if "等待" in action:
        return 1
    return 0


def target_position(market, override=None):
    """根据大盘状态给出仓位上限, 与网页建议取小。

    override: 若指定(0~1), 直接使用该目标仓位, 跳过自动计算。
    """
    if override is not None:
        return round(max(0.0, min(1.0, override)), 2)
    regime = market["regime"]
    suggest = market["suggest_position"]
    caps = {
        "强多": 1.00, "偏多": 0.80, "中性": 0.50,
        "偏空": 0.60, "强空": 0.20,
    }
    cap = caps.get(regime, 0.60)
    # 大盘偏空但市场偏多时, 折中压低
    if regime == "偏空" and "多" in market.get("market", ""):
        cap = 0.60
    return round(min(suggest, cap), 2)


def theme_of(code):
    for theme, codes in THEME_MAP.items():
        if code in codes:
            return theme
    return None


def select(rows, tgt_pos, top_n=6):
    cand = []
    for r in rows:
        if r["excluded"] or r["score"] <= 0:
            continue
        if r["rsi"] is not None and r["rsi"] > 70:
            continue

        ar = rank_action(r["action"])
        rsi = r["rsi"] if r["rsi"] is not None else 50

        if ar >= 3 and r["score"] >= 30 and rsi <= 45:
            r["signal"] = "buy"          # 强信号: 可买
        elif ar >= 2 and r["score"] >= 28 and rsi <= 45:
            r["signal"] = "watch_buy"    # 中信号: 确认买
        else:
            continue

        r["action_rank"] = ar
        r["theme"] = theme_of(r["code"])
        cand.append(r)

    # 排序: 动作等级 > 评分 > RSI低优先
    cand.sort(key=lambda x: (x["action_rank"], x["score"], -(x["rsi"] or 50)),
              reverse=True)

    # 同主题去重: 每主题最多保留 2 只
    theme_count = {}
    deduped = []
    for r in cand:
        t = r["theme"]
        if t:
            if theme_count.get(t, 0) >= 2:
                continue
            theme_count[t] = theme_count.get(t, 0) + 1
        deduped.append(r)

    selected = deduped[:top_n]

    # 评分加权分配仓位
    ssum = sum(x["score"] for x in selected) or 1
    for x in selected:
        w = tgt_pos * x["score"] / ssum
        if x["signal"] == "watch_buy":
            w = min(w, 0.10)
        x["weight"] = round(min(w, SINGLE_MAX), 4)

    # 主题合并限仓
    theme_w = {}
    for x in selected:
        t = x["theme"]
        if not t:
            continue
        theme_w.setdefault(t, []).append(x)
    for t, members in theme_w.items():
        cap = THEME_CAP.get(t, 1.0)
        total = sum(m["weight"] for m in members)
        if total > cap:
            scale = cap / total
            for m in members:
                m["weight"] = round(m["weight"] * scale, 4)

    # 剔除低于最小仓位的
    selected = [x for x in selected if x["weight"] >= SINGLE_MIN]
    return selected


def build_report(market, selected, override=None):
    tgt = target_position(market, override)
    etf_sum = round(sum(x["weight"] for x in selected), 4)
    cash = round(max(0.0, 1 - etf_sum), 4)

    lines = []
    lines.append("=" * 56)
    lines.append("  ETF 波段雷达 V2 — 每日交易计划")
    lines.append("=" * 56)
    lines.append(f"数据更新   : {market['update']}")
    lines.append(f"大盘状态   : {market['regime']}")
    lines.append(f"市场状态   : {market['market']}")
    lines.append(f"网页建议仓位: {market['suggest_position']:.0%}")
    lines.append(f"策略目标仓位: {tgt:.0%}")
    if market["width"] is not None:
        lines.append(f"市场宽度   : {market['width']}%")
    if market["long_short_ratio"] is not None:
        lines.append(f"多空比     : {market['long_short_ratio']}")
    lines.append("")
    lines.append(f"{'ETF':<12}{'代码':<8}{'动作':<8}{'评分':>6}{'RSI':>5}"
                 f"{'仓位':>7}{'止损':>9}{'止盈':>9}")
    lines.append("-" * 72)

    for x in selected:
        sig = "可买" if x["signal"] == "buy" else "确认买"
        lines.append(
            f"{x['name']:<12}{x['code']:<8}{sig:<8}"
            f"{x['score']:>6.1f}{(x['rsi'] or 0):>5}"
            f"{x['weight']*100:>6.1f}%"
            f"{x['stop']:>9.3f}{x['take_profit']:>9.3f}"
        )

    lines.append("-" * 72)
    lines.append(f"{'ETF 合计仓位':<20}{etf_sum*100:>5.1f}%")
    lines.append(f"{'现金':<20}{cash*100:>5.1f}%")
    lines.append("")
    lines.append("执行规则:")
    lines.append("  · 可买  : 次日开盘涨幅<=1.5% 直接建仓; 超卖类<=1.0%")
    lines.append("  · 确认买: 突破昨高 / 收盘站上MA5 / 放量不破昨低 才买")
    lines.append("  · 止损  : 收盘<=止损价 次日清仓")
    lines.append("  · 止盈  : >=止盈价 卖50%, 余下移动止盈(2xATR)")
    lines.append("  · 衰减  : 评分<15 / 转等待 / 被排除 / RSI>70 减仓或清仓")
    lines.append("=" * 56)
    text = "\n".join(lines)

    data = {
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "market": market,
        "target_position": tgt,
        "etf_total": etf_sum,
        "cash": cash,
        "positions": selected,
    }
    return text, data


def main():
    ap = argparse.ArgumentParser(description="ETF 波段雷达 V2 策略执行器")
    ap.add_argument("--top", type=int, default=6, help="最大持仓数")
    ap.add_argument("--position", type=float, default=None,
                    help="手动指定目标总仓位(如 0.8 表示80%%), 默认按大盘自动")
    ap.add_argument("--file", help="使用本地 html 文件而非联网抓取")
    ap.add_argument("--notify", action="store_true",
                    help="推送到已配置的推送渠道(server酱/Telegram)")
    ap.add_argument("--no-save", action="store_true",
                    help="不保存报告到文件")
    args = ap.parse_args()

    if args.file:
        with open(args.file, encoding="utf-8", errors="replace") as f:
            text = f.read()
    else:
        text = fetch()

    market = parse_market(text)
    rows = parse_rows(text)
    tgt = target_position(market, args.position)
    selected = select(rows, tgt, top_n=args.top)
    report, data = build_report(market, selected, args.position)

    print(report)

    if args.notify:
        try:
            import notify
            sent = notify.send(
                f"ETF雷达 {market['update']} 仓位{tgt:.0%}", report)
            if sent:
                print(f"\n已推送: {', '.join(sent)}")
            else:
                print("\n[notify] 未配置推送渠道, 跳过")
        except Exception as e:
            print(f"\n[notify] 推送异常: {e}")

    if not args.no_save:
        os.makedirs(REPORT_DIR, exist_ok=True)
        day = market["update"] or datetime.date.today().strftime("%Y%m%d")
        with open(os.path.join(REPORT_DIR, f"plan_{day}.txt"), "w",
                  encoding="utf-8") as f:
            f.write(report)
        with open(os.path.join(REPORT_DIR, f"plan_{day}.json"), "w",
                  encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"\n已保存: {REPORT_DIR}/plan_{day}.txt / .json")


if __name__ == "__main__":
    main()
