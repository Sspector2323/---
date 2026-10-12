"""Шар Джарвиса: маленькое окно поверх всех программ в углу экрана.

Живёт отдельным процессом (окнам нужен главный поток): python -m core.orb <адрес дашборда>
Клик — «слушаю», двойной клик или Ctrl+Alt+Space — строка команды и быстрые кнопки. Шар можно перетащить.
"""
import sys

import webview

SMALL, BIG = (150, 150), (430, 600)


class Api:
    def __init__(self):
        self.window = None
        self.expanded = False

    def _place(self, w, h):
        win = self.window
        # растём вверх и влево — правый нижний угол шара остаётся на месте
        x = win.x + win.width - w
        y = win.y + win.height - h
        win.resize(w, h)
        win.move(max(0, x), max(0, y))

    def expand(self):
        if not self.expanded:
            self.expanded = True
            self._place(*BIG)
        return True

    def collapse(self):
        if self.expanded:
            self.expanded = False
            self._place(*SMALL)
        return True


def main():
    base = sys.argv[1]
    screen = webview.screens[0]
    w, h = SMALL
    api = Api()
    api.window = webview.create_window(
        "J.A.R.V.I.S.", f"{base}/orb", js_api=api, width=w, height=h,
        x=screen.x + screen.width - w - 28, y=screen.y + screen.height - h - 70,
        frameless=True, on_top=True, transparent=True, easy_drag=True, resizable=False,
        background_color="#000000")
    webview.start()


if __name__ == "__main__":
    main()
