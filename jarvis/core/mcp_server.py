"""MCP-сервер Джарвиса: отдаёт его умения (дела, почта, звук, ПК…) в Claude Code.

Claude Code запускает этот файл сам (см. brain_claude_code.py) и общается с ним
по протоколу MCP — строками JSON-RPC через stdin/stdout.
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.tools import load_all  # noqa: E402

# Это Claude Code умеет и сам (файлы, терминал) — не дублируем
SKIP = {"run_command", "claude_code", "list_folder", "find_files", "read_file", "write_file", "move_file", "delete_file"}
TOOLS = {n: t for n, t in load_all().items() if n not in SKIP}

APPROVE = {
    "name": "approve",
    "description": "Служебный: спрашивает у пользователя голосом разрешение на действие Claude Code.",
    "inputSchema": {"type": "object", "properties": {"tool_name": {"type": "string"}, "input": {"type": "object"},
                                                     "tool_use_id": {"type": "string"}}, "required": ["tool_name"]},
}


def ask_user(tool_name: str, tool_input: dict) -> bool:
    """Спросить разрешение через главный процесс Джарвиса (там микрофон и голос)."""
    if os.getenv("CONFIRM_DANGEROUS", "true").lower() not in ("1", "true", "yes", "да"):
        return True
    import requests
    detail = tool_input.get("command") or tool_input.get("file_path") or tool_input.get("description") \
        or json.dumps(tool_input, ensure_ascii=False)[:200]
    names = {"Bash": "выполнить команду", "PowerShell": "выполнить команду", "Write": "записать файл",
             "Edit": "изменить файл", "NotebookEdit": "изменить файл"}
    what = names.get(tool_name, TOOLS[tool_name.split("__")[-1]].description
                     if tool_name.split("__")[-1] in TOOLS else tool_name)
    try:
        r = requests.post(f"http://127.0.0.1:{os.environ['JARVIS_PORT']}/api/confirm",
                          json={"question": f"{what}: {detail}"},
                          headers={"X-Jarvis-Token": os.environ["JARVIS_TOKEN"]},
                          proxies={"http": None, "https": None}, timeout=60)
        return bool(r.json().get("ok"))
    except Exception:  # noqa: BLE001 — нет связи с Джарвисом — лучше отказать
        return False


def call(name: str, args: dict) -> tuple[str, bool]:
    if name == "approve":
        tool_input = args.get("input") or {}
        if ask_user(args.get("tool_name", ""), tool_input):
            return json.dumps({"behavior": "allow", "updatedInput": tool_input}), False
        return json.dumps({"behavior": "deny", "message": "Пользователь запретил это действие."}), False
    t = TOOLS.get(name)
    if not t:
        return f"Нет инструмента {name}", True
    try:
        return str(t.func(**args)), False
    except Exception as e:  # noqa: BLE001
        return f"Ошибка: {type(e).__name__}: {e}", True


def handle(msg: dict) -> dict | None:
    method, mid = msg.get("method"), msg.get("id")
    if mid is None:
        return None  # уведомление — ответ не нужен
    if method == "initialize":
        result = {"protocolVersion": msg.get("params", {}).get("protocolVersion", "2025-06-18"),
                  "capabilities": {"tools": {}}, "serverInfo": {"name": "jarvis", "version": "1.0"}}
    elif method == "tools/list":
        result = {"tools": [{"name": t.name, "description": t.description, "inputSchema": t.schema()["input_schema"]}
                            for t in TOOLS.values()] + [APPROVE]}
    elif method == "tools/call":
        p = msg.get("params", {})
        text, is_err = call(p.get("name", ""), p.get("arguments") or {})
        result = {"content": [{"type": "text", "text": text[:20000]}], "isError": is_err}
    elif method == "ping":
        result = {}
    else:
        return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"Unknown method {method}"}}
    return {"jsonrpc": "2.0", "id": mid, "result": result}


def main():
    stdin = open(sys.stdin.fileno(), encoding="utf-8", closefd=False)
    out = open(sys.stdout.fileno(), "w", encoding="utf-8", closefd=False)
    for line in stdin:
        if not line.strip():
            continue
        try:
            reply = handle(json.loads(line))
        except Exception as e:  # noqa: BLE001
            reply = {"jsonrpc": "2.0", "id": None, "error": {"code": -32603, "message": str(e)}}
        if reply:
            out.write(json.dumps(reply, ensure_ascii=False) + "\n")
            out.flush()


if __name__ == "__main__":
    main()
