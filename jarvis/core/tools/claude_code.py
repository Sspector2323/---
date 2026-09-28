"""Делегирование сложных задач Claude Code, если он установлен на компьютере."""
from pathlib import Path

from . import S, tool


@tool("claude_code",
      "Поручить сложную многошаговую задачу Claude Code (агенту, который сам пишет код, правит файлы, "
      "запускает команды): сделать сайт, скрипт, разобрать папку, починить проект и т.п.",
      {"task": S("Подробное описание задачи"), "folder": S("Рабочая папка, по умолчанию домашняя")},
      ["task"], dangerous=True)
def claude_code(task: str, folder: str = "~"):
    from ..finder import find
    exe = find("claude")
    if not exe:
        return ("Claude Code не установлен. Установка: Windows — `irm https://claude.ai/install.ps1 | iex` в PowerShell; "
                "Mac/Linux — `curl -fsSL https://claude.ai/install.sh | bash`.")
    from .. import config
    from ..brain_claude_code import _clean_env, mcp_config, run_claude
    cwd = Path(folder).expanduser()
    if folder in ("", "~"):  # по умолчанию — папка с результатами, а не весь домашний каталог
        cwd = Path(config.OUTPUT_DIR).expanduser()
        cwd.mkdir(parents=True, exist_ok=True)
    rules = (f"Результат — готовый файл, а не текст в ответе. Новые файлы сохраняй в {config.OUTPUT_DIR}. "
             "PDF (отчёт, план, документ) делай через mcp__jarvis__make_pdf: весь текст в content, в markdown, "
             "структурно и по делу, без воды. В конце одной-двумя фразами: что сделано и как называется файл.")
    r = run_claude([exe, "-p", task, "--permission-mode", "acceptEdits", "--append-system-prompt", rules,
                    "--mcp-config", mcp_config(),
                    "--allowedTools", "mcp__jarvis__make_pdf", "mcp__jarvis__open_file", "mcp__jarvis__telegram_send_file",
                    "Read", "Glob", "Grep", "WebSearch", "WebFetch", "Write", "Edit", "TodoWrite"],
                   cwd=cwd, env=_clean_env(), capture_output=True, text=True, timeout=1800,
                   encoding="utf-8", errors="replace")
    return (r.stdout or r.stderr).strip()[-6000:] or "Готово"
