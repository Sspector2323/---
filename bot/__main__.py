"""Точка входа: python -m bot"""
import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.types import BotCommand, BotCommandScopeChat, BotCommandScopeDefault

from .ai import AIResponder
from .config import load_config
from .handlers import setup_router
from .repost import Reposter
from .sheets import PlayersSheet, SettingsStore
from .welcome import Welcome

ADMIN_COMMANDS = [
    BotCommand(command="broadcasts", description="Готовые рассылки"),
    BotCommand(command="send", description="Разослать сообщение (ответом на него)"),
    BotCommand(command="stats", description="Сколько людей в базе"),
    BotCommand(command="welcome", description="Текущее приветствие"),
    BotCommand(command="admin", description="Подсказка по командам"),
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
    reposter = Reposter(cfg.source_channel, cfg.promo_channel_id, cfg.repost_mode, cfg.admin_ids)
    welcome = Welcome(SettingsStore(sheet))
    await welcome.load()
    log.info("Приветствие: %s", "своё (из таблицы)" if welcome.current else "стандартное")
    dp.include_router(setup_router(cfg, sheet, ai, reposter, welcome))

    # Снимаем вебхук n8n, иначе long polling не получит обновления
    await bot.delete_webhook(drop_pending_updates=False)
    # Меню команд («/» и кнопка «Меню») видят только админы, обычные пользователи — нет
    await bot.set_my_commands([], scope=BotCommandScopeDefault())
    for admin_id in cfg.admin_ids:
        try:
            await bot.set_my_commands(ADMIN_COMMANDS, scope=BotCommandScopeChat(chat_id=admin_id))
        except Exception as e:
            log.warning("Не удалось поставить меню админу %s (он ещё не писал боту?): %s", admin_id, e)
    me = await bot.get_me()
    log.info("Бот @%s запущен, админы: %s", me.username, sorted(cfg.admin_ids) or "не заданы")
    log.info("Автопересылка: @%s → %s, режим %s", cfg.source_channel, cfg.promo_channel_id, reposter.mode)
    await dp.start_polling(bot, allowed_updates=["message", "callback_query", "channel_post"])


if __name__ == "__main__":
    asyncio.run(main())
