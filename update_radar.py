#!/usr/bin/env python3
"""更新 ETF 雷达数据到 GitHub Pages"""
import json, os, re, urllib.request, http.client
from datetime import datetime

# 下载原雷达数据
URL = "https://jianwu-zhao.github.io/aggregator/radar.html"
try:
    with urllib.request.urlopen(URL, timeout=15) as f:
        raw = f.read().decode()
except:
    print("下载失败")
    exit(1)

# 解析
etfs = []
for tr in re.findall(r'<tr[^>]*>(.*?)</tr>', raw, re.DOTALL):
    name = re.search(r'class="an">([^<]+)<', tr)
    code = re.search(r'([0-9]{6})\s', tr)
    price = re.search(r'[-+]?[0-9]+\.[0-9]+', tr)
    # 提取所有 td 内容
    tds = re.findall(r'<td[^>]*>(.*?)</td>', tr, re.DOTALL)
    fields = []
    for td in tds:
        fields.append(re.sub(r'<[^>]+>', '', td).strip())
    if name:
        etfs.append({
            "name": name.group(1).strip(),
            "code": code.group(1) if code else "",
            "price": price.group(0) if price else "",
        })

# 去重
seen = set()
uniq = []
for e in etfs:
    if e["name"] not in seen:
        seen.add(e["name"])
        uniq.append(e)

now = datetime.now().strftime("%Y%m%d %H:%M")

# 生成 HTML
html = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ETF 波段雷达 V2</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif;background:#0f172a;color:#e2e8f0}
.wrap{max-width:1800px;margin:0 auto;padding:20px}
h1{font-size:22px;color:#fff;letter-spacing:.5px}
.sub{color:#cbd5e1;font-size:13px;line-height:1.8;margin-top:8px}
table{width:100%;border-collapse:collapse;margin-top:16px}
th{background:#1e293b;color:#94a3b8;font-size:11px;text-align:left;padding:10px 8px;border-bottom:1px solid #334155;white-space:nowrap}
td{padding:10px 8px;border-bottom:1px solid #1e293b;font-size:12px}
tr:hover{background:#1e293b}
.rank{color:#94a3b8;font-family:monospace;font-size:11px}
.an{font-weight:800;font-size:13px;color:#e2e8f0}
.ac{color:#64748b;font-family:monospace;font-size:10px;margin-top:3px}
</style>
</head>
<body>
<div class="wrap">
<h1>ETF 波段雷达 V2</h1>
<div class="sub">更新: {now} | 共 {len(uniq)} 个</div>
<table>
<thead>
<tr>
<th>#</th>
<th>标的</th>
<th>代码</th>
<th>价格</th>
</tr>
</thead>
<tbody>
"""
for i, e in enumerate(uniq):
    html += f"<tr><td>{i+1}</td><td class='an'>{e['name']}</td><td class='ac'>{e['code']}</td><td>{e['price']}</td></tr>\n"
html += "</tbody></table></div></body></html>"

# 保存
with open("reports/radar_detail.html", "w") as f:
    f.write(html)
print(f"已更新 {len(uniq)} 个")

# 推送
import notify
notify.send("E:\\t\\f\\雷达", html[:200])
print("已推送")
