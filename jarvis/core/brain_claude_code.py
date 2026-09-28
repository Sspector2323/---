"""Мозг Джарвиса = Claude Code на этом компьютере (работает по подписке Claude, без API-ключа).

Джарвис передаёт фразу в `claude -p`, Claude Code делает всё сам — своими инструментами
(файлы, терминал, поиск в интернете) и инструментами Джарвиса через MCP (дела, почта, звук…),
а ответ Джарвис произносит голосом. Разговор продолжается в одной сессии Claude Code.
"""
import json
import os
import subprocess
import threading
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
Почту разбирай ТОЛЬКО через mcp__jarvis__organize_email / search_email / mark_email — не пиши для этого скрипты.
Итоговый ответ всегда короткий и разговорный: его прочитают вслух."""

# Безопасное — выполняется без вопросов. Всё остальное (команды, запись файлов, выключение ПК,
# письма…) Claude Code спросит через mcp__jarvis__approve, а Джарвис — у вас голосом.
SAFE_BUILTIN = ["Read", "Glob", "Grep", "WebSearch", "WebFetch", "TodoWrite"]


# Состояние Claude Code для дашборда: ok=True/False/None (ещё не проверяли)
STATUS = {"ok": None, "note": "проверяю…", "detail": ""}
AUTH_WORDS = ("401", "authenticat", "oauth", "log in", "login", "not logged", "invalid api key")


import threading as _threading

# Никогда не запускаем два Claude Code одновременно: параллельные процессы обновляют токен входа
# наперегонки и могут его отозвать («401 OAuth access token is invalid»)
RUN_LOCK = _threading.Lock()


def run_claude(cmd, **kw):
    with RUN_LOCK:
        return subprocess.run(cmd, **kw)  # noqa: S603


TOKEN_VARS = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "CLAUDE_CODE_OAUTH_TOKEN")


def _clean_env() -> dict:
    """Окружение для Claude Code: вход по подписке (/login). Переменные с ключами/токенами перебивают
    нормальный вход и дают «401 OAuth access token is invalid», поэтому их не передаём."""
    return {k: v for k, v in os.environ.items() if k not in TOKEN_VARS}


def token_vars_in_windows() -> list[str]:
    """Какие переменные с токенами Claude заданы в Windows (они ломают вход в Claude Code)."""
    found = [k for k in TOKEN_VARS if os.environ.get(k, "").strip()]
    try:
        import winreg
        for root, key in ((winreg.HKEY_CURRENT_USER, "Environment"),
                          (winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment")):
            try:
                with winreg.OpenKey(root, key) as k:
                    for name in TOKEN_VARS:
                        try:
                            if winreg.QueryValueEx(k, name)[0] and name not in found:
                                found.append(name)
                        except OSError:
                            pass
            except OSError:
                pass
    except ImportError:
        pass
    # ключ из .env Джарвиса — это не переменная Windows, его не считаем
    from . import config
    return [n for n in found if not (n == "ANTHROPIC_API_KEY" and n in config.read_env_file() and n not in config.SHADOWED)]


def check(exe: str | None = None) -> dict:
    """Быстрая проверка: установлен ли Claude Code и вошли ли в аккаунт."""
    from .finder import find
    exe = exe or find("claude")
    if not exe:
        STATUS.update(ok=False, note="не установлен — login_claude.bat")
        return STATUS
    try:
        r = run_claude([exe, "-p", "Ответь одним словом: ок", "--output-format", "json", "--model", "haiku"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=90,
                           env=_clean_env(), cwd=Path.home())
        out = (r.stdout or "") + (r.stderr or "")
        try:
            data = json.loads(r.stdout.strip().splitlines()[-1]) if r.stdout.strip() else {}
        except json.JSONDecodeError:
            data = {}
        import re as _re
        STATUS["detail"] = _re.sub(r"\x1b\[[0-9;]*m", "", (data.get("result") if data else "") or out).strip()[-400:]
        low = STATUS["detail"].lower()
        region = any(w in low for w in ("not available in your", "unsupported_country", "unsupported country"))
        forbidden = "403" in low or "forbidden" in low
        if data and not data.get("is_error"):
            STATUS.update(ok=True, note="на связи")
        elif any(w in low for w in AUTH_WORDS):
            extra = token_vars_in_windows()
            STATUS.update(ok=False, note=("в Windows задана переменная " + ", ".join(extra) + " — она ломает вход; "
                                          "запустите login_claude.bat") if extra else
                          "вход устарел — login_claude.bat → /logout → /login")
        elif region:
            STATUS.update(ok=False, note="Anthropic не пускает из вашего региона — включите VPN в режиме TUN (для всех программ)")
        elif forbidden:
            STATUS.update(ok=False, note="доступ запрещён (403): нужен VPN для всех программ или подписка Pro/Max")

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

    def _stream(self, cmd: list) -> tuple[dict | None, str]:
        """Запускает Claude Code и по ходу разбирает его события: каждый инструмент — в «Прямой эфир»."""
        from . import activity
        with RUN_LOCK:
            proc = subprocess.Popen(cmd, cwd=self.cwd, env=_clean_env(), stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
            killer = threading.Timer(900, proc.kill)
            killer.start()
            err_lines: list[str] = []
            threading.Thread(target=lambda: err_lines.extend(proc.stderr), daemon=True).start()
            result, names = None, {}
            try:
                for line in proc.stdout:
                    try:
                        ev = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    kind = ev.get("type")
                    if kind == "assistant":
                        for block in ev.get("message", {}).get("content", []):
                            if block.get("type") == "tool_use":
                                name = block.get("name", "")
                                names[block.get("id")] = name
                                if name.endswith("__approve"):
                                    continue
                                label, detail = activity.describe(name, block.get("input"))
                                activity.emit("tool", label, detail, "claude")
                                activity.task_step()
                            elif block.get("type") == "text" and block.get("text", "").strip():
                                activity.emit("think", block["text"].strip()[:200], "", "claude")
                    elif kind == "user":
                        for block in ev.get("message", {}).get("content", []) or []:
                            if isinstance(block, dict) and block.get("type") == "tool_result" and block.get("is_error"):
                                label = activity.describe(names.get(block.get("tool_use_id"), ""), {})[0]
                                content = block.get("content")
                                text = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
                                activity.emit("error", f"{label} — не получилось", text[:600], "claude")
                    elif kind == "result":
                        result = ev
                proc.wait(timeout=30)
            finally:
                killer.cancel()
            if proc.returncode is None or (proc.returncode < 0 and result is None):
                raise subprocess.TimeoutExpired(cmd, 900)
            return result or {}, "".join(err_lines)

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
        cmd[cmd.index("json")] = "stream-json"  # поток событий: каждый шаг сразу в «Прямой эфир»
        cmd.append("--verbose")
        try:
            data, stderr = self._stream(cmd)
        except subprocess.TimeoutExpired:
            data, stderr = None, ""
            answer = "Задача заняла больше пятнадцати минут, я её остановил."
        if data is None and not stderr:
            pass
        elif not data:
            answer = "Claude Code не ответил. " + stderr[-300:]
            if any(w in stderr.lower() for w in AUTH_WORDS):
                self.down_until = time.time() + 600
                STATUS.update(ok=False, note="не выполнен вход — login_claude.bat")
                return self._fallback(text, f"{config.USER_NAME}, Claude Code без входа: запустите login_claude.bat.")
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
                    return self._fallback(text, f"{config.USER_NAME}, Claude Code разлогинился: запустите "
                                          "login_claude.bat и войдите заново.")
        storage.log("jarvis", answer)
        return answer
