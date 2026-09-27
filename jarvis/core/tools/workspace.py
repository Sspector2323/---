"""«Рабочая зона» (идея из Notion): одной командой открыть всё для работы, открыть проект в VS Code."""
import difflib
import os
import shutil
import subprocess
import webbrowser
from pathlib import Path

from . import S, tool
from .. import config

GIT_BASH = r"C:\Program Files\Git\git-bash.exe"


def _projects() -> dict[str, Path]:
    root = Path(config.PROJECTS_DIR).expanduser()
    return {p.name.lower(): p for p in root.iterdir() if p.is_dir()} if root.exists() else {}


@tool("open_project", "Открыть проект (репозиторий) в VS Code и Git Bash в его папке. Понимает приблизительные "
      "названия: «таймкодер» → timecoder, «дайс бот» → Telegram-Dice-Bot.",
      {"name": S("Название проекта")}, ["name"])
def open_project(name: str):
    projects = _projects()
    if not projects:
        return f"Папка проектов пуста ({config.PROJECTS_DIR}). Скажите «скачай все репозитории»."
    # как называют проекты голосом → как они называются в GitHub
    aliases = {"дайс": "dice", "таймкодер": "timecoder", "тайм": "time", "витус": "vitus", "борис": "boris",
               "арбитраж": "arbitrage", "телеграм": "telegram", "бот": "bot", "шаблон": "template",
               "пайплайн": "pipeline", "джарвис": "jarvis"}
    words = [aliases.get(w, w) for w in name.lower().replace("-", " ").split()]
    norm = {k.replace("-", "").replace("_", ""): v for k, v in projects.items()}
    # больше совпавших слов (и более «редких» — длинных) = лучше; «bot» есть почти везде, поэтому вес по длине
    scored = sorted(((sum(len(w) for w in words if w in k), k) for k in norm), reverse=True)
    match = [scored[0][1]] if scored and scored[0][0] else difflib.get_close_matches("".join(words), norm, n=1, cutoff=0.4)
    if not match:
        return "Не нашёл такой проект. Есть: " + ", ".join(p.name for p in projects.values())
    path = norm[match[0]]
    code = shutil.which("code")
    if code:
        subprocess.Popen([code, str(path)], shell=os.name == "nt")
    if os.path.exists(GIT_BASH):
        subprocess.Popen([GIT_BASH, f"--cd={path}"])
    return f"Открыл {path.name}" + ("" if code else " (VS Code не найден — установите его и отметьте «Add to PATH»)")


@tool("start_workspace", "Запустить рабочую зону: VS Code, Railway, GitHub, Notion, Claude — всё, что нужно для работы.")
def start_workspace():
    for url in [u.strip() for u in config.WORKSPACE_URLS.split(",") if u.strip()]:
        webbrowser.open(url)
    code = shutil.which("code")
    if code:
        subprocess.Popen([code, str(Path(config.PROJECTS_DIR).expanduser())], shell=os.name == "nt")
    return "Рабочая зона запущена"
