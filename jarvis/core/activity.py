"""«Прямой эфир»: всё, что делает Джарвис, — для панели на дашборде.

emit(...) — записать событие; task_start/task_end — баннер «Сейчас: …» с таймером;
describe(...) — человеческое название действия («Читает файл …», «Ищет в интернете: …»).
"""
import json
import threading
import time
from collections import deque
from datetime import datetime

from . import storage

_lock = threading.Lock()
_events: deque = deque(maxlen=600)
_seq = 0
CURRENT: dict = {}  # текущая задача: {"title", "started", "source"}

storage.execute("""CREATE TABLE IF NOT EXISTS activity (
    id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, kind TEXT, title TEXT, detail TEXT, source TEXT)""")
for row in storage.query("SELECT * FROM activity ORDER BY id DESC LIMIT 200")[::-1]:
    _seq = max(_seq, row["id"])
    _events.append(row)

ICONS = {"task": "🎯", "tool": "⚙️", "done": "✅", "error": "❌", "think": "💭", "confirm": "⚠️",
         "voice": "🎙", "telegram": "✈️", "answer": "💬", "system": "🛰"}


def emit(kind: str, title: str, detail: str = "", source: str = "") -> None:
    global _seq
    detail = detail if isinstance(detail, str) else json.dumps(detail, ensure_ascii=False)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    rid = storage.execute("INSERT INTO activity (ts, kind, title, detail, source) VALUES (?, ?, ?, ?, ?)",
                          (ts, kind, title[:300], detail[:4000], source))
    with _lock:
        _seq = rid
        _events.append({"id": rid, "ts": ts, "kind": kind, "title": title[:300], "detail": detail[:4000],
                        "source": source})
    if rid % 500 == 0:  # не раздуваем базу
        storage.execute("DELETE FROM activity WHERE id < ?", (rid - 3000,))


def task_start(title: str, source: str = "") -> None:
    CURRENT.update(title=title[:200], started=time.time(), source=source, steps=0)
    emit("task", title, source=source)


def task_step() -> None:
    if CURRENT:
        CURRENT["steps"] = CURRENT.get("steps", 0) + 1


def task_end(answer: str = "", ok: bool = True) -> None:
    took = time.time() - CURRENT.get("started", time.time())
    steps = CURRENT.get("steps", 0)
    emit("answer" if ok else "error", (answer or "Готово")[:300],
         f"заняло {took:.1f} с · шагов: {steps}", CURRENT.get("source", ""))
    CURRENT.clear()


def listing(after: int = 0) -> dict:
    with _lock:
        items = [e for e in _events if e["id"] > after][-300:]
    cur = dict(CURRENT)
    if cur:
        cur["elapsed"] = round(time.time() - cur["started"], 1)
    return {"events": items, "current": cur or None}


# ---------- Человеческие названия действий ----------

def _short(v, n=90) -> str:
    s = str(v).replace("\n", " ").strip()
    return s if len(s) <= n else s[:n - 1] + "…"


LABELS = {
    # Джарвис
    "shutdown_computer": "Выключение компьютера", "restart_computer": "Перезагрузка компьютера",
    "sleep_computer": "Спящий режим", "lock_computer": "Блокирует экран", "cancel_shutdown": "Отменяет выключение",
    "open_app": "Открывает программу", "close_app": "Закрывает программу", "open_url": "Открывает сайт",
    "play_youtube": "Ищет на YouTube", "volume": "Меняет громкость", "media_control": "Управляет музыкой",
    "type_text": "Печатает текст", "press_hotkey": "Нажимает клавиши", "clipboard": "Буфер обмена",
    "screenshot": "Делает скриншот", "system_status": "Смотрит состояние ПК", "top_processes": "Смотрит процессы",
    "run_command": "Выполняет команду", "open_dashboard": "Открывает дашборд", "list_folder": "Смотрит папку",
    "find_files": "Ищет файлы", "read_file": "Читает файл", "write_file": "Записывает файл", "open_file": "Открывает файл",
    "move_file": "Перемещает файл", "delete_file": "Удаляет файл", "add_task": "Добавляет дело",
    "list_tasks": "Смотрит дела", "complete_task": "Отмечает дело выполненным", "delete_task": "Удаляет дело",
    "add_reminder": "Ставит напоминание", "list_reminders": "Смотрит напоминания", "delete_reminder": "Удаляет напоминание",
    "add_note": "Записывает заметку", "list_notes": "Смотрит заметки", "remember": "Запоминает", "forget": "Забывает",
    "check_email": "Проверяет почту", "read_email": "Читает письмо", "search_email": "Ищет письма",
    "mark_email": "Помечает письмо", "send_email": "Отправляет письмо", "email_folders": "Смотрит папки почты",
    "organize_email": "Разбирает почту", "get_datetime": "Смотрит время", "weather": "Смотрит погоду",
    "exchange_rates": "Смотрит курсы валют", "claude_code": "Поручает задачу Claude Code",
    "notion_tasks": "Notion: смотрит задачи", "notion_add_task": "Notion: добавляет задачу",
    "notion_set_status": "Notion: меняет статус", "notion_search": "Notion: ищет", "notion_read": "Notion: читает страницу",
    "notion_log": "Notion: пишет в штаб", "github_overview": "GitHub: смотрит репозитории",
    "github_commits": "GitHub: смотрит коммиты", "github_issues": "GitHub: смотрит задачи",
    "github_sync": "GitHub: скачивает репозитории", "open_project": "Открывает проект", "codex_task": "Поручает задачу Codex",
    "start_workspace": "Запускает рабочую зону", "telegram_send": "Пишет вам в Телеграм",
    "telegram_send_file": "Отправляет файл в Телеграм", "web_search": "Ищет в интернете",
    # Claude Code
    "Read": "Читает файл", "Write": "Записывает файл", "Edit": "Правит файл", "MultiEdit": "Правит файл",
    "NotebookEdit": "Правит блокнот", "Bash": "Выполняет команду", "PowerShell": "Выполняет команду",
    "Glob": "Ищет файлы", "Grep": "Ищет в файлах", "LS": "Смотрит папку", "WebSearch": "Ищет в интернете",
    "WebFetch": "Открывает страницу", "TodoWrite": "Составляет план", "Task": "Запускает помощника",
    "Agent": "Запускает помощника",
}
# Короткая фраза для голосового подтверждения («Разрешите …?»)
SPOKEN = {
    "shutdown_computer": "выключить компьютер", "restart_computer": "перезагрузить компьютер",
    "sleep_computer": "перевести компьютер в сон", "close_app": "закрыть программу", "run_command": "выполнить команду",
    "write_file": "записать файл", "move_file": "переместить файл", "delete_file": "удалить файл",
    "send_email": "отправить письмо", "mark_email": "изменить письмо", "organize_email": "разобрать почту",
    "claude_code": "поручить задачу Claude Code", "github_sync": "скачать репозитории", "codex_task": "поручить задачу Codex",
    "Bash": "выполнить команду", "PowerShell": "выполнить команду", "Write": "записать файл", "Edit": "изменить файл",
    "MultiEdit": "изменить файл", "NotebookEdit": "изменить файл", "WebFetch": "открыть страницу",
}
KEY_ARGS = ("command", "file_path", "path", "pattern", "query", "url", "name", "title", "text", "task", "to",
            "subject", "repo", "city", "action", "folder", "description", "prompt", "key")


def describe(name: str, args: dict | None) -> tuple[str, str]:
    """(«Читает файл», «C:\\…\\notes.txt») — для эфира и подтверждений."""
    base = name.split("__")[-1]  # mcp__jarvis__add_task → add_task
    label = LABELS.get(base, base.replace("_", " ")) or "Шаг"
    args = args or {}
    main = next((args[k] for k in KEY_ARGS if args.get(k)), "")
    return label, _short(main) if main else ""


def spoken(name: str) -> str:
    base = name.split("__")[-1]
    return SPOKEN.get(base) or LABELS.get(base, "это действие").lower()
