"""Личные дела: задачи, напоминания, заметки, долговременная память."""
from datetime import datetime

from . import I, S, tool
from .. import storage


@tool("add_task", "Добавить задачу в список дел.",
      {"title": S("Что сделать"), "due": S("Срок в формате ГГГГ-ММ-ДД ЧЧ:ММ (необязательно)"),
       "priority": S("Приоритет", enum=["низкий", "обычный", "высокий"]), "notes": S("Подробности")},
      ["title"])
def add_task(title: str, due: str | None = None, priority: str = "обычный", notes: str = ""):
    tid = storage.execute("INSERT INTO tasks (title, notes, priority, due, created) VALUES (?, ?, ?, ?, ?)",
                          (title, notes, priority, due, storage.now()))
    return f"Задача №{tid} добавлена"


@tool("list_tasks", "Показать задачи.", {"include_done": {"type": "boolean", "description": "Включая выполненные"}})
def list_tasks(include_done: bool = False):
    rows = storage.query("SELECT * FROM tasks" + ("" if include_done else " WHERE done = 0")
                         + " ORDER BY done, CASE priority WHEN 'высокий' THEN 0 WHEN 'обычный' THEN 1 ELSE 2 END, due")
    if not rows:
        return "Задач нет"
    return "\n".join(f"№{r['id']} {'✅' if r['done'] else '⬜'} {r['title']}"
                     f"{' (до ' + r['due'] + ')' if r['due'] else ''} [{r['priority']}]" for r in rows)


@tool("complete_task", "Отметить задачу выполненной.", {"task_id": I("Номер задачи")}, ["task_id"])
def complete_task(task_id: int):
    storage.execute("UPDATE tasks SET done = 1 WHERE id = ?", (task_id,))
    return f"Задача №{task_id} выполнена"


@tool("delete_task", "Удалить задачу.", {"task_id": I("Номер задачи")}, ["task_id"])
def delete_task(task_id: int):
    storage.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    return f"Задача №{task_id} удалена"


@tool("add_reminder", "Поставить напоминание — в нужное время Джарвис скажет его вслух.",
      {"text": S("О чём напомнить"), "at": S("Когда, формат ГГГГ-ММ-ДД ЧЧ:ММ")}, ["text", "at"])
def add_reminder(text: str, at: str):
    datetime.strptime(at, "%Y-%m-%d %H:%M")  # проверка формата
    rid = storage.execute("INSERT INTO reminders (text, at) VALUES (?, ?)", (text, at))
    return f"Напоминание №{rid} на {at}"


@tool("list_reminders", "Показать будущие напоминания.")
def list_reminders():
    rows = storage.query("SELECT * FROM reminders WHERE fired = 0 ORDER BY at")
    return "\n".join(f"№{r['id']} {r['at']} — {r['text']}" for r in rows) or "Напоминаний нет"


@tool("delete_reminder", "Удалить напоминание.", {"reminder_id": I("Номер")}, ["reminder_id"])
def delete_reminder(reminder_id: int):
    storage.execute("DELETE FROM reminders WHERE id = ?", (reminder_id,))
    return "Удалено"


@tool("add_note", "Записать заметку (идеи, мысли, списки покупок).", {"text": S("Текст")}, ["text"])
def add_note(text: str):
    storage.execute("INSERT INTO notes (text, created) VALUES (?, ?)", (text, storage.now()))
    return "Записал"


@tool("list_notes", "Показать последние заметки.")
def list_notes():
    rows = storage.query("SELECT * FROM notes ORDER BY id DESC LIMIT 30")
    return "\n".join(f"№{r['id']} [{r['created']}] {r['text']}" for r in rows) or "Заметок нет"


@tool("remember", "Запомнить факт о пользователе навсегда (день рождения мамы, любимая музыка, пароль от Wi-Fi гостей и т.п.).",
      {"key": S("О чём (коротко)"), "value": S("Что именно")}, ["key", "value"])
def remember(key: str, value: str):
    storage.execute("INSERT OR REPLACE INTO memory (key, value, updated) VALUES (?, ?, ?)", (key, value, storage.now()))
    return "Запомнил"


@tool("forget", "Забыть факт.", {"key": S("О чём")}, ["key"])
def forget(key: str):
    storage.execute("DELETE FROM memory WHERE key = ?", (key,))
    return "Забыл"


def memory_text() -> str:
    rows = storage.query("SELECT key, value FROM memory ORDER BY key")
    return "\n".join(f"- {r['key']}: {r['value']}" for r in rows)


def due_reminders() -> list[dict]:
    rows = storage.query("SELECT * FROM reminders WHERE fired = 0 AND at <= ?", (storage.now(),))
    for r in rows:
        storage.execute("UPDATE reminders SET fired = 1 WHERE id = ?", (r["id"],))
    return rows
