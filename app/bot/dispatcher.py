from __future__ import annotations

from aiogram import Dispatcher

from app.admin.handlers.panel import router as admin_router
from app.bot.handlers.start import router as start_router


def create_dispatcher() -> Dispatcher:
    dispatcher = Dispatcher()
    dispatcher.include_router(start_router)
    dispatcher.include_router(admin_router)
    return dispatcher
