import pandas as pd
import pandas_ta as ta
import pytz

from data.market_data import get_bars
from config.trading_params import INTRADAY_LOOKBACK, TREND_LOOKBACK


def _compute_trend(df: pd.DataFrame) -> dict:
    if df.empty or len(df) < 26:
        return {}

    close = df["close"]
    ema21 = ta.ema(close, length=21)
    macd_df = ta.macd(close, fast=12, slow=26, signal=9)
    latest_close = close.iloc[-1]

    result = {
        "price_above_ema21": bool(latest_close > ema21.iloc[-1]) if ema21 is not None else None,
    }

    if macd_df is not None and not macd_df.empty:
        macd_line = macd_df["MACD_12_26_9"].iloc[-1]
        signal_line = macd_df["MACDs_12_26_9"].iloc[-1]
        histogram = macd_df["MACDh_12_26_9"].iloc[-1]
        prev_histogram = macd_df["MACDh_12_26_9"].iloc[-2]

        result.update({
            "macd_hist_expanding": bool(abs(histogram) > abs(prev_histogram)),
            "macd_bullish": bool(macd_line > signal_line),
        })

    return result


def _compute_momentum(df: pd.DataFrame) -> dict:
    if df.empty or len(df) < 15:
        return {}

    close = df["close"]
    rsi = ta.rsi(close, length=14)

    if rsi is None or rsi.empty:
        return {}

    return {"rsi": round(rsi.iloc[-1], 2)}


def _compute_volume(df: pd.DataFrame) -> dict:
    if df.empty or len(df) < 21:
        return {}

    close = df["close"]
    volume = df["volume"]
    obv = ta.obv(close, volume)

    vol_avg_20 = volume.rolling(20).mean().iloc[-1]
    vol_current = volume.iloc[-1]
    vol_ratio = round(vol_current / vol_avg_20, 2) if vol_avg_20 > 0 else None

    result = {
        "volume_ratio": vol_ratio,
    }

    if obv is not None and len(obv) >= 10:
        result["obv_rising"] = bool(obv.iloc[-1] > obv.iloc[-10])

    return result


def _compute_atr(df: pd.DataFrame, period: int = 14) -> float | None:
    if df.empty or len(df) < period + 1:
        return None
    atr = ta.atr(df["high"], df["low"], df["close"], length=period)
    if atr is None or atr.empty:
        return None
    return round(atr.iloc[-1], 4)


def get_full_snapshot(symbol: str) -> dict:
    df_4h = get_bars(symbol, timeframe="4h", limit=INTRADAY_LOOKBACK)
    df_1d = get_bars(symbol, timeframe="1d", limit=TREND_LOOKBACK)

    last_bar_time = None
    if not df_4h.empty:
        bar_open = df_4h.index[-1].astimezone(pytz.timezone("America/New_York"))
        bar_close = bar_open + pd.Timedelta(hours=4)
        last_bar_time = bar_close.strftime("%Y-%m-%d %H:%M ET")

    snapshot = {
        "symbol": symbol,
        "current_price": round(df_4h["close"].iloc[-1], 4) if not df_4h.empty else None,
        "last_bar_time": last_bar_time,
        "4h": {},
        "1d": {},
    }

    if not df_4h.empty:
        snapshot["4h"] = {
            **_compute_trend(df_4h),
            **_compute_momentum(df_4h),
            **_compute_volume(df_4h),
            "atr": _compute_atr(df_4h),
        }

    if not df_1d.empty:
        snapshot["1d"] = {
            **_compute_trend(df_1d),
            **_compute_momentum(df_1d),
            **_compute_volume(df_1d),
            "atr": _compute_atr(df_1d),
        }

    return snapshot
