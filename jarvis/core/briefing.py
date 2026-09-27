"""Короткая сводка дня при запуске: дела, напоминания, Notion, почта, погода."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from . import config, storage


def _plural(n: int, one: str, few: str, many: str) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


def _notion():
    from .tools import notion
    if notion.enabled():
        return sum(1 for r in notion.tasks_rows() if r["status"] == "В работе")


def _mail():
    if not (config.EMAIL_ADDRESS and config.EMAIL_PASSWORD):
        return None
    from .tools.mail import _imap
    m = _imap()
    try:
        m.select("INBOX", readonly=True)
        return len(m.uid("search", None, "UNSEEN")[1][0].split())
    finally:
        m.logout()


def _weather():
    from .tools.info import weather
    first = weather().splitlines()[0]  # «Москва сейчас: 12°, ощущается 10°, пасмурно, …»
    return first.split(":", 1)[1].split(", ветер")[0].strip()


def brief() -> str:
    today = datetime.now().strftime("%Y-%m-%d")
    tasks = storage.query("SELECT COUNT(*) c FROM tasks WHERE done = 0")[0]["c"]
    due = storage.query("SELECT COUNT(*) c FROM tasks WHERE done = 0 AND due LIKE ?", (today + "%",))[0]["c"]
    rem = storage.query("SELECT COUNT(*) c FROM reminders WHERE fired = 0 AND at LIKE ?", (today + "%",))[0]["c"]

    with ThreadPoolExecutor(3) as ex:  # сеть — параллельно и с таймаутом, чтобы не задерживать приветствие
        futures = {k: ex.submit(f) for k, f in (("notion", _notion), ("mail", _mail), ("weather", _weather))}
        got = {}
        for k, f in futures.items():
            try:
                got[k] = f.result(timeout=6)
            except Exception:  # noqa: BLE001
                got[k] = None

    parts = []
    if got["weather"]:
        parts.append(f"За окном {got['weather']}")
    if tasks:
        s = f"{tasks} {_plural(tasks, 'личное дело', 'личных дела', 'личных дел')}"
        if due:
            s += f", из них на сегодня {due}"
        parts.append(s)
    if got["notion"]:
        n = got["notion"]
        parts.append(f"{n} {_plural(n, 'проект', 'проекта', 'проектов')} в работе")
    if rem:
        parts.append(f"{rem} {_plural(rem, 'напоминание', 'напоминания', 'напоминаний')} на сегодня")
    if got["mail"]:
        n = got["mail"]
        parts.append(f"{n} {_plural(n, 'новое письмо', 'новых письма', 'новых писем')}")
    return (". ".join(parts) + ".") if parts else ""
