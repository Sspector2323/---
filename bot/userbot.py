"""Аккаунт-публикатор: обычный аккаунт Telegram, через который бот пересылает посты в группы.

Бот в группе всегда пишет от своего имени — даже если ему включить «Анонимность». А сообщения
админа-человека с «Анонимностью» Telegram подписывает названием группы. Поэтому посты в группы
бот отправляет руками этого аккаунта: пересылка «без автора» (drop_author) — как копия, без «Переслано из…»,
с текстом, форматированием, медиа, кнопками-ссылками и альбомами.

Настройка (один раз):
  1. my.telegram.org → войти этим аккаунтом → API development tools → создать приложение →
     USERBOT_API_ID и USERBOT_API_HASH в Railway Variables.
  2. Аккаунт — админ с «Анонимностью» во всех группах, куда идут пересылки, и подписан на канал-источник.
  3. Админ пишет боту /userbot → номер → код (цифры через пробел) → пароль 2FA, если есть.
     Бот пришлёт строку сессии — вставить в Railway как USERBOT_SESSION (до перезапуска работает и без неё).
"""
import asyncio
import logging
import os

log = logging.getLogger(__name__)

try:
    from telethon import TelegramClient, errors
    from telethon.sessions import StringSession
except ImportError:  # библиотека не установлена — просто выключено
    TelegramClient = None


class Userbot:
    def __init__(self):
        self.api_id = int(os.getenv("USERBOT_API_ID", "0") or 0)
        self.api_hash = os.getenv("USERBOT_API_HASH", "").strip()
        self.session = os.getenv("USERBOT_SESSION", "").strip()
        self.client = None
        self.me = None
        self.error = ""
        self._login: dict[int, dict] = {}   # admin_id → {client, phone, hash, step}
        self._lock = asyncio.Lock()

    @property
    def configured(self) -> bool:
        return bool(TelegramClient and self.api_id and self.api_hash)

    @property
    def ready(self) -> bool:
        return bool(self.client and self.me and self.client.is_connected())

    def _new_client(self, session: str = ""):
        return TelegramClient(StringSession(session), self.api_id, self.api_hash,
                              device_model="Vitus Reposter", system_version="server", app_version="1.0")

    async def start(self) -> None:
        if not self.configured or not self.session:
            return
        try:
            client = self._new_client(self.session)
            await client.connect()
            if not await client.is_user_authorized():
                self.error = "сессия недействительна — войдите заново: /userbot"
                await client.disconnect()
                return
            await self._activate(client)
        except Exception as e:
            self.error = str(e)
            log.exception("Аккаунт-публикатор не запустился")

    async def _activate(self, client) -> None:
        self.client = client
        self.me = await client.get_me()
        await client.get_dialogs()  # чтобы знать группы и каналы по их id
        self.error = ""
        log.info("Аккаунт-публикатор: %s (@%s)", self.me.first_name, self.me.username)

    async def stop(self) -> None:
        if self.client:
            await self.client.disconnect()

    # ---------- вход через бота ----------
    def login_step(self, admin_id: int) -> str:
        return (self._login.get(admin_id) or {}).get("step", "")

    def cancel_login(self, admin_id: int) -> None:
        st = self._login.pop(admin_id, None)
        if st and st.get("client"):
            asyncio.create_task(st["client"].disconnect())

    def begin_login(self, admin_id: int) -> None:
        self.cancel_login(admin_id)
        self._login[admin_id] = {"step": "phone"}

    async def send_phone(self, admin_id: int, phone: str) -> str:
        phone = "+" + "".join(ch for ch in phone if ch.isdigit())
        client = self._new_client()
        await client.connect()
        sent = await client.send_code_request(phone)
        self._login[admin_id] = {"step": "code", "client": client, "phone": phone, "hash": sent.phone_code_hash}
        return phone

    async def send_code(self, admin_id: int, code: str) -> str:
        """Возвращает 'ok', 'password' (нужен пароль 2FA) или текст ошибки."""
        st = self._login.get(admin_id) or {}
        client = st.get("client")
        code = "".join(ch for ch in code if ch.isdigit())
        try:
            await client.sign_in(st["phone"], code, phone_code_hash=st["hash"])
        except errors.SessionPasswordNeededError:
            st["step"] = "password"
            return "password"
        except (errors.PhoneCodeInvalidError, errors.PhoneCodeExpiredError) as e:
            return "код не подошёл или устарел — начните заново: /userbot" if isinstance(e, errors.PhoneCodeExpiredError) \
                else "код неверный — пришлите ещё раз (цифры через пробел)"
        return await self._finish(admin_id)

    async def send_password(self, admin_id: int, password: str) -> str:
        st = self._login.get(admin_id) or {}
        try:
            await st["client"].sign_in(password=password)
        except errors.PasswordHashInvalidError:
            return "пароль неверный — пришлите ещё раз"
        return await self._finish(admin_id)

    async def _finish(self, admin_id: int) -> str:
        st = self._login.pop(admin_id)
        client = st["client"]
        async with self._lock:
            if self.client and self.client is not client:
                await self.client.disconnect()
            await self._activate(client)
            self.session = client.session.save()
        return "ok"

    # ---------- публикация ----------
    async def can_post(self, chat_id: int) -> bool:
        if not self.ready:
            return False
        try:
            perms = await self.client.get_permissions(chat_id, "me")
            return bool(perms.is_admin and getattr(perms, "anonymous", False))
        except Exception as e:
            log.warning("Аккаунт-публикатор: нет доступа к %s: %s", chat_id, e)
            return False

    async def is_channel(self, chat_id: int) -> bool:
        """Канал (не группа): там бот и так публикует от имени канала — аккаунт не нужен."""
        try:
            ent = await self.client.get_entity(chat_id)
            return bool(getattr(ent, "broadcast", False))
        except Exception:
            return False

    async def forward_copy(self, target: int, source: int | str, message_ids: list[int]) -> None:
        """Копия поста (без «Переслано из…»), альбом остаётся альбомом. От анонимного админа — от имени группы."""
        await self.client.forward_messages(target, message_ids, source, drop_author=True)

    async def chat_title(self, chat_id: int) -> str:
        try:
            return getattr(await self.client.get_entity(chat_id), "title", str(chat_id))
        except Exception:
            return str(chat_id)


# ---------- админка в личке бота ----------
from aiogram import Bot, F, Router  # noqa: E402
from aiogram.filters import Command  # noqa: E402
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message  # noqa: E402

SETUP_HELP = (
    "🕶 <b>Аккаунт-публикатор</b> — чтобы посты в группах шли от имени группы, а не бота.\n\n"
    "1. Зайди на my.telegram.org этим аккаунтом → <b>API development tools</b> → создай приложение "
    "(название любое, платформа Other).\n"
    "2. Скопируй <b>App api_id</b> и <b>App api_hash</b> в Railway → Variables: "
    "<code>USERBOT_API_ID</code> и <code>USERBOT_API_HASH</code>.\n"
    "3. После перезапуска снова напиши /userbot и войди в аккаунт."
)


def setup_userbot_router(userbot: Userbot, admin_ids: set[int], reposter=None, chats=None) -> Router:
    router = Router()
    is_admin = (F.chat.type == "private") & F.from_user.id.func(lambda uid: uid in admin_ids)

    def kb() -> InlineKeyboardMarkup:
        rows = [[InlineKeyboardButton(text="🔐 Войти" if not userbot.ready else "🔁 Сменить аккаунт",
                                      callback_data="ub:login", style="primary")]]
        if userbot.ready:
            rows.append([InlineKeyboardButton(text="🧪 Проверить группы", callback_data="ub:check")])
        return InlineKeyboardMarkup(inline_keyboard=rows)

    async def group_report() -> str:
        if not reposter:
            return ""
        lines = []
        for r in reposter.routes:
            if r.style != "copy":
                continue
            for t in r.targets:
                if await userbot.is_channel(t):
                    continue
                title = chats.title(t) if chats else await userbot.chat_title(t)
                ok = await userbot.can_post(t)
                r._ub_checked.pop(t, None)
                lines.append(f"{'✅' if ok else '❌'} {title}" + ("" if ok else
                             " — сделай аккаунт админом с «Анонимностью» (и проверь, что он в группе)"))
        return ("\n\n<b>Группы пересылки «как есть»:</b>\n" + "\n".join(lines)) if lines else \
            "\n\nГрупп в пересылках пока нет — выбери их в /reposts."

    @router.message(is_admin, Command("userbot"))
    async def status(message: Message):
        if not userbot.configured:
            await message.answer(SETUP_HELP, parse_mode="HTML")
            return
        if userbot.ready:
            me = userbot.me
            text = (f"🕶 Аккаунт-публикатор: <b>{me.first_name}</b>" + (f" (@{me.username})" if me.username else "") +
                    "\nПосты Профит Хаты в группы идут от его имени — а с «Анонимностью» это имя группы."
                    + await group_report())
        else:
            text = "🕶 Аккаунт-публикатор не подключён" + (f" ({userbot.error})" if userbot.error else "") + \
                   ".\nПока посты в группы отправляет бот от своего имени."
        await message.answer(text, parse_mode="HTML", reply_markup=kb())

    @router.callback_query(F.data == "ub:check", F.from_user.id.func(lambda uid: uid in admin_ids))
    async def check(cb: CallbackQuery):
        await cb.answer("Проверяю…")
        await cb.message.answer("🧪 Проверка" + (await group_report() or ": групп нет"), parse_mode="HTML")

    @router.callback_query(F.data == "ub:login", F.from_user.id.func(lambda uid: uid in admin_ids))
    async def login(cb: CallbackQuery):
        if not userbot.configured:
            await cb.message.answer(SETUP_HELP, parse_mode="HTML")
            await cb.answer()
            return
        userbot.begin_login(cb.from_user.id)
        await cb.answer()
        await cb.message.answer("📱 Пришли номер телефона аккаунта, например <code>+79991234567</code>.\n"
                                "Отмена — /cancel", parse_mode="HTML")

    def in_login(message: Message) -> bool:
        return bool(userbot.login_step(message.from_user.id)) and bool(message.text)

    @router.message(is_admin, Command("cancel"), in_login)
    async def cancel(message: Message):
        userbot.cancel_login(message.from_user.id)
        await message.answer("Вход отменён.")

    @router.message(is_admin, in_login)
    async def login_input(message: Message, bot: Bot):
        uid, text = message.from_user.id, message.text.strip()
        step = userbot.login_step(uid)
        try:
            if step == "phone":
                phone = await userbot.send_phone(uid, text)
                await message.answer(
                    f"✉️ Telegram отправил код на {phone} (в приложение Telegram этого аккаунта).\n\n"
                    "Пришли его <b>цифрами через пробел</b>, например <code>1 2 3 4 5</code> — "
                    "иначе Telegram посчитает, что код кому-то переслали, и отменит его.", parse_mode="HTML")
                return
            if step == "code":
                await _delete(message)
                res = await userbot.send_code(uid, text)
            else:
                await _delete(message)  # пароль не оставляем в чате
                res = await userbot.send_password(uid, text)
        except Exception as e:
            log.exception("Вход аккаунта-публикатора")
            userbot.cancel_login(uid)
            await message.answer(f"⚠️ Не получилось: {e}\nПопробуй ещё раз: /userbot")
            return
        if res == "password":
            await message.answer("🔑 На аккаунте включена двухэтапная проверка — пришли пароль от неё "
                                 "(сообщение сразу удалю).")
        elif res == "ok":
            me = userbot.me
            sent = await message.answer(
                f"✅ Аккаунт подключён: <b>{me.first_name}</b>. Пересылки в группы уже идут через этот аккаунт.\n\n"
                "Чтобы вход пережил перезапуски, скопируй строку ниже в Railway → Variables → "
                "<code>USERBOT_SESSION</code>. Это ключ от аккаунта — никому не показывай. "
                "Сообщение удалю через 10 минут.\n\n"
                f"<tg-spoiler><code>{userbot.session}</code></tg-spoiler>", parse_mode="HTML")
            asyncio.create_task(_delete_later(sent, 600))
            await message.answer("🧪 Проверка" + (await group_report() or ": групп нет"), parse_mode="HTML")
        else:
            await message.answer("⚠️ " + res)

    return router


async def _delete(message) -> None:
    try:
        await message.delete()
    except Exception:
        pass


async def _delete_later(message, seconds: int) -> None:
    await asyncio.sleep(seconds)
    await _delete(message)
