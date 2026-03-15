from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.admin.service import DEFAULT_GREETING_TEXT, DEFAULT_MASTER_CONTACT_INSTAGRAM, DEFAULT_MASTER_CONTACT_NAME, DEFAULT_MASTER_CONTACT_PHONE, DEFAULT_MASTER_CONTACT_TELEGRAM, get_default_master, get_effective_schedule, get_setting_value
from app.config import get_settings
from app.models.booking import Booking
from app.models.client import Client
from app.models.enums import BookingStatus, SettingKey
from app.models.schedule import BlockedPeriod
from app.models.service import Service
from app.services.booking_slots import SlotCalculationInput, SlotCalculator, TimeRange, build_busy_ranges


async def get_welcome_text(session: AsyncSession, first_name: str | None) -> str:
    template = await get_setting_value(session, SettingKey.GREETING_TEXT, DEFAULT_GREETING_TEXT)
    name = first_name or "гость"
    try:
        return template.format(name=name)
    except KeyError:
        return template.replace("{name}", name)


async def get_master_contacts(session: AsyncSession) -> dict[str, str]:
    return {
        "name": await get_setting_value(session, SettingKey.MASTER_CONTACT_NAME, DEFAULT_MASTER_CONTACT_NAME),
        "phone": await get_setting_value(session, SettingKey.MASTER_CONTACT_PHONE, DEFAULT_MASTER_CONTACT_PHONE),
        "telegram": await get_setting_value(session, SettingKey.MASTER_CONTACT_TELEGRAM, DEFAULT_MASTER_CONTACT_TELEGRAM),
        "instagram": await get_setting_value(session, SettingKey.MASTER_CONTACT_INSTAGRAM, DEFAULT_MASTER_CONTACT_INSTAGRAM),
    }


async def get_or_create_client(session: AsyncSession, *, telegram_id: int, username: str | None, first_name: str | None, last_name: str | None) -> Client:
    result = await session.execute(select(Client).where(Client.telegram_id == telegram_id))
    client = result.scalar_one_or_none()
    if client is None:
        client = Client(telegram_id=telegram_id, username=username, first_name=first_name, last_name=last_name)
        session.add(client)
        await session.commit()
        await session.refresh(client)
        return client
    client.username = username
    client.first_name = first_name
    client.last_name = last_name
    await session.commit()
    await session.refresh(client)
    return client


async def list_active_services(session: AsyncSession) -> list[Service]:
    result = await session.execute(select(Service).where(Service.is_active.is_(True)).order_by(Service.name.asc()))
    return list(result.scalars().all())


async def get_service(session: AsyncSession, service_id: int) -> Service | None:
    result = await session.execute(select(Service).where(Service.id == service_id))
    return result.scalar_one_or_none()


async def list_available_dates_for_service(session: AsyncSession, service_id: int, *, days_limit: int = 14, scan_horizon_days: int = 60) -> list[date]:
    service = await get_service(session, service_id)
    if service is None or not service.is_active:
        return []
    available_dates: list[date] = []
    today = datetime.now().date()
    for offset in range(scan_horizon_days):
        target_date = today + timedelta(days=offset)
        slots = await list_available_slots_for_service(session, service_id, target_date)
        if slots:
            available_dates.append(target_date)
        if len(available_dates) >= days_limit:
            break
    return available_dates


async def list_available_slots_for_service(session: AsyncSession, service_id: int, target_date: date) -> list[datetime]:
    service = await get_service(session, service_id)
    if service is None or not service.is_active:
        return []
    master = await get_default_master(session)
    is_working_day, start_time, end_time, _ = await get_effective_schedule(session, target_date)
    if not is_working_day or start_time is None or end_time is None:
        return []
    day_start = datetime.combine(target_date, start_time)
    day_end = datetime.combine(target_date, end_time)
    bookings_result = await session.execute(select(Booking.start_at, Booking.end_at, Booking.status).where(Booking.master_id == master.id, Booking.start_at < day_end, Booking.end_at > day_start))
    bookings = list(bookings_result.all())
    blocked_result = await session.execute(select(BlockedPeriod).where(BlockedPeriod.master_id == master.id, BlockedPeriod.start_at < day_end, BlockedPeriod.end_at > day_start))
    blocked_ranges = [TimeRange(start_at=period.start_at, end_at=period.end_at) for period in blocked_result.scalars().all()]
    slot_minutes = int(await get_setting_value(session, SettingKey.SLOT_MINUTES, str(get_settings().slot_minutes)))
    slots = SlotCalculator(SlotCalculationInput(target_date=target_date, day_start=start_time, day_end=end_time, slot_minutes=slot_minutes, service_duration_minutes=service.duration_minutes, busy_ranges=build_busy_ranges(bookings), blocked_ranges=blocked_ranges)).build_available_slots()
    if target_date != datetime.now().date():
        return slots
    now = datetime.now()
    return [slot for slot in slots if slot > now]


async def create_booking(session: AsyncSession, *, telegram_id: int, username: str | None, first_name: str | None, last_name: str | None, service_id: int, start_at: datetime) -> Booking | None:
    client = await get_or_create_client(session, telegram_id=telegram_id, username=username, first_name=first_name, last_name=last_name)
    service = await get_service(session, service_id)
    if service is None or not service.is_active:
        return None
    available_slots = await list_available_slots_for_service(session, service_id, start_at.date())
    if start_at not in available_slots:
        return None
    auto_confirm = await get_setting_value(session, SettingKey.AUTO_CONFIRM_BOOKINGS, "true" if get_settings().auto_confirm_bookings else "false")
    status = BookingStatus.CONFIRMED if auto_confirm.lower() == "true" else BookingStatus.PENDING
    booking = Booking(client_id=client.id, service_id=service.id, master_id=service.master_id or (await get_default_master(session)).id, start_at=start_at, end_at=start_at + timedelta(minutes=service.duration_minutes), status=status)
    session.add(booking)
    await session.commit()
    await session.refresh(booking)
    return booking


async def list_client_bookings(session: AsyncSession, telegram_id: int) -> list[Booking]:
    result = await session.execute(select(Booking).join(Client, Client.id == Booking.client_id).options(selectinload(Booking.service), selectinload(Booking.client)).where(Client.telegram_id == telegram_id, Booking.status.in_([BookingStatus.PENDING, BookingStatus.CONFIRMED])).order_by(Booking.start_at.asc()))
    return list(result.scalars().all())


async def get_client_booking(session: AsyncSession, telegram_id: int, booking_id: int) -> Booking | None:
    result = await session.execute(select(Booking).join(Client, Client.id == Booking.client_id).options(selectinload(Booking.service), selectinload(Booking.client)).where(Client.telegram_id == telegram_id, Booking.id == booking_id))
    return result.scalar_one_or_none()


async def can_cancel_booking(session: AsyncSession, booking: Booking) -> bool:
    cancel_limit_minutes = int(await get_setting_value(session, SettingKey.CANCEL_LIMIT_MINUTES, str(get_settings().cancel_limit_minutes)))
    return booking.start_at - datetime.now() > timedelta(minutes=cancel_limit_minutes)


async def cancel_booking(session: AsyncSession, telegram_id: int, booking_id: int) -> tuple[bool, str]:
    booking = await get_client_booking(session, telegram_id, booking_id)
    if booking is None:
        return False, "Запись не найдена."
    if booking.status == BookingStatus.CANCELLED:
        return False, "Эта запись уже отменена."
    if not await can_cancel_booking(session, booking):
        return False, "Запись уже нельзя отменить меньше чем за час до начала."
    booking.status = BookingStatus.CANCELLED
    await session.commit()
    return True, "Запись отменена."
