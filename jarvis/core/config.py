"""Настройки Джарвиса из файла .env."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)


def _bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "yes", "да")


# Чей мозг: openai (GPT) или claude
AI_PROVIDER = os.getenv("AI_PROVIDER", "openai").strip().lower()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1")
MODEL = os.getenv("JARVIS_MODEL", "claude-opus-5")
EFFORT = os.getenv("JARVIS_EFFORT", "low")

WAKE_WORDS = [w.strip().lower() for w in os.getenv("WAKE_WORDS", "джарвис,jarvis").split(",") if w.strip()]
TTS_VOICE = os.getenv("TTS_VOICE", "ru-RU-DmitryNeural")
USER_NAME = os.getenv("USER_NAME", "сэр")
CITY = os.getenv("CITY", "Москва")

EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS", "")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD", "")
IMAP_HOST = os.getenv("IMAP_HOST", "")
SMTP_HOST = os.getenv("SMTP_HOST", "")

CONFIRM_DANGEROUS = _bool("CONFIRM_DANGEROUS", True)
DASHBOARD_PORT = int(os.getenv("DASHBOARD_PORT", "5050"))
