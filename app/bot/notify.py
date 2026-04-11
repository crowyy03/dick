from typing import Any

import structlog
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup

log = structlog.get_logger(__name__)


async def safe_send_admin(
    bot: Bot,
    admin_telegram_id: int,
    text: str,
    *,
    reply_markup: InlineKeyboardMarkup | None = None,
    parse_mode: str | None = None,
) -> None:
    try:
        kwargs: dict[str, Any] = {}
        if reply_markup is not None:
            kwargs["reply_markup"] = reply_markup
        if parse_mode is not None:
            kwargs["parse_mode"] = parse_mode
        await bot.send_message(admin_telegram_id, text, **kwargs)
    except Exception as e:
        log.warning("admin_notify_failed", error=str(e))
