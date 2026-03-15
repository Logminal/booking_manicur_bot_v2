from __future__ import annotations

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiogram import Bot

from app.notifications.service import run_reminder_cycle


def start_scheduler(bot: Bot) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()
    scheduler.add_job(run_reminder_cycle, "interval", minutes=1, args=[bot], id="booking-reminders", replace_existing=True)
    scheduler.start()
    return scheduler
