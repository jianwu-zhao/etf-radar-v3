from collections import Counter
from datetime import datetime, timedelta, timezone

from journal.store import _connect
from notifications.telegram import send_message
from monitoring.logger import log


def send_weekly_digest() -> None:
    since = datetime.now(timezone.utc) - timedelta(days=7)
    since_iso = since.isoformat()

    try:
        with _connect() as conn:
            signal_rows = conn.execute(
                "SELECT symbol, direction FROM signals WHERE emitted_at >= ?",
                (since_iso,),
            ).fetchall()
            neutral_count = conn.execute(
                "SELECT COUNT(*) FROM neutral_signals WHERE emitted_at >= ?",
                (since_iso,),
            ).fetchone()[0]
            filtered_count = conn.execute(
                "SELECT COUNT(*) FROM filtered_signals WHERE emitted_at >= ?",
                (since_iso,),
            ).fetchone()[0]
    except Exception as e:
        log.error(f"Weekly digest query failed: {e}")
        return

    by_direction = Counter(r["direction"] for r in signal_rows)
    long_count = by_direction.get("long", 0)
    short_count = by_direction.get("short", 0)
    total = long_count + short_count + neutral_count + filtered_count

    if total == 0:
        send_message("*Weekly Digest*\n\nNo activity in the last 7 days.")
        log.info("Weekly digest sent: no activity")
        return

    by_symbol = Counter(r["symbol"] for r in signal_rows)

    lines = [
        "*Weekly Digest* — last 7 days",
        "",
        f"*Long signals:* {long_count}",
        f"*Short signals:* {short_count}",
        f"*Neutral:* {neutral_count}",
        f"*Pre-filtered:* {filtered_count}",
    ]

    if by_symbol:
        lines += ["", "*Actionable signals by ETF:*"]
        for sym, count in by_symbol.most_common():
            lines.append(f"  {sym}: {count}")

    send_message("\n".join(lines))
    log.info(
        f"Weekly digest sent: {long_count}L {short_count}S {neutral_count}N {filtered_count}F"
    )
