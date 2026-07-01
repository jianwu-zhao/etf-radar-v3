#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ETF 雷达 V3.1 策略参数
根据市场状态动态调整
"""

# 市场状态判断参数
MARKET_PARAMS = {
    "强多": {
        "target_pos": 0.95,
        "rsi_buy_max": 65,      # 牛市允许追强势
        "rsi_overbought": 80,
        "momentum_pref": "strong",  # 偏好强动量
        "trend_weight": 0.30,   # 趋势因子权重
        "reversal_weight": 0.10,
        "score_threshold": 45,
    },
    "偏多": {
        "target_pos": 0.80,
        "rsi_buy_max": 55,
        "rsi_overbought": 75,
        "momentum_pref": "balanced",
        "trend_weight": 0.25,
        "reversal_weight": 0.15,
        "score_threshold": 45,
    },
    "中性": {
        "target_pos": 0.50,
        "rsi_buy_max": 50,
        "rsi_overbought": 70,
        "momentum_pref": "reversal",
        "trend_weight": 0.20,
        "reversal_weight": 0.20,
        "score_threshold": 50,
    },
    "偏空": {
        "target_pos": 0.30,
        "rsi_buy_max": 45,
        "rsi_overbought": 65,
        "momentum_pref": "reversal",
        "trend_weight": 0.15,
        "reversal_weight": 0.25,
        "score_threshold": 55,
    },
    "强空": {
        "target_pos": 0.10,
        "rsi_buy_max": 40,
        "rsi_overbought": 60,
        "momentum_pref": "reversal",
        "trend_weight": 0.10,
        "reversal_weight": 0.30,
        "score_threshold": 60,
    },
}

# 静态权重（在动态基础上微调）
BASE_WEIGHTS = {
    "trend": 0.25,        # MA 排列
    "momentum": 0.20,     # 20/60日动量
    "reversal": 0.15,     # RSI 超卖
    "lowvol": 0.10,       # 低波动
    "structure": 0.15,    # 布林带/均值回归
    "macd": 0.10,         # MACD
    "mean_reversion": 0.05,  # 偏离MA60
}

SINGLE_MAX = 0.20
SINGLE_MIN = 0.05
TOP_N = 6
