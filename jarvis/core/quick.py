"""Мгновенные команды без нейросети — для частых простых действий (ответ < 0.1 c)."""
import re
from datetime import datetime

from .tools import system

MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа",
          "сентября", "октября", "ноября", "декабря"]
DAYS = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]


def _time():
    n = datetime.now()
    return f"{n:%H:%M}"


def _date():
    n = datetime.now()
    return f"Сегодня {DAYS[n.weekday()]}, {n.day} {MONTHS[n.month - 1]}"


def _vol(action, steps=5):
    return lambda: (system.volume(action, steps), "Готово")[1]


def _media(action):
    return lambda: (system.media_control(action), "")[1]


# (шаблон, действие). Шаблон должен совпасть со ВСЕЙ фразой — иначе команда уходит нейросети.
RULES = [
    (r"(сколько|который) (сейчас )?час\w*|сколько времени|время", _time),
    (r"как(ое|ой) (сегодня )?(число|день)|какая (сегодня )?дата", _date),
    (r"(сделай )?(погромче|громче)( пожалуйста)?", _vol("up")),
    (r"(сделай )?(потише|тише)( пожалуйста)?", _vol("down")),
    (r"(выключи|отключи) звук|без звука|заглуши", _vol("mute")),
    (r"(включи )?звук", _vol("mute")),
    (r"(поставь на )?паузу|пауза|продолжи|играй|включи музыку", _media("play_pause")),
    (r"(следующ\w+|дальше|переключи)( трек| песн\w+)?", _media("next")),
    (r"(предыдущ\w+|назад)( трек| песн\w+)?", _media("previous")),
    (r"заблокируй (компьютер|экран|комп)", lambda: (system.lock_computer(), "Блокирую")[1]),
    (r"(открой )?дашборд", lambda: (system.open_dashboard(), "Открываю")[1]),
]
_COMPILED = [(re.compile(rf"^(?:{p})$", re.I), f) for p, f in RULES]


def try_quick(command: str) -> str | None:
    """Вернуть ответ, если команда простая, иначе None."""
    text = re.sub(r"[^\w\s]", "", command.lower()).strip()
    for rx, fn in _COMPILED:
        if rx.match(text):
            try:
                return fn()
            except Exception:  # noqa: BLE001 — не вышло мгновенно, пусть разбирается нейросеть
                return None
    return None
