import json

import requests

from config.settings import settings
from monitoring.logger import log

TELEGRAM_API = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"


def send_message(text: str) -> None:
    try:
        resp = requests.post(
            TELEGRAM_API,
            json={
                "chat_id": settings.telegram_chat_id,
                "text": text,
                "parse_mode": "Markdown",
            },
            timeout=10,
        )
        if not resp.ok:
            log.warning(f"Telegram send failed: {resp.status_code} {resp.text}")
    except Exception as e:
        log.error(f"Telegram error: {e}")


def send_signal(payload: dict) -> None:
    direction = payload["direction"].upper()
    symbol = payload["symbol"]
    price = payload["entry_price"]
    stop = payload.get("stop")
    target = payload.get("target")

    if direction in ("LONG", "SHORT") and stop is not None and target is not None:
        header = (
            f"*{direction} {symbol}* AT ${price:.2f} | SL ${stop:.2f} | TP ${target:.2f}"
        )
    else:
        header = f"*{direction} {symbol}* AT ${price:.2f}"

    body = json.dumps(payload, indent=2, default=str)
    send_message(f"{header}\n\n```json\n{body}\n```")
