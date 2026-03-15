from __future__ import annotations

from datetime import datetime, timedelta

from aiogram import Bot
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.session import SessionLocal
from app.models.booking import Booking
from app.models.enums import BookingStatus, NotificationType
from app.models.notification import NotificationLog


def _format_reminder(booking: Booking, *, reminder_label: str) -> str:
    service_name = booking.service.name if booking.service else "Услуга"
    return (
        f"Напоминание о записи ({reminder_label})\n\n"
        f"Услуга: {service_name}\n"
        f"Дата: {booking.start_at.strftime('%d.%m.%Y')}\n"
        f"Время: {booking.start_at.strftime('%H:%M')}\n\n"
        "Если планы изменились, проверь раздел 'Мои записи'."
    )


async def _has_notification_log(session: AsyncSession, booking_id: int, notification_type: NotificationType) -> bool:
    result = await session.execute(
        select(NotificationLog).where(
            NotificationLog.booking_id == booking_id,
            NotificationLog.notification_type == notification_type,
            NotificationLog.status == "sent",
        )
    )
    return result.scalar_one_or_none() is not None


async def _store_notification_log(session: AsyncSession, booking_id: int, notification_type: NotificationType) -> None:
    session.add(NotificationLog(booking_id=booking_id, notification_type=notification_type, status="sent"))
    await session.commit()


async def _send_due_notifications(bot: Bot, notification_type: NotificationType, *, window_start: datetime, window_end: datetime, reminder_label: str) -> None:
    async with SessionLocal() as session:
        result = await session.execute(
            select(Booking)
            .options(selectinload(Booking.client), selectinload(Booking.service))
            .where(
                Booking.status == BookingStatus.CONFIRMED,
                Booking.start_at > window_start,
                Booking.start_at <= window_end,
            )
            .order_by(Booking.start_at.asc())
        )
        bookings = list(result.scalars().all())

        for booking in bookings:
            if booking.client is None:
                continue
            already_sent = await _has_notification_log(session, booking.id, notification_type)
            if already_sent:
                continue
            try:
                await bot.send_message(booking.client.telegram_id, _format_reminder(booking, reminder_label=reminder_label))
            except Exception:
                continue
            await _store_notification_log(session, booking.id, notification_type)


async def run_reminder_cycle(bot: Bot) -> None:
    now = datetime.now()
    await _send_due_notifications(
        bot,
        NotificationType.REMINDER_DAY,
        window_start=now + timedelta(hours=23),
        window_end=now + timedelta(hours=24),
        reminder_label="за день",
    )
    await _send_due_notifications(
        bot,
        NotificationType.REMINDER_HOUR,
        window_start=now,
        window_end=now + timedelta(hours=1),
        reminder_label="за час",
    )
