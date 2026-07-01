# Setup Guide

Step-by-step instructions to get Freki running after forking the repository.

## Prerequisites

You need accounts on three services (plus FRED, which is optional). All have free tiers that are sufficient.

| Service | What Freki uses it for | Sign up |
|---|---|---|
| Alpaca | Market data (OHLCV candles) | https://alpaca.markets/ |
| Anthropic | Signal analysis via Claude | https://console.anthropic.com/ |
| Telegram | Trade signal delivery | https://telegram.org/ |
| FRED | Macro context for Claude (optional) | https://fred.stlouisfed.org/docs/api/api_key.html |

You also need **Python 3.11+** installed.

## 1. Clone and install

```bash
git clone <your-fork-url> && cd freki
python -m venv .venv
```

Activate the virtual environment:

```bash
# Linux / macOS
source .venv/bin/activate

# Windows
.venv\Scripts\activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

## 2. Get your API keys

### Alpaca

1. Create an account at [alpaca.markets](https://alpaca.markets/).
2. Go to the dashboard and generate a new **paper trading** API key pair.
3. Copy the **API Key** and **Secret Key**.

> Use paper trading keys while testing. Freki only reads market data (no orders), but paper keys keep your live account isolated.

### Anthropic

1. Create an account at [console.anthropic.com](https://console.anthropic.com/).
2. Go to **API Keys** and create a new key.
3. Copy the key (starts with `sk-ant-`).

### Telegram

1. Open Telegram and message [@BotFather](https://t.me/BotFather).
2. Send `/newbot`, follow the prompts, and copy the **bot token**.
3. Start a chat with your new bot (send it any message).
4. Get your **chat ID** by visiting `https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates` in a browser. Look for `"chat":{"id": 123456789}` in the JSON response.

### FRED (optional)

1. Register at [fred.stlouisfed.org](https://fred.stlouisfed.org/docs/api/api_key.html).
2. Generate a free API key.
3. Copy the key and add it to `.env` as `FRED_API_KEY`.

If omitted, Freki runs without macro context — Claude evaluates on technicals only.

## 3. Configure environment

```bash
cp .env.example .env
```

Open `.env` and fill in your keys:

```
ALPACA_API_KEY=PK...
ALPACA_SECRET_KEY=...
ANTHROPIC_API_KEY=sk-ant-...
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
```

The remaining variables have sensible defaults. See the full reference below if you want to customize them.

## 4. Run

```bash
python main.py
```

Freki will start the scheduler and print the scan times to the console. It runs in the foreground — press `Ctrl+C` to stop.

Logs go to `logs/freki_YYYY-MM-DD.log` (auto-rotated daily, kept for 30 days).

## 5. Verify

After the first scheduled scan fires, you should see:
- Console output showing each symbol being scanned.
- A Telegram message if a long or short signal is generated.
- A log file under `logs/`.

If nothing happens at the scheduled time, check that:
- Your system clock is correct (the scheduler uses `America/New_York`).
- The market is open (Alpaca returns no data on weekends and holidays).
- Your `.env` values are correct (a bad Alpaca key will log a warning per symbol).

## Configuration Reference

### Environment variables (`.env`)

| Variable | Required | Default | Description |
|---|---|---|---|
| `ALPACA_API_KEY` | yes | -- | Alpaca API key |
| `ALPACA_SECRET_KEY` | yes | -- | Alpaca secret key |
| `ANTHROPIC_API_KEY` | yes | -- | Anthropic API key |
| `ANTHROPIC_MODEL` | no | `claude-sonnet-4-6` | Claude model to use for analysis |
| `ANTHROPIC_TEMPERATURE` | no | `0.2` | Model temperature (0.0 - 1.0) |
| `FRED_API_KEY` | no | -- | FRED API key for macro context. Leave blank to disable. |
| `TELEGRAM_BOT_TOKEN` | yes | -- | Telegram bot token from BotFather |
| `TELEGRAM_CHAT_ID` | yes | -- | Your Telegram chat ID |
| `ETF_SYMBOLS` | no | `USO,BITO,SPY,QQQ,IWM,GLD` | Comma-separated list of symbols to scan |
| `TIMEZONE` | no | `America/New_York` | Timezone for scheduling |
| `LOG_LEVEL` | no | `INFO` | Logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |

### Trading parameters (`config/trading_params.py`)

These are constants in code, not environment variables. Edit the file directly to change them.

| Parameter | Default | Description |
|---|---|---|
| `INTRADAY_LOOKBACK` | `60` | Number of bars to fetch for the entry timeframe |
| `TREND_LOOKBACK` | `100` | Number of bars to fetch for the trend timeframe |
| `ATR_STOP_MULT` | `1.5` | Stop loss distance = ATR x this multiplier |
| `MIN_RISK_REWARD` | `2.5` | Take profit distance = stop distance x this multiplier |

**Per-symbol overrides** (`config/per_symbol_params.py`): Optional symbol-specific overrides for RSI zones and ATR multiplier. Values here take precedence over `trading_params.py` for the named symbol.

### Scan schedule (`main.py`)

The schedule is defined as a list of `(hour, minute)` tuples in `main.py`. To add more scan times:

```python
scan_times = [
    (10, 32),
    (11, 02),
    (12, 32),
    (14, 32),
    (15, 32),
]
```

Each entry creates an APScheduler cron job in Eastern Time.

### Watchlist

To change which ETFs are scanned, set `ETF_SYMBOLS` in your `.env`:

```
ETF_SYMBOLS=SPY,QQQ,TQQQ,SQQQ,GLD,SLV
```

Any symbol available on Alpaca will work.

## Running in Production

For long-running deployments, run Freki under a process manager:

```bash
# systemd (Linux)
# Create a unit file at /etc/systemd/system/freki.service

# PM2 (cross-platform)
pm2 start "python main.py" --name freki

# Screen / tmux
screen -S freki python main.py
```

Make sure the `.env` file is in the working directory where the process starts.
