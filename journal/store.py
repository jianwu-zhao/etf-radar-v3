import json
import os
import sqlite3
from datetime import datetime, timezone

from config.settings import settings
from monitoring.logger import log

DB_PATH = os.path.join("journal", "signals.sqlite")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    emitted_at TEXT NOT NULL,
    symbol TEXT NOT NULL,
    direction TEXT NOT NULL,
    entry_price REAL NOT NULL,
    bar_time TEXT,
    stop REAL NOT NULL,
    target REAL NOT NULL,
    reasoning TEXT,
    model TEXT,
    atr REAL,
    rsi_4h REAL,
    rsi_1d REAL,
    macd_4h_bullish INTEGER,
    ema_4h_above INTEGER,
    ema_1d_above INTEGER,
    vol_ratio_4h REAL,
    obv_4h_rising INTEGER,
    macro_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_signals_emitted_at ON signals(emitted_at);
CREATE INDEX IF NOT EXISTS idx_signals_symbol ON signals(symbol);

CREATE TABLE IF NOT EXISTS filtered_signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    emitted_at TEXT NOT NULL,
    symbol TEXT NOT NULL,
    filter_reason TEXT NOT NULL,
    entry_price REAL,
    bar_time TEXT,
    atr REAL,
    rsi_4h REAL,
    rsi_1d REAL,
    macd_4h_bullish INTEGER,
    ema_4h_above INTEGER,
    ema_1d_above INTEGER,
    vol_ratio_4h REAL,
    obv_4h_rising INTEGER,
    macro_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_filtered_emitted_at ON filtered_signals(emitted_at);
CREATE INDEX IF NOT EXISTS idx_filtered_symbol ON filtered_signals(symbol);

CREATE TABLE IF NOT EXISTS neutral_signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    emitted_at TEXT NOT NULL,
    symbol TEXT NOT NULL,
    entry_price REAL NOT NULL,
    bar_time TEXT,
    reasoning TEXT,
    model TEXT,
    atr REAL,
    rsi_4h REAL,
    rsi_1d REAL,
    macd_4h_bullish INTEGER,
    ema_4h_above INTEGER,
    ema_1d_above INTEGER,
    vol_ratio_4h REAL,
    obv_4h_rising INTEGER,
    macro_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_neutral_emitted_at ON neutral_signals(emitted_at);
CREATE INDEX IF NOT EXISTS idx_neutral_symbol ON neutral_signals(symbol);
"""


def _connect() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_schema() -> None:
    with _connect() as conn:
        conn.executescript(_SCHEMA)


_ensure_schema()


def _to_int_bool(v) -> int | None:
    if v is None:
        return None
    return 1 if v else 0


def build_signal_payload(
    symbol: str,
    direction: str,
    entry_price: float,
    bar_time: str | None,
    stop: float | None,
    target: float | None,
    reasoning: str,
    snapshot: dict,
    macro: dict | None,
) -> dict:
    tf_4h = snapshot.get("4h", {}) or {}
    tf_1d = snapshot.get("1d", {}) or {}
    return {
        "emitted_at": datetime.now(timezone.utc).isoformat(),
        "symbol": symbol,
        "direction": direction,
        "entry_price": entry_price,
        "bar_time": bar_time,
        "stop": stop,
        "target": target,
        "reasoning": reasoning,
        "model": settings.anthropic_model,
        "atr": tf_4h.get("atr"),
        "rsi_4h": tf_4h.get("rsi"),
        "rsi_1d": tf_1d.get("rsi"),
        "macd_4h_bullish": tf_4h.get("macd_bullish"),
        "ema_4h_above": tf_4h.get("price_above_ema21"),
        "ema_1d_above": tf_1d.get("price_above_ema21"),
        "vol_ratio_4h": tf_4h.get("volume_ratio"),
        "obv_4h_rising": tf_4h.get("obv_rising"),
        "macro": macro or {},
    }


def record_signal(payload: dict) -> None:
    row = (
        payload["emitted_at"],
        payload["symbol"],
        payload["direction"],
        payload["entry_price"],
        payload["bar_time"],
        payload["stop"],
        payload["target"],
        payload["reasoning"],
        payload["model"],
        payload["atr"],
        payload["rsi_4h"],
        payload["rsi_1d"],
        _to_int_bool(payload["macd_4h_bullish"]),
        _to_int_bool(payload["ema_4h_above"]),
        _to_int_bool(payload["ema_1d_above"]),
        payload["vol_ratio_4h"],
        _to_int_bool(payload["obv_4h_rising"]),
        json.dumps(payload["macro"]) if payload["macro"] else None,
    )

    try:
        with _connect() as conn:
            conn.execute(
                """
                INSERT INTO signals (
                    emitted_at, symbol, direction, entry_price, bar_time,
                    stop, target, reasoning, model,
                    atr, rsi_4h, rsi_1d, macd_4h_bullish, ema_4h_above,
                    ema_1d_above, vol_ratio_4h, obv_4h_rising, macro_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                row,
            )
    except sqlite3.Error as e:
        log.error(f"Journal write failed for {payload['symbol']}: {e}")


def record_filtered(
    symbol: str,
    filter_reason: str,
    snapshot: dict,
    macro: dict | None,
) -> None:
    tf_4h = snapshot.get("4h", {}) or {}
    tf_1d = snapshot.get("1d", {}) or {}
    row = (
        datetime.now(timezone.utc).isoformat(),
        symbol,
        filter_reason,
        snapshot.get("current_price"),
        snapshot.get("last_bar_time"),
        tf_4h.get("atr"),
        tf_4h.get("rsi"),
        tf_1d.get("rsi"),
        _to_int_bool(tf_4h.get("macd_bullish")),
        _to_int_bool(tf_4h.get("price_above_ema21")),
        _to_int_bool(tf_1d.get("price_above_ema21")),
        tf_4h.get("volume_ratio"),
        _to_int_bool(tf_4h.get("obv_rising")),
        json.dumps(macro) if macro else None,
    )
    try:
        with _connect() as conn:
            conn.execute(
                """
                INSERT INTO filtered_signals (
                    emitted_at, symbol, filter_reason, entry_price, bar_time,
                    atr, rsi_4h, rsi_1d, macd_4h_bullish, ema_4h_above,
                    ema_1d_above, vol_ratio_4h, obv_4h_rising, macro_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                row,
            )
    except sqlite3.Error as e:
        log.error(f"Filtered journal write failed for {symbol}: {e}")


def record_neutral(payload: dict) -> None:
    row = (
        payload["emitted_at"],
        payload["symbol"],
        payload["entry_price"],
        payload["bar_time"],
        payload["reasoning"],
        payload["model"],
        payload["atr"],
        payload["rsi_4h"],
        payload["rsi_1d"],
        _to_int_bool(payload["macd_4h_bullish"]),
        _to_int_bool(payload["ema_4h_above"]),
        _to_int_bool(payload["ema_1d_above"]),
        payload["vol_ratio_4h"],
        _to_int_bool(payload["obv_4h_rising"]),
        json.dumps(payload["macro"]) if payload["macro"] else None,
    )
    try:
        with _connect() as conn:
            conn.execute(
                """
                INSERT INTO neutral_signals (
                    emitted_at, symbol, entry_price, bar_time, reasoning, model,
                    atr, rsi_4h, rsi_1d, macd_4h_bullish, ema_4h_above,
                    ema_1d_above, vol_ratio_4h, obv_4h_rising, macro_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                row,
            )
    except sqlite3.Error as e:
        log.error(f"Neutral journal write failed for {payload['symbol']}: {e}")
