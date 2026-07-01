_MACRO_LABELS = (
    ("fed_funds_rate", "Fed Funds Rate (effective)", "%"),
    ("fed_funds_target_upper", "Fed Funds Target (upper)", "%"),
    ("fed_funds_target_lower", "Fed Funds Target (lower)", "%"),
    ("ten_year_yield", "10Y Treasury Yield", "%"),
    ("real_10y", "Real 10Y Yield (TIPS)", "%"),
    ("yield_curve", "2Y-10Y Spread", "%"),
    ("cpi_yoy", "CPI YoY", "%"),
    ("core_cpi_yoy", "Core CPI YoY", "%"),
    ("unemployment_rate", "Unemployment", "%"),
    ("hy_spread", "HY Credit Spread", "bps"),
)

_LIVE_LABELS = (
    ("vix", "VIX", ""),
    ("skew", "SKEW", ""),
)


def format_macro_summary(macro: dict | None, live: dict | None = None) -> str:
    sections = []

    if macro:
        lines = ["Macro (FRED, daily):"]
        for key, label, suffix in _MACRO_LABELS:
            v = macro.get(key)
            lines.append(f"  {label}: {v:.2f}{suffix}" if v is not None else f"  {label}: N/A")
        sections.append("\n".join(lines))

    if live:
        lines = ["Market (live):"]
        for key, label, suffix in _LIVE_LABELS:
            v = live.get(key)
            lines.append(f"  {label}: {v:.2f}{suffix}" if v is not None else f"  {label}: N/A")
        sections.append("\n".join(lines))

    return "\n\n".join(sections)


def format_snapshot_summary(snapshot: dict) -> str:
    lines = []
    price = snapshot.get("current_price")
    if price:
        lines.append(f"Price: ${price:.2f}")

    for tf_key in ("4h", "1d"):
        tf = snapshot.get(tf_key, {})
        if not tf:
            continue
        label = tf_key.upper()

        macd_bullish = tf.get("macd_bullish")
        macd_dir = "bullish" if macd_bullish is True else ("bearish" if macd_bullish is False else "N/A")

        macd_expanding = tf.get("macd_hist_expanding")
        hist = "expanding" if macd_expanding is True else ("contracting" if macd_expanding is False else "N/A")

        above_ema = tf.get("price_above_ema21")
        ema = "above" if above_ema is True else ("below" if above_ema is False else "N/A")

        rsi = tf.get("rsi")
        rsi_str = f"{rsi}" if rsi is not None else "N/A"

        atr = tf.get("atr")
        atr_str = f"${atr}" if atr is not None else "N/A"

        obv_rising = tf.get("obv_rising")
        obv = "rising" if obv_rising is True else ("falling" if obv_rising is False else "N/A")

        vol_ratio = tf.get("volume_ratio")
        vol_str = f"{vol_ratio}x" if vol_ratio is not None else "N/A"

        lines.append(
            f"{label}: MACD {macd_dir} ({hist}) | {ema} EMA21 | "
            f"RSI {rsi_str} | ATR {atr_str} | Vol {vol_str} | OBV {obv}"
        )

    return "\n".join(lines)
