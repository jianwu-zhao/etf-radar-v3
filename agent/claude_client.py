import json
import re

import anthropic
from anthropic import Anthropic
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from config.settings import settings
from monitoring.logger import log

_client = Anthropic(api_key=settings.anthropic_api_key)

_RETRYABLE = (anthropic.APIConnectionError, anthropic.APITimeoutError, anthropic.RateLimitError, anthropic.InternalServerError)

SIGNAL_SYSTEM_PROMPT = (
    "You are a disciplined ETF swing signal analyst. "
    "You receive raw technical indicator data for an ETF across two timeframes: 4h (entry timing) and 1d (trend). "
    "When macro context is provided, assess the macro regime — "
    "risk-on vs risk-off, rate environment, inflation trend, credit stress, and market fear — "
    "and factor it into your signal decision. "
    "FRED daily indicators: Fed Funds Rate, 10Y Treasury Yield, Real 10Y Yield, 2Y-10Y Spread, "
    "CPI YoY, Core CPI YoY, Unemployment, HY Credit Spread. "
    "Live market indicators: VIX (fear gauge), SKEW (tail-risk demand). "
    "Guidance: VIX >25 = elevated fear/risk-off; VIX >35 = extreme fear, avoid new longs; "
    "SKEW >140 = high demand for crash protection, treat as a warning even if VIX is low; "
    "HY spread >600bps = credit stress/avoid risk; "
    "inverted yield curve = late-cycle caution; real 10Y >2% = headwind for growth/duration ETFs; "
    "tightening cycles favor defensives, steepening curve favors cyclicals. "
    "Analyze all data independently and decide whether there is a clear swing trading opportunity. "
    "Be selective and conservative — only signal LONG or SHORT when there is genuine alignment "
    "across both timeframes and the macro regime is supportive. Most setups should be NEUTRAL. "
    "Respond in JSON with two fields: "
    "\"direction\": \"long\", \"short\", or \"neutral\", "
    "\"reasoning\": string (100 words max, always required regardless of direction)."
)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(min=2, max=10),
    retry=retry_if_exception_type(_RETRYABLE),
    reraise=True,
)
def evaluate_with_claude(
    symbol: str,
    snapshot_summary: str,
    macro_summary: str = "",
) -> tuple[str, str]:
    prompt = (
        f"ETF: {symbol}\n\n"
        f"Technical snapshot:\n{snapshot_summary}\n\n"
    )
    if macro_summary:
        prompt += f"{macro_summary}\n\n"
    prompt += "Analyze all data and give your signal."

    response = _client.messages.create(
        model=settings.anthropic_model,
        max_tokens=1024,
        system=[{"type": "text", "text": SIGNAL_SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": prompt}],
    )
    text = "".join(b.text for b in response.content if b.type == "text").strip()

    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError(f"No JSON object found in response: {text!r}")
    result = json.loads(match.group())
    direction = result.get("direction", "neutral").lower()
    reasoning = result.get("reasoning", "").strip()
    return direction, reasoning
