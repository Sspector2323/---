"""Настройки Джарвиса из файла .env."""
import os
from pathlib import Path

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")  # без рекламной строки pygame в окне

ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT / ".env"


def read_env_file(path: Path = ENV_FILE) -> dict:
    """Простое и терпимое чтение .env: BOM, пробелы вокруг «=», кавычки любого вида, «export» — всё прощаем."""
    values = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        key = key.strip().removeprefix("export ").strip()
        val = val.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
            val = val[1:-1]
        val = val.strip().strip("«»“”").strip()
        values[key] = val
    return values


# Значения из .env главнее одноимённых переменных Windows: иначе Джарвис молча игнорирует файл
_file_values = read_env_file()
SHADOWED = {k: os.environ[k] for k, v in _file_values.items() if k in os.environ and os.environ[k] != v}
os.environ.update({k: v for k, v in _file_values.items() if v != "" or k not in os.environ})

DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)


def _bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "yes", "да")


# Чей мозг: openai (GPT), claude (Claude API) или claude_code (Claude Code на этом ПК, по подписке)
AI_PROVIDER = os.getenv("AI_PROVIDER", "openai").strip().lower()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1")
# hybrid: разговор ведёт быстрая модель OpenAI, большие задачи — Claude Code (самый отзывчивый режим)
HYBRID_MODEL = os.getenv("HYBRID_MODEL", "gpt-4.1-mini")
MODEL = os.getenv("JARVIS_MODEL", "claude-opus-5")
# Для claude_code: пусто = модель по умолчанию из подписки; sonnet/haiku — быстрее
CLAUDE_CODE_MODEL = os.getenv("CLAUDE_CODE_MODEL", "").strip()
EFFORT = os.getenv("JARVIS_EFFORT", "low")

WAKE_WORDS = [w.strip().lower() for w in os.getenv("WAKE_WORDS", "джарвис,jarvis").split(",") if w.strip()]
TTS_VOICE = os.getenv("TTS_VOICE", "ru-RU-DmitryNeural")
# Какой голос пробовать первым: edge (бесплатный Microsoft) или openai (стабильный, нужен OPENAI_API_KEY)
# Голос ElevenLabs (ваш собственный, созданный там): ключ API и ID голоса
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "").strip()
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "").strip()
# eleven_flash_v2_5 — самый быстрый отклик; eleven_multilingual_v2 — чуть выразительнее, но медленнее
ELEVENLABS_MODEL = os.getenv("ELEVENLABS_MODEL", "eleven_flash_v2_5").strip()
# по умолчанию: ваш голос ElevenLabs, если настроен; иначе OpenAI; иначе бесплатный Microsoft
TTS_ENGINE = os.getenv("TTS_ENGINE", "elevenlabs" if ELEVENLABS_API_KEY and ELEVENLABS_VOICE_ID else
                       "openai" if os.getenv("OPENAI_API_KEY") else "edge").strip().lower()
OPENAI_VOICE = os.getenv("OPENAI_VOICE", "onyx").strip()  # onyx — самый низкий и бархатный
VOICE_SPEED = float(os.getenv("VOICE_SPEED", "1.12") or 1.12)   # 1.0 — обычный темп, 1.12 — чуть быстрее
VOICE_PITCH = os.getenv("VOICE_PITCH", "-12Hz").strip()         # для голоса Microsoft: ниже = глубже
# Стиль голоса: «дворецкий» (по умолчанию), «хриплый бас» или свой текст в VOICE_STYLE
VOICE_PRESETS = {
    "дворецкий": ("onyx", "-12Hz",
                  "Голос: низкий, глубокий, бархатный мужской баритон — тёплый, обволакивающий, уверенный. "
                  "Темп: чуть быстрее обычного, собранно, без затянутых пауз. "
                  "Манера: безупречный британский дворецкий — учтиво, с лёгкой иронией и теплом. Интонация живая и "
                  "выразительная: улыбка в голосе, акценты на главном, естественные паузы — никакой монотонности. "
                  "Говори по-русски."),
    "хриплый бас": ("onyx", "-18Hz",
                    "Голос: низкий мужской бас-баритон с хрипотцой и лёгкой песочной шероховатостью, как после долгой "
                    "дороги. Интонация: расслабленная, уверенная, чуть дерзкая, с усмешкой — по-свойски, но с уважением. "
                    "Темп: живой, чуть быстрее обычного, без пафоса. Говори по-русски."),
}
VOICE_PRESET = os.getenv("VOICE_PRESET", "дворецкий").strip().lower()
_preset = VOICE_PRESETS.get(VOICE_PRESET, VOICE_PRESETS["дворецкий"])
if not os.getenv("OPENAI_VOICE"):
    OPENAI_VOICE = _preset[0]
if not os.getenv("VOICE_PITCH"):
    VOICE_PITCH = _preset[1]
VOICE_STYLE = os.getenv("VOICE_STYLE", "").strip() or _preset[2]
# Перебивание: заговорили, пока Джарвис говорит, — он замолкает и слушает. Чувствительность: меньше — чутче
BARGE_IN = _bool("BARGE_IN", True)
BARGE_SENSITIVITY = float(os.getenv("BARGE_SENSITIVITY", "2.5") or 2.5)
# word — перебить можно только словом («Джарвис», «стоп», «хватит», «подожди»): эхо из колонок не обрывает его;
# any — любой громкий голос (удобно в наушниках)
BARGE_MODE = (os.getenv("BARGE_MODE", "word") or "word").strip().lower()
# Чувствительность микрофона: больше — слышит тише (1 — обычно, 1.5–2 — если приходится повышать голос)
MIC_SENSITIVITY = float(os.getenv("MIC_SENSITIVITY", "1.0") or 1.0)
# Распознавание речи: smart — команды точным ElevenLabs Scribe (если есть ключ ElevenLabs), фон — бесплатным Google;
# elevenlabs — всё через Scribe (точнее, но расходует минуты ElevenLabs); google — только Google
STT_ENGINE = (os.getenv("STT_ENGINE", "smart") or "smart").strip().lower()
STT_MODEL = os.getenv("STT_MODEL", "scribe_v1").strip() or "scribe_v1"
# Двойной хлопок будит Джарвиса без слова «Джарвис»
CLAP_WAKE = _bool("CLAP_WAKE", True)
# Звуки интерфейса: сигнал «слушаю», звон «готово», сигнал ошибки
SOUNDS = _bool("SOUNDS", True)
# Фразы, пока он думает: one — одна короткая и тишина; chatty — болтает каждые несколько секунд; off — молча
FILLERS = (os.getenv("FILLERS", "one") or "one").strip().lower()
# Браузер, которым управляет Джарвис: msedge (есть в каждой Windows) или chrome. Профиль — свой, data/browser_profile
BROWSER_CHANNEL = (os.getenv("BROWSER_CHANNEL", "msedge") or "msedge").strip().lower()
BROWSER_PATH = os.getenv("BROWSER_PATH", "").strip().strip('"')  # свой путь к msedge.exe/chrome.exe, если нужно
BROWSER_HEADLESS = _bool("BROWSER_HEADLESS", False)  # без окна — только для проверок
# Музыка: boot — заставка при запуске; all — ещё и тихий фон во время долгой задачи; off — без музыки
MUSIC = (os.getenv("MUSIC", "boot") or "boot").strip().lower()
# Горячие клавиши: «слушаю» и «замолчи» (пусто — выключено)
HOTKEY_TALK = os.getenv("HOTKEY_TALK", "ctrl+alt+j").strip().lower()
HOTKEY_STOP = os.getenv("HOTKEY_STOP", "ctrl+alt+x").strip().lower()
# Жесты перед камерой включаются сами при запуске (иначе — голосом: «Джарвис, включи жесты»)
GESTURES = _bool("GESTURES", False)
# Главный монитор: core — 3D-ядро Джарвиса (при трёх и более мониторах), dashboard — обычный дашборд
MAIN_SCREEN = (os.getenv("MAIN_SCREEN", "core") or "core").strip().lower()
# Голос: realtime — живой разговор через OpenAI Realtime (мгновенно, с интонацией, можно перебивать);
# classic — прежняя схема: распознавание → мозг → озвучка
VOICE_MODE = (os.getenv("VOICE_MODE", "realtime") or "realtime").strip().lower()
REALTIME_MODEL = os.getenv("REALTIME_MODEL", "gpt-realtime").strip() or "gpt-realtime"
REALTIME_VOICE = os.getenv("REALTIME_VOICE", "cedar").strip() or "cedar"   # cedar — низкий бархатный мужской
REALTIME_SPEED = float(os.getenv("REALTIME_SPEED", "1.0") or 1.0)
REALTIME_VAD = (os.getenv("REALTIME_VAD", "semantic") or "semantic").strip().lower()  # semantic — даёт договорить
REALTIME_EAGERNESS = (os.getenv("REALTIME_EAGERNESS", "medium") or "medium").strip().lower()
REALTIME_NOISE = (os.getenv("REALTIME_NOISE", "far_field") or "far_field").strip().lower()  # near_field — гарнитура
REALTIME_ECHO_GATE = _bool("REALTIME_ECHO_GATE", True)  # false — если вы в наушниках
REALTIME_IDLE = float(os.getenv("REALTIME_IDLE", "25") or 25)  # секунд тишины до «сна»
# Уведомления Windows: напоминания, готовые задачи, задачи из чатов
NOTIFICATIONS = _bool("NOTIFICATIONS", True)
# Плавающий Джарвис поверх всех окон (шар в углу экрана) и значок в трее
ORB = _bool("ORB", True)
TRAY = _bool("TRAY", True)
HOTKEY_PALETTE = os.getenv("HOTKEY_PALETTE", "ctrl+alt+space").strip().lower()
# Модель OpenAI, которая смотрит на экран и в камеру (инструмент look)
VISION_MODEL = os.getenv("VISION_MODEL", "gpt-4.1-mini").strip() or "gpt-4.1-mini"
# Сколько секунд тишины считать концом фразы (больше — можно делать паузы, не боясь, что Джарвис перебьёт)
PAUSE_SECONDS = float(os.getenv("PAUSE_SECONDS", "1.0") or 1.0)
# Запасной голос Windows, если основной недоступен (на многих ПК он только женский — Irina)
OFFLINE_VOICE = _bool("OFFLINE_VOICE", True)
USER_NAME = os.getenv("USER_NAME", "Сабина")
if USER_NAME.strip().lower() in ("", "сэр"):  # старое значение из первых версий
    USER_NAME = "Сабина"
GREETING = os.getenv("GREETING", "Моё почтение, {user}. Я к вашим услугам.")
INTRO_ANIMATION = _bool("INTRO_ANIMATION", True)
# Дашборд после запуска: all = на всех мониторах, main = только на главном, off = не открывать
DASHBOARD_SCREENS = os.getenv("DASHBOARD_SCREENS", "all").strip().lower()  # анимация появления на всех мониторах
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
# Куда Джарвис и Claude Code складывают готовые документы, PDF и прочие файлы
OUTPUT_DIR = os.getenv("OUTPUT_DIR", "").strip() or str(Path.home() / "Documents" / "Jarvis")
EDITOR = os.getenv("EDITOR", "cursor").strip().lower()  # редактор по умолчанию: cursor или vscode
WORKSPACE_URLS = os.getenv("WORKSPACE_URLS", "https://railway.com/dashboard,https://github.com,"
                           "https://www.notion.so,https://claude.ai/code")

# Телеграм-бот Джарвиса: токен от @BotFather; ID хозяйки запоминается сам при /start с кодом
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_OWNER_ID = os.getenv("TELEGRAM_OWNER_ID", "").strip()
TELEGRAM_BRIEF = _bool("TELEGRAM_BRIEF", True)  # присылать сводку дня в Телеграм при запуске

# Задачи из рабочих чатов Телеграма (вход в ВАШ аккаунт, только чтение): https://my.telegram.org → API
TG_API_ID = os.getenv("TG_API_ID", "").strip()
TG_API_HASH = os.getenv("TG_API_HASH", "").strip()
TG_SCAN_MINUTES = int(os.getenv("TG_SCAN_MINUTES", "30") or 30)
TG_DIGEST_TIME = os.getenv("TG_DIGEST_TIME", "10:00").strip()  # утренняя сводка задач из чатов; пусто — не нужна
TG_MODEL = os.getenv("TG_MODEL", "gpt-4.1-mini").strip()

CONFIRM_DANGEROUS = _bool("CONFIRM_DANGEROUS", True)
DASHBOARD_PORT = int(os.getenv("DASHBOARD_PORT", "5050"))
