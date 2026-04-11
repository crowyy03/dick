import asyncio

import structlog

from app.bot.factory import build_bot, build_dispatcher
from app.core.config import get_settings
from app.core.logging import setup_logging
from app.services.container import AppContainer

log = structlog.get_logger(__name__)


async def _run() -> None:
    settings = get_settings()
    setup_logging(settings.log_level)
    container = AppContainer(settings)
    bot = build_bot(settings.telegram_bot_token)
    dp = build_dispatcher(container)
    log.info("polling_start")
    try:
        await dp.start_polling(bot)
    finally:
        await container.shutdown()
        log.info("shutdown_complete")


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
