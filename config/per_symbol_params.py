from config.trading_params import (
    ATR_STOP_MULT,
    MIN_RISK_REWARD,
    RSI_BEAR_MAX,
    RSI_BEAR_MIN,
    RSI_BULL_MAX,
    RSI_BULL_MIN,
)

DEFAULTS: dict = {
    "rsi_bull_min": RSI_BULL_MIN,
    "rsi_bull_max": RSI_BULL_MAX,
    "rsi_bear_min": RSI_BEAR_MIN,
    "rsi_bear_max": RSI_BEAR_MAX,
    "atr_stop_mult": ATR_STOP_MULT,
    "min_risk_reward": MIN_RISK_REWARD,
}

OVERRIDES: dict[str, dict] = {
    # "BITO": {"rsi_bull_max": 75, "atr_stop_mult": 2.0},
}


def get_params(symbol: str) -> dict:
    return {**DEFAULTS, **OVERRIDES.get(symbol, {})}
