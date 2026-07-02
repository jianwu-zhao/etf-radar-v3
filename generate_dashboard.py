#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成 ETF 雷达 V3 网页看板（参考 radar.html 风格）
"""
import os
import json
import glob
import datetime
from sector_map import CORE_SECTOR_MAP, sector_scores


def load_latest_plan():
    files = sorted(glob.glob("reports/plan_v3_1_*.json"), reverse=True)
    if not files:
        return None
    with open(files[0], encoding="utf-8") as f:
        return json.load(f)


def html_escape(s):
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def grade_class(score):
    if score >= 60:
        return "grade-s"
    if score >= 50:
        return "grade-a"
    if score >= 40:
        return "grade-b"
    return "grade-c"


def action_class(action):
    if action == "可买":
        return "buy"
    if action == "确认买":
        return "confirm"
    if action == "超卖观察":
        return "watch"
    return "wait"


def generate(data):
    date = data.get("date", "")
    market = data.get("market_regime", "未知")
    target = data.get("target_position", 0)
    positions = data.get("positions", [])
    total = data.get("etf_total", 0)
    cash = data.get("cash", 0)
    scanned = data.get("all_scanned", 0)

    # 生成选中池表格
    selected_rows = []
    for i, p in enumerate(positions, 1):
        bb = p.get("bollinger", {})
        macd = p.get("macd", {})
        ma60_dist = (p.get("price", 0) / p.get("ma60", 1) - 1) * 100 if p.get("ma60") else 0
        selected_rows.append(f"""
        <tr>
            <td>{i}</td>
            <td class="name"><b>{html_escape(p.get('name',''))}</b><br><small>{p.get('code','')}</small></td>
            <td><span class="badge {action_class(p.get('action',''))}">{p.get('action','')}</span></td>
            <td class="sig">{format_signal(p)}</td>
            <td class="score {grade_class(p.get('score',0))}">{p.get('score',0):.1f}</td>
            <td>{macd.get('histogram',0):.4f}</td>
            <td>{ma60_dist:+.1f}%</td>
            <td>{bb.get('percent_b',0):.1f}%</td>
            <td><b>RSI{p.get('rsi14',0):.0f}</b><br><small>ATR{p.get('atr14',0):.3f}</small></td>
            <td class="{'up' if (p.get('momentum_60') or 0) > 0 else 'down'}">{p.get('momentum_60',0):+.1f}%</td>
            <td class="{'up' if (p.get('momentum_20') or 0) > 0 else 'down'}">{p.get('momentum_20',0):+.1f}%</td>
            <td class="{'up' if (p.get('change_pct') or 0) > 0 else 'down'}">{p.get('change_pct',0):+.2f}%</td>
            <td class="plan">回踩 {p.get('stop',0):.3f}<br>止盈 {p.get('take_profit',0):.3f}<br>仓位 {p.get('weight',0)*100:.1f}%</td>
        </tr>
        """)

    selected_html = "".join(selected_rows) if selected_rows else "<tr><td colspan='13'>暂无入选</td></tr>"

    # 行业轮动
    sec_scores = sector_scores(data.get("positions", []), CORE_SECTOR_MAP)
    sec_html = " | ".join([f"<span class=\"badge wait\">{s}:{v['score']:.1f}</span>" for s, v in sorted(sec_scores.items(), key=lambda x: x[1]['score'], reverse=True)])

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>ETF 波段雷达 V3.1</title>
    <style>
        :root {{
            --bg: #0f172a;
            --card: #1e293b;
            --text: #e2e8f0;
            --muted: #94a3b8;
            --accent: #38bdf8;
            --up: #ef4444;
            --down: #22c55e;
            --buy: #22c55e;
            --watch: #f59e0b;
            --confirm: #38bdf8;
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Microsoft YaHei", sans-serif; background: var(--bg); color: var(--text); padding: 16px; line-height: 1.5; font-size: 14px; }}
        .container {{ max-width: 1100px; margin: 0 auto; }}
        h1 {{ text-align: center; margin-bottom: 6px; font-size: 24px; }}
        .sub {{ text-align: center; color: var(--muted); margin-bottom: 20px; font-size: 13px; }}
        .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 10px; margin-bottom: 20px; }}
        .card {{ background: var(--card); border-radius: 10px; padding: 14px; text-align: center; }}
        .card .label {{ color: var(--muted); font-size: 11px; }}
        .card .value {{ font-size: 20px; font-weight: bold; margin-top: 4px; }}
        table {{ width: 100%; border-collapse: collapse; background: var(--card); border-radius: 10px; overflow: hidden; font-size: 13px; }}
        th, td {{ padding: 10px 6px; text-align: center; border-bottom: 1px solid #334155; }}
        th {{ background: #0f172a; color: var(--accent); font-weight: 600; font-size: 12px; position: sticky; top: 0; }}
        tr:hover {{ background: #334155; }}
        td.name {{ text-align: left; }}
        td.plan {{ font-size: 11px; line-height: 1.6; }}
        td.sig {{ font-size: 11px; color: var(--muted); max-width: 120px; }}
        .badge {{ display: inline-block; padding: 3px 8px; border-radius: 4px; font-size: 11px; font-weight: 600; }}
        .buy {{ background: rgba(34,197,94,0.15); color: var(--buy); }}
        .watch {{ background: rgba(245,158,11,0.15); color: var(--watch); }}
        .confirm {{ background: rgba(56,189,248,0.15); color: var(--confirm); }}
        .wait {{ background: rgba(148,163,184,0.15); color: var(--muted); }}
        .grade-s {{ background: rgba(239,68,68,0.2); color: #fca5a5; }}
        .grade-a {{ background: rgba(249,115,22,0.2); color: #fdba74; }}
        .grade-b {{ background: rgba(59,130,246,0.2); color: #93c5fd; }}
        .grade-c {{ background: rgba(148,163,184,0.2); color: #cbd5e1; }}
        .score {{ font-weight: bold; border-radius: 4px; padding: 2px 4px; display: inline-block; }}
        .up {{ color: var(--up); }}
        .down {{ color: var(--down); }}
        .footer {{ text-align: center; color: var(--muted); margin-top: 20px; font-size: 11px; }}
        .rules {{ background: var(--card); border-radius: 10px; padding: 14px; margin-top: 20px; font-size: 12px; }}
        .rules h3 {{ margin-bottom: 10px; color: var(--accent); }}
        .rules li {{ margin: 5px 0; color: var(--muted); }}
        @media (max-width: 768px) {{
            body {{ padding: 8px; font-size: 12px; }}
            th, td {{ padding: 6px 3px; }}
            td.sig, td.plan {{ font-size: 10px; }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>📡 ETF 波段雷达 V3.1</h1>
        <div class="sub">更新：{date}　大盘：{market}　建议仓位：{target*100:.0f}%　扫描：{scanned}只</div>

        <div class="grid">
            <div class="card"><div class="label">目标仓位</div><div class="value">{target*100:.0f}%</div></div>
            <div class="card"><div class="label">ETF 仓位</div><div class="value">{total*100:.1f}%</div></div>
            <div class="card"><div class="label">现金</div><div class="value">{cash*100:.1f}%</div></div>
            <div class="card"><div class="label">入选标的</div><div class="value">{len(positions)}</div></div>
        </div>

        <table>
            <thead>
                <tr>
                    <th>序</th>
                    <th>标的</th>
                    <th>行业</th>
                    <th>操作建议</th>
                    <th>15m</th>
                    <th>V4评分</th>
                    <th>MACD柱</th>
                    <th>均值回归</th>
                    <th>价格结构</th>
                    <th>RSI/风控</th>
                    <th>月线</th>
                    <th>周线</th>
                    <th>日线</th>
                    <th>买点参考</th>
                </tr>
            </thead>
            <tbody>
                {selected_html}
            </tbody>
        </table>

        <div class="rules">
            <h3>执行规则</h3>
            <ul>
                <li>可买：次日开盘涨幅 ≤ 1.5% 直接建仓</li>
                <li>确认买：突破昨高 / 收盘站上 MA5 才买</li>
                <li>超卖观察：分批建仓，每跌 2% 加一次</li>
                <li>止损：收盘 ≤ 止损价，次日清仓</li>
                <li>止盈：≥ 止盈价卖 50%，余下移动止盈</li>
            </ul>
        </div>

        <div class="footer">
            本工具仅做策略信号计算，不构成投资建议，不自动下单。<br>
            数据源：东方财富 API · 生成时间 {datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S")}
        </div>
    </div>
</body>
</html>
"""
    return html


def format_signal(p):
    """生成拐点信号文字"""
    parts = []
    macd = p.get("macd", {})
    rsi = p.get("rsi14", 50)
    bb = p.get("bollinger", {})
    price = p.get("price", 0)
    ma5 = p.get("ma5", 0)

    if macd.get("histogram", 0) > 0:
        parts.append("MACD红柱")
    elif macd.get("histogram", 0) < 0:
        parts.append("MACD绿柱")

    if rsi < 35:
        parts.append("RSI超卖")
    elif rsi > 65:
        parts.append("RSI超买")
    elif 40 <= rsi <= 60:
        parts.append("RSI中性")

    if bb.get("percent_b", 50) < 20:
        parts.append("布林下轨")
    elif bb.get("percent_b", 50) > 80:
        parts.append("布林上轨")

    if price > ma5:
        parts.append("站上MA5")
    else:
        parts.append("跌破MA5")

    return " · ".join(parts)


def main():
    data = load_latest_plan()
    if not data:
        print("未找到 plan_v3_*.json")
        return

    os.makedirs("pages", exist_ok=True)
    html = generate(data)
    with open("pages/index.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("已生成 pages/index.html")


if __name__ == "__main__":
    main()
