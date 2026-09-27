"""Подключение Джарвиса к Cursor и Codex (MCP) и проверка, что где подключено."""
import json
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


def connect_cursor() -> str:
    CURSOR_MCP.parent.mkdir(parents=True, exist_ok=True)
    data = {}
    if CURSOR_MCP.exists():
        text = CURSOR_MCP.read_text(encoding="utf-8").strip()
        if text:
            data = json.loads(text)
            CURSOR_MCP.with_suffix(".json.bak").write_text(text, encoding="utf-8")
    data.setdefault("mcpServers", {})["jarvis"] = _entry()
    CURSOR_MCP.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    (HOME / ".cursor" / "jarvis-rules.md").write_text(RULES, encoding="utf-8")
    return f"Cursor: Джарвис прописан в {CURSOR_MCP}"


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
    return f"Codex: Джарвис прописан в {CODEX_CFG} и {CODEX_AGENTS}"


def status() -> list[dict]:
    """Что подключено — для панели на дашборде."""
    from .tools import notion, github
    from .tools.workspace import editor_exe
    cursor_cfg = CURSOR_MCP.exists() and '"jarvis"' in CURSOR_MCP.read_text(encoding="utf-8", errors="ignore")
    codex_cfg = CODEX_CFG.exists() and "[mcp_servers.jarvis]" in CODEX_CFG.read_text(encoding="utf-8", errors="ignore")
    def editor_note(installed: bool, configured: bool) -> str:
        if not installed:
            return "не установлен"
        return "Джарвис подключён" if configured else "запустите connect_editors.bat"

    has_cursor, has_codex = bool(editor_exe("cursor")), bool(find("codex"))
    items = [
        ("Claude Code", bool(find("claude")), "мозг Джарвиса" if config.AI_PROVIDER == "claude_code" else "установлен",
         "https://claude.ai/code"),
        ("Cursor", has_cursor and cursor_cfg, editor_note(has_cursor, cursor_cfg), "https://cursor.com"),
        ("Codex", has_codex and codex_cfg, editor_note(has_codex, codex_cfg), "https://developers.openai.com/codex"),
        ("VS Code", bool(editor_exe("vscode")), "установлен" if editor_exe("vscode") else "не установлен",
         "https://code.visualstudio.com"),
        ("Notion", notion.enabled(), "подключён" if notion.enabled() else "нужен секрет в настройках", "/settings"),
        ("GitHub", github.enabled(), "подключён" if github.enabled() else "нужен токен в настройках", "/settings"),
        ("Почта", bool(config.EMAIL_ADDRESS and config.EMAIL_PASSWORD),
         config.EMAIL_ADDRESS or "не настроена", "/settings"),
    ]
    return [{"name": n, "ok": ok, "note": note, "url": url} for n, ok, note, url in items]


if __name__ == "__main__":
    print(connect_cursor())
    print(connect_codex())
    try:
        import pyperclip
        pyperclip.copy(RULES.replace(MARK, "").strip())
        print("\nПравила для Cursor скопированы в буфер обмена: Cursor → Settings → Rules → User Rules → вставьте (Ctrl+V).")
    except Exception:  # noqa: BLE001
        print(f"\nПравила для Cursor: {HOME / '.cursor' / 'jarvis-rules.md'} — вставьте их в Cursor → Settings → Rules.")
    print("Перезапустите Cursor и Codex — в них появится Джарвис.")
