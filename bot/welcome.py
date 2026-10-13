"""Приветствие на /start и «Привет». Админ меняет его прямо из Telegram (кнопка «Сделать приветствием»)."""
import json
import logging

from aiogram import Bot
from aiogram.types import Message

from .sender import send_html, send_post, strip_html, with_retry
from .sheets import SettingsStore
from .texts import WELCOME_CAPTION, WELCOME_PHOTO

log = logging.getLogger(__name__)

KEY = "welcome"


def welcome_from_message(message: Message) -> dict:
    """Пост админа → приветствие: картинка/видео/гифка (file_id) + текст с форматированием."""
    html_text = message.html_text if (message.text or message.caption) else ""
    if message.photo:
        return {"kind": "photo", "file_id": message.photo[-1].file_id, "html": html_text}
    if message.video:
        return {"kind": "video", "file_id": message.video.file_id, "html": html_text}
    if message.animation:
        return {"kind": "animation", "file_id": message.animation.file_id, "html": html_text}
    if message.text:
        return {"kind": "text", "html": html_text}
    raise ValueError("Приветствием может быть текст, фото, видео или гифка с подписью")


class Welcome:
    def __init__(self, store: SettingsStore):
        self._store = store
        self.current: dict | None = None  # None — стандартное приветствие из texts.py

    async def load(self) -> None:
        try:
            raw = await self._store.get(KEY)
            self.current = json.loads(raw) if raw else None
        except Exception:
            log.exception("Не удалось загрузить приветствие из таблицы — будет стандартное")

    async def save(self, data: dict) -> None:
        await self._store.set(KEY, json.dumps(data, ensure_ascii=False))
        self.current = data

    async def send(self, bot: Bot, chat_id: int) -> None:
        w = self.current
        if not w:
            await send_post(bot, chat_id, WELCOME_PHOTO, WELCOME_CAPTION)
            return
        kind, html_text = w["kind"], w.get("html", "")
        if kind == "text":
            await send_html(bot, chat_id, html_text)
            return
        method = {"photo": bot.send_photo, "video": bot.send_video, "animation": bot.send_animation}[kind]
        try:
            await with_retry(lambda: method(chat_id, w["file_id"], caption=html_text or None, parse_mode="HTML"))
        except Exception as e:
            if "chat not found" in str(e).lower() or "blocked" in str(e).lower():
                raise
            # например, премиум-эмодзи, которые боту нельзя, — шлём без форматирования
            log.warning("Приветствие с форматированием не отправилось (%s), шлю без него", e)
            await with_retry(lambda: method(chat_id, w["file_id"], caption=strip_html(html_text) or None))
