from __future__ import annotations

import asyncio
import logging

from aiogram import Bot
from sqlalchemy import text

from app.admin.service import ensure_core_data
from app.bot.dispatcher import create_dispatcher
from app.config import get_settings
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.notifications.scheduler import start_scheduler


async def ensure_runtime_schema() -> None:
    async with engine.begin() as connection:
        result = await connection.execute(text("PRAGMA table_info(clients)"))
        columns = {row[1] for row in result.fetchall()}
        if "note" not in columns:
            await connection.execute(text("ALTER TABLE clients ADD COLUMN note VARCHAR(1000)"))


async def bootstrap() -> Bot:
    settings = get_settings()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    await ensure_runtime_schema()

    async with SessionLocal() as session:
        await ensure_core_data(session)

    logging.getLogger(__name__).info(
        "Project bootstrap completed. Bot token configured: %s",
        "yes" if settings.bot_token else "no",
    )

    return Bot(token=settings.bot_token)


async def run_bot() -> None:
    settings = get_settings()
    if not settings.bot_token:
        raise RuntimeError("BOT_TOKEN is not configured")

    bot = await bootstrap()
    dispatcher = create_dispatcher()
    scheduler = start_scheduler(bot)

    logging.getLogger(__name__).info("Starting Telegram polling")
    try:
        await dispatcher.start_polling(bot)
    finally:
        scheduler.shutdown(wait=False)
        await bot.session.close()


def main() -> None:
    asyncio.run(run_bot())
