"""Автопересылка постов из канала Витуса (SOURCE_CHANNEL, по умолчанию @vtss2) в наш канал (PROMO_CHANNEL_ID).

Бот видит посты канала, только если он добавлен туда администратором (права можно все выключить).
Из поста остаются медиа (фото / видео / альбом) и первые строки автора, служебный блок
со ссылками заменяется нашей подписью MOMENT_FOOTER.

REPOST_MODE:
  auto    — публиковать сразу (по умолчанию);
  approve — сначала прислать админам превью с кнопками «Опубликовать / Как стрим / Пропустить»;
  off     — выключено.
"""
import asyncio
import html
import itertools
import json
import logging
import re
from dataclasses import dataclass, field

from aiogram import Bot
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaDocument,
    InputMediaPhoto,
    InputMediaVideo,
    Message,
)

from .sender import CAPTION_LIMIT, build_keyboard, send_html, with_retry
from .texts import BOILERPLATE_MARKERS, MOMENT_FOOTER, MOMENT_KEYBOARD, STREAM_CAPTION, STREAM_KEYBOARD

log = logging.getLogger(__name__)

ALBUM_WAIT = 2.0  # сколько ждать остальные части альбома, сек
TEXT_LIMIT = 4096
_URL_RE = re.compile(r"https?://|t\.me/|www\.", re.IGNORECASE)
_LEADING_JUNK_RE = re.compile(r"^[\W_]+", re.UNICODE)


def extract_author_text(text: str) -> str:
    """Первые строки поста — до служебного блока (строка со ссылкой или маркером из BOILERPLATE_MARKERS)."""
    kept: list[str] = []
    for line in (text or "").splitlines():
        normalized = _LEADING_JUNK_RE.sub("", line).strip().lower()
        if _URL_RE.search(line) or any(normalized.startswith(m) for m in BOILERPLATE_MARKERS):
            break
        kept.append(line.rstrip())
    return "\n".join(kept).strip()


def build_caption(kind: str, author_text: str, limit: int) -> tuple[str, list]:
    if kind == "stream":
        return STREAM_CAPTION, STREAM_KEYBOARD
    if not author_text:
        return MOMENT_FOOTER, MOMENT_KEYBOARD
    room = limit - len(MOMENT_FOOTER) - 2
    author = author_text if len(author_text) <= room else author_text[: max(room - 1, 0)].rstrip() + "…"
    return f"{html.escape(author)}\n\n{MOMENT_FOOTER}", MOMENT_KEYBOARD


@dataclass
class SourcePost:
    chat_id: int
    messages: list[Message] = field(default_factory=list)

    @property
    def text(self) -> str:
        for m in self.messages:
            if m.caption or m.text:
                return m.caption or m.text
        return ""

    @property
    def is_album(self) -> bool:
        return len(self.messages) > 1

    @property
    def has_media(self) -> bool:
        return any(m.photo or m.video or m.animation or m.document or m.audio for m in self.messages)


def _album_item(m: Message, caption: str | None):
    kw = {"caption": caption, "parse_mode": "HTML"} if caption else {}
    if m.photo:
        return InputMediaPhoto(media=m.photo[-1].file_id, **kw)
    if m.video:
        return InputMediaVideo(media=m.video.file_id, **kw)
    if m.document:
        return InputMediaDocument(media=m.document.file_id, **kw)
    return None


async def publish(bot: Bot, post: SourcePost, target: int, kind: str = "moment") -> None:
    author = extract_author_text(post.text)
    if post.is_album:
        caption, _ = build_caption(kind, author, CAPTION_LIMIT)
        items = [it for it in (_album_item(m, None) for m in post.messages) if it]
        if items:
            items[0] = _album_item(post.messages[0], caption) or items[0]
            await with_retry(lambda: bot.send_media_group(target, items))
            return
    if post.has_media:
        caption, kb = build_caption(kind, author, CAPTION_LIMIT)
        msg = post.messages[0]
        await with_retry(
            lambda: bot.copy_message(
                target, post.chat_id, msg.message_id,
                caption=caption, parse_mode="HTML", reply_markup=build_keyboard(kb),
            )
        )
        return
    text, kb = build_caption(kind, author, TEXT_LIMIT)
    await send_html(bot, target, text, build_keyboard(kb))


async def publish_copy(bot: Bot, post: SourcePost, target: int) -> None:
    """Пост «как есть»: текст, форматирование, медиа, альбом и кнопки — без пометки «переслано»."""
    ids = [m.message_id for m in post.messages]
    if len(ids) == 1:
        await with_retry(lambda: bot.copy_message(target, post.chat_id, ids[0]))
    else:
        await with_retry(lambda: bot.copy_messages(target, post.chat_id, ids))


_job_ids = itertools.count(1)  # общий счётчик: id заявок не пересекаются между пересылками

STYLE_TITLES = {"vitus": "с нашей подписью", "copy": "как есть"}
MODE_TITLES = {"auto": "сразу", "approve": "после проверки админом", "off": "выключена"}


class Reposter:
    """Одна пересылка: канал-источник → один или несколько каналов/групп.

    style «vitus» — фраза автора + наша подпись (канал Витуса → ВИТУС);
    style «copy»  — пост целиком, как в оригинале.
    """

    def __init__(self, source: str, targets, mode: str, admin_ids: set[int],
                 style: str = "vitus", title: str = "Канал Витуса", key: str = "vitus"):
        self.source = str(source).lstrip("@").lower()
        self.targets: list[int] = [targets] if isinstance(targets, int) else [int(t) for t in targets]
        self.mode = mode if mode in {"auto", "approve", "off"} else "auto"
        self.admin_ids = admin_ids
        self.style = style if style in STYLE_TITLES else "vitus"
        self.title = title
        self.key = key
        self._albums: dict[str, SourcePost] = {}
        self._pending: dict[int, SourcePost] = {}
        self._tasks: set[asyncio.Task] = set()

    @property
    def target(self) -> int:
        return self.targets[0] if self.targets else 0

    def is_source(self, message: Message) -> bool:
        chat = message.chat
        return bool(self.source) and (
            (chat.username or "").lower() == self.source or str(chat.id) == self.source
        )

    async def on_channel_post(self, message: Message, bot: Bot) -> None:
        if self.mode == "off" or not self.targets or not self.is_source(message) or message.chat.id in self.targets:
            return
        if not (message.text or message.caption or message.photo or message.video or message.animation
                or message.document or message.audio or message.voice or message.video_note or message.poll):
            return  # служебные сообщения (закреп, смена названия и т.п.)

        if message.media_group_id:
            post = self._albums.get(message.media_group_id)
            if post:
                post.messages.append(message)
                return
            self._albums[message.media_group_id] = SourcePost(message.chat.id, [message])
            self._spawn(self._flush_album(message.media_group_id, bot))
            return
        await self._handle(SourcePost(message.chat.id, [message]), bot)

    def _spawn(self, coro) -> None:
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _flush_album(self, group_id: str, bot: Bot) -> None:
        await asyncio.sleep(ALBUM_WAIT)
        post = self._albums.pop(group_id, None)
        if post:
            post.messages.sort(key=lambda m: m.message_id)
            await self._handle(post, bot)

    async def _publish(self, bot: Bot, post: SourcePost, target: int, kind: str = "moment") -> None:
        if self.style == "copy":
            await publish_copy(bot, post, target)
        else:
            await publish(bot, post, target, kind=kind)

    async def _publish_all(self, bot: Bot, post: SourcePost, kind: str = "moment") -> list[str]:
        errors = []
        for target in self.targets:
            try:
                await self._publish(bot, post, target, kind)
            except Exception as e:
                log.exception("Пересылка «%s»: не удалось отправить в %s", self.title, target)
                errors.append(f"{target}: {e}")
        return errors

    async def _handle(self, post: SourcePost, bot: Bot) -> None:
        if self.mode == "auto":
            errors = await self._publish_all(bot, post)
            log.info("Пересылка «%s»: пост %s → %s", self.title, post.messages[0].message_id, self.targets)
            if errors:
                await self._notify_admins(bot, f"⚠️ Пересылка «{self.title}»: не удалось отправить пост\n" + "\n".join(errors))
            return
        await self._ask_admins(post, bot)

    async def _notify_admins(self, bot: Bot, text: str, keyboard=None) -> None:
        for admin_id in self.admin_ids:
            try:
                await bot.send_message(admin_id, text, reply_markup=keyboard)
            except Exception as e:
                log.warning("Не удалось написать админу %s: %s", admin_id, e)

    async def _ask_admins(self, post: SourcePost, bot: Bot) -> None:
        job_id = next(_job_ids)
        self._pending[job_id] = post
        while len(self._pending) > 100:
            self._pending.pop(next(iter(self._pending)))
        rows = [[InlineKeyboardButton(text="✅ Опубликовать", callback_data=f"rp:{job_id}:moment")]]
        if self.style == "vitus":
            rows.append([InlineKeyboardButton(text="🔴 Опубликовать как анонс стрима", callback_data=f"rp:{job_id}:stream")])
        rows.append([InlineKeyboardButton(text="❌ Пропустить", callback_data=f"rp:{job_id}:skip")])
        for admin_id in self.admin_ids:
            try:
                await self._publish(bot, post, admin_id)  # превью ровно в том виде, как уйдёт в каналы
            except Exception as e:
                log.warning("Превью для %s не отправилось: %s", admin_id, e)
        await self._notify_admins(bot, f"👆 Новый пост: {self.title}. Публикуем?", InlineKeyboardMarkup(inline_keyboard=rows))

    def has_job(self, job_id: int) -> bool:
        return job_id in self._pending

    async def resolve(self, job_id: int, action: str, bot: Bot) -> str:
        post = self._pending.pop(job_id, None)
        if post is None:
            return "Этот пост уже обработан (или бот перезапускался)."
        if action == "skip":
            return "❌ Пропущено"
        errors = await self._publish_all(bot, post, kind=action)
        if errors:
            return "⚠️ Не везде получилось:\n" + "\n".join(errors)
        where = "в канал" if len(self.targets) == 1 else f"в {len(self.targets)} канала/группы"
        return f"✅ Опубликовано {where}" + (" как анонс стрима" if action == "stream" else "")


class RepostHub:
    """Все пересылки бота. Куда пересылать и режим админ меняет в /reposts; хранится в «Настройки бота»."""

    KEY = "routes"

    def __init__(self, routes: list[Reposter], store=None):
        self.routes = routes
        self._store = store

    def get(self, key: str) -> Reposter | None:
        return next((r for r in self.routes if r.key == key), None)

    # совместимость: лента мини-приложения и старый код спрашивают про канал Витуса
    def is_source(self, message: Message) -> bool:
        r = self.get("vitus")
        return bool(r and r.is_source(message))

    @property
    def mode(self) -> str:
        r = self.get("vitus")
        return r.mode if r else "off"

    def is_any_source(self, message: Message) -> bool:
        return any(r.is_source(message) for r in self.routes)

    async def on_channel_post(self, message: Message, bot: Bot) -> None:
        for r in self.routes:
            await r.on_channel_post(message, bot)

    async def resolve(self, job_id: int, action: str, bot: Bot) -> str:
        for r in self.routes:
            if r.has_job(job_id):
                return await r.resolve(job_id, action, bot)
        return "Этот пост уже обработан (или бот перезапускался)."

    async def load(self) -> None:
        if not self._store:
            return
        try:
            raw = await self._store.get(self.KEY)
            saved = json.loads(raw) if raw else {}
        except Exception:
            log.exception("Не удалось загрузить настройки пересылок")
            return
        for r in self.routes:
            data = saved.get(r.key) or {}
            if "targets" in data:
                r.targets = [int(t) for t in data["targets"]]
            if data.get("mode") in MODE_TITLES:
                r.mode = data["mode"]

    async def save(self) -> None:
        if not self._store:
            return
        data = {r.key: {"targets": r.targets, "mode": r.mode} for r in self.routes}
        await self._store.set(self.KEY, json.dumps(data))
