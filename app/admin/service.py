from __future__ import annotations

from datetime import date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.models.booking import Booking
from app.models.client import Client
from app.models.enums import BookingStatus, SettingKey
from app.models.master import Master
from app.models.schedule import BlockedPeriod, ScheduleDay
from app.models.service import Service
from app.models.setting import AppSetting
from app.services.booking_slots import SlotCalculationInput, SlotCalculator, TimeRange, build_busy_ranges


DEFAULT_MASTER_NAME = "Основной мастер"
DEFAULT_GREETING_TEXT = "Привет, {name}!\n\nЯ бот для записи на маникюр.\nВыбери нужный раздел в меню ниже."
DEFAULT_MASTER_CONTACT_NAME = "Имя мастера"
DEFAULT_MASTER_CONTACT_PHONE = "+7 "
DEFAULT_MASTER_CONTACT_TELEGRAM = "@master"
DEFAULT_MASTER_CONTACT_INSTAGRAM = "https://instagram.com/"
DEFAULT_WORK_START = "09:00"
DEFAULT_WORK_END = "20:00"


async def ensure_core_data(session: AsyncSession) -> None:
    await get_default_master(session)
    await ensure_setting(session, SettingKey.AUTO_CONFIRM_BOOKINGS, "true" if get_settings().auto_confirm_bookings else "false")
    await ensure_setting(session, SettingKey.SLOT_MINUTES, str(get_settings().slot_minutes))
    await ensure_setting(session, SettingKey.CANCEL_LIMIT_MINUTES, str(get_settings().cancel_limit_minutes))
    await ensure_setting(session, SettingKey.GREETING_TEXT, DEFAULT_GREETING_TEXT)
    await ensure_setting(session, SettingKey.MASTER_CONTACT_NAME, DEFAULT_MASTER_CONTACT_NAME)
    await ensure_setting(session, SettingKey.MASTER_CONTACT_PHONE, DEFAULT_MASTER_CONTACT_PHONE)
    await ensure_setting(session, SettingKey.MASTER_CONTACT_TELEGRAM, DEFAULT_MASTER_CONTACT_TELEGRAM)
    await ensure_setting(session, SettingKey.MASTER_CONTACT_INSTAGRAM, DEFAULT_MASTER_CONTACT_INSTAGRAM)
    await ensure_setting(session, SettingKey.DEFAULT_WORK_START, DEFAULT_WORK_START)
    await ensure_setting(session, SettingKey.DEFAULT_WORK_END, DEFAULT_WORK_END)
    await session.commit()


async def get_default_master(session: AsyncSession) -> Master:
    result = await session.execute(select(Master).order_by(Master.id).limit(1))
    master = result.scalar_one_or_none()
    if master is not None:
        return master
    master = Master(name=DEFAULT_MASTER_NAME, is_active=True)
    session.add(master)
    await session.flush()
    return master


async def ensure_setting(session: AsyncSession, key: SettingKey, default_value: str) -> AppSetting:
    result = await session.execute(select(AppSetting).where(AppSetting.key == key))
    setting = result.scalar_one_or_none()
    if setting is not None:
        return setting
    setting = AppSetting(key=key, value=default_value)
    session.add(setting)
    await session.flush()
    return setting


async def get_setting_value(session: AsyncSession, key: SettingKey, default_value: str) -> str:
    setting = await ensure_setting(session, key, default_value)
    return setting.value


async def set_setting_value(session: AsyncSession, key: SettingKey, value: str, default_value: str | None = None) -> AppSetting:
    setting = await ensure_setting(session, key, default_value or value)
    setting.value = value
    await session.commit()
    await session.refresh(setting)
    return setting


async def get_master_contacts(session: AsyncSession) -> dict[str, str]:
    return {
        "name": await get_setting_value(session, SettingKey.MASTER_CONTACT_NAME, DEFAULT_MASTER_CONTACT_NAME),
        "phone": await get_setting_value(session, SettingKey.MASTER_CONTACT_PHONE, DEFAULT_MASTER_CONTACT_PHONE),
        "telegram": await get_setting_value(session, SettingKey.MASTER_CONTACT_TELEGRAM, DEFAULT_MASTER_CONTACT_TELEGRAM),
        "instagram": await get_setting_value(session, SettingKey.MASTER_CONTACT_INSTAGRAM, DEFAULT_MASTER_CONTACT_INSTAGRAM),
    }


async def get_default_work_hours(session: AsyncSession) -> tuple[time, time]:
    start_raw = await get_setting_value(session, SettingKey.DEFAULT_WORK_START, DEFAULT_WORK_START)
    end_raw = await get_setting_value(session, SettingKey.DEFAULT_WORK_END, DEFAULT_WORK_END)
    return time.fromisoformat(start_raw), time.fromisoformat(end_raw)


async def set_default_work_hours(session: AsyncSession, start_value: time, end_value: time) -> None:
    await set_setting_value(session, SettingKey.DEFAULT_WORK_START, start_value.strftime("%H:%M"), DEFAULT_WORK_START)
    await set_setting_value(session, SettingKey.DEFAULT_WORK_END, end_value.strftime("%H:%M"), DEFAULT_WORK_END)


async def get_schedule_override(session: AsyncSession, target_date: date) -> ScheduleDay | None:
    master = await get_default_master(session)
    result = await session.execute(select(ScheduleDay).where(ScheduleDay.master_id == master.id, ScheduleDay.work_date == target_date))
    return result.scalar_one_or_none()


async def get_effective_schedule(session: AsyncSession, target_date: date) -> tuple[bool, time | None, time | None, str | None]:
    override = await get_schedule_override(session, target_date)
    if override is not None:
        if not override.is_working_day:
            return False, None, None, override.note
        return True, override.start_time, override.end_time, override.note
    start_value, end_value = await get_default_work_hours(session)
    return True, start_value, end_value, None


async def toggle_auto_confirm(session: AsyncSession) -> bool:
    current = await ensure_setting(session, SettingKey.AUTO_CONFIRM_BOOKINGS, "true" if get_settings().auto_confirm_bookings else "false")
    current.value = "false" if current.value.lower() == "true" else "true"
    await session.commit()
    return current.value.lower() == "true"


async def list_services(session: AsyncSession) -> list[Service]:
    result = await session.execute(select(Service).order_by(Service.is_active.desc(), Service.name.asc()))
    return list(result.scalars().all())


async def create_service(session: AsyncSession, *, name: str, price_rub: int, duration_minutes: int, description: str | None) -> Service:
    master = await get_default_master(session)
    service = Service(master_id=master.id, name=name, price_rub=price_rub, duration_minutes=duration_minutes, description=description or None, is_active=True)
    session.add(service)
    await session.commit()
    await session.refresh(service)
    return service


async def get_service(session: AsyncSession, service_id: int) -> Service | None:
    result = await session.execute(select(Service).where(Service.id == service_id))
    return result.scalar_one_or_none()


async def update_service(session: AsyncSession, service_id: int, *, name: str | None = None, price_rub: int | None = None, duration_minutes: int | None = None, description: str | None = None) -> Service | None:
    service = await get_service(session, service_id)
    if service is None:
        return None
    if name is not None:
        service.name = name
    if price_rub is not None:
        service.price_rub = price_rub
    if duration_minutes is not None:
        service.duration_minutes = duration_minutes
    if description is not None:
        service.description = description
    await session.commit()
    await session.refresh(service)
    return service


async def toggle_service(session: AsyncSession, service_id: int) -> Service | None:
    service = await get_service(session, service_id)
    if service is None:
        return None
    service.is_active = not service.is_active
    await session.commit()
    await session.refresh(service)
    return service


async def delete_service_by_id(session: AsyncSession, service_id: int) -> bool:
    service = await get_service(session, service_id)
    if service is None:
        return False
    await session.delete(service)
    await session.commit()
    return True


async def upsert_schedule_day(session: AsyncSession, *, target_date: date, is_working_day: bool, start_time: time | None, end_time: time | None, note: str | None) -> ScheduleDay:
    master = await get_default_master(session)
    result = await session.execute(select(ScheduleDay).where(ScheduleDay.master_id == master.id, ScheduleDay.work_date == target_date))
    day = result.scalar_one_or_none()
    if day is None:
        day = ScheduleDay(master_id=master.id, work_date=target_date)
        session.add(day)
    day.is_working_day = is_working_day
    day.start_time = start_time
    day.end_time = end_time
    day.note = note or None
    await session.commit()
    await session.refresh(day)
    return day


async def delete_schedule_override(session: AsyncSession, target_date: date) -> bool:
    day = await get_schedule_override(session, target_date)
    if day is None:
        return False
    await session.delete(day)
    await session.commit()
    return True


async def list_schedule_days(session: AsyncSession, limit: int = 30) -> list[ScheduleDay]:
    master = await get_default_master(session)
    today = datetime.now().date()
    result = await session.execute(select(ScheduleDay).where(ScheduleDay.master_id == master.id, ScheduleDay.work_date >= today).order_by(ScheduleDay.work_date.asc()).limit(limit))
    return list(result.scalars().all())


async def get_schedule_day(session: AsyncSession, target_date: date) -> ScheduleDay | None:
    return await get_schedule_override(session, target_date)


async def create_blocked_period(session: AsyncSession, *, target_date: date, start_time: time, end_time: time, reason: str | None) -> BlockedPeriod:
    master = await get_default_master(session)
    blocked_period = BlockedPeriod(master_id=master.id, start_at=datetime.combine(target_date, start_time), end_at=datetime.combine(target_date, end_time), reason=reason or None)
    session.add(blocked_period)
    await session.commit()
    await session.refresh(blocked_period)
    return blocked_period


async def list_blocked_periods(session: AsyncSession, limit: int = 20) -> list[BlockedPeriod]:
    master = await get_default_master(session)
    now = datetime.now()
    result = await session.execute(select(BlockedPeriod).where(BlockedPeriod.master_id == master.id, BlockedPeriod.end_at >= now).order_by(BlockedPeriod.start_at.asc()).limit(limit))
    return list(result.scalars().all())


async def get_blocked_period(session: AsyncSession, blocked_period_id: int) -> BlockedPeriod | None:
    result = await session.execute(select(BlockedPeriod).where(BlockedPeriod.id == blocked_period_id))
    return result.scalar_one_or_none()


async def delete_blocked_period(session: AsyncSession, blocked_period_id: int) -> bool:
    blocked_period = await get_blocked_period(session, blocked_period_id)
    if blocked_period is None:
        return False
    await session.delete(blocked_period)
    await session.commit()
    return True


async def list_upcoming_bookings(session: AsyncSession, limit: int = 10) -> list[Booking]:
    now = datetime.now()
    result = await session.execute(select(Booking).options(selectinload(Booking.client), selectinload(Booking.service)).where(Booking.start_at >= now).order_by(Booking.start_at.asc()).limit(limit))
    return list(result.scalars().all())


async def list_bookings_for_date(session: AsyncSession, target_date: date) -> list[Booking]:
    start_of_day = datetime.combine(target_date, time.min)
    end_of_day = datetime.combine(target_date, time.max)
    result = await session.execute(
        select(Booking)
        .options(selectinload(Booking.client), selectinload(Booking.service))
        .where(Booking.start_at >= start_of_day, Booking.start_at <= end_of_day)
        .order_by(Booking.start_at.asc())
    )
    return list(result.scalars().all())


async def get_booking(session: AsyncSession, booking_id: int) -> Booking | None:
    result = await session.execute(select(Booking).options(selectinload(Booking.client), selectinload(Booking.service)).where(Booking.id == booking_id))
    return result.scalar_one_or_none()


async def confirm_booking(session: AsyncSession, booking_id: int) -> Booking | None:
    booking = await get_booking(session, booking_id)
    if booking is None:
        return None
    booking.status = BookingStatus.CONFIRMED
    await session.commit()
    await session.refresh(booking)
    return await get_booking(session, booking_id)


async def cancel_booking_by_admin(session: AsyncSession, booking_id: int) -> Booking | None:
    booking = await get_booking(session, booking_id)
    if booking is None:
        return None
    booking.status = BookingStatus.CANCELLED
    await session.commit()
    await session.refresh(booking)
    return await get_booking(session, booking_id)


async def complete_booking(session: AsyncSession, booking_id: int) -> Booking | None:
    booking = await get_booking(session, booking_id)
    if booking is None:
        return None
    booking.status = BookingStatus.COMPLETED
    await session.commit()
    await session.refresh(booking)
    return await get_booking(session, booking_id)


async def set_client_note(session: AsyncSession, client_id: int, note: str | None) -> Client | None:
    result = await session.execute(select(Client).where(Client.id == client_id))
    client = result.scalar_one_or_none()
    if client is None:
        return None
    client.note = note or None
    await session.commit()
    await session.refresh(client)
    return client


async def list_available_reschedule_slots(session: AsyncSession, booking_id: int, target_date: date) -> list[datetime]:
    booking = await get_booking(session, booking_id)
    if booking is None or booking.service is None:
        return []
    service = booking.service
    master = await get_default_master(session)
    is_working_day, start_time, end_time, _ = await get_effective_schedule(session, target_date)
    if not is_working_day or start_time is None or end_time is None:
        return []
    day_start = datetime.combine(target_date, start_time)
    day_end = datetime.combine(target_date, end_time)
    bookings_result = await session.execute(
        select(Booking.start_at, Booking.end_at, Booking.status)
        .where(
            Booking.master_id == master.id,
            Booking.id != booking_id,
            Booking.start_at < day_end,
            Booking.end_at > day_start,
        )
    )
    bookings = list(bookings_result.all())
    blocked_result = await session.execute(
        select(BlockedPeriod).where(BlockedPeriod.master_id == master.id, BlockedPeriod.start_at < day_end, BlockedPeriod.end_at > day_start)
    )
    blocked_ranges = [TimeRange(start_at=period.start_at, end_at=period.end_at) for period in blocked_result.scalars().all()]
    slot_minutes = int(await get_setting_value(session, SettingKey.SLOT_MINUTES, str(get_settings().slot_minutes)))
    slots = SlotCalculator(
        SlotCalculationInput(
            target_date=target_date,
            day_start=start_time,
            day_end=end_time,
            slot_minutes=slot_minutes,
            service_duration_minutes=service.duration_minutes,
            busy_ranges=build_busy_ranges(bookings),
            blocked_ranges=blocked_ranges,
        )
    ).build_available_slots()
    if target_date != datetime.now().date():
        return slots
    now = datetime.now()
    return [slot for slot in slots if slot > now]


async def reschedule_booking(session: AsyncSession, booking_id: int, start_at: datetime) -> Booking | None:
    booking = await get_booking(session, booking_id)
    if booking is None or booking.service is None:
        return None
    slots = await list_available_reschedule_slots(session, booking_id, start_at.date())
    if start_at not in slots:
        return None
    booking.start_at = start_at
    booking.end_at = start_at + timedelta(minutes=booking.service.duration_minutes)
    if booking.status == BookingStatus.CANCELLED:
        booking.status = BookingStatus.CONFIRMED
    await session.commit()
    await session.refresh(booking)
    return await get_booking(session, booking_id)
