"""Отправка сообщений и файлов хозяйке в Телеграм."""
from . import S, tool


@tool("telegram_send", "Прислать пользователю сообщение в Телеграм (список, ссылку, напоминание, итог задачи).",
      {"text": S("Текст сообщения")}, ["text"])
def telegram_send(text: str):
    from ..telegram_bot import send
    return "Отправил в Телеграм" if send(text) else "Телеграм не подключён или не привязан"


@tool("telegram_send_file", "Прислать пользователю файл или картинку с компьютера в Телеграм.",
      {"path": S("Путь к файлу"), "caption": S("Подпись (необязательно)")}, ["path"])
def telegram_send_file(path: str, caption: str = ""):
    from .files import _p
    from ..telegram_bot import send_file
    return "Отправил файл в Телеграм" if send_file(str(_p(path)), caption) else "Телеграм не подключён или не привязан"
