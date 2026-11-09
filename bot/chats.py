"""Каналы и группы, в которых состоит бот.

Telegram не даёт боту список его чатов, а по ссылке-приглашению (t.me/+…) бот не узнает, что это за чат.
Поэтому бот запоминает чат, как только видит в нём что-нибудь: пост в канале, сообщение в группе,
добавление бота админом. Чтобы чат точно появился, достаточно написать в нём /bind
(в канале — опубликовать /bind, бот сам удалит это сообщение).
Список хранится на листе «Настройки бота» и показывается в админке /reposts.
"""
import json
import logging

from aiogram.types import Chat

from .sheets import SettingsStore

log = logging.getLogger(__name__)

KEY = "chats"
TYPE_TITLES = {"channel": "канал", "supergroup": "группа", "group": "группа"}


class ChatRegistry:
    def __init__(self, store: SettingsStore | None):
        self._store = store
        self.chats: dict[int, dict] = {}

    async def load(self) -> None:
        if not self._store:
            return
        try:
            raw = await self._store.get(KEY)
            self.chats = {int(k): v for k, v in (json.loads(raw) if raw else {}).items()}
        except Exception:
            log.exception("Не удалось загрузить список чатов")

    async def _save(self) -> None:
        if not self._store:
            return
        try:
            await self._store.set(KEY, json.dumps({str(k): v for k, v in self.chats.items()}, ensure_ascii=False))
        except Exception:
            log.exception("Не удалось сохранить список чатов")

    async def note(self, chat: Chat, is_admin: bool | None = None) -> bool:
        """Запомнить чат. Возвращает True, если он новый."""
        if chat.type not in TYPE_TITLES:
            return False
        old = self.chats.get(chat.id)
        info = {
            "title": chat.title or (old or {}).get("title") or str(chat.id),
            "type": chat.type,
            "username": chat.username or "",
            "admin": is_admin if is_admin is not None else (old or {}).get("admin", True),
        }
        if old == info:
            return False
        self.chats[chat.id] = info
        await self._save()
        return old is None

    async def forget(self, chat_id: int) -> None:
        if self.chats.pop(chat_id, None) is not None:
            await self._save()

    def title(self, chat_id: int) -> str:
        info = self.chats.get(int(chat_id))
        if not info:
            return f"чат {chat_id}"
        kind = TYPE_TITLES.get(info["type"], "чат")
        return f"{info['title']} ({kind})"

    def label(self, source: str) -> str:
        """Подпись для источника, заданного юзернеймом или id."""
        for cid, info in self.chats.items():
            if info.get("username", "").lower() == source or str(cid) == source:
                return info["title"]
        return f"@{source}" if not source.lstrip("-").isdigit() else source
