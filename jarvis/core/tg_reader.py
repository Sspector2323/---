"""Задачи из рабочих чатов Телеграма → Notion + напоминания.

Джарвис входит в ВАШ аккаунт Телеграма только на чтение: ничего не отправляет, не отмечает прочитанным,
вслух переписки не зачитывает. Смотрит только выбранные вами рабочие чаты. Новые сообщения раз в
TG_SCAN_MINUTES минут отдаёт ИИ (OpenAI), тот выделяет задачи для вас — они уходят в «Сводку задач» Notion,
а по срокам ставятся напоминания.

Вход и выбор чатов:  telegram_login.bat   (python -m core.tg_reader login)
"""
import asyncio
import json
import threading
import time
from datetime import datetime, timedelta

from . import activity, config, storage

SESSION = config.DATA_DIR / "tg_user"          # файл входа (= доступ к аккаунту, храните в секрете)
CHATS_FILE = config.DATA_DIR / "tg_chats.json"  # выбранные рабочие чаты
STATE_FILE = config.DATA_DIR / "tg_state.json"  # последнее прочитанное сообщение в каждом чате
_scan_lock = threading.Lock()

storage.execute("""CREATE TABLE IF NOT EXISTS tg_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER, chat TEXT, msg_id INTEGER, title TEXT, details TEXT,
    due TEXT, priority TEXT, link TEXT, notion_id TEXT, notion_url TEXT, created TEXT, key TEXT UNIQUE)""")


def enabled() -> bool:
    return bool(config.TG_API_ID and config.TG_API_HASH)


def logged_in() -> bool:
    return SESSION.with_suffix(".session").exists()


def _load(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def selected_chats() -> list[dict]:
    return _load(CHATS_FILE, [])


def save_chats(chats: list[dict]):
    CHATS_FILE.write_text(json.dumps(chats, ensure_ascii=False, indent=1), encoding="utf-8")


def _client():
    from telethon import TelegramClient
    return TelegramClient(str(SESSION), int(config.TG_API_ID), config.TG_API_HASH,
                          device_model="J.A.R.V.I.S.", app_version="1.0")


async def _dialogs(limit: int = 300) -> list[dict]:
    client = _client()
    await client.connect()
    try:
        if not await client.is_user_authorized():
            raise RuntimeError("не выполнен вход — запустите telegram_login.bat")
        out = []
        async for d in client.iter_dialogs(limit=limit):
            kind = "канал" if d.is_channel and not d.is_group else "группа" if d.is_group else "личный чат"
            out.append({"id": d.id, "name": d.name or "(без названия)", "kind": kind})
        return out
    finally:
        await client.disconnect()


def dialogs() -> list[dict]:
    return asyncio.run(_dialogs())


def _link(chat_id: int, msg_id: int) -> str:
    s = str(chat_id)
    return f"https://t.me/c/{s[4:]}/{msg_id}" if s.startswith("-100") else ""


# ---------- Извлечение задач ----------

SCHEMA = {"type": "object", "additionalProperties": False, "required": ["tasks"], "properties": {"tasks": {
    "type": "array", "items": {"type": "object", "additionalProperties": False,
                               "required": ["title", "details", "due", "priority", "message_id", "quote"],
                               "properties": {
                                   "title": {"type": "string"}, "details": {"type": "string"},
                                   "due": {"type": "string"}, "priority": {"type": "string", "enum": ["High", "Medium", "Low"]},
                                   "message_id": {"type": "integer"}, "quote": {"type": "string"}}}}}}

PROMPT = """Ты помощник {user}. Ниже — новые сообщения из рабочего чата «{chat}». Сейчас {now}.
Выдели ТОЛЬКО задачи, которые должна сделать {user}: что ей поручили, о чём попросили, что она сама пообещала
(её сообщения помечены «Я»). Не выдумывай: болтовня, новости и задачи других людей — не задачи.
Для каждой задачи: короткий title в повелительном наклонении («Отправить отчёт Борису»), details — суть
и контекст в 1–2 предложениях, due — срок в формате ГГГГ-ММ-ДД ЧЧ:ММ если он назван или ясно следует
(«до пятницы», «завтра к 12»), иначе пустая строка; priority — High если срочно/важно, иначе Medium или Low;
message_id — номер сообщения, из которого задача; quote — короткая цитата оттуда.
Если задач нет — пустой список.

Сообщения:
{messages}"""


def _extract(chat: str, lines: list[str]) -> list[dict]:
    import openai
    resp = openai.OpenAI().chat.completions.create(
        model=config.TG_MODEL,
        messages=[{"role": "user", "content": PROMPT.format(
            user=config.USER_NAME, chat=chat, now=datetime.now().strftime("%Y-%m-%d %H:%M, %A"),
            messages="\n".join(lines)[-60000:])}],
        response_format={"type": "json_schema", "json_schema": {"name": "tasks", "schema": SCHEMA, "strict": True}},
    )
    return json.loads(resp.choices[0].message.content or "{}").get("tasks", [])


async def _read_new(chat: dict, last_id: int) -> tuple[list[str], int]:
    """Новые сообщения чата (без отметки «прочитано»). Первый раз — только за последние 3 дня."""
    client = _client()
    await client.connect()
    try:
        if not await client.is_user_authorized():
            raise RuntimeError("не выполнен вход — запустите telegram_login.bat")
        me = await client.get_me()
        since = datetime.now().astimezone() - timedelta(days=3)
        lines, top = [], last_id
        async for m in client.iter_messages(chat["id"], limit=300, min_id=last_id):
            if not last_id and m.date < since:
                break
            top = max(top, m.id)
            text = (m.message or "").strip()
            if not text:
                continue
            who = "Я" if m.sender_id == me.id else (getattr(m.sender, "first_name", None) or
                                                   getattr(m.sender, "title", None) or "Кто-то")
            reply = f" (ответ на #{m.reply_to_msg_id})" if m.reply_to_msg_id else ""
            lines.append(f"#{m.id} [{m.date.astimezone():%d.%m %H:%M}] {who}{reply}: {text[:1500]}")
        return lines[::-1], top
    finally:
        await client.disconnect()


def scan(force: bool = False) -> str:
    """Проверить рабочие чаты, новые задачи — в Notion и напоминания. Вернёт краткий итог."""
    if not enabled():
        return "Чтение чатов не настроено (TG_API_ID / TG_API_HASH)"
    if not logged_in():
        return "Нет входа в Телеграм — запустите telegram_login.bat"
    chats = selected_chats()
    if not chats:
        return "Рабочие чаты не выбраны — ⚙ Настройки → Рабочие чаты"
    if not _scan_lock.acquire(blocking=False):
        return "Уже проверяю чаты"
    try:
        state = _load(STATE_FILE, {})
        added = []
        for chat in chats:
            activity.emit("tool", "Просматривает рабочий чат", chat["name"], "chats")
            lines, top = asyncio.run(_read_new(chat, int(state.get(str(chat["id"]), 0))))
            state[str(chat["id"])] = top
            if not lines:
                continue
            for t in _extract(chat["name"], lines):
                added += [x for x in [_save_task(chat, t)] if x]
        STATE_FILE.write_text(json.dumps(state), encoding="utf-8")
        if added:
            activity.emit("done", f"Задачи из чатов: +{len(added)} в Notion", "\n".join(added), "chats")
            try:
                from .telegram_bot import send
                send("🗂 Новые задачи из рабочих чатов:\n\n" + "\n".join(f"• {a}" for a in added))
            except Exception:  # noqa: BLE001
                pass
            from .briefing import _plural
            n = len(added)
            return f"Нашёл {n} {_plural(n, 'новую задачу', 'новые задачи', 'новых задач')} и записал в Notion: " + "; ".join(added)
        return "Новых задач в рабочих чатах нет"
    except Exception as e:  # noqa: BLE001
        activity.emit("error", "Чтение рабочих чатов — ошибка", str(e), "chats")
        return f"Не получилось проверить чаты: {e}"
    finally:
        _scan_lock.release()


def _save_task(chat: dict, t: dict) -> str | None:
    title = t["title"].strip()[:180]
    key = f"{chat['id']}:{t['message_id']}:{title.lower()[:60]}"
    if storage.query("SELECT 1 FROM tg_tasks WHERE key = ?", (key,)):
        return None
    link = _link(chat["id"], t["message_id"])
    details = (f"{t['details']}\n\nИз чата «{chat['name']}»: «{t['quote'][:300]}»" + (f"\n{link}" if link else ""))
    due = t.get("due") or None
    notion_id = notion_url = ""
    try:
        from .tools import notion
        if notion.enabled():
            res = notion.add_task_raw(title, status="Не начато", priority=t.get("priority") or "Medium",
                                      details=details, due=due)
            notion_id, notion_url = res["id"], res["url"]
    except Exception as e:  # noqa: BLE001
        activity.emit("error", "Notion: не записал задачу из чата", f"{title}: {e}", "chats")
    storage.execute("INSERT OR IGNORE INTO tg_tasks (chat_id, chat, msg_id, title, details, due, priority, link, "
                    "notion_id, notion_url, created, key) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (chat["id"], chat["name"], t["message_id"], title, details, due or "", t.get("priority"), link,
                     notion_id, notion_url, storage.now(), key))
    if due:  # напоминания: за 2 часа и в срок
        from .tools.tasks import add_reminder
        try:
            when = datetime.strptime(due, "%Y-%m-%d %H:%M")
            for at, prefix in ((when - timedelta(hours=2), "Через 2 часа срок"), (when, "Срок")):
                if at > datetime.now():
                    add_reminder(f"{prefix}: {title} (чат «{chat['name']}»)", at.strftime("%Y-%m-%d %H:%M"))
        except ValueError:
            pass
    return title + (f" — до {due}" if due else "")


def open_tasks(days: int = 14) -> list[dict]:
    """Задачи из чатов за последние дни, которые в Notion ещё не «Готово»."""
    rows = storage.query("SELECT * FROM tg_tasks WHERE created >= ? ORDER BY id DESC",
                         ((datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d"),))
    try:
        from .tools import notion
        if notion.enabled():
            active = {r["id"].replace("-", "") for r in notion.tasks_rows()}
            rows = [r for r in rows if not r["notion_id"] or r["notion_id"].replace("-", "") in active]
    except Exception:  # noqa: BLE001
        pass
    return rows


def digest() -> str:
    rows = open_tasks()
    if not rows:
        return ""
    def when(due: str) -> str:
        try:
            return datetime.strptime(due, "%Y-%m-%d %H:%M").strftime("%d.%m в %H:%M")
        except ValueError:
            return due
    items = [f"{r['title']}" + (f" (до {when(r['due'])})" if r["due"] else "") for r in rows[:8]]
    return f"Из рабочих чатов у вас открыто задач: {len(rows)}. " + "; ".join(items) + "."


def background_loop():
    """Проверка чатов по расписанию + утренняя сводка задач из чатов."""
    last_scan, last_digest = 0.0, ""
    while True:
        try:
            if enabled() and logged_in() and selected_chats() and time.time() - last_scan > config.TG_SCAN_MINUTES * 60:
                last_scan = time.time()
                scan()
            today = datetime.now().strftime("%Y-%m-%d")
            if config.TG_DIGEST_TIME and datetime.now().strftime("%H:%M") >= config.TG_DIGEST_TIME \
                    and last_digest != today and enabled():
                last_digest = today
                text = digest()
                if text:
                    storage.execute("INSERT INTO reminders (text, at) VALUES (?, ?)", (text, storage.now()))
        except Exception as e:  # noqa: BLE001
            activity.emit("error", "Задачи из чатов — ошибка фоновой проверки", str(e), "chats")
        time.sleep(60)


# ---------- Вход и выбор чатов (консоль) ----------

async def _login_and_pick():
    client = _client()
    print("Вход в ваш Телеграм (только чтение рабочих чатов).")
    await client.start(phone=lambda: input("Номер телефона (+7…): ").strip(),
                       code_callback=lambda: input("Код из Телеграма: ").strip(),
                       password=lambda: __import__("getpass").getpass("Пароль двухэтапной проверки (если есть): "))
    me = await client.get_me()
    print(f"\n✅ Вход выполнен: {me.first_name}\n")
    chats = []
    async for d in client.iter_dialogs(limit=200):
        if d.is_group or d.is_channel:
            chats.append({"id": d.id, "name": d.name or "(без названия)"})
    await client.disconnect()
    chosen = {c["id"] for c in selected_chats()}
    print("Группы и каналы (первые 200):")
    for i, c in enumerate(chats, 1):
        print(f"  {i:3}. {'[x]' if c['id'] in chosen else '[ ]'} {c['name']}")
    raw = input("\nНомера РАБОЧИХ чатов через запятую (Enter — оставить как есть; личные переписки можно выбрать на дашборде): ")
    if raw.strip():
        nums = {int(x) for x in raw.replace(" ", "").split(",") if x.isdigit()}
        picked = [c for i, c in enumerate(chats, 1) if i in nums]
        save_chats(picked)
        print("Выбрано: " + ", ".join(c["name"] for c in picked))
    print("\nГотово. Джарвис будет проверять эти чаты раз в", config.TG_SCAN_MINUTES, "мин.")


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    if not enabled():
        print("Сначала впишите TG_API_ID и TG_API_HASH (⚙ Настройки → Рабочие чаты) и запустите снова.")
    elif len(sys.argv) > 1 and sys.argv[1] == "scan":
        print(scan(force=True))
    else:
        asyncio.run(_login_and_pick())
