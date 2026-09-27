"""Работа с файлами и папками."""
import os
import shutil
from pathlib import Path

from . import I, S, tool

HOME = Path.home()


def _p(path: str) -> Path:
    shortcuts = {"рабочий стол": "Desktop", "загрузки": "Downloads", "документы": "Documents",
                 "desktop": "Desktop", "downloads": "Downloads", "documents": "Documents"}
    key = path.strip().lower()
    if key in shortcuts:
        return HOME / shortcuts[key]
    p = Path(os.path.expandvars(path)).expanduser()
    return p if p.is_absolute() else HOME / p


@tool("list_folder", "Показать содержимое папки. Понимает 'рабочий стол', 'загрузки', 'документы'.",
      {"path": S("Путь к папке")}, ["path"])
def list_folder(path: str):
    p = _p(path)
    if not p.is_dir():
        return f"Папки нет: {p}"
    items = sorted(p.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))[:100]
    return f"{p}:\n" + "\n".join(("📁 " if i.is_dir() else "📄 ") + i.name for i in items)


@tool("find_files", "Найти файлы по части имени в папке (рекурсивно).",
      {"name": S("Часть имени файла"), "folder": S("Где искать, по умолчанию домашняя папка")}, ["name"])
def find_files(name: str, folder: str = "~"):
    root = _p(folder)
    found = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not d.startswith(".") and d not in ("node_modules", "AppData", "Library")]
        for f in filenames:
            if name.lower() in f.lower():
                found.append(os.path.join(dirpath, f))
                if len(found) >= 30:
                    return "\n".join(found)
    return "\n".join(found) or "Ничего не нашёл"


@tool("read_file", "Прочитать текстовый файл.",
      {"path": S("Путь к файлу"), "max_chars": I("Сколько символов, по умолчанию 8000")}, ["path"])
def read_file(path: str, max_chars: int = 8000):
    return _p(path).read_text(encoding="utf-8", errors="replace")[:max_chars]


@tool("write_file", "Создать или перезаписать текстовый файл.",
      {"path": S("Путь к файлу"), "content": S("Содержимое")}, ["path", "content"], dangerous=True)
def write_file(path: str, content: str):
    p = _p(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return f"Сохранил {p}"


@tool("open_file", "Открыть файл или папку в программе по умолчанию.",
      {"path": S("Путь")}, ["path"])
def open_file(path: str):
    import platform
    import subprocess
    p = _p(path)
    if platform.system() == "Windows":
        os.startfile(p)  # type: ignore[attr-defined]
    else:
        subprocess.Popen(["open" if platform.system() == "Darwin" else "xdg-open", str(p)])
    return f"Открыл {p}"


@tool("move_file", "Переместить или переименовать файл/папку.",
      {"source": S("Откуда"), "destination": S("Куда")}, ["source", "destination"], dangerous=True)
def move_file(source: str, destination: str):
    return f"Перенёс в {shutil.move(str(_p(source)), str(_p(destination)))}"


@tool("delete_file", "Удалить файл или папку.", {"path": S("Путь")}, ["path"], dangerous=True)
def delete_file(path: str):
    p = _p(path)
    shutil.rmtree(p) if p.is_dir() else p.unlink()
    return f"Удалил {p}"
