"""Задачи из рабочих чатов Телеграма."""
from . import tool


@tool("chat_tasks_scan", "Проверить рабочие чаты Телеграма прямо сейчас: найти новые задачи для пользователя, "
      "записать их в Notion и поставить напоминания по срокам. Содержимое переписок вслух не пересказывай.")
def chat_tasks_scan():
    from ..tg_reader import scan
    return scan(force=True)


@tool("chat_tasks_list", "Открытые задачи, собранные из рабочих чатов (за 2 недели): что, откуда, срок.")
def chat_tasks_list():
    from ..tg_reader import open_tasks
    rows = open_tasks()
    return "\n".join(f"{r['title']} — чат «{r['chat']}»" + (f", до {r['due']}" if r["due"] else "") for r in rows) \
        or "Открытых задач из чатов нет"
