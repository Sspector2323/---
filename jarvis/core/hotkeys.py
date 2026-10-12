"""Горячие клавиши по всей системе (работают, даже когда окно Джарвиса не в фокусе).

HOTKEY_TALK    (Ctrl+Alt+J)     — «слушаю» без слова «Джарвис»
HOTKEY_STOP    (Ctrl+Alt+X)     — замолчать и бросить текущую задачу
HOTKEY_PALETTE (Ctrl+Alt+Space) — строка команды у шара Джарвиса: напечатать задачу
Пустое значение в настройках — клавиша выключена.
"""
from . import config


def start(wake, stop, palette=None) -> str:
    try:
        import keyboard
    except ImportError:
        return "нет пакета keyboard — горячие клавиши выключены (обновите Джарвиса)"
    done = []
    for combo, fn in ((config.HOTKEY_TALK, wake), (config.HOTKEY_STOP, stop), (config.HOTKEY_PALETTE, palette)):
        if combo and fn:
            try:
                keyboard.add_hotkey(combo, fn, suppress=False)
                done.append(combo)
            except Exception as e:  # noqa: BLE001
                print(f"(горячая клавиша {combo} не установилась: {e})")
    return ", ".join(done)
