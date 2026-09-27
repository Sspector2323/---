"""Поиск установленных программ, даже если окно Джарвиса запущено со старым PATH.

После установки программы Windows обновляет PATH только для НОВЫХ окон. Поэтому
сначала смотрим свежий PATH из реестра, потом — стандартные папки установки.
"""
import os
import platform
import shutil

from . import config


def _fresh_path() -> str:
    """Актуальный PATH из реестра Windows (пользовательский + системный)."""
    if platform.system() != "Windows":
        return os.environ.get("PATH", "")
    import winreg
    parts = []
    for root, key in ((winreg.HKEY_CURRENT_USER, "Environment"),
                      (winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment")):
        try:
            with winreg.OpenKey(root, key) as k:
                parts.append(os.path.expandvars(winreg.QueryValueEx(k, "Path")[0]))
        except OSError:
            pass
    return os.pathsep.join(parts + [os.environ.get("PATH", "")])


KNOWN = {
    "claude": [r"%USERPROFILE%\.local\bin\claude.exe", r"%LOCALAPPDATA%\Microsoft\WinGet\Links\claude.exe",
               r"%APPDATA%\npm\claude.cmd", "~/.local/bin/claude", "/usr/local/bin/claude", "/opt/homebrew/bin/claude"],
    "codex": [r"%APPDATA%\npm\codex.cmd", r"%LOCALAPPDATA%\Microsoft\WinGet\Links\codex.exe", "~/.local/bin/codex"],
    "cursor": [r"%LOCALAPPDATA%\Programs\cursor\resources\app\bin\cursor.cmd", r"%LOCALAPPDATA%\Programs\cursor\Cursor.exe"],
    "code": [r"%LOCALAPPDATA%\Programs\Microsoft VS Code\bin\code.cmd", r"%ProgramFiles%\Microsoft VS Code\bin\code.cmd"],
}


def find(name: str) -> str | None:
    override = os.getenv(f"{name.upper()}_PATH", "").strip()  # можно указать путь вручную в .env
    if override and os.path.exists(override):
        return override
    found = shutil.which(name) or shutil.which(name, path=_fresh_path())
    if found:
        return found
    for c in KNOWN.get(name, []):
        p = os.path.expanduser(os.path.expandvars(c))
        if os.path.exists(p):
            return p
    return None
