"""Горячие клавиши по всей системе (работают, даже когда окно Джарвиса не в фокусе).

HOTKEY_TALK (по умолчанию Ctrl+Alt+J) — «слушаю» без слова «Джарвис».
HOTKEY_STOP (по умолчанию Ctrl+Alt+X) — замолчать и бросить текущую задачу.
Пустое значение в настройках — клавиша выключена.
"""
from . import config


def start(io) -> str:
    try:
        import keyboard
    except ImportError:
        return "нет пакета keyboard — горячие клавиши выключены (обновите Джарвиса)"
    done = []
    for combo, fn in ((config.HOTKEY_TALK, io.wake), (config.HOTKEY_STOP, io.interrupt)):
        if combo:
            try:
                keyboard.add_hotkey(combo, fn, suppress=False)
                done.append(combo)
            except Exception as e:  # noqa: BLE001
                print(f"(горячая клавиша {combo} не установилась: {e})")
    return ", ".join(done)
