"""Подключение Джарвиса к Cursor и Codex (MCP) и проверка, что где подключено."""
import json
import shutil
import sys
from pathlib import Path

from . import config
from .finder import find

HOME = Path.home()
SERVER = Path(__file__).resolve().with_name("mcp_server.py")
CURSOR_MCP = HOME / ".cursor" / "mcp.json"
CODEX_CFG = HOME / ".codex" / "config.toml"
CODEX_AGENTS = HOME / ".codex" / "AGENTS.md"
MARK = "<!-- jarvis -->"

RULES = f"""{MARK}
## Джарвис
Ты работаешь вместе с Джарвисом — личным ассистентом {config.USER_NAME}. Его инструменты доступны через MCP-сервер `jarvis`:
задачи и проекты в Notion (notion_tasks, notion_add_task, notion_set_status), общий штаб (notion_log),
GitHub (github_overview, github_commits), личные дела и напоминания, почта, управление компьютером.
- Когда закончишь заметную работу, запиши итог в штаб: `notion_log` («что сделано, где, что дальше»).
- Если задача из «Сводки задач» в Notion — обнови её статус.
- Обращайся к пользователю «{config.USER_NAME}», отвечай по-русски.
"""


def _entry() -> dict:
    return {"command": sys.executable, "args": [str(SERVER)], "env": {"PYTHONIOENCODING": "utf-8"}}


def _cursor_configured() -> bool:
    try:
        data = json.loads(CURSOR_MCP.read_text(encoding="utf-8-sig") or "{}")
        return "jarvis" in data.get("mcpServers", {})
    except (OSError, ValueError):
        return False


def connect_cursor() -> str:
    CURSOR_MCP.parent.mkdir(parents=True, exist_ok=True)
    data = {}
    if CURSOR_MCP.exists():
        text = CURSOR_MCP.read_text(encoding="utf-8-sig").strip()
        if text:
            CURSOR_MCP.with_suffix(".json.bak").write_text(text, encoding="utf-8")
            try:
                data = json.loads(text)
            except ValueError:
                data = {}  # файл был испорчен — копия сохранена в mcp.json.bak, начинаем заново
            if not isinstance(data, dict):
                data = {}
    data.setdefault("mcpServers", {})["jarvis"] = _entry()
    CURSOR_MCP.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    (HOME / ".cursor" / "jarvis-rules.md").write_text(RULES, encoding="utf-8")
    if not _cursor_configured():
        return f"❌ Cursor: не получилось записать {CURSOR_MCP}"
    return f"✅ Cursor: Джарвис прописан в {CURSOR_MCP}"


def connect_codex() -> str:
    CODEX_CFG.parent.mkdir(parents=True, exist_ok=True)
    cfg = CODEX_CFG.read_text(encoding="utf-8") if CODEX_CFG.exists() else ""
    if "[mcp_servers.jarvis]" not in cfg:
        # одинарные кавычки в TOML — «буквальные» строки, обратные слеши путей Windows не ломаются
        cfg = cfg.rstrip() + ("\n\n" if cfg.strip() else "") + (
            "[mcp_servers.jarvis]\n"
            f"command = '{sys.executable}'\n"
            f"args = ['{SERVER}']\n"
            "env = { PYTHONIOENCODING = \"utf-8\" }\n")
        CODEX_CFG.write_text(cfg, encoding="utf-8")
    agents = CODEX_AGENTS.read_text(encoding="utf-8") if CODEX_AGENTS.exists() else ""
    if MARK not in agents:
        CODEX_AGENTS.write_text(agents.rstrip() + ("\n\n" if agents.strip() else "") + RULES, encoding="utf-8")
    return f"✅ Codex: Джарвис прописан в {CODEX_CFG} (его читают и приложение Codex, и консольная версия)"


def telegram_item():
    from .telegram_bot import STATE, PAIR_CODE, owner
    if not config.TELEGRAM_BOT_TOKEN:
        return ("Телеграм", False, "нажмите, чтобы подключить", "/settings#g-telegram")
    if STATE["ok"] is False:
        return ("Телеграм", False, STATE["note"], "/settings#g-telegram")
    if not owner():
        return ("Телеграм", False, f"отправьте боту /start {PAIR_CODE}", "/settings#g-telegram")
    return ("Телеграм", True, STATE["note"] if STATE["username"] else "привязан",
            f"https://t.me/{STATE['username']}" if STATE["username"] else "/settings#g-telegram")


def claude_item():
    from .brain_claude_code import STATUS
    installed = bool(find("claude"))
    if not installed:
        return ("Claude Code", False, "не установлен — login_claude.bat", "/settings#g-brain")
    if STATUS["ok"] is False:
        return ("Claude Code", False, STATUS["note"], "/settings#g-brain")
    note = "мозг Джарвиса · " + STATUS["note"] if config.AI_PROVIDER == "claude_code" else "установлен"
    return ("Claude Code", bool(STATUS["ok"]) or config.AI_PROVIDER != "claude_code", note, "https://claude.ai/code")


def status() -> list[dict]:
    """Что подключено — для панели на дашборде."""
    from .tools import notion, github
    from .tools.workspace import editor_exe
    cursor_cfg = _cursor_configured()
    codex_cfg = CODEX_CFG.exists() and "[mcp_servers.jarvis]" in CODEX_CFG.read_text(encoding="utf-8", errors="ignore")
    def editor_note(installed: bool, configured: bool) -> str:
        if not installed:
            return "не установлен"
        return "Джарвис подключён" if configured else "запустите connect_editors.bat"

    has_cursor, has_codex = bool(editor_exe("cursor")), bool(find("codex"))
    if codex_cfg:
        codex_note = "Джарвис подключён" + ("" if has_codex else " · для «поручи Кодексу» нужен консольный codex")
    else:
        codex_note = "запустите connect_editors.bat"
    items = [
        claude_item(),
        ("Cursor", has_cursor and cursor_cfg, editor_note(has_cursor, cursor_cfg), "https://cursor.com"),
        ("Codex", codex_cfg, codex_note, "https://developers.openai.com/codex"),
        ("VS Code", bool(editor_exe("vscode")), "установлен" if editor_exe("vscode") else "не установлен",
         "https://code.visualstudio.com"),
        ("Notion", notion.enabled(), "подключён" if notion.enabled() else "нажмите, чтобы подключить", "/settings#g-notion"),
        ("GitHub", github.enabled(), "подключён" if github.enabled() else "нажмите, чтобы подключить", "/settings#g-github"),
        telegram_item(),
        ("Почта", bool(config.EMAIL_ADDRESS and config.EMAIL_PASSWORD),
         config.EMAIL_ADDRESS or "нажмите, чтобы подключить", "/settings#g-email"),
    ]
    return [{"name": n, "ok": ok, "note": note, "url": url} for n, ok, note, url in items]


def _wait_closed(names: tuple[str, ...]):
    """Cursor/Codex, если открыты, при закрытии перезаписывают свои настройки — просим закрыть."""
    try:
        import psutil
    except ImportError:
        return
    while True:
        running = sorted({p.info["name"] for p in psutil.process_iter(["name"])
                          if (p.info["name"] or "").lower().split(".")[0] in names})
        if not running:
            return
        print(f"⚠️ Сейчас открыты: {', '.join(running)}. Закройте их полностью (и в трее у часов), потом нажмите Enter.")
        input()


def _install_codex_cli():
    if find("codex"):
        print("✅ Консольный Codex уже установлен.")
        return
    npm = find("npm") or shutil.which("npm.cmd")
    if not npm:
        print("ℹ️ Для голосовых задач «поручи Кодексу…» нужен консольный Codex. Установите Node.js (https://nodejs.org),\n"
              "   затем снова запустите connect_editors.bat — он поставит Codex сам.")
        return
    print("Ставлю консольный Codex (npm install -g @openai/codex)…")
    import subprocess
    r = subprocess.run([npm, "install", "-g", "@openai/codex"], shell=npm.lower().endswith(".cmd"))
    if r.returncode == 0:
        print("✅ Консольный Codex установлен. Войдите в него один раз: откройте PowerShell и выполните  codex login")
    else:
        print("❌ Не получилось поставить Codex — сфотографируйте окно и пришлите Claude.")


if __name__ == "__main__":
    import shutil
    _wait_closed(("cursor", "codex"))
    print(connect_cursor())
    print(connect_codex())
    _install_codex_cli()
    try:
        import pyperclip
        pyperclip.copy(RULES.replace(MARK, "").strip())
        print("\n📋 Правила для Cursor скопированы в буфер обмена: Cursor → Settings → Rules → User Rules → вставьте (Ctrl+V).")
    except Exception:  # noqa: BLE001
        print(f"\nПравила для Cursor: {HOME / '.cursor' / 'jarvis-rules.md'} — вставьте их в Cursor → Settings → Rules.")
    print("\nГотово. Откройте Cursor и Codex — в них появится Джарвис.")
    print("В Cursor проверьте: Settings → MCP (или Tools & Integrations) → «jarvis» должен гореть зелёным.")
