"""Мозг Джарвиса = Claude Code на этом компьютере (работает по подписке Claude, без API-ключа).

Джарвис передаёт фразу в `claude -p`, Claude Code делает всё сам — своими инструментами
(файлы, терминал, поиск в интернете) и инструментами Джарвиса через MCP (дела, почта, звук…),
а ответ Джарвис произносит голосом. Разговор продолжается в одной сессии Claude Code.
"""
import json
import os
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


# Состояние Claude Code для дашборда: ok=True/False/None (ещё не проверяли)
STATUS = {"ok": None, "note": "проверяю…"}
AUTH_WORDS = ("401", "authenticat", "oauth", "log in", "login", "not logged", "invalid api key")


def _clean_env() -> dict:
    """Окружение для Claude Code: без пустых ANTHROPIC_* и без платного ключа — вход по подписке."""
    env = {k: v for k, v in os.environ.items()
           if not (k in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN") and not v.strip())}
    env.pop("ANTHROPIC_API_KEY", None)
    return env


def check(exe: str | None = None) -> dict:
    """Быстрая проверка: установлен ли Claude Code и вошли ли в аккаунт."""
    from .finder import find
    exe = exe or find("claude")
    if not exe:
        STATUS.update(ok=False, note="не установлен — login_claude.bat")
        return STATUS
    try:
        r = subprocess.run([exe, "-p", "Ответь одним словом: ок", "--output-format", "json", "--model", "haiku"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=90,
                           env=_clean_env(), cwd=Path.home())
        out = (r.stdout or "") + (r.stderr or "")
        data = json.loads(r.stdout.strip().splitlines()[-1]) if r.stdout.strip() else {}
        if data and not data.get("is_error"):
            STATUS.update(ok=True, note="на связи")
        elif any(w in out.lower() for w in AUTH_WORDS):
            STATUS.update(ok=False, note="не выполнен вход — login_claude.bat")
        else:
            STATUS.update(ok=False, note=(data.get("result") or out or "не отвечает")[:80])
    except Exception as e:  # noqa: BLE001
        STATUS.update(ok=False, note=f"ошибка: {e}"[:80])
    return STATUS


class ClaudeCodeBrain:
    def __init__(self, confirm: Callable[[str], bool], on_status: Callable[[str], None] = print):
        from .finder import find
        self.exe = find("claude")
        if not self.exe:
            raise RuntimeError("Claude Code не установлен. PowerShell: irm https://claude.ai/install.ps1 | iex")
        from .tools import load_all
        self.tools = load_all()
        self.on_status = on_status
        self.confirm = confirm
        self.session_id: str | None = None
        self.cwd = Path.home()
        self.down_until = 0.0  # пока Claude Code недоступен — сразу отвечаем запасным мозгом
        import threading
        threading.Thread(target=self._startup_check, daemon=True).start()

    def _startup_check(self):
        if not check(self.exe)["ok"]:
            import time
            self.down_until = time.time() + 600
            self.on_status(f"⚠ Claude Code: {STATUS['note']}. Пока отвечаю через OpenAI.")

    def reset(self):
        self.session_id = None

    def _fallback(self, text: str, problem: str) -> str:
        """Claude Code недоступен — отвечаем мозгом OpenAI (если есть ключ) и один раз говорим, что чинить."""
        if not os.getenv("OPENAI_API_KEY"):
            storage.log("jarvis", problem)
            return problem
        if not hasattr(self, "_backup"):
            from .brain_openai import OpenAIBrain
            self._backup = OpenAIBrain(confirm=self.confirm, on_status=self.on_status)
            answer = self._backup.ask(text)
            return f"{problem} Пока отвечаю через OpenAI. {answer}"
        return self._backup.ask(text)

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
        import time
        n = datetime.now()
        storage.log("user", text)
        if time.time() < self.down_until:  # не ждём заведомо недоступный Claude Code
            return self._fallback(text, f"{config.USER_NAME}, Claude Code пока без входа: запустите login_claude.bat.")
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
            env = _clean_env()
            r = subprocess.run(cmd, cwd=self.cwd, capture_output=True, text=True, encoding="utf-8",
                               errors="replace", timeout=900, env=env)
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
                if not data.get("is_error"):
                    STATUS.update(ok=True, note="на связи")
                answer = (data.get("result") or "").strip() or "Готово."
                if data.get("is_error"):
                    self.reset()
                    if any(w in answer.lower() for w in AUTH_WORDS):
                        self.down_until = time.time() + 600
                        STATUS.update(ok=False, note="не выполнен вход — login_claude.bat")
                        return self._fallback(text, f"{config.USER_NAME}, Claude Code разлогинился: откройте PowerShell, "
                                              "наберите claude и войдите заново командой слеш логин.")
        storage.log("jarvis", answer)
        return answer
