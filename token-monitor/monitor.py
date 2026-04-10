import httpx
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


async def check_token_status(
    api_key: str,
    api_url: str = "https://api.anthropic.com",
    model: str = "claude-sonnet-4-6",
) -> dict:
    """Make a minimal API call to retrieve rate-limit headers."""
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    payload = {
        "model": model,
        "max_tokens": 1,
        "messages": [{"role": "user", "content": "hi"}],
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{api_url}/v1/messages",
            headers=headers,
            json=payload,
            timeout=30.0,
        )

    h = response.headers

    def safe_int(key: str) -> int:
        val = h.get(key, "0")
        try:
            return int(val)
        except (ValueError, TypeError):
            return 0

    tokens_limit = safe_int("anthropic-ratelimit-tokens-limit")
    tokens_remaining = safe_int("anthropic-ratelimit-tokens-remaining")
    input_limit = safe_int("anthropic-ratelimit-input-tokens-limit")
    input_remaining = safe_int("anthropic-ratelimit-input-tokens-remaining")
    output_limit = safe_int("anthropic-ratelimit-output-tokens-limit")
    output_remaining = safe_int("anthropic-ratelimit-output-tokens-remaining")
    requests_limit = safe_int("anthropic-ratelimit-requests-limit")
    requests_remaining = safe_int("anthropic-ratelimit-requests-remaining")

    def pct(remaining: int, limit: int) -> float:
        if limit == 0:
            return 0.0
        return round(remaining / limit * 100, 1)

    result = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status_code": response.status_code,
        "ok": response.status_code == 200,
        # Tokens (total)
        "tokens_limit": tokens_limit,
        "tokens_remaining": tokens_remaining,
        "tokens_used": tokens_limit - tokens_remaining,
        "tokens_pct": pct(tokens_remaining, tokens_limit),
        "tokens_reset": h.get("anthropic-ratelimit-tokens-reset", ""),
        # Input tokens
        "input_tokens_limit": input_limit,
        "input_tokens_remaining": input_remaining,
        "input_tokens_used": input_limit - input_remaining,
        "input_tokens_pct": pct(input_remaining, input_limit),
        "input_tokens_reset": h.get("anthropic-ratelimit-input-tokens-reset", ""),
        # Output tokens
        "output_tokens_limit": output_limit,
        "output_tokens_remaining": output_remaining,
        "output_tokens_used": output_limit - output_remaining,
        "output_tokens_pct": pct(output_remaining, output_limit),
        "output_tokens_reset": h.get("anthropic-ratelimit-output-tokens-reset", ""),
        # Requests
        "requests_limit": requests_limit,
        "requests_remaining": requests_remaining,
        "requests_used": requests_limit - requests_remaining,
        "requests_pct": pct(requests_remaining, requests_limit),
        "requests_reset": h.get("anthropic-ratelimit-requests-reset", ""),
    }

    logger.info(
        "Token check: tokens=%d/%d (%.1f%%), requests=%d/%d",
        tokens_remaining,
        tokens_limit,
        result["tokens_pct"],
        requests_remaining,
        requests_limit,
    )
    return result
