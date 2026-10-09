"""Рассылки по базе игроков (замена ручного запуска «ЗАПУСК РАССЫЛКИ» в n8n)."""
import asyncio
import logging
from dataclasses import dataclass
from typing import Awaitable, Callable

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

from .sender import build_keyboard, send_post, with_retry
from .texts import BROADCASTS

log = logging.getLogger(__name__)


@dataclass
class BroadcastResult:
    total: int = 0
    sent: int = 0
    blocked: int = 0
    failed: int = 0

    def summary(self) -> str:
        return (
            f"✅ Рассылка завершена\n\n"
            f"Всего в базе: {self.total}\n"
            f"Доставлено: {self.sent}\n"
            f"Заблокировали бота: {self.blocked}\n"
            f"Ошибки: {self.failed}"
        )


async def run_broadcast(
    chat_ids: list[int],
    send_one: Callable[[int], Awaitable[object]],
    delay: float,
) -> BroadcastResult:
    result = BroadcastResult(total=len(chat_ids))
    for chat_id in chat_ids:
        try:
            await send_one(chat_id)
            result.sent += 1
        except TelegramForbiddenError:
            result.blocked += 1
        except TelegramBadRequest as e:
            result.failed += 1
            log.warning("Рассылка: %s — %s", chat_id, e)
        except Exception:
            result.failed += 1
            log.exception("Рассылка: ошибка для %s", chat_id)
        await asyncio.sleep(delay)
    return result


def template_sender(bot: Bot, key: str) -> Callable[[int], Awaitable[object]]:
    tpl = BROADCASTS[key]
    keyboard = build_keyboard(tpl["keyboard"])
    return lambda chat_id: send_post(bot, chat_id, tpl["photo"], tpl["caption"], keyboard)


def copy_sender(bot: Bot, from_chat_id: int, message_ids: list[int]) -> Callable[[int], Awaitable[object]]:
    """Копия поста (одно сообщение или альбом) без пометки «переслано»."""
    if len(message_ids) == 1:
        return lambda chat_id: with_retry(lambda: bot.copy_message(chat_id, from_chat_id, message_ids[0]))
    return lambda chat_id: with_retry(lambda: bot.copy_messages(chat_id, from_chat_id, message_ids))
