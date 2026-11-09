"""Точка входа: python -m bot"""
import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.types import (
    BotCommand,
    BotCommandScopeChat,
    BotCommandScopeDefault,
    MenuButtonCommands,
)

from .ai import AIResponder
from .config import load_config
from .handlers import setup_chat_router, setup_router
from .mirrors import Mirrors
from .chats import ChatRegistry
from .repost import RepostHub, Reposter
from .sheets import PlayersSheet, SettingsStore
from .webapp import Feed, create_app, start_server
from .welcome import Welcome

USER_COMMANDS = [
    BotCommand(command="start", description="Запустить бота"),
    BotCommand(command="app", description="Открыть приложение"),
]

ADMIN_COMMANDS = [
    BotCommand(command="start", description="Запустить бота"),
    BotCommand(command="app", description="Открыть приложение"),
    BotCommand(command="broadcasts", description="Готовые рассылки"),
    BotCommand(command="send", description="Разослать сообщение (ответом на него)"),
    BotCommand(command="stats", description="Сколько людей в базе"),
    BotCommand(command="welcome", description="Текущее приветствие"),
    BotCommand(command="admin", description="Подсказка по командам"),
    BotCommand(command="mirrors", description="Обновить зеркала из закрепа"),
    BotCommand(command="reposts", description="Пересылки между каналами"),
    BotCommand(command="myid", description="Мой Telegram ID"),
    BotCommand(command="usermode", description="Режим обычного пользователя вкл/выкл"),
]


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    log = logging.getLogger("bot")
    cfg = load_config()

    sheet = PlayersSheet(cfg.google_service_account, cfg.spreadsheet_id, cfg.sheet_gid)
    if not sheet.enabled:
        log.warning("GOOGLE_SERVICE_ACCOUNT_JSON не задан — запись в таблицу и рассылки отключены")
    ai = AIResponder(
        cfg.openai_api_key, cfg.openai_model, cfg.openai_max_tokens, cfg.openai_temperature, cfg.memory_window
    )

    bot = Bot(cfg.telegram_token, default=DefaultBotProperties(link_preview_is_disabled=False))
    dp = Dispatcher()
    settings = SettingsStore(sheet)
    # Пересылки: канал Витуса → ВИТУС (с нашей подписью), Профит Хата → группы (как есть).
    # Куда пересылать и режим меняются в админке /reposts и хранятся в «Настройки бота».
    reposter = RepostHub([
        Reposter(cfg.source_channel, cfg.promo_channel_id, cfg.repost_mode, cfg.admin_ids,
                 style="vitus", title="Канал Витуса", key="vitus"),
        Reposter(cfg.profit_source, [], cfg.profit_mode, cfg.admin_ids,
                 style="copy", title="Профит Хата", key="profit"),
    ], settings)
    await reposter.load()
    chats = ChatRegistry(settings)
    await chats.load()
    welcome = Welcome(settings)
    await welcome.load()
    feed = Feed(settings)
    await feed.load()
    mirrors = Mirrors(settings, cfg.mirrors_channel_id, cfg.admin_ids)
    await mirrors.load()
    log.info("Приветствие: %s", "своё (из таблицы)" if welcome.current else "стандартное")
    dp.include_router(setup_chat_router(chats, cfg.admin_ids, reposter))
    dp.include_router(setup_router(cfg, sheet, ai, reposter, welcome, feed, mirrors, chats))

    # Снимаем вебхук n8n, иначе long polling не получит обновления
    await bot.delete_webhook(drop_pending_updates=False)
    # Меню команд (кнопка «Меню» у поля ввода): пользователям — /start и /app, админам — полный список
    await bot.set_my_commands(USER_COMMANDS, scope=BotCommandScopeDefault())
    for admin_id in cfg.admin_ids:
        try:
            await bot.set_my_commands(ADMIN_COMMANDS, scope=BotCommandScopeChat(chat_id=admin_id))
        except Exception as e:
            log.warning("Не удалось поставить меню админу %s (он ещё не писал боту?): %s", admin_id, e)
    # Кнопка у поля ввода — меню команд (а не приложение): так видны /start, /app и команды админа.
    # Приложение открывается командой /app и кнопками под «ВАЖНО».
    try:
        await bot.set_chat_menu_button(menu_button=MenuButtonCommands())
    except Exception as e:
        log.warning("Не удалось вернуть кнопку меню команд: %s", e)
    channels = {"stream": f"@{cfg.source_channel}", "promo": cfg.promo_channel_id}
    runner = await start_server(create_app(bot, cfg.telegram_token, feed, channels, mirrors), cfg.port)
    if not cfg.webapp_url:
        log.warning("WEBAPP_URL не задан — кнопки ведут на старые страницы Framer")
    # Названия каналов из пересылок — сразу в список чатов, чтобы в /reposts не было голых номеров
    for r in reposter.routes:
        for ref in [f"@{r.source}" if not r.source.lstrip("-").isdigit() else int(r.source), *r.targets]:
            try:
                await chats.note(await bot.get_chat(ref))
            except Exception as e:
                log.warning("Не удалось получить чат %s: %s (бот там админ?)", ref, e)
    me = await bot.get_me()
    log.info("Бот @%s запущен, админы: %s", me.username, sorted(cfg.admin_ids) or "не заданы")
    for r in reposter.routes:
        log.info("Пересылка «%s»: @%s → %s, режим %s", r.title, r.source, r.targets or "не выбрано", r.mode)
    try:
        mirrors_task = asyncio.create_task(mirrors.loop(bot))  # закреп с зеркалами — при запуске и раз в 30 минут
        await dp.start_polling(
            bot, allowed_updates=["message", "callback_query", "channel_post", "edited_channel_post", "my_chat_member"]
        )
    finally:
        mirrors_task.cancel()
        await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
