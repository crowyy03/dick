from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from app.bot.middlewares import ContainerMiddleware
from app.handlers.admin import build_admin_router
from app.handlers.user import build_user_router
from app.services.container import AppContainer


def build_dispatcher(container: AppContainer) -> Dispatcher:
    dp = Dispatcher(storage=MemoryStorage())
    mw = ContainerMiddleware(container)
    dp.message.middleware(mw)
    dp.callback_query.middleware(mw)
    dp.include_router(build_admin_router(container.settings))
    dp.include_router(build_user_router())
    return dp


def build_bot(token: str) -> Bot:
    return Bot(token=token)
