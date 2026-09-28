"""Диагностика Джарвиса: проверяет .env на типичные ошибки и каждый сервис. Ключи не показывает.

Запуск: check_jarvis.bat  (или python -m core.doctor)
"""
import re
import sys

from . import config

KNOWN_KEYS = {
    "AI_PROVIDER", "OPENAI_API_KEY", "OPENAI_MODEL", "ANTHROPIC_API_KEY", "JARVIS_MODEL", "JARVIS_EFFORT",
    "CLAUDE_CODE_MODEL", "CLAUDE_PATH", "CODEX_PATH", "CURSOR_PATH", "CODE_PATH", "WAKE_WORDS", "TTS_VOICE",
    "TTS_ENGINE", "OPENAI_VOICE", "OFFLINE_VOICE", "USER_NAME", "GREETING", "INTRO_ANIMATION", "DASHBOARD_SCREENS",
    "MORNING_BRIEF", "CITY", "EMAIL_ADDRESS", "EMAIL_PASSWORD", "IMAP_HOST", "SMTP_HOST", "CONFIRM_DANGEROUS",
    "DASHBOARD_PORT", "NOTION_TOKEN", "NOTION_TASKS_DB", "NOTION_HUB_PAGE", "GITHUB_TOKEN", "PROJECTS_DIR",
    "EDITOR", "WORKSPACE_URLS",
}
PREFIX = {"OPENAI_API_KEY": "sk-", "ANTHROPIC_API_KEY": "sk-ant-", "NOTION_TOKEN": ("ntn_", "secret_"),
          "GITHUB_TOKEN": ("github_pat_", "ghp_")}
SECRET = {"OPENAI_API_KEY", "ANTHROPIC_API_KEY", "NOTION_TOKEN", "GITHUB_TOKEN", "EMAIL_PASSWORD"}

OK, BAD, WARN = "✅", "❌", "⚠️"


def mask(v: str) -> str:
    return (v[:6] + "…" + v[-3:]) if len(v) > 12 else "…"


def check_env() -> list[str]:
    out = []
    env = config.ROOT / ".env"
    if not env.exists():
        if (config.ROOT / ".env.txt").exists():
            return [f"{BAD} Файл сохранён как «.env.txt». Переименуйте его в «.env» (без .txt) — или сохраните в Блокноте "
                    "с типом файла «Все файлы»."]
        return [f"{BAD} Файла .env нет. Скопируйте .env.example в .env и заполните."]
    if (config.ROOT / ".env.txt").exists():
        out.append(f"{WARN} Рядом лежит «.env.txt» — Джарвис его НЕ читает. Если ключи вписывали туда, перенесите их в «.env».")
    seen = {}
    for n, line in enumerate(env.read_text(encoding="utf-8-sig").splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if "=" not in line:
            out.append(f"{WARN} Строка {n}: нет знака «=» — Джарвис её пропустит: «{line[:40]}»")
            continue
        k, v = line.split("=", 1)
        k = k.strip().removeprefix("export ").strip()
        if " " in k:
            out.append(f"{WARN} Строка {n}: пробел внутри названия «{k}» — Джарвис эту строку не поймёт.")
        if k not in KNOWN_KEYS:
            close = [x for x in KNOWN_KEYS if x.replace("_", "") == k.upper().replace("_", "")]
            out.append(f"{WARN} Строка {n}: неизвестная настройка «{k}»" + (f" — может, {close[0]}?" if close else ""))
        if k in seen:
            out.append(f"{WARN} «{k}» записан дважды (строки {seen[k]} и {n}) — действует последняя строка.")
        seen[k] = n
        raw = v.strip()
        if (raw[:1] in "\"'" and raw[-1:] != raw[:1]) or (raw[-1:] in "\"'" and raw[:1] != raw[-1:]):
            out.append(f"{BAD} {k}: кавычка открыта, но не закрыта — уберите кавычки.")
        v = raw.strip("\"'«»“” ")
        if v == "" and (k in SECRET or k == "EMAIL_ADDRESS"):
            out.append(f"○ {k}: пусто — ключ ещё не вписан (строка {n}).")
            continue
        if k in SECRET and " " in v and k != "EMAIL_PASSWORD":
            out.append(f"{BAD} {k}: внутри ключа пробел — скопируйте ключ заново целиком.")
        pre = PREFIX.get(k)
        if pre and v and not v.startswith(pre):
            out.append(f"{WARN} {k}: обычно начинается с «{pre if isinstance(pre, str) else ' или '.join(pre)}», "
                       f"а у вас «{v[:5]}…» — проверьте, то ли вставили.")
    for k in ("OPENAI_API_KEY", "NOTION_TOKEN", "GITHUB_TOKEN", "EMAIL_ADDRESS", "EMAIL_PASSWORD"):
        val = getattr(config, k, "") or ""
        import os
        val = val or os.getenv(k, "")
        out.append(f"{OK if val else '○'} {k}: {'задан (' + mask(val) + ')' if val and k in SECRET else (val or 'не задан')}")
    return out


def main():
    print("=" * 64)
    print("  Диагностика J.A.R.V.I.S.")
    print("=" * 64)
    import datetime as _dt
    env = config.ENV_FILE
    when = ""
    if env.exists():
        mins = int((_dt.datetime.now().timestamp() - env.stat().st_mtime) // 60)
        when = "только что" if mins < 1 else f"{mins} мин назад" if mins < 120 else _dt.datetime.fromtimestamp(env.stat().st_mtime).strftime("%d.%m %H:%M")
    print(f"\nФайл настроек: {env}\n  изменён: {when or '—'}  ← если вы правили .env недавно, а здесь давно — вы правите ДРУГОЙ файл")
    print(f"Мозг: {config.AI_PROVIDER}   Модель OpenAI: {config.OPENAI_MODEL}\n")
    if config.SHADOWED:
        print("⚠️ В Windows есть переменные с теми же именами (Джарвис теперь берёт значения из .env): "
              + ", ".join(config.SHADOWED) + "\n")
    print("— Файл настроек .env —")
    for line in check_env():
        print("  " + line)

    print("\n— Проверка сервисов (займёт до минуты) —")
    from .dashboard import run_test
    tests = [("claude", "Claude Code"), ("openai", "OpenAI"), ("notion", "Notion"), ("github", "GitHub"), ("email", "Почта")]
    for svc, name in tests:
        if svc == "openai" and not __import__("os").getenv("OPENAI_API_KEY"):
            print(f"  ○ {name}: ключ не задан")
            continue
        if svc == "notion" and not config.NOTION_TOKEN or svc == "github" and not config.GITHUB_TOKEN \
                or svc == "email" and not (config.EMAIL_ADDRESS and config.EMAIL_PASSWORD):
            print(f"  ○ {name}: не настроено")
            continue
        print(f"  … {name}", end="\r", flush=True)
        ok, msg = run_test(svc)
        print(f"  {OK if ok else BAD} {name}: {re.sub(r'^(Claude Code: )', '', msg)}")
        if svc == "claude" and not ok:
            from .brain_claude_code import STATUS, token_vars_in_windows
            tv = token_vars_in_windows()
            if tv:
                print(f"     {WARN} В Windows заданы {', '.join(tv)} — они перебивают вход по подписке. "
                      "Запустите login_claude.bat: он предложит их удалить.")
            if STATUS.get("detail"):
                print("     Что ответил сам Claude Code:")
                for ln in STATUS["detail"].splitlines()[-6:]:
                    print("     │ " + ln[:110])

    print("\n— Cursor и Codex —")
    from .integrations import status as istatus, CURSOR_MCP, CODEX_CFG
    for it in istatus():
        if it["name"] in ("Cursor", "Codex"):
            print(f"  {OK if it['ok'] else WARN} {it['name']}: {it['note']}")
    from .finder import find
    if not find("codex") and CODEX_CFG.exists():
        print(f"  {WARN} Codex: настройки есть, но программа codex (CLI) не найдена — голосовые задачи для Codex "
              "не заработают. Установка: npm install -g @openai/codex")
    print(f"  файлы подключения: {CURSOR_MCP}  |  {CODEX_CFG}")

    print("\n— Голос —")
    try:
        import edge_tts  # noqa: F401
        from importlib.metadata import version
        v = version("edge-tts")
        print(f"  {OK if int(v.split('.')[0]) >= 7 else WARN} edge-tts {v}" +
              ("" if int(v.split('.')[0]) >= 7 else " — устарел, запустите update_jarvis.bat"))
    except Exception:  # noqa: BLE001
        print(f"  {WARN} edge-tts не установлен — запустите update_jarvis.bat")
    try:
        import webview  # noqa: F401
        print(f"  {OK} окна на всех мониторах (pywebview) установлены")
    except Exception:  # noqa: BLE001
        print(f"  {WARN} pywebview не установлен — анимация будет в браузере. Запустите update_jarvis.bat")
    print("\nГотово. Если есть ❌ — сфотографируйте это окно (ключей в нём не видно) и пришлите Claude.")
    print("Чтобы открыть ИМЕННО этот .env в Блокноте — дважды кликните edit_env.bat")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
