"""Делегирование сложных задач Claude Code, если он установлен на компьютере."""
import shutil
import subprocess
from pathlib import Path

from . import S, tool


@tool("claude_code",
      "Поручить сложную многошаговую задачу Claude Code (агенту, который сам пишет код, правит файлы, "
      "запускает команды): сделать сайт, скрипт, разобрать папку, починить проект и т.п.",
      {"task": S("Подробное описание задачи"), "folder": S("Рабочая папка, по умолчанию домашняя")},
      ["task"], dangerous=True)
def claude_code(task: str, folder: str = "~"):
    exe = shutil.which("claude")
    if not exe:
        return ("Claude Code не установлен. Установка: Windows — `irm https://claude.ai/install.ps1 | iex` в PowerShell; "
                "Mac/Linux — `curl -fsSL https://claude.ai/install.sh | bash`.")
    cwd = Path(folder).expanduser()
    r = subprocess.run([exe, "-p", task, "--permission-mode", "acceptEdits"], cwd=cwd,
                       capture_output=True, text=True, timeout=1800, encoding="utf-8", errors="replace")
    return (r.stdout or r.stderr).strip()[-6000:] or "Готово"
