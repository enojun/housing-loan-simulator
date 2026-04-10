import json
import os
from pathlib import Path

CONFIG_FILE = Path(__file__).parent / "config.json"

DEFAULTS = {
    "anthropic_api_key": "",
    "anthropic_api_url": "https://api.anthropic.com",
    "check_model": "claude-sonnet-4-6",
    "slack_webhook_url": "",
    "check_interval_minutes": 60,
    "alert_threshold": 20,
    "port": 3000,
    "host": "0.0.0.0",
    "max_history": 168,
}

# Keys that are integers
_INT_KEYS = {"check_interval_minutes", "alert_threshold", "port", "max_history"}

# Mapping from config key → env var name
_ENV_MAP = {
    "anthropic_api_key": "ANTHROPIC_API_KEY",
    "anthropic_api_url": "ANTHROPIC_API_URL",
    "check_model": "CHECK_MODEL",
    "slack_webhook_url": "SLACK_WEBHOOK_URL",
    "check_interval_minutes": "CHECK_INTERVAL_MINUTES",
    "alert_threshold": "ALERT_THRESHOLD",
    "port": "PORT",
    "host": "HOST",
    "max_history": "MAX_HISTORY",
}

# Keys that should never be returned in full via API
SECRET_KEYS = {"anthropic_api_key", "slack_webhook_url"}


def _load_json() -> dict:
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save_json(data: dict) -> None:
    with open(CONFIG_FILE, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def load_config() -> dict:
    """Load config with priority: JSON file > env vars > defaults."""
    cfg = dict(DEFAULTS)

    # Override with env vars
    for key, env_name in _ENV_MAP.items():
        val = os.getenv(env_name)
        if val:
            cfg[key] = int(val) if key in _INT_KEYS else val

    # Override with JSON file (highest priority)
    saved = _load_json()
    for key, val in saved.items():
        if key in DEFAULTS and val not in (None, ""):
            cfg[key] = int(val) if key in _INT_KEYS else val

    return cfg


def save_config(updates: dict) -> dict:
    """Save config updates to JSON file. Returns the full config."""
    current = _load_json()
    for key, val in updates.items():
        if key in DEFAULTS:
            current[key] = int(val) if key in _INT_KEYS else val
    _save_json(current)
    return load_config()


def mask_secret(value: str) -> str:
    """Mask a secret value for display."""
    if not value:
        return ""
    if len(value) <= 8:
        return "****"
    return value[:4] + "****" + value[-4:]


def config_for_api(cfg: dict) -> dict:
    """Return config safe for API responses (secrets masked)."""
    result = {}
    for key, val in cfg.items():
        if key in SECRET_KEYS:
            result[key] = mask_secret(str(val))
            result[f"{key}_set"] = bool(val)
        else:
            result[key] = val
    return result
