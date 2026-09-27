"""Все настройки и секреты берутся из переменных окружения (Railway → Variables)."""
import base64
import json
import os
from dataclasses import dataclass, field


def _env(name: str, default: str | None = None, required: bool = False) -> str:
    value = os.getenv(name, default)
    if required and not value:
        raise RuntimeError(f"Не задана переменная окружения {name}")
    return value or ""


def _parse_service_account(raw: str) -> dict | None:
    """GOOGLE_SERVICE_ACCOUNT_JSON: либо сам JSON, либо он же в base64."""
    raw = raw.strip()
    if not raw:
        return None
    if not raw.startswith("{"):
        raw = base64.b64decode(raw).decode("utf-8")
    return json.loads(raw)


@dataclass
class Config:
    telegram_token: str
    openai_api_key: str
    openai_model: str
    openai_max_tokens: int
    openai_temperature: float
    memory_window: int
    google_service_account: dict | None
    spreadsheet_id: str
    sheet_gid: int
    admin_ids: set[int] = field(default_factory=set)
    promo_channel_id: int = 0
    followup_delay: int = 10
    broadcast_delay: float = 0.05


def load_config() -> Config:
    admin_ids = {
        int(x) for x in _env("ADMIN_IDS").replace(";", ",").split(",") if x.strip()
    }
    return Config(
        telegram_token=_env("TELEGRAM_BOT_TOKEN", required=True),
        openai_api_key=_env("OPENAI_API_KEY", required=True),
        openai_model=_env("OPENAI_MODEL", "gpt-4o-mini"),
        openai_max_tokens=int(_env("OPENAI_MAX_TOKENS", "200")),
        openai_temperature=float(_env("OPENAI_TEMPERATURE", "0.7")),
        memory_window=int(_env("MEMORY_WINDOW", "5")),
        google_service_account=_parse_service_account(_env("GOOGLE_SERVICE_ACCOUNT_JSON")),
        spreadsheet_id=_env("SPREADSHEET_ID", "16GFYOAe74YSPDDMLGPxvKjFS0d6heVbvs7VgUs_-Tnw"),
        sheet_gid=int(_env("SHEET_GID", "0")),
        admin_ids=admin_ids,
        promo_channel_id=int(_env("PROMO_CHANNEL_ID", "-1001407379425")),
        followup_delay=int(_env("FOLLOWUP_DELAY", "10")),
        broadcast_delay=float(_env("BROADCAST_DELAY", "0.05")),
    )
