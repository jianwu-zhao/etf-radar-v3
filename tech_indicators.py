#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
技术指标计算（纯 Python，不依赖 pandas-ta）
"""
import math


def sma(values, period):
    """简单移动平均"""
    if len(values) < period:
        return []
    return [sum(values[i:i+period]) / period for i in range(len(values) - period + 1)]


def ema(values, period):
    """指数移动平均"""
    if len(values) < period:
        return []
    k = 2 / (period + 1)
    ema_vals = [sum(values[:period]) / period]
    for v in values[period:]:
        ema_vals.append(v * k + ema_vals[-1] * (1 - k))
    return ema_vals


def rsi(closes, period=14):
    """RSI 相对强弱指数"""
    if len(closes) < period + 1:
        return []
    gains, losses = [], []
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i-1]
        gains.append(max(diff, 0))
        losses.append(abs(min(diff, 0)))
    
    rsis = []
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        if avg_loss == 0:
            rsis.append(100)
        else:
            rs = avg_gain / avg_loss
            rsis.append(round(100 - (100 / (1 + rs)), 2))
    return rsis


def macd(closes, fast=12, slow=26, signal=9):
    """MACD 指标"""
    ema_fast = ema(closes, fast)
    ema_slow = ema(closes, slow)
    # 对齐长度
    diff_line = [f - s for f, s in zip(ema_fast[-len(ema_slow):], ema_slow)]
    signal_line = ema(diff_line, signal)
    histogram = [d - s for d, s in zip(diff_line[-len(signal_line):], signal_line)]
    return {
        "macd": round(diff_line[-1], 4) if diff_line else None,
        "signal": round(signal_line[-1], 4) if signal_line else None,
        "histogram": round(histogram[-1], 4) if histogram else None,
    }


def bollinger(closes, period=20, std_mult=2):
    """布林带"""
    if len(closes) < period:
        return {}
    ma_vals = sma(closes, period)
    ma = ma_vals[-1]
    recent = closes[-period:]
    std = math.sqrt(sum((x - ma) ** 2 for x in recent) / period)
    return {
        "middle": round(ma, 3),
        "upper": round(ma + std_mult * std, 3),
        "lower": round(ma - std_mult * std, 3),
        "width": round(2 * std_mult * std, 3),
        "percent_b": round((closes[-1] - (ma - std_mult * std)) / (2 * std_mult * std) * 100, 2) if std > 0 else 50,
    }


def atr(highs, lows, closes, period=14):
    """真实波动幅度 ATR"""
    if len(closes) < period + 1:
        return None
    trs = []
    for i in range(1, len(closes)):
        tr1 = highs[i] - lows[i]
        tr2 = abs(highs[i] - closes[i-1])
        tr3 = abs(lows[i] - closes[i-1])
        trs.append(max(tr1, tr2, tr3))
    return round(sum(trs[-period:]) / period, 3)


def analyze(klines):
    """综合分析：从 K 线计算所有指标"""
    closes = [k["close"] for k in klines]
    highs = [k["high"] for k in klines]
    lows = [k["low"] for k in klines]
    
    if len(closes) < 60:
        return {"error": "数据不足"}
    
    ma5 = sma(closes, 5)[-1]
    ma10 = sma(closes, 10)[-1]
    ma20 = sma(closes, 20)[-1]
    ma60 = sma(closes, 60)[-1]
    
    rsi14 = rsi(closes, 14)
    rsi6 = rsi(closes, 6)
    
    macd_vals = macd(closes)
    boll = bollinger(closes)
    atr14 = atr(highs, lows, closes)
    
    # 近期收益
    daily_ret = [(closes[i] - closes[i-1]) / closes[i-1] * 100 for i in range(1, len(closes))]
    momentum_20 = (closes[-1] - closes[-21]) / closes[-21] * 100 if len(closes) >= 21 else None
    momentum_60 = (closes[-1] - closes[-61]) / closes[-61] * 100 if len(closes) >= 61 else None
    
    return {
        "price": closes[-1],
        "ma5": round(ma5, 3),
        "ma10": round(ma10, 3),
        "ma20": round(ma20, 3),
        "ma60": round(ma60, 3),
        "rsi14": rsi14[-1] if rsi14 else None,
        "rsi6": rsi6[-1] if rsi6 else None,
        "macd": macd_vals,
        "bollinger": boll,
        "atr14": atr14,
        "momentum_20": round(momentum_20, 2) if momentum_20 else None,
        "momentum_60": round(momentum_60, 2) if momentum_60 else None,
        "volatility_20": round(sum(abs(x) for x in daily_ret[-20:]) / 20, 2) if len(daily_ret) >= 20 else None,
    }


def intraday_signal(k15):
    """15分钟级别择时信号"""
    if len(k15) < 20:
        return {"signal": "unknown", "rsi14": None, "macd_hist": 0}
    closes = [k["close"] for k in k15]
    from tech_indicators import rsi, macd
    rsi14 = rsi(closes, 14)
    macd_vals = macd(closes, 12, 26, 9)
    recent_low = min(k["low"] for k in k15[-20:])
    recent_high = max(k["high"] for k in k15[-20:])
    price = closes[-1]
    
    signal = "neutral"
    if rsi14[-1] < 40 and macd_vals.get("histogram", 0) > -0.01 and price < recent_low * 1.01:
        signal = "buy_pullback"
    elif macd_vals.get("histogram", 0) > 0 and rsi14[-1] < 65 and price > recent_high * 0.99:
        signal = "buy_breakout"
    elif rsi14[-1] > 75:
        signal = "overbought"
    
    return {
        "signal": signal,
        "rsi14": rsi14[-1] if rsi14 else None,
        "macd_hist": macd_vals.get("histogram", 0),
        "recent_low": recent_low,
        "recent_high": recent_high,
    }


if __name__ == "__main__":
    from data_source import daily_kline
    import pprint
    k = daily_kline("515210")
    r = analyze(k)
    pprint.pprint(r)
