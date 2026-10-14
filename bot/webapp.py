"""Мини-приложение (Telegram Web App): раздаёт страницу webapp/index.html и небольшое API.

GET  /           — само приложение
GET  /api/feed   — последние посты из каналов, которые увидел бот
POST /api/me     — данные игрока: подписан ли он на каналы (тело запроса — Telegram initData)

Railway сам задаёт PORT. Публичный адрес (Settings → Networking → Generate Domain) нужно
указать в переменной WEBAPP_URL — по нему открываются кнопки мини-приложения в боте.
"""
import hashlib
import hmac
import json
import logging
import re
import time
from pathlib import Path
from urllib.parse import parse_qsl

from aiogram import Bot
from aiogram.types import Message
from aiohttp import web

from .repost import extract_author_text
from .sheets import SettingsStore

log = logging.getLogger(__name__)

INDEX = Path(__file__).resolve().parent.parent / "webapp" / "index.html"
FEED_KEY = "feed"
FEED_LIMIT = 30
MEMBER_STATUSES = {"creator", "administrator", "member", "restricted"}


def check_init_data(init_data: str, bot_token: str, max_age: int = 24 * 3600) -> dict | None:
    """Проверка подписи Telegram initData. Возвращает данные пользователя или None."""
    try:
        pairs = dict(parse_qsl(init_data, keep_blank_values=True, strict_parsing=True))
    except ValueError:
        return None
    received = pairs.pop("hash", "")
    check_string = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    expected = hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()
    if not received or not hmac.compare_digest(expected, received):
        return None
    if max_age and time.time() - int(pairs.get("auth_date", "0") or 0) > max_age:
        return None
    try:
        return json.loads(pairs.get("user", "{}"))
    except ValueError:
        return None


def _kind(text: str) -> str:
    low = text.lower()
    if "занос" in low or "big win" in low or "хайрол" in low or re.search(r"\bx\d+|\d+x\b", low):
        return "win"
    if "колес" in low or "розыгрыш" in low:
        return "wheel"
    if "стрим" in low or "летим" in low or "погнали" in low or "kick.com" in low:
        return "live"
    return "post"


def _post_link(message: Message) -> str:
    chat = message.chat
    if chat.username:
        return f"https://t.me/{chat.username}/{message.message_id}"
    internal = str(chat.id).removeprefix("-100")
    return f"https://t.me/c/{internal}/{message.message_id}"


class Feed:
    """Лента постов из каналов: хранится на листе «Настройки бота», переживает перезапуски."""

    def __init__(self, store: SettingsStore):
        self._store = store
        self.items: list[dict] = []

    async def load(self) -> None:
        try:
            raw = await self._store.get(FEED_KEY)
            self.items = json.loads(raw) if raw else []
        except Exception:
            log.exception("Не удалось загрузить ленту")

    async def add(self, message: Message) -> None:
        full = message.text or message.caption or ""
        text = extract_author_text(full) or full.split("\n", 1)[0]
        if not text and not (message.photo or message.video):
            return
        item = {
            "id": f"{message.chat.id}:{message.message_id}",
            "date": int(message.date.timestamp()),
            "channel": message.chat.title or message.chat.username or "",
            "text": text[:280],
            "kind": _kind(full),
            "media": bool(message.photo or message.video or message.animation),
            "link": _post_link(message),
        }
        if message.media_group_id and any(i.get("group") == message.media_group_id for i in self.items):
            return  # альбом — одна запись
        item["group"] = message.media_group_id
        self.items = [item] + [i for i in self.items if i["id"] != item["id"]]
        self.items = self.items[:FEED_LIMIT]
        try:
            await self._store.set(FEED_KEY, json.dumps(self.items, ensure_ascii=False))
        except Exception:
            log.exception("Не удалось сохранить ленту")


def create_app(bot: Bot, bot_token: str, feed: Feed, channels: dict[str, int | str]) -> web.Application:
    app = web.Application()

    async def index(_request):
        if not INDEX.exists():
            return web.Response(text="webapp/index.html не найден", status=500)
        return web.FileResponse(INDEX, headers={"Cache-Control": "no-cache"})

    async def api_feed(_request):
        return web.json_response({"items": feed.items})

    async def api_me(request):
        user = check_init_data(await request.text(), bot_token)
        if not user:
            return web.json_response({"error": "bad init data"}, status=401)
        subs = {}
        for key, chat_id in channels.items():
            try:
                member = await bot.get_chat_member(chat_id, user["id"])
                subs[key] = member.status in MEMBER_STATUSES and getattr(member, "is_member", True) is not False
            except Exception as e:
                log.warning("Не удалось проверить подписку %s на %s: %s", user.get("id"), chat_id, e)
                subs[key] = None
        return web.json_response({"user": {"id": user["id"], "first_name": user.get("first_name", "")}, "subs": subs})

    app.router.add_get("/", index)
    app.router.add_get("/api/feed", api_feed)
    app.router.add_post("/api/me", api_me)
    return app


async def start_server(app: web.Application, port: int) -> web.AppRunner:
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", port).start()
    log.info("Мини-приложение слушает порт %s", port)
    return runner
