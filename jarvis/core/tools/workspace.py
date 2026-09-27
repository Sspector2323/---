"""«Рабочая зона» (идея из Notion), проекты в VS Code / Cursor, задачи для Codex."""
import difflib
import os
import subprocess
import webbrowser
from pathlib import Path

from . import S, tool
from .. import config

GIT_BASH = r"C:\Program Files\Git\git-bash.exe"

# как называют проекты голосом → как они называются в GitHub
ALIASES = {"дайс": "dice", "таймкодер": "timecoder", "тайм": "time", "витус": "vitus", "борис": "boris",
           "арбитраж": "arbitrage", "телеграм": "telegram", "бот": "bot", "шаблон": "template",
           "пайплайн": "pipeline", "джарвис": "jarvis"}


def _projects() -> dict[str, Path]:
    root = Path(config.PROJECTS_DIR).expanduser()
    return {p.name.lower(): p for p in root.iterdir() if p.is_dir()} if root.exists() else {}


def find_project(name: str) -> Path | None:
    projects = _projects()
    words = [ALIASES.get(w, w) for w in name.lower().replace("-", " ").split()]
    norm = {k.replace("-", "").replace("_", ""): v for k, v in projects.items()}
    # больше совпавших слов (и длиннее — «bot» есть почти везде) = лучше
    scored = sorted(((sum(len(w) for w in words if w in k), k) for k in norm), reverse=True)
    match = [scored[0][1]] if scored and scored[0][0] else \
        difflib.get_close_matches("".join(words), list(norm), n=1, cutoff=0.4)
    return norm[match[0]] if match else None


def editor_exe(editor: str) -> str | None:
    """vscode → code; cursor → cursor (или Cursor.exe в стандартной папке установки)."""
    from ..finder import find
    return find("cursor" if editor == "cursor" else "code")


def _open_in(exe: str, path: Path):
    # code/cursor в PATH — это .cmd-обёртки, их запускаем через оболочку
    subprocess.Popen([exe, str(path)], shell=exe.lower().endswith((".cmd", ".bat")))


@tool("open_project", "Открыть проект (репозиторий) в редакторе и Git Bash в его папке. Понимает приблизительные "
      "названия: «таймкодер» → timecoder, «дайс бот» → Telegram-Dice-Bot. Редактор: cursor или vscode.",
      {"name": S("Название проекта"), "editor": S("Редактор (по умолчанию из настроек)", enum=["cursor", "vscode"])},
      ["name"])
def open_project(name: str, editor: str | None = None):
    if not _projects():
        return f"Папка проектов пуста ({config.PROJECTS_DIR}). Скажите «скачай все репозитории»."
    path = find_project(name)
    if not path:
        return "Не нашёл такой проект. Есть: " + ", ".join(p.name for p in _projects().values())
    editor = editor or config.EDITOR
    exe = editor_exe(editor)
    if exe:
        _open_in(exe, path)
    if os.path.exists(GIT_BASH):
        subprocess.Popen([GIT_BASH, f"--cd={path}"])
    label = "Cursor" if editor == "cursor" else "VS Code"
    return f"Открыл {path.name} в {label}" if exe else f"{label} не найден — установите его"


@tool("codex_task", "Поручить задачу Codex (агенту OpenAI для кода) в папке проекта: написать, исправить, "
      "разобраться в коде. Возвращает его отчёт.",
      {"task": S("Подробное описание задачи"), "project": S("Название проекта (необязательно)")},
      ["task"], dangerous=True)
def codex_task(task: str, project: str | None = None):
    from ..finder import find
    exe = find("codex")
    if not exe:
        return "Codex не установлен. Установка: npm install -g @openai/codex, затем codex login."
    cwd = (find_project(project) if project else None) or Path(config.PROJECTS_DIR).expanduser()
    if not cwd.exists():
        cwd = Path.home()
    r = subprocess.run([exe, "exec", "--full-auto", task], cwd=cwd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=1800)
    return (r.stdout or r.stderr).strip()[-6000:] or "Готово"


@tool("start_workspace", "Запустить рабочую зону: редактор, Railway, GitHub, Notion, Claude — всё, что нужно для работы.")
def start_workspace():
    for url in [u.strip() for u in config.WORKSPACE_URLS.split(",") if u.strip()]:
        webbrowser.open(url)
    exe = editor_exe(config.EDITOR) or editor_exe("vscode")
    root = Path(config.PROJECTS_DIR).expanduser()
    if exe and root.exists():
        _open_in(exe, root)
    return "Рабочая зона запущена"
