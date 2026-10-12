"""Джарвис вне своих окон: шар поверх всех программ, значок в трее, уведомления Windows."""
import subprocess
import sys
import threading
import webbrowser

from . import config


def start(url: str, wake, stop, quit_fn):
    if config.ORB:
        try:
            import webview  # noqa: F401
            subprocess.Popen([sys.executable, "-m", "core.orb", url], cwd=config.ROOT)
        except Exception as e:  # noqa: BLE001
            print(f"(шар Джарвиса не запустился: {e})")
    if config.TRAY:
        threading.Thread(target=_tray, args=(url, wake, stop, quit_fn), daemon=True).start()


def _tray(url, wake, stop, quit_fn):
    try:
        import pystray
        from PIL import Image
        from .icon import icon_path
        from . import gestures
    except Exception as e:  # noqa: BLE001
        print(f"(значок в трее недоступен: {e})")
        return

    def toggle_gestures(icon, item):
        threading.Thread(target=gestures.stop if gestures.running() else gestures.start, daemon=True).start()

    menu = pystray.Menu(
        pystray.MenuItem("Говорить", lambda: wake(), default=True),
        pystray.MenuItem("Замолчать", lambda: stop()),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("3D-ядро", lambda: webbrowser.open(f"{url}/core")),
        pystray.MenuItem("Дашборд", lambda: webbrowser.open(url)),
        pystray.MenuItem("Жесты", toggle_gestures, checked=lambda item: gestures.running()),
        pystray.MenuItem("Настройки", lambda: webbrowser.open(f"{url}/settings")),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Выключить Джарвиса", lambda icon, item: (icon.stop(), quit_fn())),
    )
    icon = pystray.Icon("jarvis", Image.open(icon_path()), "J.A.R.V.I.S.", menu)
    icon.run()
