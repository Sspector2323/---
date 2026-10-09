"""Логика бота — повторяет граф n8n:

Telegram Trigger → «только личка» → запись в «База игроков» → If (/start | Привет)
    да  → «Розыгрыш» (фото)                → ждём 10 сек → «⚠️ ВАЖНО!» с кнопками
    нет → AI Agent (gpt-4o-mini + память) → «Ии-ответ»   → ждём 10 сек → «⚠️ ВАЖНО!»

Плюс админ-команды для рассылок (вместо ручного запуска в n8n).
"""
import asyncio
import itertools
import logging

from aiogram import Bot, F, Router
from aiogram.enums import ChatAction
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from .ai import AIResponder
from .broadcast import copy_sender, run_broadcast, template_sender
from .config import Config
from .sender import build_keyboard, send_html, send_post
from .repost import Reposter
from .sheets import PlayersSheet
from .texts import BROADCASTS, IMPORTANT_KEYBOARD, IMPORTANT_TEXT, WELCOME_CAPTION, WELCOME_PHOTO

log = logging.getLogger(__name__)

GREETINGS = {"Привет"}

ADMIN_HELP = (
    "<b>Админка бота</b>\n\n"
    "Просто пришли мне пост (текст, фото, видео, альбом) — я спрошу, куда его отправить: "
    "всей базе или в канал. ИИ тебе не отвечает.\n\n"
    "/broadcasts — готовые рассылки (колесо, стрим, итоги и т.д.)\n"
    "/send — ответь этой командой на любое сообщение (текст, фото, видео), "
    "и выбери: разослать копию всей базе или опубликовать в канал\n"
    "/stats — сколько людей в базе\n"
    "/myid — твой Telegram ID\n"
    "/usermode — включить/выключить режим обычного пользователя (проверить ИИ-ответы)\n\n"
    "Посты из канала Витуса бот сам пересылает в наш канал "
    "(если он добавлен туда администратором)."
)


def setup_router(cfg: Config, sheet: PlayersSheet, ai: AIResponder, reposter: Reposter) -> Router:
    router = Router()
    router.message.filter(F.chat.type == "private")  # «Фильтр: только личка»
    important_kb = build_keyboard(IMPORTANT_KEYBOARD)
    state = {"busy": False, "task": None}
    drafts: dict[str, list[int]] = {}  # черновик рассылки: токен -> id сообщений поста
    albums: dict[str, list[int]] = {}  # альбом админа собирается здесь, пока приходят его части
    user_mode: set[int] = set()  # админы, временно переключённые в режим обычного пользователя
    counter = itertools.count(1)

    def is_admin(user_id: int) -> bool:
        return user_id in cfg.admin_ids

    # ---------- админка ----------

    @router.message(Command("myid"))
    async def my_id(message: Message):
        await message.answer(f"Твой ID: <code>{message.from_user.id}</code>", parse_mode="HTML")

    @router.message(Command("admin"), F.from_user.id.func(is_admin))
    async def admin_help(message: Message):
        await message.answer(ADMIN_HELP, parse_mode="HTML")

    @router.message(Command("stats"), F.from_user.id.func(is_admin))
    async def stats(message: Message):
        try:
            ids = await sheet.unique_ids()
            await message.answer(f"👥 Уникальных пользователей в базе: <b>{len(ids)}</b>", parse_mode="HTML")
        except Exception as e:
            await message.answer(f"Не удалось прочитать базу: {e}")

    @router.message(Command("broadcasts"), F.from_user.id.func(is_admin))
    async def broadcasts_menu(message: Message):
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=tpl["title"], callback_data=f"bc:{key}")]
                for key, tpl in BROADCASTS.items()
            ]
        )
        await message.answer("Выбери рассылку — сначала покажу превью:", reply_markup=kb)

    async def ask_destination(chat_id: int, message_ids: list[int], bot: Bot) -> None:
        token = f"d{next(counter)}"
        drafts[token] = message_ids
        while len(drafts) > 50:
            drafts.pop(next(iter(drafts)))
        await bot.send_message(
            chat_id,
            "Куда отправить этот пост?",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="👥 Всей базе", callback_data=f"cp:{token}")],
                    [InlineKeyboardButton(text="📣 В канал", callback_data=f"cpch:{token}")],
                    [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")],
                ]
            ),
        )

    def draft_ids(token: str) -> list[int] | None:
        if token in drafts:
            return drafts[token]
        return [int(token)] if token.isdigit() else None  # кнопки, созданные до обновления

    @router.message(Command("send"), F.from_user.id.func(is_admin))
    async def send_copy(message: Message, bot: Bot):
        src = message.reply_to_message
        if not src:
            await message.answer("Просто пришли мне пост — я спрошу, куда его отправить.")
            return
        await ask_destination(message.chat.id, [src.message_id], bot)

    @router.message(Command("usermode"), F.from_user.id.func(is_admin))
    async def toggle_user_mode(message: Message):
        uid = message.from_user.id
        if uid in user_mode:
            user_mode.discard(uid)
            await message.answer("👑 Админский режим включён: присылай посты, я спрошу, куда их отправить.")
        else:
            user_mode.add(uid)
            await message.answer(
                "👤 Режим обычного пользователя: отвечаю как ИИ, как всем. "
                "Вернуться в админский режим — снова /usermode."
            )

    @router.callback_query(F.data.startswith("cpch:"), F.from_user.id.func(is_admin))
    async def copy_to_channel(call: CallbackQuery, bot: Bot):
        ids = draft_ids(call.data.split(":", 1)[1])
        await call.answer()
        if not ids:
            await call.message.edit_text("Черновик устарел (бот перезапускался). Пришли пост ещё раз.")
            return
        try:
            await copy_sender(bot, call.message.chat.id, ids)(cfg.promo_channel_id)
            await call.message.edit_text("✅ Отправлено в канал")
        except Exception as e:
            await call.message.edit_text(
                f"Ошибка отправки в канал: {e}\n\nПроверь, что бот — админ канала с правом публиковать сообщения."
            )

    @router.callback_query(F.data.startswith("bc:"), F.from_user.id.func(is_admin))
    async def broadcast_preview(call: CallbackQuery, bot: Bot):
        key = call.data.split(":", 1)[1]
        tpl = BROADCASTS.get(key)
        if not tpl:
            await call.answer("Нет такой рассылки", show_alert=True)
            return
        await call.answer()
        await send_post(bot, call.message.chat.id, tpl["photo"], tpl["caption"], build_keyboard(tpl["keyboard"]))
        where = "в канал" if tpl["target"] == "channel" else "всей базе"
        await call.message.answer(f"👆 Превью. Отправить «{tpl['title']}» {where}?", reply_markup=_confirm_kb(f"go:{key}"))

    @router.callback_query(F.data == "cancel")
    async def cancel(call: CallbackQuery):
        await call.answer("Отменено")
        await call.message.edit_text("❌ Отменено")

    @router.callback_query(F.data.startswith(("go:", "cp:")), F.from_user.id.func(is_admin))
    async def broadcast_start(call: CallbackQuery, bot: Bot):
        if state["busy"]:
            await call.answer("Уже идёт другая рассылка, дождись окончания", show_alert=True)
            return
        kind, arg = call.data.split(":", 1)

        if kind == "go" and BROADCASTS.get(arg, {}).get("target") == "channel":
            tpl = BROADCASTS[arg]
            await call.answer()
            try:
                await send_post(bot, cfg.promo_channel_id, tpl["photo"], tpl["caption"], build_keyboard(tpl["keyboard"]))
                await call.message.edit_text("✅ Отправлено в канал")
            except Exception as e:
                await call.message.edit_text(f"Ошибка отправки в канал: {e}")
            return

        try:
            ids = await sheet.unique_ids()
        except Exception as e:
            await call.answer()
            await call.message.edit_text(f"Не удалось прочитать базу: {e}")
            return

        if kind == "cp":
            ids_to_copy = draft_ids(arg)
            if not ids_to_copy:
                await call.answer()
                await call.message.edit_text("Черновик устарел (бот перезапускался). Пришли пост ещё раз.")
                return
            send_one = copy_sender(bot, call.message.chat.id, ids_to_copy)
        else:
            send_one = template_sender(bot, arg)
        await call.answer()
        await call.message.edit_text(f"🚀 Рассылка запущена на {len(ids)} чел. Пришлю отчёт, когда закончу.")

        async def worker():
            state["busy"] = True
            try:
                result = await run_broadcast(ids, send_one, cfg.broadcast_delay)
                await bot.send_message(call.message.chat.id, result.summary())
            except Exception:
                log.exception("Рассылка упала")
                await bot.send_message(call.message.chat.id, "Рассылка прервалась с ошибкой, смотри логи Railway.")
            finally:
                state["busy"] = False

        state["task"] = asyncio.create_task(worker())

    # ---------- автопересылка из канала Витуса ----------

    @router.channel_post()
    async def on_channel_post(message: Message, bot: Bot):
        await reposter.on_channel_post(message, bot)

    @router.callback_query(F.data.startswith("rp:"), F.from_user.id.func(is_admin))
    async def repost_decision(call: CallbackQuery, bot: Bot):
        _, job_id, action = call.data.split(":", 2)
        await call.answer()
        try:
            result = await reposter.resolve(int(job_id), action, bot)
        except Exception as e:
            result = f"Ошибка публикации: {e}"
        await call.message.edit_text(result)

    # ---------- основной сценарий ----------

    @router.message()
    async def on_message(message: Message, bot: Bot):
        uid = message.from_user.id
        if is_admin(uid) and uid not in user_mode:
            await admin_draft(message, bot)  # админский режим: без ИИ, без «ВАЖНО», без записи в базу
            return

        await sheet.log_message(message)  # «База игроков» (append)

        text = message.text or message.caption
        if not text:
            return
        chat_id = message.chat.id

        if text.startswith("/start") or text in GREETINGS:
            await send_post(bot, chat_id, WELCOME_PHOTO, WELCOME_CAPTION)  # «Розыгрыш»
        else:
            await bot.send_chat_action(chat_id, ChatAction.TYPING)
            answer = await ai.answer(message.from_user.id, text)  # «AI Agent1»
            await send_html(bot, chat_id, answer)  # «Ии-ответ»

        await asyncio.sleep(cfg.followup_delay)  # «Wait3»
        await send_html(bot, chat_id, IMPORTANT_TEXT, important_kb)  # «Send a text message»

    async def admin_draft(message: Message, bot: Bot) -> None:
        if message.text and message.text.startswith("/") and not message.text.startswith("/start"):
            await message.answer("Не знаю такой команды.\n\n" + ADMIN_HELP, parse_mode="HTML")
            return
        if message.text and message.text.startswith("/start"):
            await message.answer(ADMIN_HELP, parse_mode="HTML")
            return
        group = message.media_group_id
        if not group:
            await ask_destination(message.chat.id, [message.message_id], bot)
            return
        if group in albums:
            albums[group].append(message.message_id)
            return
        albums[group] = [message.message_id]

        async def flush():
            await asyncio.sleep(1.5)  # ждём остальные части альбома
            ids = sorted(albums.pop(group, []))
            if ids:
                await ask_destination(message.chat.id, ids, bot)

        task = asyncio.create_task(flush())
        state.setdefault("album_tasks", set()).add(task)
        task.add_done_callback(state["album_tasks"].discard)

    return router


def _confirm_kb(ok_data: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Отправить", callback_data=ok_data),
                InlineKeyboardButton(text="❌ Отмена", callback_data="cancel"),
            ]
        ]
    )
