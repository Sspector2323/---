"""Анимация появления Джарвиса на всех мониторах (окна Edge/Chrome во весь экран, без рамок)."""
import os
import platform
import shutil
import subprocess
import threading
import urllib.parse
from pathlib import Path

from . import config

DURATION = 9  # сек; страница закрывается сама, это — страховка


def monitors() -> list[dict]:
    """Прямоугольники всех мониторов (логические координаты Windows) — главный первым."""
    if platform.system() != "Windows":
        return [{"x": 0, "y": 0, "w": 1920, "h": 1080, "primary": True}]
    import ctypes
    from ctypes import wintypes

    class MONITORINFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                    ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]

    found = []
    proc = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(wintypes.RECT), ctypes.c_double)

    def cb(hmon, _hdc, _rect, _data):
        info = MONITORINFO()
        info.cbSize = ctypes.sizeof(MONITORINFO)
        ctypes.windll.user32.GetMonitorInfoW(ctypes.c_void_p(hmon), ctypes.byref(info))
        r = info.rcMonitor
        found.append({"x": r.left, "y": r.top, "w": r.right - r.left, "h": r.bottom - r.top,
                      "primary": bool(info.dwFlags & 1)})
        return 1

    ctypes.windll.user32.EnumDisplayMonitors(None, None, proc(cb), 0)
    found.sort(key=lambda m: (not m["primary"], m["x"]))
    return found or [{"x": 0, "y": 0, "w": 1920, "h": 1080, "primary": True}]


def _browser() -> str | None:
    candidates = [
        os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return shutil.which("msedge") or shutil.which("google-chrome") or shutil.which("chromium")


def launch(base_url: str) -> bool:
    """Показать анимацию на всех мониторах. False — если браузер не найден."""
    exe = _browser()
    if not exe:
        return False
    mons = monitors()
    procs = []
    for i, m in enumerate(mons):
        role = "main" if i == 0 else ("left" if m["x"] < mons[0]["x"] else "right")
        q = urllib.parse.urlencode({"role": role, "n": i, "total": len(mons),
                                    "name": config.USER_NAME, "greeting": config.GREETING.format(user=config.USER_NAME)})
        profile = config.DATA_DIR / "intro_profiles" / str(i)  # свой профиль = отдельное окно на своём мониторе
        profile.mkdir(parents=True, exist_ok=True)
        procs.append(subprocess.Popen([
            exe, f"--app={base_url}/intro?{q}", f"--user-data-dir={profile}",
            f"--window-position={m['x'] + 50},{m['y'] + 50}", "--window-size=800,600", "--start-fullscreen",
            "--no-first-run", "--no-default-browser-check", "--disable-extensions", "--disable-sync",
            "--autoplay-policy=no-user-gesture-required", "--hide-crash-restore-bubble",
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))

    def cleanup():
        for p in procs:
            if p.poll() is None:
                p.terminate()
    threading.Timer(DURATION + 3, cleanup).start()
    return True


if __name__ == "__main__":  # быстрый просмотр: python -m core.intro (Джарвис должен быть запущен)
    print(monitors())
    launch(f"http://localhost:{config.DASHBOARD_PORT}")
