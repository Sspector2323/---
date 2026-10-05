"""Логика бота — повторяет граф n8n:

Telegram Trigger → «только личка» → запись в «База игроков» → If (/start | Привет)
    да  → «Розыгрыш» (фото)                → ждём 10 сек → «⚠️ ВАЖНО!» с кнопками
    нет → AI Agent (gpt-4o-mini + память) → «Ии-ответ»   → ждём 10 сек → «⚠️ ВАЖНО!»

Плюс админ-команды для рассылок (вместо ручного запуска в n8n).
"""
import asyncio
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
    "/broadcasts — готовые рассылки (колесо, стрим, итоги и т.д.)\n"
    "/send — ответь этой командой на любое сообщение (текст, фото, видео), "
    "и выбери: разослать копию всей базе или опубликовать в канал\n"
    "/stats — сколько людей в базе\n"
    "/myid — твой Telegram ID\n\n"
    "Посты из канала Витуса бот сам пересылает в наш канал "
    "(если он добавлен туда администратором)."
)


def setup_router(cfg: Config, sheet: PlayersSheet, ai: AIResponder, reposter: Reposter) -> Router:
    router = Router()
    router.message.filter(F.chat.type == "private")  # «Фильтр: только личка»
    important_kb = build_keyboard(IMPORTANT_KEYBOARD)
    state = {"busy": False, "task": None}

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

    @router.message(Command("send"), F.from_user.id.func(is_admin))
    async def send_copy(message: Message):
        src = message.reply_to_message
        if not src:
            await message.answer("Ответь командой /send на сообщение, которое нужно разослать.")
            return
        await message.answer(
            "Куда отправить это сообщение?",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="👥 Всей базе", callback_data=f"cp:{src.message_id}")],
                    [InlineKeyboardButton(text="📣 В канал", callback_data=f"cpch:{src.message_id}")],
                    [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")],
                ]
            ),
        )

    @router.callback_query(F.data.startswith("cpch:"), F.from_user.id.func(is_admin))
    async def copy_to_channel(call: CallbackQuery, bot: Bot):
        message_id = int(call.data.split(":", 1)[1])
        await call.answer()
        try:
            await bot.copy_message(cfg.promo_channel_id, call.message.chat.id, message_id)
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

        send_one = template_sender(bot, arg) if kind == "go" else copy_sender(bot, call.message.chat.id, int(arg))
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
