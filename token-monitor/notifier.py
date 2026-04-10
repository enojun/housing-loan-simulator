import httpx
import logging

logger = logging.getLogger(__name__)


def _build_slack_blocks(status: dict, threshold: int) -> dict:
    """Build a Slack Block Kit payload for Incoming Webhook."""
    tokens_pct = status.get("tokens_pct", 0)
    tokens_remaining = status.get("tokens_remaining", 0)
    tokens_limit = status.get("tokens_limit", 0)
    tokens_reset = status.get("tokens_reset", "N/A")
    input_pct = status.get("input_tokens_pct", 0)
    output_pct = status.get("output_tokens_pct", 0)

    is_alert = tokens_pct <= threshold
    emoji = ":warning:" if is_alert else ":white_check_mark:"
    label = "トークン残量警告" if is_alert else "トークン残量レポート"
    title = f"{emoji} {label} ({tokens_pct}%)"

    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": title, "emoji": True},
        },
        {
            "type": "section",
            "fields": [
                {
                    "type": "mrkdwn",
                    "text": f"*トークン残量*\n{tokens_remaining:,} / {tokens_limit:,} ({tokens_pct}%)",
                },
                {
                    "type": "mrkdwn",
                    "text": f"*リセット日時*\n{tokens_reset}",
                },
                {
                    "type": "mrkdwn",
                    "text": f"*入力トークン*\n{status.get('input_tokens_remaining', 0):,} / {status.get('input_tokens_limit', 0):,} ({input_pct}%)",
                },
                {
                    "type": "mrkdwn",
                    "text": f"*出力トークン*\n{status.get('output_tokens_remaining', 0):,} / {status.get('output_tokens_limit', 0):,} ({output_pct}%)",
                },
            ],
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"確認日時: {status.get('timestamp', '')}",
                }
            ],
        },
    ]

    return {"blocks": blocks}


async def send_slack_notification(
    webhook_url: str, status: dict, threshold: int
) -> bool:
    """Send a notification to Slack via Incoming Webhook."""
    if not webhook_url:
        logger.warning("Slack webhook URL is not configured. Skipping notification.")
        return False

    payload = _build_slack_blocks(status, threshold)

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(webhook_url, json=payload, timeout=15.0)
        if resp.status_code == 200 and resp.text == "ok":
            logger.info("Slack notification sent successfully.")
            return True
        else:
            logger.error(
                "Slack notification failed: status=%d body=%s",
                resp.status_code,
                resp.text[:200],
            )
            return False
    except Exception as e:
        logger.error("Slack notification error: %s", e)
        return False
