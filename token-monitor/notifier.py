import httpx
import logging

logger = logging.getLogger(__name__)


def _build_adaptive_card(status: dict, threshold: int) -> dict:
    """Build an Adaptive Card payload for Teams Workflows webhook."""
    tokens_pct = status.get("tokens_pct", 0)
    tokens_remaining = status.get("tokens_remaining", 0)
    tokens_limit = status.get("tokens_limit", 0)
    tokens_reset = status.get("tokens_reset", "N/A")
    input_pct = status.get("input_tokens_pct", 0)
    output_pct = status.get("output_tokens_pct", 0)

    if tokens_pct <= threshold:
        color = "attention"
        title = f"⚠️ トークン残量警告 ({tokens_pct}%)"
    else:
        color = "good"
        title = f"✅ トークン残量レポート ({tokens_pct}%)"

    card = {
        "type": "message",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": {
                    "type": "AdaptiveCard",
                    "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                    "version": "1.4",
                    "body": [
                        {
                            "type": "TextBlock",
                            "text": title,
                            "weight": "bolder",
                            "size": "medium",
                            "color": color,
                        },
                        {
                            "type": "FactSet",
                            "facts": [
                                {
                                    "title": "トークン残量",
                                    "value": f"{tokens_remaining:,} / {tokens_limit:,} ({tokens_pct}%)",
                                },
                                {
                                    "title": "入力トークン残量",
                                    "value": f"{status.get('input_tokens_remaining', 0):,} / {status.get('input_tokens_limit', 0):,} ({input_pct}%)",
                                },
                                {
                                    "title": "出力トークン残量",
                                    "value": f"{status.get('output_tokens_remaining', 0):,} / {status.get('output_tokens_limit', 0):,} ({output_pct}%)",
                                },
                                {
                                    "title": "リセット日時",
                                    "value": tokens_reset,
                                },
                                {
                                    "title": "確認日時",
                                    "value": status.get("timestamp", ""),
                                },
                            ],
                        },
                    ],
                },
            }
        ],
    }
    return card


async def send_teams_notification(
    webhook_url: str, status: dict, threshold: int
) -> bool:
    """Send a notification to Teams via Incoming Webhook (Workflows)."""
    if not webhook_url:
        logger.warning("Teams webhook URL is not configured. Skipping notification.")
        return False

    payload = _build_adaptive_card(status, threshold)

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(webhook_url, json=payload, timeout=15.0)
        if resp.status_code in (200, 202):
            logger.info("Teams notification sent successfully.")
            return True
        else:
            logger.error(
                "Teams notification failed: status=%d body=%s",
                resp.status_code,
                resp.text[:200],
            )
            return False
    except Exception as e:
        logger.error("Teams notification error: %s", e)
        return False
