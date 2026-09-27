"""Веб-дашборд Джарвиса: http://localhost:5050"""
import logging
import platform
import threading
from datetime import datetime

from flask import Flask, jsonify, request, send_from_directory

from . import config, storage
from .tools import tasks as t

WEB = __import__("pathlib").Path(__file__).parent / "web"
app = Flask(__name__)
logging.getLogger("werkzeug").setLevel(logging.ERROR)

BRAIN = {"ask": None}
_ask_lock = threading.Lock()


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
    return send_from_directory(WEB, "index.html")


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
