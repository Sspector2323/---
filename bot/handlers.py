"""Логика бота — повторяет граф n8n:

Telegram Trigger → «только личка» → запись в «База игроков» → If (/start | Привет)
    да  → «Розыгрыш» (фото)                → ждём 10 сек → «⚠️ ВАЖНО!» с кнопками
    нет → AI Agent (gpt-4o-mini + память) → «Ии-ответ»   → ждём 10 сек → «⚠️ ВАЖНО!»

Плюс админ-команды для рассылок (вместо ручного запуска в n8n).
"""
import asyncio
import itertools
import logging
import time

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.enums import ChatAction
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message, WebAppInfo

from .ai import AIResponder
from .broadcast import copy_sender, run_broadcast, template_sender
from .config import Config
from .sender import build_keyboard, send_html, send_post
from .mirrors import is_mirrors_post, message_text
from .chats import TYPE_TITLES, ChatRegistry
from .repost import MODE_TITLES, STYLE_TITLES, Reposter
from .sheets import PlayersSheet
from .texts import BROADCASTS, IMPORTANT_KEYBOARD, IMPORTANT_TEXT
from .welcome import Welcome, welcome_from_message

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
    "/welcome — показать текущее приветствие. Сменить: пришли пост и нажми «Сделать приветствием»\n"
    "/app — открыть мини-приложение\n"
    "/mirrors — обновить зеркала в приложении из закрепа\n"
    "/reposts — пересылки между каналами: откуда, куда, режим\n"
    "/myid — твой Telegram ID\n"
    "/usermode — включить/выключить режим обычного пользователя (проверить ИИ-ответы)\n\n"
    "Посты из канала Витуса и из Профит Хаты бот сам пересылает по настройкам /reposts. "
    "Новый канал или группа появятся в списке, когда бот увидит там любое сообщение "
    "(или напиши там /bind)."
)


def setup_router(
    cfg: Config, sheet: PlayersSheet, ai: AIResponder, reposter: Reposter, welcome: Welcome, feed=None, mirrors=None,
    chats: ChatRegistry | None = None,
) -> Router:
    router = Router()
    router.message.filter(F.chat.type == "private")  # «Фильтр: только личка»
    important_kb = build_keyboard(important_keyboard(cfg.webapp_url))
    fallback_kb = build_keyboard(IMPORTANT_KEYBOARD)  # старые кнопки, если Telegram не принял кнопки приложения
    state = {"busy": False, "task": None}
    drafts: dict[str, list[Message]] = {}  # черновик рассылки: токен -> сообщения поста
    albums: dict[str, list[Message]] = {}  # альбом админа собирается здесь, пока приходят его части
    user_mode: set[int] = set()  # админы, временно переключённые в режим обычного пользователя
    counter = itertools.count(1)

    def is_admin(user_id: int) -> bool:
        return user_id in cfg.admin_ids

    # ---------- админка ----------

    @router.message(Command("app"))
    async def open_app(message: Message):
        if not cfg.webapp_url:
            await message.answer("Приложение скоро появится 🙌")
            return
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📱 Открыть приложение", web_app=WebAppInfo(url=cfg.webapp_url + "/"))],
        ])
        await message.answer(
            "<b>Приложение Витуса</b>\n\nКазино и актуальные зеркала, колесо бонусов, база знаний и личный кабинет 👇",
            parse_mode="HTML", reply_markup=kb,
        )

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

    async def ask_destination(chat_id: int, messages: list[Message], bot: Bot) -> None:
        token = f"d{next(counter)}"
        drafts[token] = messages
        while len(drafts) > 50:
            drafts.pop(next(iter(drafts)))
        await bot.send_message(
            chat_id,
            "Куда отправить этот пост?",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="👥 Всей базе", callback_data=f"cp:{token}")],
                    [InlineKeyboardButton(text="📣 В канал", callback_data=f"cpch:{token}")],
                    [InlineKeyboardButton(text="👋 Сделать приветствием", callback_data=f"wl:{token}")],
                    [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")],
                ]
            ),
        )

    def draft_ids(token: str) -> list[int] | None:
        if token in drafts:
            return [m.message_id for m in drafts[token]]
        return [int(token)] if token.isdigit() else None  # кнопки, созданные до обновления

    @router.message(Command("send"), F.from_user.id.func(is_admin))
    async def send_copy(message: Message, bot: Bot):
        src = message.reply_to_message
        if not src:
            await message.answer("Просто пришли мне пост — я спрошу, куда его отправить.")
            return
        await ask_destination(message.chat.id, [src], bot)

    @router.message(Command("welcome"), F.from_user.id.func(is_admin))
    async def show_welcome(message: Message, bot: Bot):
        await message.answer(
            "👋 Так сейчас выглядит приветствие (на /start и «Привет»). "
            "Чтобы поменять — пришли мне новый пост и нажми «Сделать приветствием»."
        )
        await welcome.send(bot, message.chat.id)

    @router.callback_query(F.data.startswith("wl:"), F.from_user.id.func(is_admin))
    async def set_welcome(call: CallbackQuery, bot: Bot):
        messages = drafts.get(call.data.split(":", 1)[1])
        await call.answer()
        if not messages:
            await call.message.edit_text("Черновик устарел (бот перезапускался). Пришли пост ещё раз.")
            return
        src = next((m for m in messages if m.caption or m.text), messages[0])
        media = next((m for m in messages if m.photo or m.video or m.animation), src)
        try:
            data = welcome_from_message(media)
            if media is not src:  # альбом: картинка из первой части, подпись — откуда она есть
                data["html"] = src.html_text
            await welcome.save(data)
        except Exception as e:
            await call.message.edit_text(f"Не получилось сохранить приветствие: {e}")
            return
        note = "\n(В альбоме приветствием стала первая картинка.)" if len(messages) > 1 else ""
        await call.message.edit_text("✅ Приветствие обновлено. Вот как его увидят пользователи:" + note)
        await welcome.send(bot, call.message.chat.id)

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
        if chats is not None:
            is_new = await chats.note(message.chat)
            if (message.text or "").strip().split("@")[0] == "/bind":
                try:
                    await message.delete()
                except Exception:
                    pass
                await notify_admins(bot, f"✅ Канал «{message.chat.title}» подключён.\nДобавить его в пересылку?",
                                    bind_keyboard(reposter, message.chat.id, message.chat.username or ""))
                return
            if is_new:
                await notify_admins(bot, f"📡 Бот увидел новый канал: «{message.chat.title}». Его можно выбрать в /reposts.")
        if mirrors is not None and message.chat.id == mirrors.chat_id:
            # закреп «Актуальные зеркала»: новый пост или сообщение о закреплении
            await mirrors.consider(message.pinned_message or message, bot)
            if message.pinned_message or is_mirrors_post(message_text(message)):
                return  # сам пост с зеркалами в ленту не кладём
        if message.pinned_message:
            return
        if feed is not None and (reposter.is_source(message) or message.chat.id == cfg.promo_channel_id):
            await feed.add(message)  # лента мини-приложения
        await reposter.on_channel_post(message, bot)

    @router.edited_channel_post()
    async def on_channel_post_edit(message: Message, bot: Bot):
        if mirrors is not None and message.chat.id == mirrors.chat_id:
            await mirrors.consider(message, bot)  # отредактировали пост с зеркалами

    @router.message(Command("mirrors"), F.from_user.id.func(is_admin))
    async def mirrors_status(message: Message, bot: Bot):
        if mirrors is None:
            await message.answer("Автообновление зеркал выключено.")
            return
        result = await mirrors.refresh_from_pinned(bot)
        when = time.strftime("%d.%m %H:%M", time.localtime(mirrors.updated)) if mirrors.updated else "ещё не было"
        await message.answer(
            f"🔄 Проверил закреп в канале с зеркалами: {result}.\n"
            f"Казино в приложении: {len(mirrors.items)}. Последнее обновление: {when}."
        )

    @router.callback_query(F.data.startswith("rp:"), F.from_user.id.func(is_admin))
    async def repost_decision(call: CallbackQuery, bot: Bot):
        _, job_id, action = call.data.split(":", 2)
        await call.answer()
        try:
            result = await reposter.resolve(int(job_id), action, bot)
        except Exception as e:
            result = f"Ошибка публикации: {e}"
        await call.message.edit_text(result)

    # ---------- админка пересылок ----------

    async def notify_admins(bot: Bot, text: str, kb=None) -> None:
        for admin_id in cfg.admin_ids:
            try:
                await bot.send_message(admin_id, text, reply_markup=kb)
            except Exception:
                pass

    def routes():
        return getattr(reposter, "routes", [reposter])

    def route_by_key(key: str):
        return next((r for r in routes() if r.key == key), None)

    def chat_title(chat_id: int) -> str:
        return chats.title(chat_id) if chats is not None else str(chat_id)

    def source_label(r) -> str:
        return chats.label(r.source) if chats is not None else f"@{r.source}"

    def routes_view():
        lines = ["<b>Пересылки</b>\n"]
        rows = []
        for r in routes():
            targets = ", ".join(chat_title(t) for t in r.targets) or "не выбрано"
            lines.append(f"<b>{r.title}</b>\n{source_label(r)} → {targets}\n"
                         f"Режим: {MODE_TITLES[r.mode]} · пост {STYLE_TITLES[r.style]}\n")
            rows.append([InlineKeyboardButton(text=f"⚙️ {r.title}", callback_data=f"rt:{r.key}")])
        lines.append("Новый канал или группа появятся в списке, когда бот увидит там любое сообщение. "
                     "Можно просто написать там /bind.")
        return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows)

    def route_view(r):
        targets = "\n".join(f"• {chat_title(t)}" for t in r.targets) or "• пока не выбрано"
        text = (f"<b>{r.title}</b>\n\nОткуда: {source_label(r)}\nКуда:\n{targets}\n\n"
                f"Режим: <b>{MODE_TITLES[r.mode]}</b>\nПост: {STYLE_TITLES[r.style]}")
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📍 Куда пересылать", callback_data=f"rtt:{r.key}")],
            [InlineKeyboardButton(text=f"🔁 Режим: {MODE_TITLES[r.mode]}", callback_data=f"rtm:{r.key}")],
            [InlineKeyboardButton(text="‹ Все пересылки", callback_data="rts")],
        ])
        return text, kb

    def targets_view(r):
        known = {cid: info for cid, info in (chats.chats.items() if chats is not None else [])
                 if not r.is_source(_FakeMsg(cid, info.get("username", "")))}
        rows = [[InlineKeyboardButton(
            text=("✅ " if cid in r.targets else "▫️ ") + f"{info['title']} · {TYPE_TITLES.get(info['type'], 'чат')}",
            callback_data=f"rtx:{r.key}:{cid}")] for cid, info in known.items()]
        rows.append([InlineKeyboardButton(text="✔️ Готово", callback_data=f"rt:{r.key}")])
        text = (f"<b>{r.title}: куда пересылать</b>\n\nОтметь каналы и группы. "
                "Если нужной группы нет в списке — напиши в ней /bind (бот должен быть там админом) "
                "и открой этот экран заново.")
        if not known:
            text += "\n\n<i>Бот пока не видел ни одного канала или группы.</i>"
        return text, InlineKeyboardMarkup(inline_keyboard=rows)

    async def save_routes():
        if hasattr(reposter, "save"):
            try:
                await reposter.save()
            except Exception:
                log.exception("Не удалось сохранить пересылки")

    @router.message(Command("reposts"), F.from_user.id.func(is_admin))
    async def reposts_menu(message: Message):
        text, kb = routes_view()
        await message.answer(text, parse_mode="HTML", reply_markup=kb)

    @router.callback_query(F.data.startswith("rta:"), F.from_user.id.func(is_admin))
    async def reposts_add_target(call: CallbackQuery):
        _, key, cid = call.data.split(":", 2)
        r, cid = route_by_key(key), int(cid)
        await call.answer()
        if r is None:
            await call.message.edit_text("Пересылка не найдена.")
            return
        if cid not in r.targets:
            r.targets = r.targets + [cid]
            await save_routes()
        targets = ", ".join(chat_title(t) for t in r.targets)
        await call.message.edit_text(
            f"✅ Готово: «{chat_title(cid)}» добавлена в пересылку «{r.title}».\n\n"
            f"Сейчас: {source_label(r)} → {targets}"
        )

    @router.callback_query(F.data.startswith(("rts", "rt:", "rtt:", "rtm:", "rtx:")), F.from_user.id.func(is_admin))
    async def reposts_callbacks(call: CallbackQuery):
        parts = call.data.split(":")
        kind = parts[0]
        await call.answer()
        if kind == "rts":
            text, kb = routes_view()
        else:
            r = route_by_key(parts[1])
            if r is None:
                await call.message.edit_text("Пересылка не найдена.")
                return
            if kind == "rtm":
                order = ["auto", "approve", "off"]
                r.mode = order[(order.index(r.mode) + 1) % len(order)]
                await save_routes()
                text, kb = route_view(r)
            elif kind == "rtx":
                cid = int(parts[2])
                r.targets = [t for t in r.targets if t != cid] if cid in r.targets else r.targets + [cid]
                await save_routes()
                text, kb = targets_view(r)
            elif kind == "rtt":
                text, kb = targets_view(r)
            else:
                text, kb = route_view(r)
        try:
            await call.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
        except TelegramBadRequest as e:
            if "not modified" not in str(e):
                raise

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
            await welcome.send(bot, chat_id)  # «Розыгрыш» — приветствие, которое задаёт админ
        else:
            await bot.send_chat_action(chat_id, ChatAction.TYPING)
            answer = await ai.answer(message.from_user.id, text)  # «AI Agent1»
            await send_html(bot, chat_id, answer)  # «Ии-ответ»

        await asyncio.sleep(cfg.followup_delay)  # «Wait3»
        try:
            await send_html(bot, chat_id, IMPORTANT_TEXT, important_kb, no_preview=True)  # «Send a text message»
        except TelegramBadRequest as e:
            if important_kb is fallback_kb:
                raise
            log.error("Telegram не принял кнопки мини-приложения (проверь WEBAPP_URL=%s): %s", cfg.webapp_url, e)
            await send_html(bot, chat_id, IMPORTANT_TEXT, fallback_kb, no_preview=True)

    async def admin_draft(message: Message, bot: Bot) -> None:
        origin = message.forward_origin
        if chats is not None and origin is not None and getattr(origin, "chat", None) is not None:
            # переслали пост из канала — запоминаем канал, чтобы его можно было выбрать в /reposts
            if await chats.note(origin.chat):
                await message.answer(
                    f"📡 Канал «{origin.chat.title}» добавлен в список. Добавить его в пересылку?",
                    reply_markup=bind_keyboard(reposter, origin.chat.id, origin.chat.username or ""),
                )
        if message.text and message.text.startswith("/") and not message.text.startswith("/start"):
            await message.answer("Не знаю такой команды.\n\n" + ADMIN_HELP, parse_mode="HTML")
            return
        if message.text and message.text.startswith("/start"):
            await message.answer(ADMIN_HELP, parse_mode="HTML")
            return
        group = message.media_group_id
        if not group:
            await ask_destination(message.chat.id, [message], bot)
            return
        if group in albums:
            albums[group].append(message)
            return
        albums[group] = [message]

        async def flush():
            await asyncio.sleep(1.5)  # ждём остальные части альбома
            parts = sorted(albums.pop(group, []), key=lambda m: m.message_id)
            if parts:
                await ask_destination(message.chat.id, parts, bot)

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


def important_keyboard(webapp_url: str) -> list:
    """Кнопки под «ВАЖНО»: если мини-приложение подключено (WEBAPP_URL), ведут в его разделы."""
    if not webapp_url:
        return IMPORTANT_KEYBOARD
    return [
        [("🎰 Казино Витуса", "web_app", f"{webapp_url}/#casino")],
        [("🎡 Колесо и фишки", "web_app", f"{webapp_url}/#tools")],
        [("📖 Справочник игрока", "web_app", f"{webapp_url}/#guide")],
        [("👤 Личный кабинет", "web_app", f"{webapp_url}/#profile")],
    ]


def bind_keyboard(reposter, chat_id: int, username: str = "") -> InlineKeyboardMarkup | None:
    """Кнопки «➕ Добавить в пересылку …» для только что подключённого чата."""
    routes = getattr(reposter, "routes", [reposter] if reposter is not None else [])
    rows = [[InlineKeyboardButton(text=f"➕ Пересылать сюда из «{r.title}»", callback_data=f"rta:{r.key}:{chat_id}")]
            for r in routes if not r.is_source(_FakeMsg(chat_id, username)) and chat_id not in r.targets]
    return InlineKeyboardMarkup(inline_keyboard=rows) if rows else None


class _FakeMsg:
    """Минимальный «пост» для проверки, является ли чат источником пересылки."""

    def __init__(self, chat_id: int, username: str):
        class _Chat:
            pass
        self.chat = _Chat()
        self.chat.id = chat_id
        self.chat.username = username


def setup_chat_router(chats: ChatRegistry, admin_ids: set[int], reposter=None) -> Router:
    """Группы: запоминаем чат по любому сообщению и по /bind; бот добавлен/удалён — тоже."""
    router = Router()

    async def notify(bot: Bot, text: str, kb=None) -> None:
        for admin_id in admin_ids:
            try:
                await bot.send_message(admin_id, text, reply_markup=kb)
            except Exception:
                pass

    @router.message(F.chat.type.in_({"group", "supergroup"}))
    async def group_message(message: Message, bot: Bot):
        is_new = await chats.note(message.chat)
        if (message.text or "").strip().split("@")[0] == "/bind":
            await message.reply(f"✅ Группа «{message.chat.title}» подключена к боту.")
            await notify(bot, f"✅ В группе «{message.chat.title}» написали /bind.\nДобавить её в пересылку?",
                         bind_keyboard(reposter, message.chat.id, message.chat.username or ""))
        elif is_new:
            await notify(bot, f"👥 Бот увидел новую группу: «{message.chat.title}». Её можно выбрать в /reposts.")

    @router.my_chat_member()
    async def bot_status(update, bot: Bot):
        chat = update.chat
        status = update.new_chat_member.status
        if chat.type == "private":
            return
        if status in {"administrator", "member", "creator"}:
            if await chats.note(chat, is_admin=status in {"administrator", "creator"}):
                await notify(bot, f"➕ Бота добавили в «{chat.title}». Его можно выбрать в /reposts.")
        elif status in {"left", "kicked"}:
            await chats.forget(chat.id)
            await notify(bot, f"➖ Бота убрали из «{chat.title}».")

    return router
