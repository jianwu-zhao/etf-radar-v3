#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
推送模块: 把每日交易计划通过 127.0.0.1:2080 代理发到 Telegram。

配置: ~/etf-radar/notify.json
  {
    "tg_bot_token": "123:abc",
    "tg_chat_id": "123456"
  }
"""

import os
import json
import urllib.parse
import http.client

HOME = os.path.expanduser("~")
CONF = os.path.join(HOME, "etf-radar", "notify.json")
PROXY = ("127.0.0.1", 2080)


def _load_config():
    cfg = {"tg_bot_token": "", "tg_chat_id": ""}
    if os.path.exists(CONF):
        try:
            with open(CONF, encoding="utf-8") as f:
                data = json.load(f)
            for k in cfg:
                if data.get(k):
                    cfg[k] = data[k]
        except Exception:
            pass
    return cfg


def send(title, content):
    cfg = _load_config()
    token, cid = cfg.get("tg_bot_token", ""), cfg.get("tg_chat_id", "")
    if not token or not cid:
        print("Telegram 未配置 -> 跳过")
        return []

    text = f"*{title}*\n```\n{content}\n```"
    body = urllib.parse.urlencode({
        "chat_id": cid,
        "text": text,
        "parse_mode": "Markdown",
    }).encode()

    try:
        conn = http.client.HTTPSConnection(*PROXY, timeout=20)
        conn.set_tunnel("api.telegram.org", 443)
        conn.request("POST", f"/bot{token}/sendMessage",
                      body=body,
                      headers={
                          "Host": "api.telegram.org",
                          "User-Agent": "Mozilla/5.0",
                          "Content-Type": "application/x-www-form-urlencoded",
                          "Connection": "close",
                      })
        r = conn.getresponse()
        resp = r.read().decode("utf-8", "replace")
        data = json.loads(resp)
        if data.get("ok"):
            print(f"已推送: {title}")
            return ["telegram"]
        else:
            print(f"推送失败: {data}")
            return []
    except Exception as e:
        print(f"推送异常: {e}")
        return []
    finally:
        conn.close()


if __name__ == "__main__":
    import sys
    t = sys.argv[1] if len(sys.argv) > 1 else "ETF雷达"
    c = sys.argv[2] if len(sys.argv) > 2 else "测试"
    send(t, c)