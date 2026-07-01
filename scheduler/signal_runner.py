from datetime import datetime

import pytz

from config.settings import settings
from config.symbols import ETF_SYMBOLS
from config.per_symbol_params import get_params
from indicators.composite import get_full_snapshot
from signals.formatter import format_snapshot_summary, format_macro_summary
from agent.claude_client import evaluate_with_claude
from filters.registry import run_symbol_filters
from journal.store import build_signal_payload, record_filtered, record_neutral, record_signal
from macro.fred_client import get_macro_snapshot
from macro.live_client import get_live_snapshot
from notifications.telegram import send_signal
from monitoring.logger import log

ET = pytz.timezone(settings.timezone)


def run_signal_scan():
    now = datetime.now(ET)
    log.info(f"{'='*50}")
    log.info(f"  Signal Scan | {len(ETF_SYMBOLS)} ETFs | {now.strftime('%Y-%m-%d %H:%M ET')}")
    log.info(f"{'='*50}")

    macro = get_macro_snapshot()
    live = get_live_snapshot()
    macro_summary = format_macro_summary(macro, live)
    if macro:
        log.info(f"  Macro context loaded: {len(macro)} FRED indicators")
    else:
        log.info("  Macro context: unavailable (proceeding without)")
    if live:
        log.info(f"  Live market: VIX={live.get('vix')} SKEW={live.get('skew')}")
    else:
        log.info("  Live market data: unavailable (proceeding without)")

    for sym in ETF_SYMBOLS:
        snap = get_full_snapshot(sym)
        if not snap.get("current_price"):
            log.warning(f"  {sym}: no data, skipping")
            continue

        tech_ok, tech_reason = run_symbol_filters(snap)
        if not tech_ok:
            log.info(f"  {sym:6s} | FILTERED | {tech_reason}")
            record_filtered(sym, tech_reason, snap, {**(macro or {}), **(live or {})})
            continue

        params = get_params(sym)
        price = snap["current_price"]
        bar_time = snap.get("last_bar_time", "N/A")
        atr = snap.get("4h", {}).get("atr", 0)
        stop_dist = atr * params["atr_stop_mult"] if atr else price * 0.01

        summary = format_snapshot_summary(snap)
        try:
            direction, reasoning = evaluate_with_claude(sym, summary, macro_summary)
        except Exception as e:
            log.error(f"  {sym:6s} | ERROR   | Claude evaluation failed: {e}")
            continue

        if direction in ("long", "short"):
            if direction == "long":
                stop = round(price - stop_dist, 2)
                target = round(price + stop_dist * params["min_risk_reward"], 2)
            else:
                stop = round(price + stop_dist, 2)
                target = round(price - stop_dist * params["min_risk_reward"], 2)

            log.info(
                f"  {sym:6s} | {direction.upper():5s} | ${price:.2f} ({bar_time}) | SL ${stop:.2f} | TP ${target:.2f}"
            )
        else:
            stop = None
            target = None
            log.info(f"  {sym:6s} | NEUTRAL | ${price:.2f} ({bar_time})")

        payload = build_signal_payload(
            sym, direction, price, bar_time, stop, target, reasoning,
            snap, {**(macro or {}), **(live or {})},
        )
        send_signal(payload)
        if direction in ("long", "short"):
            record_signal(payload)
        else:
            record_neutral(payload)

    log.info(f"{'='*50}")
