#!/usr/bin/env python3
"""向TG推送ETF雷达的详细数据"""
import json, os, re, sys
from datetime import datetime

HOME = os.path.expanduser("~")
BASE = os.path.join(HOME, "etf-radar")
CONF = os.path.join(BASE, "notify.json")
REPORT_DIR = os.path.join(BASE, "reports")
os.makedirs(REPORT_DIR, exist_ok=True)

# 下载雷达 HTML
import urllib.request
URL = "https://jianwu-zhao.github.io/aggregator/radar.html"
try:
    with urllib.request.urlopen(URL, timeout=15) as f:
        html = f.read().decode("utf-8")
except:
    print("下载失败")
    sys.exit(1)

# 提取所有 ETF 行
rows = re.findall(r'<tr[^>]*>(.*?)</tr>', html, re.DOTALL)

# 解析每行
etf_data = []
for row in rows:
    tds = re.findall(r'<td[^>]*>(.*?)</td>', row, re.DOTALL)
    if len(tds) < 5: continue
    # 提取名称
    name = ""
    name_m = re.search(r'<div class="an">([^<]+)</div>', tds[1] if len(tds)>1 else "")
    if name_m: name = name_m.group(1)
    code = ""
    code_m = re.search(r'([0-9]{3,6})', str(tds[1:2]))
    if code_m: code = code_m.group(1)
    etf_data.append({"name": name, "code": code, "html_row": row[:200]})

# 去重
seen = set()
unique = []
for e in etf_data:
    if e["name"] and e["name"] not in seen:
        seen.add(e["name"])
        unique.append(e)

print(f"共 {len(unique)} 个ETF")

# 构建消息
msg = f"📡 ETF 雷达V2 详细数据\n"
msg += f"更新: {datetime.now().strftime('%m%d %H:%M')}\n"
msg += f"来源: {URL}\n\n"
for e in unique[:10]:
    msg += f"• {e['name']} ({e['code']})\n"
msg += f"\n...共 {len(unique)} 个标的"

# 保存
with open(os.path.join(REPORT_DIR, "radar_detail.txt"), "w") as f:
    f.write(msg)
print("已保存")
print(msg[:500])
