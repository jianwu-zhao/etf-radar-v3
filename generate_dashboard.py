#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成 ETF 雷达 V3 网页看板
从最新 plan_v3_*.json 生成 index.html
"""
import os
import json
import glob
import datetime


def load_latest_plan():
    files = sorted(glob.glob("reports/plan_v3_*.json"), reverse=True)
    if not files:
        return None
    with open(files[0], encoding="utf-8") as f:
        return json.load(f)


def html_escape(s):
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def generate(data):
    date = data.get("date", "")
    market = data.get("market_regime", "未知")
    target = data.get("target_position", 0)
    positions = data.get("positions", [])
    total = data.get("etf_total", 0)
    cash = data.get("cash", 0)
    scanned = data.get("all_scanned", 0)

    rows = []
    for p in positions:
        rows.append(f"""
        <tr>
            <td><b>{html_escape(p.get('name',''))}</b><br><small>{p.get('code','')}</small></td>
            <td><span class="badge {'buy' if p.get('action') == '可买' else 'watch' if p.get('action') == '超卖观察' else 'confirm'}">{p.get('action','')}</span></td>
            <td>{p.get('score',0):.1f}</td>
            <td>{p.get('rsi14',0):.1f}</td>
            <td>{p.get('weight',0)*100:.1f}%</td>
            <td>{p.get('price',0):.3f}</td>
            <td>{p.get('stop',0):.3f}</td>
            <td>{p.get('take_profit',0):.3f}</td>
        </tr>
        """)

    rows_html = "".join(rows) if rows else "<tr><td colspan='8'>暂无入选</td></tr>"

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>ETF 波段雷达 V3</title>
    <style>
        :root {{ --bg: #0f172a; --card: #1e293b; --text: #e2e8f0; --muted: #94a3b8; --accent: #38bdf8; --up: #22c55e; --down: #ef4444; }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Microsoft YaHei", sans-serif; background: var(--bg); color: var(--text); padding: 20px; line-height: 1.6; }}
        .container {{ max-width: 900px; margin: 0 auto; }}
        h1 {{ text-align: center; margin-bottom: 8px; }}
        .sub {{ text-align: center; color: var(--muted); margin-bottom: 24px; }}
        .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 12px; margin-bottom: 24px; }}
        .card {{ background: var(--card); border-radius: 12px; padding: 16px; text-align: center; }}
        .card .label {{ color: var(--muted); font-size: 12px; }}
        .card .value {{ font-size: 22px; font-weight: bold; margin-top: 4px; }}
        table {{ width: 100%; border-collapse: collapse; background: var(--card); border-radius: 12px; overflow: hidden; }}
        th, td {{ padding: 12px; text-align: center; border-bottom: 1px solid #334155; }}
        th {{ background: #0f172a; color: var(--accent); font-weight: 600; }}
        tr:hover {{ background: #334155; }}
        .badge {{ display: inline-block; padding: 4px 10px; border-radius: 20px; font-size: 12px; font-weight: 600; }}
        .buy {{ background: #22c55e33; color: #4ade80; }}
        .watch {{ background: #f59e0b33; color: #fbbf24; }}
        .confirm {{ background: #38bdf833; color: #38bdf8; }}
        .footer {{ text-align: center; color: var(--muted); margin-top: 24px; font-size: 12px; }}
        .rules {{ background: var(--card); border-radius: 12px; padding: 16px; margin-top: 24px; }}
        .rules h3 {{ margin-bottom: 12px; color: var(--accent); }}
        .rules li {{ margin: 6px 0; color: var(--muted); }}
    </style>
</head>
<body>
    <div class="container">
        <h1>📡 ETF 波段雷达 V3</h1>
        <div class="sub">数据更新：{date} · 数据源：东方财富 API</div>

        <div class="grid">
            <div class="card">
                <div class="label">大盘状态</div>
                <div class="value">{market}</div>
            </div>
            <div class="card">
                <div class="label">目标仓位</div>
                <div class="value">{target*100:.0f}%</div>
            </div>
            <div class="card">
                <div class="label">ETF 仓位</div>
                <div class="value">{total*100:.1f}%</div>
            </div>
            <div class="card">
                <div class="label">现金</div>
                <div class="value">{cash*100:.1f}%</div>
            </div>
            <div class="card">
                <div class="label">扫描标的</div>
                <div class="value">{scanned}</div>
            </div>
        </div>

        <table>
            <thead>
                <tr>
                    <th>ETF</th>
                    <th>动作</th>
                    <th>评分</th>
                    <th>RSI14</th>
                    <th>仓位</th>
                    <th>现价</th>
                    <th>止损</th>
                    <th>止盈</th>
                </tr>
            </thead>
            <tbody>
                {rows_html}
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
            Generated at {datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
        </div>
    </div>
</body>
</html>
"""
    return html


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
