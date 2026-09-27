"""Веб-дашборд Джарвиса: http://localhost:5050"""
import logging
import os
import platform
import secrets
import threading
from datetime import datetime

from flask import Flask, jsonify, request

from . import config, storage
from .tools import tasks as t

WEB = __import__("pathlib").Path(__file__).parent / "web"
app = Flask(__name__)
logging.getLogger("werkzeug").setLevel(logging.ERROR)

BRAIN = {"ask": None}
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
SETTINGS = [
    # (ключ, подпись, тип, варианты/подсказка)
    ("AI_PROVIDER", "Чей мозг", "select", ["openai", "claude"]),
    ("OPENAI_API_KEY", "Ключ OpenAI", "secret", "sk-…"),
    ("OPENAI_MODEL", "Модель OpenAI", "select", ["gpt-4.1-mini", "gpt-4.1", "gpt-4o-mini", "gpt-4o"]),
    ("ANTHROPIC_API_KEY", "Ключ Claude", "secret", "sk-ant-…"),
    ("USER_NAME", "Как к вам обращаться", "text", "сэр"),
    ("CITY", "Город для погоды", "text", "Москва"),
    ("WAKE_WORDS", "Слова-активаторы", "text", "джарвис,jarvis"),
    ("TTS_VOICE", "Голос", "select", ["ru-RU-DmitryNeural", "ru-RU-SvetlanaNeural"]),
    ("OFFLINE_VOICE", "Запасной голос Windows, если основной не отвечает", "select", ["true", "false"]),
    ("EMAIL_ADDRESS", "Почта", "text", "you@gmail.com"),
    ("EMAIL_PASSWORD", "Пароль приложения почты", "secret", "xxxx xxxx xxxx xxxx"),
    ("CONFIRM_DANGEROUS", "Спрашивать «да/нет» перед опасными действиями", "select", ["true", "false"]),
]
SECRET_KEYS = {k for k, _, kind, _ in SETTINGS if kind == "secret"}


def _read_env() -> dict:
    values = {}
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                values[k.strip()] = v.strip()
    return values


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


@app.get("/settings")
def settings_page():
    return _page("settings.html")


@app.get("/api/settings")
def get_settings():
    env = _read_env()
    return jsonify([{"key": k, "label": label, "kind": kind, "options": opts,
                     "value": "" if k in SECRET_KEYS else env.get(k, ""),
                     "is_set": bool(env.get(k))} for k, label, kind, opts in SETTINGS])


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
    return jsonify(ok=True, message="Сохранено. Перезапустите Джарвиса, чтобы изменения вступили в силу.")


@app.get("/api/state")
def state():
    return jsonify({
        "now": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "user": config.USER_NAME,
        "tasks": storage.query("SELECT * FROM tasks ORDER BY done, due IS NULL, due, id DESC LIMIT 100"),
        "reminders": storage.query("SELECT * FROM reminders WHERE fired = 0 ORDER BY at LIMIT 50"),
        "notes": storage.query("SELECT * FROM notes ORDER BY id DESC LIMIT 30"),
        "memory": storage.query("SELECT * FROM memory ORDER BY key"),
        "mail": storage.query("SELECT * FROM mail_cache ORDER BY rowid DESC LIMIT 15"),
        "log": storage.query("SELECT * FROM log ORDER BY id DESC LIMIT 40"),
        "system": _system(),
    })


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


def start(ask_fn=None):
    BRAIN["ask"] = ask_fn
    threading.Thread(target=lambda: app.run(host="127.0.0.1", port=config.DASHBOARD_PORT, use_reloader=False),
                     daemon=True).start()
    return f"http://localhost:{config.DASHBOARD_PORT}"
