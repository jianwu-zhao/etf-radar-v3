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


def generate(data, equity_data=None):
    version = data.get("version", "V3.1")
    date = data.get("date", "")
    market = data.get("market_regime", "未知")
    target = data.get("target_position", 0)
    positions = data.get("positions", [])
    total = data.get("etf_total", 0)
    cash = data.get("cash", 0)
    scanned = data.get("all_scanned", 0)

    # 图表数据
    if equity_data:
        equity_json = json.dumps({
            "dates": equity_data.get("dates_curve", []),
            "equity_curve": equity_data.get("equity_curve", []),
            "benchmark_curve": equity_data.get("benchmark_curve", []),
        }, ensure_ascii=False)
    else:
        equity_json = '{"dates":[],"equity_curve":[],"benchmark_curve":[]}'

    # 行业轮动数据
    sec_scores = sector_scores(data.get("positions", []), CORE_SECTOR_MAP)
    sorted_sec = sorted(sec_scores.items(), key=lambda x: x[1]['score'], reverse=True)
    sector_json = json.dumps({
        "labels": [s[0] for s in sorted_sec],
        "scores": [round(s[1]['score'], 1) for s in sorted_sec],
    }, ensure_ascii=False)

    # 从 positions 提取行业信息
    sec_names = {}
    for p in positions:
        sec = p.get("sector", "") or p.get("industry", "")
        if sec:
            sec_names[p.get("code","")] = sec

    # 生成选中池表格
    selected_rows = []
    for i, p in enumerate(positions, 1):
        bb = p.get("bollinger", {})
        macd = p.get("macd", {})
        ma60_dist = (p.get("price", 0) / p.get("ma60", 1) - 1) * 100 if p.get("ma60") else 0
        sec = p.get("sector", "") or p.get("industry", "") or ""
        intra_15m = p.get("intraday_signal", "") or p.get("signal_15m", "")
        if intra_15m == "unknown":
            intra_15m = ""
        selected_rows.append(f"""
        <tr>
            <td>{i}</td>
            <td class="name"><b>{html_escape(p.get('name',''))}</b><br><small>{p.get('code','')}</small></td>
            <td class="name"><small>{html_escape(sec)}</small></td>
            <td><span class="badge {action_class(p.get('action',''))}">{p.get('action','')}</span></td>
            <td class="sig">{html_escape(intra_15m)}</td>
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

    selected_html = "".join(selected_rows) if selected_rows else "<tr><td colspan='15'>暂无入选</td></tr>"

    # 使用指南
    guide = fr"""
    <details class="guide">
        <summary>📖 如何使用本页面（点击展开）</summary>
        <div class="guide-content">
            <div class="guide-section">
                <h4>🎯 核心用法</h4>
                <p>每天看 <b>操作建议</b> 列，按以下规则执行：</p>
                <table class="guide-table">
                    <tr><th>信号</th><th>含义</th><th>操作</th></tr>
                    <tr><td><span class="badge buy">可买</span></td><td>评分达标，可以买入</td><td>次日开盘涨幅 ≤ 1.5% 直接建仓</td></tr>
                    <tr><td><span class="badge confirm">确认买</span></td><td>条件强于可买，等待确认</td><td>突破昨高或站上 MA5 才买</td></tr>
                    <tr><td><span class="badge watch">超卖观察</span></td><td>已经跌多了，可能反弹</td><td>每跌 2% 加一次，分批建仓</td></tr>
                    <tr><td><span class="badge wait">等待</span></td><td>评分不够</td><td>不动，等下次入选</td></tr>
                </table>
            </div>
            <div class="guide-section">
                <h4>📊 各列解读</h4>
                <ul>
                    <li><b>序</b>：排名序号</li>
                    <li><b>标的</b>：ETF 名称 + 代码</li>
                    <li><b>行业</b>：所属行业（顶部行业轮动条显示最强行业）</li>
                    <li><b>操作建议</b>：<span class="badge buy">可买</span>/<span class="badge confirm">确认买</span>/<span class="badge watch">超卖观察</span>/<span class="badge wait">等待</span></li>
                    <li><b>15m</b>：15 分钟级别信号（buy_pullback/buy_breakout/overbought/neutral），辅助判断是否今天追</li>
                    <li><b>V4评分</b>：S(≥60)/A(50-59)/B(40-49)/C(<40)，S 最强</li>
                    <li><b>MACD柱</b>：+红柱上涨动能，-绿柱下跌动能</li>
                    <li><b>均值回归</b>：当前价偏离 MA60 的百分比</li>
                    <li><b>价格结构</b>：布林带 %B 位置，<20 下轨，>80 上轨</li>
                    <li><b>RSI/风控</b>：RSI14 + ATR14 波动率</li>
                    <li><b>月/周/日线</b>：对应周期涨跌幅</li>
                    <li><b>买点参考</b>：<span style="color:var(--down)">回踩价</span>（止损）和 <span style="color:var(--up)">止盈价</span>，仓位占比</li>
                </ul>
            </div>
            <div class="guide-section">
                <h4>⚠️ 风控规则</h4>
                <ul>
                    <li>单只 ETF 仓位上限 20%</li>
                    <li>止损：收盘价 ≤ 止损价 → 次日清仓</li>
                    <li>止盈：≥ 止盈价卖 50%，剩余保本移动止盈</li>
                    <li>大盘强多 → 95% 仓位；中性 → 50%；强空 → 10%</li>
                    <li>本工具仅做策略信号计算，<b>不构成投资建议，不自动下单</b></li>
                </ul>
            </div>
            <div class="guide-section">
                <h4>🔄 自动运行</h4>
                <ul>
                    <li>GitHub Actions 每天 15:30（北京时间）自动跑一次</li>
                    <li>页面自动更新</li>
                    <li>配置 Telegram bot 可收到每日推送</li>
                </ul>
            </div>
        </div>
    </details>
    """

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>ETF 波段雷达 {html_escape(version)}</title>
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
        .guide {{ background: var(--card); border-radius: 10px; margin-bottom: 20px; overflow: hidden; font-size: 13px; }}
        .guide summary {{ padding: 14px; cursor: pointer; color: var(--accent); font-weight: 600; font-size: 15px; }}
        .guide-content {{ padding: 0 14px 14px; }}
        .guide-section {{ margin-bottom: 14px; }}
        .guide-section h4 {{ color: var(--accent); margin-bottom: 6px; font-size: 13px; }}
        .guide-section p, .guide-section li {{ color: var(--muted); line-height: 1.7; font-size: 12px; }}
        .guide-section ul {{ padding-left: 18px; }}
        .guide-table {{ width: 100%; border-collapse: collapse; margin: 8px 0; font-size: 12px; }}
        .guide-table th {{ background: #0f172a; color: var(--accent); padding: 6px 8px; text-align: left; font-size: 12px; }}
        .guide-table td {{ padding: 6px 8px; border-bottom: 1px solid #334155; text-align: left; color: var(--muted); }}
        .guide-table tr:hover {{ background: #334155; }}
        .chart-row {{ display: flex; gap: 16px; margin-bottom: 16px; flex-wrap: wrap; }}
        .chart-box {{ background: var(--card); border-radius: 10px; padding: 14px; flex: 1; min-width: 300px; }}
        .chart-box h3 {{ color: var(--accent); font-size: 14px; margin-bottom: 10px; }}
        .chart-box canvas {{ width: 100% !important; max-height: 280px; }}
        .rules {{ background: var(--card); border-radius: 10px; padding: 14px; margin-top: 20px; font-size: 12px; }}
        .rules h3 {{ margin-bottom: 10px; color: var(--accent); }}
        .rules li {{ margin: 5px 0; color: var(--muted); }}
        @media (max-width: 768px) {{
            body {{ padding: 8px; font-size: 12px; }}
            th, td {{ padding: 6px 3px; }}
            td.sig, td.plan {{ font-size: 10px; }}
        }}
    </style>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.7/dist/chart.umd.min.js"></script>
</head>
<body>
    <div class="container">
        <h1>📡 ETF 波段雷达 {html_escape(version)}</h1>
        <div class="sub">更新：{date}　大盘：{market}　建议仓位：{target*100:.0f}%　扫描：{scanned}只</div>

        {guide}

        <div class="grid">
            <div class="card"><div class="label">目标仓位</div><div class="value">{target*100:.0f}%</div></div>
            <div class="card"><div class="label">ETF 仓位</div><div class="value">{total*100:.1f}%</div></div>
            <div class="card"><div class="label">现金</div><div class="value">{cash*100:.1f}%</div></div>
            <div class="card"><div class="label">入选标的</div><div class="value">{len(positions)}</div></div>
        </div>

        <div class="chart-row">
            <div class="chart-box">
                <h3>📈 策略净值 vs 沪深300</h3>
                <canvas id="equityChart"></canvas>
            </div>
            <div class="chart-box">
                <h3>📉 最大回撤</h3>
                <canvas id="drawdownChart"></canvas>
            </div>
        </div>
        <div class="chart-row">
            <div class="chart-box">
                <h3>🏭 行业轮动热度</h3>
                <canvas id="sectorChart"></canvas>
            </div>
        </div>

        <table>
            <thead>
                <tr>
                    <th>序</th>
                    <th>标的</th>
                    <th>行业</th>
                    <th>操作建议</th>
                    <th>15m</th>
                    <th>拐点信号</th>
                    <th>V4评分</th>
                    <th>MACD柱</th>
                    <th>均值回归</th>
                    <th>价格结构</th>
                    <th>RSI风控</th>
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

<script>
const COLORS = {{
    up: '#ef4444', down: '#22c55e', accent: '#38bdf8', muted: '#94a3b8',
    card: '#1e293b', bg: '#0f172a',
}};

// 回测净值数据
const equityData = {equity_json};
const dates = equityData.dates || [];
const strategy = equityData.equity_curve || [];
const benchmark = equityData.benchmark_curve || [];

// 1. 净值曲线
if (dates.length > 0 && document.getElementById('equityChart')) {{
    new Chart(document.getElementById('equityChart'), {{
        type: 'line',
        data: {{
            labels: dates,
            datasets: [{{
                label: '策略净值',
                data: strategy,
                borderColor: COLORS.accent,
                backgroundColor: 'rgba(56,189,248,0.1)',
                fill: true,
                tension: 0.3,
                pointRadius: 0,
            }}, {{
                label: '沪深300',
                data: benchmark,
                borderColor: COLORS.muted,
                backgroundColor: 'rgba(148,163,184,0.1)',
                fill: true,
                tension: 0.3,
                pointRadius: 0,
                borderDash: [5, 5],
            }}]
        }},
        options: {{
            responsive: true,
            maintainAspectRatio: false,
            plugins: {{ legend: {{ labels: {{ color: COLORS.muted }} }} }},
            scales: {{
                x: {{ ticks: {{ color: COLORS.muted, maxTicksLimit: 8 }}, grid: {{ color: 'rgba(148,163,184,0.1)' }} }},
                y: {{ ticks: {{ color: COLORS.muted }}, grid: {{ color: 'rgba(148,163,184,0.1)' }} }}
            }}
        }}
    }});
}}

// 2. 回撤图
if (dates.length > 0 && document.getElementById('drawdownChart')) {{
    const eq = strategy;
    let peak = eq[0];
    const dd = eq.map(v => {{
        peak = Math.max(peak, v);
        return peak > 0 ? (v - peak) / peak * 100 : 0;
    }});
    new Chart(document.getElementById('drawdownChart'), {{
        type: 'line',
        data: {{
            labels: dates,
            datasets: [{{
                label: '回撤 %',
                data: dd,
                borderColor: COLORS.up,
                backgroundColor: 'rgba(239,68,68,0.2)',
                fill: true,
                tension: 0.3,
                pointRadius: 0,
            }}]
        }},
        options: {{
            responsive: true,
            maintainAspectRatio: false,
            plugins: {{ legend: {{ labels: {{ color: COLORS.muted }} }} }},
            scales: {{
                x: {{ ticks: {{ color: COLORS.muted, maxTicksLimit: 8 }}, grid: {{ color: 'rgba(148,163,184,0.1)' }} }},
                y: {{ ticks: {{ color: COLORS.muted, callback: v => v + '%' }}, grid: {{ color: 'rgba(148,163,184,0.1)' }} }}
            }}
        }}
    }});
}}

// 3. 行业轮动热度
if (document.getElementById('sectorChart')) {{
    const sectors = {sector_json};
    if (sectors.labels && sectors.labels.length > 0) {{
        new Chart(document.getElementById('sectorChart'), {{
            type: 'bar',
            data: {{
                labels: sectors.labels,
                datasets: [{{
                    label: '行业评分',
                    data: sectors.scores,
                    backgroundColor: sectors.scores.map(s => s > 50 ? 'rgba(56,189,248,0.7)' : 'rgba(148,163,184,0.5)'),
                    borderColor: sectors.scores.map(s => s > 50 ? '#38bdf8' : '#94a3b8'),
                    borderWidth: 1,
                }}]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                indexAxis: 'y',
                plugins: {{ legend: {{ display: false }} }},
                scales: {{
                    x: {{ ticks: {{ color: COLORS.muted }}, grid: {{ color: 'rgba(148,163,184,0.1)' }} }},
                    y: {{ ticks: {{ color: COLORS.muted }}, grid: {{ display: false }} }}
                }}
            }}
        }});
    }}
}}
</script>
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
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", default=None, help="指定 plan json 文件")
    ap.add_argument("--output", default="pages/index.html", help="输出 html")
    ap.add_argument("--equity", default=None, help="回测净值数据 json 文件")
    args = ap.parse_args()

    if args.plan:
        with open(args.plan, "r", encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = load_latest_plan()
    if not data:
        print("未找到 plan json")
        return

    # 加载回测净值数据
    equity_data = None
    if args.equity:
        try:
            with open(args.equity, "r", encoding="utf-8") as f:
                equity_data = json.load(f)
        except:
            pass
    else:
        # 自动找最新的 backtest 结果
        import glob
        bt_files = sorted(glob.glob("reports/backtest_v3_2_result.json"), reverse=True)
        if bt_files:
            try:
                with open(bt_files[0], "r", encoding="utf-8") as f:
                    equity_data = json.load(f)
            except:
                pass

    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    html = generate(data, equity_data)
    with open(args.output, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"已生成 {args.output}")


if __name__ == "__main__":
    main()
