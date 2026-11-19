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


def _env(name: str) -> str:
    """Значение из Railway без пробелов и кавычек (их часто копируют вместе со значением)."""
    return os.getenv(name, "").strip().strip('"').strip("'").strip()


def describe_code(sent) -> str:
    """Куда Telegram отправил код входа — человеческими словами."""
    kind = type(getattr(sent, "type", None)).__name__
    where = {
        "SentCodeTypeApp": "в приложение Telegram этого аккаунта — чат «Telegram» с синей галочкой "
                           "(на любом устройстве, где он открыт; проверь архив и закреп)",
        "SentCodeTypeSms": "по SMS на этот номер",
        "SentCodeTypeSmsWord": "по SMS на этот номер",
        "SentCodeTypeSmsPhrase": "по SMS на этот номер",
        "SentCodeTypeFirebaseSms": "по SMS на этот номер",
        "SentCodeTypeFragmentSms": "на fragment.com (номер куплен на Fragment)",
        "SentCodeTypeCall": "звонком — код продиктуют",
        "SentCodeTypeFlashCall": "звонком — код это последние цифры входящего номера",
        "SentCodeTypeMissedCall": "пропущенным звонком — код это последние цифры входящего номера",
        "SentCodeTypeEmailCode": "на почту для входа в Telegram" + (
            f" ({sent.type.email_pattern})" if getattr(sent.type, "email_pattern", "") else ""),
        "SentCodeTypeSetUpEmailRequired": "никуда: Telegram требует сначала привязать почту для входа "
                                          "(Настройки → Конфиденциальность → Почта для входа) на этом аккаунте",
    }.get(kind, "в Telegram этого аккаунта")
    nxt = type(getattr(sent, "next_type", None)).__name__
    if nxt and nxt != "NoneType":
        where += ". Если не пришёл — нажми «🔁 Прислать код ещё раз»"
    return where


class Userbot:
    def __init__(self):
        raw_id = _env("USERBOT_API_ID")
        self.api_id = int(raw_id) if raw_id.isdigit() else 0
        self.api_id_bad = bool(raw_id) and not raw_id.isdigit()
        self.api_hash = _env("USERBOT_API_HASH")
        self.session = _env("USERBOT_SESSION")
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

    async def send_phone(self, admin_id: int, phone: str) -> tuple[str, str]:
        """Запросить код. Возвращает (номер, куда Telegram отправил код)."""
        phone = "+" + "".join(ch for ch in phone if ch.isdigit())
        client = self._new_client()
        await client.connect()
        sent = await client.send_code_request(phone)
        self._login[admin_id] = {"step": "code", "client": client, "phone": phone, "hash": sent.phone_code_hash}
        return phone, describe_code(sent)

    async def resend(self, admin_id: int) -> str:
        """Отправить код другим способом (обычно SMS). Возвращает, куда он ушёл."""
        from telethon.tl.functions.auth import ResendCodeRequest
        st = self._login.get(admin_id) or {}
        if st.get("step") != "code":
            raise RuntimeError("вход не начат — /userbot")
        sent = await st["client"](ResendCodeRequest(st["phone"], st["hash"]))
        st["hash"] = sent.phone_code_hash
        return describe_code(sent)

    # ---------- вход по QR-коду (без кода из Telegram) ----------
    async def qr_start(self, admin_id: int):
        self.cancel_login(admin_id)
        client = self._new_client()
        await client.connect()
        qr = await client.qr_login()
        self._login[admin_id] = {"step": "qr", "client": client, "qr": qr}
        return qr

    async def qr_wait(self, admin_id: int, timeout: float) -> str:
        """'ok' — вошли, 'password' — нужен пароль 2FA, 'refresh' — QR устарел (новый уже создан), 'gone' — вход отменён."""
        st = self._login.get(admin_id) or {}
        qr = st.get("qr")
        if st.get("step") != "qr" or not qr:
            return "gone"
        try:
            await qr.wait(timeout=timeout)
        except asyncio.TimeoutError:
            await qr.recreate()
            return "refresh"
        except errors.SessionPasswordNeededError:
            st["step"] = "password"
            return "password"
        return await self._finish(admin_id)

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
from aiogram.types import (  # noqa: E402
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    Message,
)


def qr_png(url: str) -> bytes:
    import io
    import qrcode
    img = qrcode.make(url, box_size=10, border=3)
    out = io.BytesIO()
    img.save(out, "PNG")
    return out.getvalue()


QR_HELP = ("📷 <b>Вход по QR-коду</b>\n\n"
           "На телефоне, где открыт аккаунт-публикатор: <b>Настройки → Устройства → Подключить устройство</b> "
           "(Settings → Devices → Link Desktop Device) и наведи камеру на этот QR.\n"
           "Код обновляется каждые ~30 секунд — просто сканируй тот, что на экране.")

SETUP_HELP = (
    "🕶 <b>Аккаунт-публикатор</b> — чтобы посты в группах шли от имени группы, а не бота.\n\n"
    "1. Зайди на my.telegram.org этим аккаунтом → <b>API development tools</b> → создай приложение "
    "(название любое, платформа Other).\n"
    "2. Скопируй <b>App api_id</b> и <b>App api_hash</b> в Railway → Variables: "
    "<code>USERBOT_API_ID</code> и <code>USERBOT_API_HASH</code>.\n"
    "Если ключи уже есть (например, от другого приложения) — можно взять их.\n"
    "3. После перезапуска снова напиши /userbot — появится кнопка «🔐 Войти». Номер телефона присылай только после неё."
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

    def diagnose() -> str:
        """Чего именно не хватает — чтобы было понятно, что поправить в Railway."""
        lines = ["\n\n<b>Что видит бот сейчас:</b>"]
        if TelegramClient is None:
            lines.append("❌ библиотека Telethon не установлена (бот не пересобрался после обновления?)")
        if userbot.api_id:
            lines.append("✅ USERBOT_API_ID")
        elif userbot.api_id_bad:
            lines.append("❌ USERBOT_API_ID — должно быть только число, без букв и пробелов")
        else:
            lines.append("❌ USERBOT_API_ID — не задана (проверь название переменной)")
        lines.append("✅ USERBOT_API_HASH" if userbot.api_hash else "❌ USERBOT_API_HASH — не задана (проверь название переменной)")
        lines.append("\nПосле изменения переменных Railway перезапускает бота — подожди минуту и снова напиши /userbot.")
        return "\n".join(lines)

    @router.message(is_admin, Command("userbot"))
    async def status(message: Message):
        if not userbot.configured:
            await message.answer(SETUP_HELP + diagnose(), parse_mode="HTML")
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
            await cb.message.answer(SETUP_HELP + diagnose(), parse_mode="HTML")
            await cb.answer()
            return
        await cb.answer()
        await cb.message.answer(
            "Как войти в аккаунт-публикатор?\n\n📷 <b>По QR-коду</b> — проще всего: сканируешь с телефона, где открыт "
            "этот аккаунт, код вводить не нужно.\n📱 <b>По номеру</b> — Telegram пришлёт код.",
            parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📷 Войти по QR-коду", callback_data="ub:qr", style="primary")],
                [InlineKeyboardButton(text="📱 По номеру телефона", callback_data="ub:phone")]]))

    @router.callback_query(F.data == "ub:phone", F.from_user.id.func(lambda uid: uid in admin_ids))
    async def login_phone(cb: CallbackQuery):
        userbot.begin_login(cb.from_user.id)
        await cb.answer()
        await cb.message.answer("📱 Пришли номер телефона аккаунта, например <code>+79991234567</code>.\n"
                                "Отмена — /cancel", parse_mode="HTML")

    @router.callback_query(F.data == "ub:qr", F.from_user.id.func(lambda uid: uid in admin_ids))
    async def login_qr(cb: CallbackQuery, bot: Bot):
        uid = cb.from_user.id
        await cb.answer()
        try:
            qr = await userbot.qr_start(uid)
        except Exception as e:
            await cb.message.answer(f"⚠️ Не получилось начать вход: {e}")
            return
        cancel = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✖️ Отмена", callback_data="ub:cancel")]])
        photo = await cb.message.answer_photo(BufferedInputFile(qr_png(qr.url), "qr.png"), caption=QR_HELP,
                                              parse_mode="HTML", reply_markup=cancel)
        asyncio.create_task(_qr_loop(bot, uid, photo, cancel))

    async def _qr_loop(bot: Bot, uid: int, photo: Message, cancel) -> None:
        for _ in range(10):  # ~5 минут
            try:
                res = await userbot.qr_wait(uid, 28)
            except Exception as e:
                if userbot.login_step(uid) != "qr":  # нажали «Отмена»
                    return
                log.exception("QR-вход")
                userbot.cancel_login(uid)
                await bot.send_message(uid, f"⚠️ Вход по QR не удался: {e}\nПопробуй ещё раз: /userbot")
                return
            if res == "gone":
                return
            if res == "refresh":
                qr = (userbot._login.get(uid) or {}).get("qr")
                try:
                    await bot.edit_message_media(
                        InputMediaPhoto(media=BufferedInputFile(qr_png(qr.url), "qr.png"), caption=QR_HELP,
                                        parse_mode="HTML"),
                        chat_id=photo.chat.id, message_id=photo.message_id, reply_markup=cancel)
                except Exception:
                    pass
                continue
            try:
                await bot.delete_message(photo.chat.id, photo.message_id)
            except Exception:
                pass
            if res == "password":
                await bot.send_message(uid, "🔑 QR отсканирован! На аккаунте включена двухэтапная проверка — "
                                            "пришли пароль от неё (сообщение сразу удалю).")
            elif res == "ok":
                await done(bot, uid)
            return
        userbot.cancel_login(uid)
        await _delete(photo)
        await bot.send_message(uid, "⏱ QR-код так и не отсканировали — начни заново: /userbot")

    def resend_kb() -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🔁 Прислать код ещё раз", callback_data="ub:resend"),
            InlineKeyboardButton(text="✖️ Отмена", callback_data="ub:cancel")]])

    def code_prompt(phone: str, where: str) -> str:
        return (f"✉️ Код для {phone} отправлен {where}.\n\n"
                "Пришли его <b>цифрами через пробел</b>, например <code>1 2 3 4 5</code> — "
                "иначе Telegram посчитает, что код кому-то переслали, и отменит его.")

    @router.callback_query(F.data == "ub:resend", F.from_user.id.func(lambda uid: uid in admin_ids))
    async def resend(cb: CallbackQuery):
        try:
            where = await userbot.resend(cb.from_user.id)
        except Exception as e:
            await cb.answer()
            await cb.message.answer(f"⚠️ Не получилось отправить код ещё раз: {e}\n"
                                    "Если Telegram просит подождать — подожди указанное время и начни с /userbot.")
            return
        await cb.answer("Отправлено")
        st = userbot._login.get(cb.from_user.id) or {}
        await cb.message.answer(code_prompt(st.get("phone", ""), where), parse_mode="HTML", reply_markup=resend_kb())

    @router.callback_query(F.data == "ub:cancel", F.from_user.id.func(lambda uid: uid in admin_ids))
    async def cancel_cb(cb: CallbackQuery):
        userbot.cancel_login(cb.from_user.id)
        await cb.answer("Отменено")
        await cb.message.answer("Вход отменён. Начать заново: /userbot")

    def in_login(message: Message) -> bool:  # ждём номер, код или пароль (QR — без текста)
        return userbot.login_step(message.from_user.id) in {"phone", "code", "password"} and bool(message.text)

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
                phone, where = await userbot.send_phone(uid, text)
                await message.answer(code_prompt(phone, where), parse_mode="HTML", reply_markup=resend_kb())
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
            await done(bot, uid)
        else:
            await message.answer("⚠️ " + res)

    async def done(bot: Bot, uid: int) -> None:
        me = userbot.me
        sent = await bot.send_message(
            uid,
            f"✅ Аккаунт подключён: <b>{me.first_name}</b>. Пересылки в группы уже идут через этот аккаунт.\n\n"
            "Чтобы вход пережил перезапуски, скопируй строку ниже в Railway → Variables → "
            "<code>USERBOT_SESSION</code>. Это ключ от аккаунта — никому не показывай. "
            "Сообщение удалю через 10 минут.\n\n"
            f"<tg-spoiler><code>{userbot.session}</code></tg-spoiler>", parse_mode="HTML")
        asyncio.create_task(_delete_later(sent, 600))
        await bot.send_message(uid, "🧪 Проверка" + (await group_report() or ": групп нет"), parse_mode="HTML")

    return router


async def _delete(message) -> None:
    try:
        await message.delete()
    except Exception:
        pass


async def _delete_later(message, seconds: int) -> None:
    await asyncio.sleep(seconds)
    await _delete(message)
