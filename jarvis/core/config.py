"""Настройки Джарвиса из файла .env."""
import os
from pathlib import Path

from dotenv import load_dotenv

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")  # без рекламной строки pygame в окне

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)


def _bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "yes", "да")


# Чей мозг: openai (GPT), claude (Claude API) или claude_code (Claude Code на этом ПК, по подписке)
AI_PROVIDER = os.getenv("AI_PROVIDER", "openai").strip().lower()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1")
MODEL = os.getenv("JARVIS_MODEL", "claude-opus-5")
# Для claude_code: пусто = модель по умолчанию из подписки; sonnet/haiku — быстрее
CLAUDE_CODE_MODEL = os.getenv("CLAUDE_CODE_MODEL", "").strip()
EFFORT = os.getenv("JARVIS_EFFORT", "low")

WAKE_WORDS = [w.strip().lower() for w in os.getenv("WAKE_WORDS", "джарвис,jarvis").split(",") if w.strip()]
TTS_VOICE = os.getenv("TTS_VOICE", "ru-RU-DmitryNeural")
# Запасной голос Windows, если основной недоступен (на многих ПК он только женский — Irina)
OFFLINE_VOICE = _bool("OFFLINE_VOICE", True)
USER_NAME = os.getenv("USER_NAME", "Сабина")
if USER_NAME.strip().lower() in ("", "сэр"):  # старое значение из первых версий
    USER_NAME = "Сабина"
GREETING = os.getenv("GREETING", "Моё почтение, {user}. Я к вашим услугам.")
INTRO_ANIMATION = _bool("INTRO_ANIMATION", True)  # анимация появления на всех мониторах
MORNING_BRIEF = _bool("MORNING_BRIEF", True)      # короткая сводка дня после приветствия
CITY = os.getenv("CITY", "Москва")

EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS", "")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD", "")
IMAP_HOST = os.getenv("IMAP_HOST", "")
SMTP_HOST = os.getenv("SMTP_HOST", "")

# Notion (интеграция: https://www.notion.so/profile/integrations)
NOTION_TOKEN = os.getenv("NOTION_TOKEN", "").strip()
NOTION_TASKS_DB = os.getenv("NOTION_TASKS_DB", "35e4ea9860c980be88d3f6d67aa0a4df").strip()  # «Сводка задач»
NOTION_HUB_PAGE = os.getenv("NOTION_HUB_PAGE", "3e84ea9860c981a7a7c5deaf8aafd8f8").strip()  # «J.A.R.V.I.S. — общий штаб»

# GitHub (токен: https://github.com/settings/tokens)
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "").strip()
PROJECTS_DIR = os.getenv("PROJECTS_DIR", str(Path.home() / "Projects"))
EDITOR = os.getenv("EDITOR", "cursor").strip().lower()  # редактор по умолчанию: cursor или vscode
WORKSPACE_URLS = os.getenv("WORKSPACE_URLS", "https://railway.com/dashboard,https://github.com,"
                           "https://www.notion.so,https://claude.ai/code")

CONFIRM_DANGEROUS = _bool("CONFIRM_DANGEROUS", True)
DASHBOARD_PORT = int(os.getenv("DASHBOARD_PORT", "5050"))
