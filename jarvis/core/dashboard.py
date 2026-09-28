"""Веб-дашборд Джарвиса: http://localhost:5050"""
import logging
import os
import platform
import secrets
import threading
import time
from datetime import datetime

from flask import Flask, jsonify, request

from . import config, storage
from .tools import tasks as t

WEB = __import__("pathlib").Path(__file__).parent / "web"
app = Flask(__name__)
logging.getLogger("werkzeug").setLevel(logging.ERROR)
import flask.cli  # noqa: E402
flask.cli.show_server_banner = lambda *a, **k: None  # без служебного текста Flask в окне Джарвиса

BRAIN = {"ask": None, "confirm": None, "say": None, "confirmer": None}
_ask_lock = threading.Lock()

# Секрет этого запуска: без него дашборд не примет изменения. Чужие сайты, открытые в том же
# браузере, прочитать его не могут — значит, и командовать Джарвисом через дашборд тоже.
TOKEN = secrets.token_urlsafe(24)


@app.before_request
def _check_token():
    # защита от подмены адреса (DNS rebinding): отвечаем только на localhost
    if request.host.split(":")[0] not in ("localhost", "127.0.0.1"):
        return "forbidden", 403
    if request.method not in ("GET", "HEAD", "OPTIONS") and request.headers.get("X-Jarvis-Token") != TOKEN:
        return jsonify(error="forbidden"), 403


def _page(name: str):
    html = (WEB / name).read_text(encoding="utf-8").replace("__TOKEN__", TOKEN)
    return html, 200, {"Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store"}


# ---------- Настройки (.env) ----------
ENV_PATH = config.ROOT / ".env"
# (ключ, подпись, тип, варианты/подсказка, группа)
SETTINGS = [
    ("AI_PROVIDER", "Чей мозг (hybrid — самый быстрый: разговор на OpenAI, большие задачи — Claude Code)", "select", ["hybrid", "claude_code", "openai", "claude"], "brain"),
    ("HYBRID_MODEL", "Быстрая модель для hybrid", "select", ["gpt-4.1-mini", "gpt-4.1", "gpt-4o-mini"], "brain"),
    ("OPENAI_API_KEY", "Ключ OpenAI", "secret", "sk-…", "brain"),
    ("OPENAI_MODEL", "Модель OpenAI (mini — быстрее)", "select", ["gpt-4.1-mini", "gpt-4.1", "gpt-4o-mini", "gpt-4o"], "brain"),
    ("CLAUDE_CODE_MODEL", "Модель Claude Code (пусто = по подписке; sonnet/haiku — быстрее)", "text", "sonnet", "brain"),
    ("CLAUDE_PATH", "Путь к Claude Code (если Джарвис его не находит)", "text", "C:\\Users\\вы\\.local\\bin\\claude.exe", "brain"),
    ("ANTHROPIC_API_KEY", "Ключ Claude API (только для режима claude)", "secret", "sk-ant-…", "brain"),
    ("NOTION_TOKEN", "Секрет интеграции Notion", "secret", "ntn_…", "notion"),
    ("NOTION_TASKS_DB", "База задач (id)", "text", "35e4ea9860c980be88d3f6d67aa0a4df", "notion"),
    ("NOTION_HUB_PAGE", "Страница «общий штаб» (id)", "text", "3e84ea9860c981a7a7c5deaf8aafd8f8", "notion"),
    ("GITHUB_TOKEN", "Токен GitHub", "secret", "github_pat_…", "github"),
    ("PROJECTS_DIR", "Папка с проектами на компьютере", "text", "C:\\Users\\вы\\Projects", "github"),
    ("EDITOR", "Редактор по умолчанию", "select", ["cursor", "vscode"], "github"),
    ("TELEGRAM_BOT_TOKEN", "Токен бота от @BotFather", "secret", "123456789:AA…", "telegram"),
    ("TELEGRAM_OWNER_ID", "Ваш Telegram ID (заполнится сам после /start с кодом)", "text", "", "telegram"),
    ("TELEGRAM_BRIEF", "Присылать сводку дня в Телеграм при запуске", "select", ["true", "false"], "telegram"),
    ("TG_API_ID", "api_id (с my.telegram.org)", "text", "1234567", "chats"),
    ("TG_API_HASH", "api_hash (с my.telegram.org)", "secret", "0123456789abcdef…", "chats"),
    ("TG_SCAN_MINUTES", "Как часто проверять чаты (минут)", "select", ["15", "30", "60", "120"], "chats"),
    ("TG_DIGEST_TIME", "Утренняя сводка задач из чатов (время; пусто — не нужна)", "text", "10:00", "chats"),
    ("EMAIL_ADDRESS", "Адрес почты", "text", "you@gmail.com", "email"),
    ("EMAIL_PASSWORD", "Пароль приложения", "secret", "xxxx xxxx xxxx xxxx", "email"),
    ("TTS_ENGINE", "Какой голос первым: edge (бесплатный) или openai (стабильный)", "select", ["edge", "openai"], "voice"),
    ("TTS_VOICE", "Голос Microsoft", "select", ["ru-RU-DmitryNeural", "ru-RU-SvetlanaNeural"], "voice"),
    ("OPENAI_VOICE", "Голос OpenAI (onyx — самый низкий и бархатный)", "select", ["onyx", "ash", "ballad", "echo", "sage", "fable"], "voice"),
    ("OFFLINE_VOICE", "Запасной голос Windows, если остальные не отвечают", "select", ["true", "false"], "voice"),
    ("VOICE_PRESET", "Стиль голоса", "select", ["дворецкий", "хриплый бас"], "voice"),
    ("BARGE_IN", "Можно перебивать: заговорили — Джарвис замолкает и слушает", "select", ["true", "false"], "voice"),
    ("BARGE_SENSITIVITY", "Чувствительность перебивания (меньше — чутче; в колонках без наушников — 3)", "select", ["2", "2.5", "3", "4"], "voice"),
    ("VOICE_SPEED", "Темп речи (1.0 — обычный, 1.12 — чуть быстрее)", "select", ["1.0", "1.05", "1.12", "1.2", "1.3"], "voice"),
    ("VOICE_PITCH", "Высота голоса Microsoft (меньше — глубже)", "select", ["-6Hz", "-12Hz", "-18Hz", "+0Hz"], "voice"),
    ("PAUSE_SECONDS", "Пауза, после которой фраза считается законченной (сек)", "select", ["0.8", "1.0", "1.3", "1.6", "2.0"], "voice"),
    ("WAKE_WORDS", "Слова-активаторы", "text", "джарвис,jarvis", "voice"),
    ("USER_NAME", "Как к вам обращаться", "text", "Сабина", "look"),
    ("GREETING", "Приветствие при запуске ({user} — имя)", "text", "Моё почтение, {user}. Я к вашим услугам.", "look"),
    ("INTRO_ANIMATION", "Анимация появления на всех мониторах", "select", ["true", "false"], "look"),
    ("DASHBOARD_SCREENS", "Дашборд при запуске: all — все мониторы, main — главный, off — нет", "select", ["all", "main", "off"], "look"),
    ("MORNING_BRIEF", "Сводка дня после приветствия", "select", ["true", "false"], "look"),
    ("CITY", "Город для погоды", "text", "Москва", "look"),
    ("WORKSPACE_URLS", "Рабочая зона: сайты через запятую", "text", "https://railway.com/dashboard,…", "look"),
    ("CONFIRM_DANGEROUS", "Спрашивать «да/нет» перед опасными действиями", "select", ["true", "false"], "look"),
]
NEEDS_RESTART = {"TELEGRAM_BOT_TOKEN", "AI_PROVIDER", "INTRO_ANIMATION", "DASHBOARD_SCREENS", "PAUSE_SECONDS", "WAKE_WORDS"}
SECRET_KEYS = {k for k, _, kind, *_ in SETTINGS if kind == "secret"}


def _read_env() -> dict:
    return config.read_env_file(ENV_PATH)


def _write_env(updates: dict):
    lines = ENV_PATH.read_text(encoding="utf-8").splitlines() if ENV_PATH.exists() else []
    done = set()
    for i, line in enumerate(lines):
        k = line.split("=", 1)[0].strip()
        if "=" in line and not line.lstrip().startswith("#") and k in updates:
            lines[i] = f"{k}={updates[k]}"
            done.add(k)
    lines += [f"{k}={v}" for k, v in updates.items() if k not in done]
    ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _system() -> dict:
    try:
        import psutil
        disk_root = "C:\\" if platform.system() == "Windows" else "/"
        bat = psutil.sensors_battery() if hasattr(psutil, "sensors_battery") else None
        return {"cpu": psutil.cpu_percent(interval=None), "ram": psutil.virtual_memory().percent,
                "disk": psutil.disk_usage(disk_root).percent, "battery": round(bat.percent) if bat else None}
    except Exception:  # noqa: BLE001
        return {}


@app.get("/")
def index():
    return _page("index.html")


@app.get("/intro")
def intro_page():
    return _page("intro.html")


@app.get("/settings")
def settings_page():
    return _page("settings.html")


def _as_text(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, list):
        return ",".join(v)
    return str(v or "")


@app.get("/api/settings")
def get_settings():
    env = _read_env()
    return jsonify([{"key": k, "label": label, "kind": kind, "options": opts, "group": group,
                     "value": "" if k in SECRET_KEYS else env.get(k, _as_text(getattr(config, k, ""))),
                     "is_set": bool(env.get(k))} for k, label, kind, opts, group in SETTINGS])


@app.post("/api/settings")
def save_settings():
    data = request.get_json(force=True)
    allowed = {k for k, *_ in SETTINGS}
    updates = {}
    for k, v in data.items():
        v = str(v).replace("\n", "").strip()
        if k in allowed and not (k in SECRET_KEYS and not v):  # пустой пароль = оставить старый
            updates[k] = v
    _write_env(updates)
    os.environ.update(updates)
    _apply_live(updates)
    restart = sorted(NEEDS_RESTART & set(updates))
    return jsonify(ok=True, message="Сохранено и применено." + (
        " Чтобы сменить мозг/запуск — перезапустите Джарвиса." if restart else ""))


def _apply_live(updates: dict):
    """Применить настройки сразу, без перезапуска: модули читают config.* в момент вызова."""
    for k, v in updates.items():
        cur = getattr(config, k, None)
        if isinstance(cur, bool):
            setattr(config, k, v.lower() in ("1", "true", "yes", "да"))
        elif isinstance(cur, int):
            try:
                setattr(config, k, int(v))
            except ValueError:
                pass
        elif isinstance(cur, float):
            try:
                setattr(config, k, float(v))
            except ValueError:
                pass
        elif isinstance(cur, list):
            setattr(config, k, [w.strip().lower() for w in v.split(",") if w.strip()])
        elif isinstance(cur, str) or cur is None:
            setattr(config, k, v)
    if "VOICE_PRESET" in updates:  # стиль голоса — сразу, вместе с тембром
        voice, pitch, style = config.VOICE_PRESETS.get(config.VOICE_PRESET, config.VOICE_PRESETS["дворецкий"])
        config.OPENAI_VOICE, config.VOICE_PITCH, config.VOICE_STYLE = voice, pitch, style
    if "USER_NAME" in updates and not config.USER_NAME:
        config.USER_NAME = "Сабина"


@app.post("/api/test/<svc>")
def test_service(svc: str):
    """Кнопка «Проверить» в настройках."""
    ok, message = run_test(svc)
    return jsonify(ok=ok, message=message)


def run_test(svc: str) -> tuple[bool, str]:
    """Проверка одного сервиса: (всё ли хорошо, понятное сообщение). Используется и в check_jarvis.bat."""
    try:
        if svc == "notion":
            from .tools import notion
            rows = notion.tasks_rows(include_done=True)
            msg = f"Notion подключён: в «Сводке задач» {len(rows)} записей."
            if config.NOTION_HUB_PAGE:
                notion._req("GET", f"/blocks/{config.NOTION_HUB_PAGE}/children?page_size=1")
                msg += " Штаб доступен."
        elif svc == "github":
            from .tools import github
            repos = github.overview(max_age=0)
            msg = f"GitHub подключён: {len(repos)} репозиториев — " + ", ".join(r["name"].split("/")[1] for r in repos[:6])
        elif svc == "email":
            from .tools.mail import _imap
            m = _imap()
            m.select("INBOX", readonly=True)
            unseen = len(m.uid("search", None, "UNSEEN")[1][0].split())
            m.logout()
            msg = f"Почта подключена: непрочитанных писем — {unseen}."
        elif svc == "openai":
            import openai
            openai.OpenAI().models.retrieve(config.OPENAI_MODEL)
            msg = f"OpenAI работает, модель {config.OPENAI_MODEL} доступна."
        elif svc == "claude":
            from .brain_claude_code import check
            st = check()
            if not st["ok"]:
                return False, f"Claude Code: {st['note']}"
            msg = "Claude Code на связи: вход выполнен."
        elif svc == "chats":
            from . import tg_reader
            if not tg_reader.enabled():
                return False, "впишите api_id и api_hash"
            if not tg_reader.logged_in():
                return False, "нет входа — запустите telegram_login.bat"
            n = len(tg_reader.dialogs())
            return True, f"вход есть, чатов в аккаунте: {n}; выбрано рабочих: {len(tg_reader.selected_chats())}"
        elif svc == "telegram":
            from .telegram_bot import test
            ok, msg = test()
            return ok, "Телеграм: " + msg
        elif svc == "voice":
            BRAIN_SAY = BRAIN.get("say")
            if BRAIN_SAY:
                BRAIN_SAY(f"Проверка голоса. К вашим услугам, {config.USER_NAME}.")
            msg = "Голос проверен — вы должны были его услышать."
        else:
            return False, "Неизвестный сервис"
        return True, msg
    except Exception as e:  # noqa: BLE001
        text = str(e)
        if "ProxyError" in type(e).__name__ or "Connection" in type(e).__name__ or "Max retries" in text:
            text = "нет связи с сервисом — проверьте интернет или VPN"
        elif "application-specific password" in text.lower():
            text = ("Gmail требует пароль приложения, а не обычный пароль. Включите двухэтапную проверку и создайте "
                    "пароль на myaccount.google.com/apppasswords")
        elif "AUTHENTICATIONFAILED" in text.upper() or "LOGIN" in text.upper() and "fail" in text.lower():
            text = "почта не приняла пароль — нужен именно пароль приложения, и включён IMAP"
        elif "403" in text and "github" in text:
            text = "GitHub не пускает — у токена нет доступа: выберите All repositories и права Read-only"
        elif "AuthenticationError" in type(e).__name__ or "401" in text:
            text = "ключ не подходит — скопируйте его ещё раз целиком"
        return False, text[:300]


@app.get("/api/state")
def state():
    return jsonify({
        "now": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "user": config.USER_NAME,
        "provider": config.AI_PROVIDER,
        "editor": config.EDITOR,
        "tasks": storage.query("SELECT * FROM tasks ORDER BY done, due IS NULL, due, id DESC LIMIT 100"),
        "reminders": storage.query("SELECT * FROM reminders WHERE fired = 0 ORDER BY at LIMIT 50"),
        "notes": storage.query("SELECT * FROM notes ORDER BY id DESC LIMIT 30"),
        "memory": storage.query("SELECT * FROM memory ORDER BY key"),
        "mail": storage.query("SELECT * FROM mail_cache ORDER BY rowid DESC LIMIT 15"),
        "log": storage.query("SELECT * FROM log ORDER BY id DESC LIMIT 40"),
        "system": _system(),
    })


@app.get("/api/work")
def work():
    """Текущая работа: репозитории GitHub и задачи Notion (грузится отдельно — может занять пару секунд)."""
    from .tools import github, notion
    out = {"github": None, "notion": None, "errors": {}, "hub": None, "notion_db": None}
    if github.enabled():
        try:
            out["github"] = github.overview()
        except Exception as e:  # noqa: BLE001
            out["errors"]["github"] = str(e)
    if notion.enabled():
        try:
            out["notion"] = notion.tasks_rows()
        except Exception as e:  # noqa: BLE001
            out["errors"]["notion"] = str(e)
        if config.NOTION_HUB_PAGE:
            out["hub"] = f"https://www.notion.so/{config.NOTION_HUB_PAGE.replace('-', '')}"
        out["notion_db"] = f"https://www.notion.so/{config.NOTION_TASKS_DB.replace('-', '')}"
    return jsonify(out)


# Инструменты, которые можно нажимать на дашборде (клик = намерение; опасные подтверждаются в самом окне)
UI_TOOLS = {
    "start_workspace", "open_project", "open_url", "open_dashboard", "volume", "media_control", "screenshot",
    "lock_computer", "sleep_computer", "shutdown_computer", "restart_computer", "cancel_shutdown", "system_status",
    "top_processes", "check_email", "read_email", "mark_email", "add_task", "complete_task", "delete_task",
    "add_reminder", "delete_reminder", "add_note", "forget", "remember", "notion_add_task", "notion_set_status",
    "github_commits", "github_issues", "github_sync", "codex_task", "open_app", "play_youtube", "chat_tasks_scan",
}
READ_ONLY_UI = {"read_email", "check_email", "github_commits", "github_issues", "system_status", "top_processes"}
_cache: dict = {}


@app.post("/api/tool")
def run_tool():
    from .tools import load_all
    d = request.get_json(force=True)
    name, args = d.get("name"), d.get("args") or {}
    tool = load_all().get(name)
    if name not in UI_TOOLS or not tool:
        return jsonify(ok=False, result="Это действие с дашборда недоступно"), 400
    try:
        from . import activity
        label, detail = activity.describe(name, args)
        activity.emit("tool", f"{label} (кнопка на дашборде)", detail, "dashboard")
        result = str(tool.func(**args))
        activity.emit("done", f"{label} — готово", result[:600], "dashboard")
        if name not in READ_ONLY_UI:  # в журнал — только действия, не просмотр
            storage.log("jarvis", f"[дашборд] {result[:200]}")
        return jsonify(ok=True, result=result)
    except Exception as e:  # noqa: BLE001
        return jsonify(ok=False, result=f"{type(e).__name__}: {e}")


@app.get("/api/weather")
def weather_api():
    from .tools.info import weather_data
    if _cache.get("wt", 0) < time.time() - 600:
        try:
            _cache.update(w=weather_data(), wt=time.time())
        except Exception as e:  # noqa: BLE001
            return jsonify(error=str(e))
    return jsonify(_cache["w"])


@app.get("/api/integrations")
def integrations_api():
    from .integrations import status
    return jsonify(status())


@app.post("/api/notion/<task_id>/status")
def notion_status(task_id: str):
    from .tools import notion
    return jsonify(result=notion.notion_set_status(task_id, request.get_json(force=True)["status"]))


@app.post("/api/tasks")
def new_task():
    d = request.get_json(force=True)
    return jsonify(result=t.add_task(d["title"], d.get("due") or None, d.get("priority") or "обычный"))


@app.post("/api/tasks/<int:tid>/toggle")
def toggle_task(tid: int):
    storage.execute("UPDATE tasks SET done = 1 - done WHERE id = ?", (tid,))
    return jsonify(ok=True)


@app.delete("/api/tasks/<int:tid>")
def del_task(tid: int):
    return jsonify(result=t.delete_task(tid))


@app.delete("/api/reminders/<int:rid>")
def del_reminder(rid: int):
    return jsonify(result=t.delete_reminder(rid))


@app.post("/api/ask")
def ask():
    if not BRAIN["ask"]:
        return jsonify(answer="Мозг ещё не запущен"), 503
    text = request.get_json(force=True).get("text", "").strip()
    with _ask_lock:
        return jsonify(answer=BRAIN["ask"](text))


@app.post("/api/confirm")
def confirm():
    """Claude Code (через MCP-сервер) спрашивает разрешение — голосом и окном на дашборде."""
    fn = BRAIN["confirm"]
    d = request.get_json(force=True)
    return jsonify(ok=bool(fn and fn(d.get("question", ""), d.get("spoken"))))


@app.get("/api/activity")
def activity_feed():
    from . import activity
    return jsonify(activity.listing(int(request.args.get("after", 0) or 0)))


@app.get("/api/tgchats")
def tg_chats():
    from . import tg_reader
    if not (tg_reader.enabled() and tg_reader.logged_in()):
        return jsonify(ok=False, message="Сначала api_id/api_hash и вход через telegram_login.bat", chats=[])
    try:
        chosen = {c["id"] for c in tg_reader.selected_chats()}
        return jsonify(ok=True, chats=[{**d, "on": d["id"] in chosen} for d in tg_reader.dialogs()])
    except Exception as e:  # noqa: BLE001
        return jsonify(ok=False, message=str(e), chats=[])


@app.post("/api/tgchats")
def tg_chats_save():
    from . import tg_reader
    chats = request.get_json(force=True).get("chats", [])
    tg_reader.save_chats([{"id": int(c["id"]), "name": str(c["name"])[:120]} for c in chats])
    return jsonify(ok=True, message=f"Сохранено рабочих чатов: {len(chats)}")


@app.get("/api/chattasks")
def chat_tasks_api():
    from . import tg_reader
    return jsonify(tg_reader.open_tasks() if tg_reader.enabled() else [])


@app.get("/api/pending")
def pending():
    c = BRAIN.get("confirmer")
    return jsonify(c.listing() if c else [])


@app.post("/api/pending/<cid>")
def pending_answer(cid: str):
    c = BRAIN.get("confirmer")
    return jsonify(ok=bool(c and c.answer(cid, bool(request.get_json(force=True).get("yes")))))


def start(ask_fn=None, confirm_fn=None):
    BRAIN["ask"] = ask_fn
    BRAIN["confirm"] = confirm_fn
    # токен запуска кладём в файл — по нему MCP-сервер Джарвиса (в Cursor/Codex) спрашивает подтверждения
    try:
        (config.DATA_DIR / ".token").write_text(TOKEN, encoding="utf-8")
    except OSError:
        pass
    threading.Thread(target=lambda: app.run(host="127.0.0.1", port=config.DASHBOARD_PORT, use_reloader=False),
                     daemon=True).start()
    return f"http://localhost:{config.DASHBOARD_PORT}"
