"""Notion: база «Сводка задач», поиск и чтение страниц, общий штаб Джарвиса и Claude."""
import requests

from . import S, tool
from .. import config

API = "https://api.notion.com/v1"
STATUSES = ["Не начато", "В работе", "Готово"]
PRIORITIES = {"высокий": "High", "средний": "Medium", "обычный": "Medium", "низкий": "Low"}


def enabled() -> bool:
    return bool(config.NOTION_TOKEN)


def _req(method: str, path: str, **kw) -> dict:
    if not enabled():
        raise RuntimeError("Notion не подключён: вставьте NOTION_TOKEN в ⚙ Настройках")
    r = requests.request(method, API + path, timeout=20, headers={
        "Authorization": f"Bearer {config.NOTION_TOKEN}", "Notion-Version": "2022-06-28"}, **kw)
    if r.status_code == 401:
        raise RuntimeError("Notion не принял секрет — скопируйте Internal Integration Secret целиком ещё раз")
    if r.status_code == 404:
        raise RuntimeError("Notion не видит страницу/базу: откройте её в Notion → ••• → Подключения → добавьте интеграцию Джарвиса")
    r.raise_for_status()
    return r.json()


def _title(page: dict) -> str:
    for prop in page.get("properties", {}).values():
        if prop.get("type") == "title":
            return "".join(t["plain_text"] for t in prop["title"]) or "(без названия)"
    return "(без названия)"


def _select(page: dict, name: str) -> str:
    sel = page.get("properties", {}).get(name, {}).get("select")
    return sel["name"] if sel else ""


def tasks_rows(include_done: bool = False) -> list[dict]:
    body = {"page_size": 50, "sorts": [{"timestamp": "last_edited_time", "direction": "descending"}]}
    if not include_done:
        body["filter"] = {"property": "Status", "select": {"does_not_equal": "Готово"}}
    data = _req("POST", f"/databases/{config.NOTION_TASKS_DB}/query", json=body)
    return [{"id": p["id"], "title": _title(p), "status": _select(p, "Status"), "priority": _select(p, "Priority"),
             "url": p["url"], "edited": p["last_edited_time"][:10]} for p in data["results"]]


@tool("notion_tasks", "Показать проекты и задачи из Notion-базы «Сводка задач» (по умолчанию — незавершённые).",
      {"include_done": {"type": "boolean", "description": "Включая выполненные"}})
def notion_tasks(include_done: bool = False):
    rows = tasks_rows(include_done)
    return "\n".join(f"[{r['status'] or '—'}] {r['title']} ({r['priority'] or 'без приоритета'}) id={r['id']}"
                     for r in rows) or "В Notion задач нет"


@tool("notion_add_task", "Добавить задачу/проект в Notion-базу «Сводка задач».",
      {"title": S("Название"), "status": S("Статус", enum=STATUSES),
       "priority": S("Приоритет", enum=["High", "Medium", "Low"]), "details": S("Описание (необязательно)")},
      ["title"])
def notion_add_task(title: str, status: str = "Не начато", priority: str = "Medium", details: str = ""):
    priority = PRIORITIES.get(priority.lower(), priority)
    body = {"parent": {"database_id": config.NOTION_TASKS_DB}, "properties": {
        "Project name": {"title": [{"text": {"content": title}}]},
        "Status": {"select": {"name": status}}, "Priority": {"select": {"name": priority}}}}
    if details:
        body["children"] = [{"object": "block", "type": "paragraph",
                             "paragraph": {"rich_text": [{"text": {"content": details[:1900]}}]}}]
    return f"Добавил в Notion: {_req('POST', '/pages', json=body)['url']}"


@tool("notion_set_status", "Поменять статус задачи в Notion (Не начато / В работе / Готово).",
      {"task_id": S("id задачи из notion_tasks"), "status": S("Статус", enum=STATUSES)}, ["task_id", "status"])
def notion_set_status(task_id: str, status: str):
    _req("PATCH", f"/pages/{task_id}", json={"properties": {"Status": {"select": {"name": status}}}})
    return f"Статус: {status}"


@tool("notion_search", "Найти страницы в Notion по словам.", {"query": S("Что искать")}, ["query"])
def notion_search(query: str):
    data = _req("POST", "/search", json={"query": query, "page_size": 10})
    return "\n".join(f"{_title(p) if p['object'] == 'page' else ''.join(t['plain_text'] for t in p.get('title', []))}"
                     f" — id={p['id']}" for p in data["results"]) or "Ничего не нашёл"


def _blocks_text(block_id: str, depth: int = 0) -> list[str]:
    out = []
    for b in _req("GET", f"/blocks/{block_id}/children?page_size=100")["results"]:
        rt = b.get(b["type"], {}).get("rich_text", [])
        text = "".join(t["plain_text"] for t in rt)
        prefix = {"heading_1": "# ", "heading_2": "## ", "heading_3": "### ", "bulleted_list_item": "- ",
                  "numbered_list_item": "1. ", "to_do": "☐ "}.get(b["type"], "")
        if text:
            out.append("  " * depth + prefix + text)
        if b.get("has_children") and depth < 2 and b["type"] not in ("child_page", "child_database"):
            out += _blocks_text(b["id"], depth + 1)
    return out


@tool("notion_read", "Прочитать страницу Notion целиком.", {"page_id": S("id страницы")}, ["page_id"])
def notion_read(page_id: str):
    return "\n".join(_blocks_text(page_id))[:12000] or "Страница пустая"


@tool("notion_log", "Записать строку в общий журнал «J.A.R.V.I.S. — общий штаб» в Notion "
      "(его видят и пользователь, и Claude в облаке). Пиши туда итоги важных дел.",
      {"text": S("Что записать")}, ["text"])
def notion_log(text: str):
    if not config.NOTION_HUB_PAGE:
        return "Страница штаба не указана (NOTION_HUB_PAGE в ⚙ Настройках)"
    from datetime import datetime
    _req("PATCH", f"/blocks/{config.NOTION_HUB_PAGE}/children", json={"children": [{
        "object": "block", "type": "bulleted_list_item", "bulleted_list_item": {"rich_text": [
            {"text": {"content": f"{datetime.now():%d.%m %H:%M} · Джарвис: "}, "annotations": {"bold": True}},
            {"text": {"content": text[:1800]}}]}}]})
    return "Записал в штаб Notion"
