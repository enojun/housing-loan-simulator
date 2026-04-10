import os
from dataclasses import dataclass, field


@dataclass
class Config:
    # Anthropic API
    anthropic_api_key: str = field(
        default_factory=lambda: os.getenv("ANTHROPIC_API_KEY", "")
    )
    anthropic_api_url: str = field(
        default_factory=lambda: os.getenv(
            "ANTHROPIC_API_URL", "https://api.anthropic.com"
        )
    )
    # Model used for lightweight check calls
    check_model: str = field(
        default_factory=lambda: os.getenv("CHECK_MODEL", "claude-sonnet-4-6")
    )

    # Teams Webhook
    teams_webhook_url: str = field(
        default_factory=lambda: os.getenv("TEAMS_WEBHOOK_URL", "")
    )

    # Monitoring
    check_interval_minutes: int = field(
        default_factory=lambda: int(os.getenv("CHECK_INTERVAL_MINUTES", "60"))
    )
    alert_threshold: int = field(
        default_factory=lambda: int(os.getenv("ALERT_THRESHOLD", "20"))
    )

    # Server
    port: int = field(
        default_factory=lambda: int(os.getenv("PORT", "3000"))
    )
    host: str = field(
        default_factory=lambda: os.getenv("HOST", "0.0.0.0")
    )

    # History retention (max records kept in memory)
    max_history: int = field(
        default_factory=lambda: int(os.getenv("MAX_HISTORY", "168"))
    )


config = Config()
