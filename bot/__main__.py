"""Точка входа: python -m bot"""
import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties

from .ai import AIResponder
from .config import load_config
from .handlers import setup_router
from .sheets import PlayersSheet


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
    dp.include_router(setup_router(cfg, sheet, ai))

    # Снимаем вебхук n8n, иначе long polling не получит обновления
    await bot.delete_webhook(drop_pending_updates=False)
    me = await bot.get_me()
    log.info("Бот @%s запущен, админы: %s", me.username, sorted(cfg.admin_ids) or "не заданы")
    await dp.start_polling(bot, allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    asyncio.run(main())
