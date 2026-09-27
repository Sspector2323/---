"""Мозг Джарвиса = Claude Code на этом компьютере (работает по подписке Claude, без API-ключа).

Джарвис передаёт фразу в `claude -p`, Claude Code делает всё сам — своими инструментами
(файлы, терминал, поиск в интернете) и инструментами Джарвиса через MCP (дела, почта, звук…),
а ответ Джарвис произносит голосом. Разговор продолжается в одной сессии Claude Code.
"""
import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Callable

from . import config, dashboard, storage
from .brain import SYSTEM
from .tools.info import DAYS
from .tools.tasks import memory_text

EXTRA = """
Ты работаешь внутри Claude Code на компьютере пользователя (Windows), тебя вызывает голосовая оболочка «Джарвис».
Инструменты Джарвиса доступны как mcp__jarvis__* — используй их для задач, напоминаний, заметок, памяти,
почты, громкости, музыки, программ, питания ПК, погоды. Для файлов, команд и интернета — свои инструменты.
Итоговый ответ всегда короткий и разговорный: его прочитают вслух."""

# Безопасное — выполняется без вопросов. Всё остальное (команды, запись файлов, выключение ПК,
# письма…) Claude Code спросит через mcp__jarvis__approve, а Джарвис — у вас голосом.
SAFE_BUILTIN = ["Read", "Glob", "Grep", "WebSearch", "WebFetch", "TodoWrite"]


class ClaudeCodeBrain:
    def __init__(self, confirm: Callable[[str], bool], on_status: Callable[[str], None] = print):
        self.exe = shutil.which("claude")
        if not self.exe:
            raise RuntimeError("Claude Code не установлен. PowerShell: irm https://claude.ai/install.ps1 | iex")
        from .tools import load_all
        self.tools = load_all()
        self.on_status = on_status
        self.session_id: str | None = None
        self.cwd = Path.home()

    def reset(self):
        self.session_id = None

    def _mcp_config(self) -> str:
        return json.dumps({"mcpServers": {"jarvis": {
            "command": sys.executable,
            "args": [str(Path(__file__).with_name("mcp_server.py"))],
            "env": {"JARVIS_PORT": str(config.DASHBOARD_PORT), "JARVIS_TOKEN": dashboard.TOKEN,
                    "CONFIRM_DANGEROUS": "true" if config.CONFIRM_DANGEROUS else "false",
                    "JARVIS_HOST": "claude_code", "PYTHONIOENCODING": "utf-8"},
        }}})

    def _allowed(self) -> list[str]:
        safe_jarvis = [f"mcp__jarvis__{n}" for n, t in self.tools.items() if not t.dangerous]
        return SAFE_BUILTIN + safe_jarvis + ["mcp__jarvis__approve"]

    def ask(self, text: str) -> str:
        n = datetime.now()
        storage.log("user", text)
        system = SYSTEM.format(user=config.USER_NAME, memory=memory_text() or "пока ничего") + EXTRA
        cmd = [self.exe, "-p", f"[Сейчас {n:%Y-%m-%d %H:%M}, {DAYS[n.weekday()]}]\n{text}",
               "--output-format", "json",
               "--append-system-prompt", system,
               "--mcp-config", self._mcp_config(),
               "--allowedTools", *self._allowed(),
               "--permission-prompt-tool", "mcp__jarvis__approve"]
        if config.CLAUDE_CODE_MODEL:
            cmd += ["--model", config.CLAUDE_CODE_MODEL]
        if self.session_id:
            cmd += ["--resume", self.session_id]
        self.on_status("⚙ передаю Claude Code…")
        try:
            r = subprocess.run(cmd, cwd=self.cwd, capture_output=True, text=True, encoding="utf-8",
                               errors="replace", timeout=900)
            data = json.loads(r.stdout.strip().splitlines()[-1]) if r.stdout.strip() else {}
        except subprocess.TimeoutExpired:
            answer = "Задача заняла больше пятнадцати минут, я её остановил."
        except (json.JSONDecodeError, IndexError):
            answer = "Claude Code ответил непонятно: " + (r.stderr or r.stdout)[-300:]
        else:
            if not data:
                answer = "Claude Code не ответил. " + (r.stderr or "")[-300:]
                if "login" in (r.stderr or "").lower() or "auth" in (r.stderr or "").lower():
                    answer = "Claude Code не авторизован. Откройте PowerShell, наберите claude и войдите в аккаунт."
            else:
                self.session_id = data.get("session_id") or self.session_id
                answer = (data.get("result") or "").strip() or "Готово."
                if data.get("is_error"):
                    self.reset()
        storage.log("jarvis", answer)
        return answer
