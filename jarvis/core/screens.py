"""Окна Джарвиса на всех мониторах: анимация появления → дашборд, разложенный по экранам.

Запускается отдельным процессом (окнам нужен главный поток):
    python -m core.screens <адрес дашборда> <intro|dash|intro+dash>
Окна — настоящие окна Windows (движок WebView2), не вкладки браузера.
"""
import sys
import threading
import time
import urllib.parse

import webview

from . import config

INTRO_SECONDS = 8.6


def ordered_screens() -> list[tuple[str, object]]:
    """[(роль, экран)]: главный — тот, что в точке (0,0); левее него — left, правее — right."""
    screens = list(webview.screens)
    main = next((s for s in screens if s.x == 0 and s.y == 0), screens[0])
    roles = [("main", main)]
    for s in sorted((s for s in screens if s is not main), key=lambda s: s.x):
        roles.append(("left" if s.x < main.x else "right", s))
    return roles


class Api:
    """Вызывается из страницы анимации: клик/клавиша — пропустить."""
    def __init__(self):
        self.skip_event = threading.Event()

    def skip(self):
        self.skip_event.set()


def main():
    base, mode = sys.argv[1], (sys.argv[2] if len(sys.argv) > 2 else "intro+dash")
    screens = ordered_screens()
    api = Api()
    intros = []
    if "intro" in mode:
        greeting = config.GREETING.format(user=config.USER_NAME)
        for i, (role, s) in enumerate(screens):
            q = urllib.parse.urlencode({"role": role, "n": i, "name": config.USER_NAME, "greeting": greeting})
            intros.append(webview.create_window(
                "J.A.R.V.I.S.", f"{base}/intro?{q}", screen=s, fullscreen=True, frameless=True, on_top=True,
                background_color="#01040a", js_api=api, focus=role == "main"))

    views = {"main": "all", "left": "work", "right": "life"}

    def open_dashboards():
        if "dash" not in mode or config.DASHBOARD_SCREENS == "off":
            return
        for role, s in screens:
            if config.DASHBOARD_SCREENS == "main" and role != "main":
                continue
            title = "J.A.R.V.I.S." if role == "main" else f"J.A.R.V.I.S. · {'работа' if role == 'left' else 'личное'}"
            webview.create_window(title, f"{base}/?view={views[role]}", screen=s, maximized=True,
                                  background_color="#03070d")

    def timeline():
        api.skip_event.wait(INTRO_SECONDS)
        open_dashboards()  # дашборды появляются под анимацией, потом она гаснет — без «мигания»
        time.sleep(0.4)
        for w in intros:
            w.destroy()

    if intros:
        webview.start(timeline)
    else:
        open_dashboards()
        webview.start()


if __name__ == "__main__":
    main()
