"""Экран Джарвиса: панели на дашборде и управление видом интерфейса.

Идея из adewaskar/jarvis (MIT): то, что удобнее увидеть, чем услышать (списки, таблицы, ссылки, цифры,
картинки), Джарвис сам выводит на экран, а вслух говорит одну фразу. И может «перекрасить» интерфейс.
"""
import os
import re
import shutil
import sys
import time
import uuid
from pathlib import Path

from .. import config
from . import S, tool

COLORS = {
    "синий": "#38d9ff", "голубой": "#38d9ff", "бирюзовый": "#2ee6c5", "зелёный": "#3ddc84", "зеленый": "#3ddc84",
    "красный": "#ff3b4e", "алый": "#ff3b4e", "оранжевый": "#ff9f1c", "золотой": "#ffc940", "жёлтый": "#ffd60a",
    "желтый": "#ffd60a", "фиолетовый": "#b388ff", "пурпурный": "#e040fb", "розовый": "#ff6fb5", "белый": "#e8f1ff",
}
EFFECTS = {"pulse", "glitch", "scan", "flash", "shake"}


def _push(op: str, data: dict) -> str:
    """Внутри Джарвиса — сразу в дашборд; из Claude Code (отдельный процесс) — по HTTP с токеном запуска."""
    dash = sys.modules.get("core.dashboard")
    if dash is not None and getattr(dash, "RUNNING", False):
        return dash.screen_op(op, data)
    import requests
    token = os.getenv("JARVIS_TOKEN") or ""
    if not token:
        try:
            token = (config.DATA_DIR / ".token").read_text(encoding="utf-8").strip()
        except OSError:
            pass
    try:
        r = requests.post(f"http://127.0.0.1:{os.getenv('JARVIS_PORT', config.DASHBOARD_PORT)}/api/screen",
                          json={"op": op, "data": data}, headers={"X-Jarvis-Token": token},
                          proxies={"http": None, "https": None}, timeout=5)
        return "ok" if r.ok else f"дашборд ответил {r.status_code}"
    except Exception as e:  # noqa: BLE001
        return f"дашборд недоступен: {e}"


def stage_image(image: str) -> str:
    """Картинка для панели: ссылка https — как есть, файл с компьютера — копия в data/screen."""
    image = (image or "").strip()
    if not image:
        return ""
    if re.match(r"^https://", image):
        return image
    p = Path(os.path.expandvars(image)).expanduser()
    if p.is_file() and p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp", ".gif"):
        folder = config.DATA_DIR / "screen"
        folder.mkdir(exist_ok=True)
        name = f"{uuid.uuid4().hex}{p.suffix.lower()}"
        shutil.copy(p, folder / name)
        return f"/api/screen/img/{name}"
    return ""


def show(title: str, content: str = "", image: str = "", link: str = "", kind: str = "info",
         size: str = "normal", panel_id: str = "") -> str:
    from .documents import markdown_to_html
    data = {"id": panel_id or uuid.uuid4().hex[:10], "title": title[:140],
            "html": markdown_to_html(content or "")[:60000], "image": stage_image(image),
            "link": link if re.match(r"^https?://", link or "") else "",
            "kind": kind if kind in ("info", "ok", "warn", "error") else "info",
            "size": "wide" if size == "wide" else "normal", "at": time.strftime("%H:%M")}
    res = _push("show", data)
    return "Показано на экране." if res == "ok" else f"Не удалось показать: {res}"


@tool("show_on_screen",
      "Вывести панель на экран Джарвиса (дашборд на мониторах). Используй для всего, что удобнее увидеть, чем "
      "услышать: списки, таблицы, сравнения, ссылки, цифры, шаги инструкции, картинки, итоги поиска. Содержание — "
      "markdown (## заголовки, списки, таблицы | a | b |, **жирный**, ссылки [текст](https://…)). Вслух после "
      "этого — одна короткая фраза, не пересказывай панель.",
      {"title": S("Заголовок панели"),
       "content": S("Содержание в markdown"),
       "image": S("Картинка: ссылка https://… или путь к файлу на компьютере (скриншот, фото)"),
       "link": S("Главная ссылка панели (кнопка «Открыть»)"),
       "kind": S("Тон: info, ok (успех), warn (внимание), error", enum=["info", "ok", "warn", "error"]),
       "size": S("normal или wide (широкая — для таблиц)", enum=["normal", "wide"])},
      ["title"])
def show_on_screen(title: str, content: str = "", image: str = "", link: str = "", kind: str = "info",
                   size: str = "normal"):
    return show(title, content, image, link, kind, size)


@tool("ui_control",
      "Управлять видом интерфейса Джарвиса (дашборд и 3D-ядро): цвет подсветки (accent: синий, красный, зелёный, золотой, фиолетовый, "
      "оранжевый, розовый, белый или #hex; «обычный» — вернуть), эффект (pulse, glitch, scan, flash, shake), "
      "убрать все панели с экрана (clear=true) или сбросить всё (reset=true). Красный — тревога или важное, "
      "зелёный — всё хорошо. Применяй, когда просят, или чтобы подчеркнуть важный момент — но без злоупотребления.",
      {"accent": S("Цвет подсветки"), "effect": S("Эффект", enum=sorted(EFFECTS)),
       "reactor": S("Вид ядра на 3D-экране: sphere (сфера), ring (дуговой реактор), wire (каркас)",
                    enum=["sphere", "ring", "wire"]),
       "size": {"type": "number", "description": "Размер ядра, 0.5–2 (1 — обычный)"},
       "spin": {"type": "number", "description": "Скорость вращения, 0–3 (1 — обычная)"},
       "orbit_image": S("Картинка (https://… или файл), которая будет кружить вокруг ядра"),
       "orbit_clear": {"type": "boolean", "description": "Убрать картинки с орбиты"},
       "clear": {"type": "boolean", "description": "Убрать все панели"},
       "reset": {"type": "boolean", "description": "Вернуть интерфейс по умолчанию"}})
def ui_control(accent: str = "", effect: str = "", clear: bool = False, reset: bool = False, reactor: str = "",
               size: float | None = None, spin: float | None = None, orbit_image: str = "",
               orbit_clear: bool = False):
    if reset:
        return "Интерфейс по умолчанию." if _push("reset", {}) == "ok" else "Дашборд недоступен."
    done = []
    if clear:
        res = _push("clear", {})
        if res != "ok":
            return f"Не получилось: {res}"
        done.append("экран очищен")
    data: dict = {}
    if accent:
        a = accent.strip().lower()
        if a in ("обычный", "по умолчанию", "стандартный", "default"):
            data["accent"] = ""
        elif re.fullmatch(r"#[0-9a-f]{6}", a):
            data["accent"] = a
        elif a in COLORS:
            data["accent"] = COLORS[a]
        else:
            return f"Не знаю цвет «{accent}». Доступны: {', '.join(sorted(COLORS))} или #RRGGBB."
        done.append("цвет изменён")
    if effect:
        if effect not in EFFECTS:
            return f"Эффекты: {', '.join(sorted(EFFECTS))}."
        data["effect"] = effect
        done.append(f"эффект {effect}")
    if reactor in ("sphere", "ring", "wire"):
        data["reactor"] = reactor
        done.append("вид ядра изменён")
    if size is not None:
        data["size"] = min(2.0, max(0.5, float(size)))
        done.append("размер ядра изменён")
    if spin is not None:
        data["spin"] = min(3.0, max(0.0, float(spin)))
        done.append("скорость вращения изменена")
    if orbit_image:
        img = stage_image(orbit_image)
        if not img:
            return "Картинку не нашёл: нужна ссылка https://… или файл с компьютера."
        data["orbit_add"] = img
        done.append("картинка на орбите")
    if orbit_clear:
        data["orbit_clear"] = True
        done.append("орбита очищена")
    if data:
        res = _push("ui", data)
        if res != "ok":
            return f"Не получилось: {res}"
    return (", ".join(done) or "Ничего не изменено").capitalize() + "."
