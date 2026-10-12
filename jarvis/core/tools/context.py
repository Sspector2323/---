"""Что сейчас перед хозяйкой: выделенный текст и активное окно — чтобы «это» в просьбе было понятно.

«Джарвис, переведи это», «сохрани это в Notion», «что это за ошибка» — сначала get_selection
(или active_window), потом действие.
"""
import time

from . import tool


@tool("get_selection",
      "Взять текст, который сейчас выделен в любой программе (копирует его и возвращает буфер обмена как был). "
      "Используй, когда говорят «это», «вот это», «выделенное».", {}, [], in_main=True)
def get_selection():
    import pyautogui
    import pyperclip
    before = pyperclip.paste()
    marker = f"__jarvis_{time.time_ns()}__"
    pyperclip.copy(marker)
    pyautogui.hotkey("ctrl", "c")
    text = ""
    for _ in range(15):
        time.sleep(0.05)
        text = pyperclip.paste()
        if text != marker:
            break
    pyperclip.copy(before)  # буфер обмена — как был
    if not text or text == marker:
        return "Ничего не выделено. Попроси выделить текст или посмотри на экран (look)."
    return text[:12000]


@tool("active_window", "Какое окно и программа сейчас на переднем плане (заголовок окна).", {}, [], in_main=True)
def active_window():
    try:
        import pygetwindow as gw
        w = gw.getActiveWindow()
        return f"Активное окно: {w.title}" if w and w.title else "Активное окно не определилось."
    except Exception as e:  # noqa: BLE001
        return f"Не удалось узнать активное окно: {e}"
