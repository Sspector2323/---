"""Отправка сообщений с защитой от типичных ошибок Telegram."""
import asyncio
import logging
import re

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

log = logging.getLogger(__name__)

CAPTION_LIMIT = 1024
_TAG_RE = re.compile(r"<[^>]+>")


def build_keyboard(rows: list[list[tuple[str, str, str]]]) -> InlineKeyboardMarkup | None:
    if not rows:
        return None
    buttons = []
    for row in rows:
        line = []
        for text, kind, url in row:
            if kind == "web_app":
                line.append(InlineKeyboardButton(text=text, web_app=WebAppInfo(url=url)))
            else:
                line.append(InlineKeyboardButton(text=text, url=url))
        buttons.append(line)
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def strip_html(text: str) -> str:
    return _TAG_RE.sub("", text)


async def with_retry(factory, retries: int = 3):
    """Повтор при флуд-лимите (429 Too Many Requests)."""
    for attempt in range(retries):
        try:
            return await factory()
        except TelegramRetryAfter as e:
            if attempt == retries - 1:
                raise
            await asyncio.sleep(e.retry_after + 1)


async def send_html(bot: Bot, chat_id: int, text: str, keyboard=None):
    try:
        return await with_retry(lambda: bot.send_message(chat_id, text, parse_mode="HTML", reply_markup=keyboard))
    except TelegramBadRequest as e:
        # ИИ иногда отдаёт битый HTML (особенно если ответ обрезан по max_tokens)
        if "parse entities" not in str(e):
            raise
        log.warning("Битый HTML, отправляю без разметки: %s", e)
        return await with_retry(lambda: bot.send_message(chat_id, strip_html(text), reply_markup=keyboard))


async def send_post(bot: Bot, chat_id: int, photo: str, caption: str, keyboard=None):
    """Фото с подписью. Если картинку не удалось отправить — шлём тот же текст без фото."""
    if photo and len(caption) <= CAPTION_LIMIT:
        try:
            return await with_retry(
                lambda: bot.send_photo(chat_id, photo, caption=caption, parse_mode="HTML", reply_markup=keyboard)
            )
        except TelegramBadRequest as e:
            if "chat not found" in str(e).lower():
                raise
            log.warning("Не удалось отправить фото %s: %s — отправляю текстом", photo, e)
    return await send_html(bot, chat_id, caption, keyboard)
