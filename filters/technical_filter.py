from config.per_symbol_params import get_params


def check_technical_filters(snapshot: dict) -> tuple[bool, str]:
    params = get_params(snapshot.get("symbol", ""))
    if _is_long_eligible(snapshot, params):
        return True, "long-eligible"
    if _is_short_eligible(snapshot, params):
        return True, "short-eligible"
    return False, "no trend+momentum alignment"


def _is_long_eligible(snapshot: dict, params: dict) -> bool:
    tf_4h = snapshot.get("4h", {})
    tf_1d = snapshot.get("1d", {})

    ema_4h = tf_4h.get("price_above_ema21")
    ema_1d = tf_1d.get("price_above_ema21")
    rsi_4h = tf_4h.get("rsi")
    macd_4h = tf_4h.get("macd_bullish")

    if None in (ema_4h, ema_1d, rsi_4h, macd_4h):
        return False

    return (
        ema_4h is True
        and ema_1d is True
        and params["rsi_bull_min"] <= rsi_4h <= params["rsi_bull_max"]
        and macd_4h is True
    )


def _is_short_eligible(snapshot: dict, params: dict) -> bool:
    tf_4h = snapshot.get("4h", {})
    tf_1d = snapshot.get("1d", {})

    ema_4h = tf_4h.get("price_above_ema21")
    ema_1d = tf_1d.get("price_above_ema21")
    rsi_4h = tf_4h.get("rsi")
    macd_4h = tf_4h.get("macd_bullish")

    if None in (ema_4h, ema_1d, rsi_4h, macd_4h):
        return False

    return (
        ema_4h is False
        and ema_1d is False
        and params["rsi_bear_min"] <= rsi_4h <= params["rsi_bear_max"]
        and macd_4h is False
    )
