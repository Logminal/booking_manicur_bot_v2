from __future__ import annotations

from datetime import date, datetime

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, Message

from app.bot.keyboards import booking_actions_keyboard, booking_confirm_keyboard, cancel_booking_confirm_keyboard, contacts_actions_keyboard, dates_keyboard, main_menu_keyboard, masters_keyboard, my_bookings_keyboard, services_keyboard, slots_keyboard
from app.bot.service import can_cancel_booking, cancel_booking, create_booking, get_booking_master, get_client_booking, get_master_contacts, get_service, get_welcome_text, list_active_services, list_available_dates_for_service, list_available_slots_for_service, list_booking_masters, list_client_bookings
from app.bot.utils import safe_answer_callback, safe_edit_text
from app.config import get_settings
from app.db.session import SessionLocal
from app.formatters import booking_status_label

router = Router(name="start")


def format_service_brief(service) -> str:
    description = service.description or "Без описания"
    return f"{service.name}\nЦена: {service.price_rub} руб.\nДлительность: {service.duration_minutes} минут\nОписание: {description}"


def format_booking_details(booking) -> str:
    service_name = booking.service.name if booking.service else "Услуга"
    master_name = booking.master.name if booking.master else "Мастер"
    note_text = booking.client.note if booking.client and booking.client.note else "нет"
    return (
        f"Запись #{booking.id}\n\n"
        f"Мастер: {master_name}\n"
        f"Услуга: {service_name}\n"
        f"Начало: {booking.start_at.strftime('%d.%m.%Y %H:%M')}\n"
        f"Окончание: {booking.end_at.strftime('%d.%m.%Y %H:%M')}\n"
        f"Статус: {booking_status_label(booking.status)}\n"
        f"Заметка мастера: {note_text}"
    )


def format_contacts(contacts: dict[str, str]) -> str:
    return f"Контакты мастера\n\nИмя: {contacts['name']}\nТелефон: {contacts['phone']}\nTelegram: {contacts['telegram']}\nInstagram: {contacts['instagram']}"


def format_admin_booking_notice(booking, service_name: str, master_name: str, client: Message | CallbackQuery) -> str:
    username = f"@{client.from_user.username}" if client.from_user and client.from_user.username else "не указан"
    name = client.from_user.first_name if client.from_user and client.from_user.first_name else "Без имени"
    return (
        "Новая запись\n\n"
        f"Клиент: {name}\n"
        f"Ник: {username}\n"
        f"Telegram ID: {client.from_user.id if client.from_user else '-'}\n"
        f"Мастер: {master_name}\n"
        f"Услуга: {service_name}\n"
        f"Дата: {booking.start_at.strftime('%d.%m.%Y')}\n"
        f"Время: {booking.start_at.strftime('%H:%M')}\n"
        f"Статус: {booking_status_label(booking.status)}"
    )


async def notify_admins_about_booking(callback: CallbackQuery, booking, service_name: str, master_name: str) -> None:
    for admin_id in get_settings().admin_ids:
        try:
            await callback.bot.send_message(admin_id, format_admin_booking_notice(booking, service_name, master_name, callback))
        except Exception:
            continue


async def render_main_menu(target: Message | CallbackQuery) -> None:
    async with SessionLocal() as session:
        text = await get_welcome_text(session, target.from_user.first_name if target.from_user else None)
    if isinstance(target, CallbackQuery):
        await safe_edit_text(target.message, text, reply_markup=main_menu_keyboard())
    else:
        await target.answer(text, reply_markup=main_menu_keyboard())


@router.message(CommandStart())
async def command_start_handler(message: Message) -> None:
    await render_main_menu(message)


@router.callback_query(F.data == "menu:main")
async def main_menu_callback_handler(callback: CallbackQuery) -> None:
    await safe_answer_callback(callback)
    await render_main_menu(callback)


@router.callback_query(F.data == "menu:help")
async def help_callback_handler(callback: CallbackQuery) -> None:
    await safe_answer_callback(callback)
    await safe_edit_text(callback.message, "Помощь\n\n1. Нажми 'Записаться'.\n2. Выбери услугу.\n3. Выбери мастера.\n4. Выбери дату и свободное время.\n5. Подтверди запись.\n\nВ разделе 'Мои записи' можно посмотреть активные записи и отменить их не позже чем за час.", reply_markup=main_menu_keyboard())


@router.callback_query(F.data == "menu:contacts")
async def contacts_callback_handler(callback: CallbackQuery) -> None:
    async with SessionLocal() as session:
        contacts = await get_master_contacts(session)
    await safe_answer_callback(callback)
    await safe_edit_text(callback.message, format_contacts(contacts), reply_markup=contacts_actions_keyboard(contacts))


@router.callback_query(F.data == "menu:book")
async def book_callback_handler(callback: CallbackQuery) -> None:
    async with SessionLocal() as session:
        services = await list_active_services(session)
    await safe_answer_callback(callback)
    if not services:
        await safe_edit_text(callback.message, "Сейчас нет доступных услуг. Попроси администратора добавить их в админ-панели.", reply_markup=main_menu_keyboard())
        return
    payload = [(service.id, service.name, service.price_rub, service.duration_minutes) for service in services]
    await safe_edit_text(callback.message, "Выбери услугу:", reply_markup=services_keyboard(payload))


@router.callback_query(F.data.startswith("book:service:"))
async def book_service_callback_handler(callback: CallbackQuery) -> None:
    service_id = int(callback.data.rsplit(":", 1)[-1])
    async with SessionLocal() as session:
        service = await get_service(session, service_id)
        masters = await list_booking_masters(session)
    await safe_answer_callback(callback)
    if service is None:
        await safe_edit_text(callback.message, "Услуга не найдена.", reply_markup=main_menu_keyboard())
        return
    if not masters:
        await safe_edit_text(callback.message, f"{format_service_brief(service)}\n\nСейчас нет активных мастеров для записи.", reply_markup=main_menu_keyboard())
        return
    payload = [(master.id, master.name) for master in masters]
    await safe_edit_text(callback.message, f"{format_service_brief(service)}\n\nВыбери мастера:", reply_markup=masters_keyboard(service_id, payload))


@router.callback_query(F.data.startswith("book:master:"))
async def book_master_callback_handler(callback: CallbackQuery) -> None:
    _, _, service_id_raw, master_id_raw = callback.data.split(":")
    service_id = int(service_id_raw)
    master_id = int(master_id_raw)
    async with SessionLocal() as session:
        service = await get_service(session, service_id)
        master = await get_booking_master(session, master_id)
        dates = await list_available_dates_for_service(session, service_id, master_id)
    await safe_answer_callback(callback)
    if service is None or master is None:
        await safe_edit_text(callback.message, "Услуга или мастер не найдены.", reply_markup=main_menu_keyboard())
        return
    if not dates:
        await safe_edit_text(callback.message, f"{format_service_brief(service)}\n\nМастер: {master.name}\n\nДля этой услуги пока нет свободных дат.", reply_markup=masters_keyboard(service_id, [(master.id, master.name)]))
        return
    await safe_edit_text(callback.message, f"{format_service_brief(service)}\n\nМастер: {master.name}\nВыбери дату:", reply_markup=dates_keyboard(service_id, master_id, dates))


@router.callback_query(F.data.startswith("book:date:"))
async def book_date_callback_handler(callback: CallbackQuery) -> None:
    _, _, service_id_raw, master_id_raw, date_raw = callback.data.split(":")
    service_id = int(service_id_raw)
    master_id = int(master_id_raw)
    target_date = date.fromisoformat(date_raw)
    async with SessionLocal() as session:
        service = await get_service(session, service_id)
        master = await get_booking_master(session, master_id)
        slots = await list_available_slots_for_service(session, service_id, master_id, target_date)
        dates = await list_available_dates_for_service(session, service_id, master_id)
    await safe_answer_callback(callback)
    if service is None or master is None:
        await safe_edit_text(callback.message, "Услуга или мастер не найдены.", reply_markup=main_menu_keyboard())
        return
    if not slots:
        await safe_edit_text(callback.message, f"{format_service_brief(service)}\n\nМастер: {master.name}\nНа {target_date.strftime('%d.%m.%Y')} свободных слотов нет.", reply_markup=dates_keyboard(service_id, master_id, dates))
        return
    await safe_edit_text(callback.message, f"{format_service_brief(service)}\n\nМастер: {master.name}\nДата: {target_date.strftime('%d.%m.%Y')}\nВыбери время:", reply_markup=slots_keyboard(service_id, master_id, target_date, slots))


@router.callback_query(F.data.startswith("book:slot:"))
async def book_slot_callback_handler(callback: CallbackQuery) -> None:
    _, _, service_id_raw, master_id_raw, date_raw, time_raw = callback.data.split(":")
    service_id = int(service_id_raw)
    master_id = int(master_id_raw)
    target_date = date.fromisoformat(date_raw)
    slot = datetime.combine(target_date, datetime.strptime(time_raw, "%H-%M").time())
    async with SessionLocal() as session:
        service = await get_service(session, service_id)
        master = await get_booking_master(session, master_id)
    await safe_answer_callback(callback)
    if service is None or master is None:
        await safe_edit_text(callback.message, "Услуга или мастер не найдены.", reply_markup=main_menu_keyboard())
        return
    await safe_edit_text(callback.message, f"Подтверди запись\n\n{format_service_brief(service)}\n\nМастер: {master.name}\nДата: {target_date.strftime('%d.%m.%Y')}\nВремя: {slot.strftime('%H:%M')}", reply_markup=booking_confirm_keyboard(service_id, master_id, target_date, slot))


@router.callback_query(F.data.startswith("book:confirm:"))
async def book_confirm_callback_handler(callback: CallbackQuery) -> None:
    _, _, service_id_raw, master_id_raw, date_raw, time_raw = callback.data.split(":")
    service_id = int(service_id_raw)
    master_id = int(master_id_raw)
    start_at = datetime.combine(date.fromisoformat(date_raw), datetime.strptime(time_raw, "%H-%M").time())
    async with SessionLocal() as session:
        booking = await create_booking(session, telegram_id=callback.from_user.id, username=callback.from_user.username, first_name=callback.from_user.first_name, last_name=callback.from_user.last_name, service_id=service_id, master_id=master_id, start_at=start_at)
        service = await get_service(session, service_id)
        master = await get_booking_master(session, master_id)
    await safe_answer_callback(callback)
    if booking is None or service is None or master is None:
        await safe_edit_text(callback.message, "Этот слот уже недоступен. Попробуй выбрать другое время.", reply_markup=main_menu_keyboard())
        return
    await notify_admins_about_booking(callback, booking, service.name, master.name)
    await safe_edit_text(callback.message, f"Запись создана.\n\nМастер: {master.name}\nУслуга: {service.name}\nДата: {booking.start_at.strftime('%d.%m.%Y')}\nВремя: {booking.start_at.strftime('%H:%M')}\nСтатус: {booking_status_label(booking.status)}", reply_markup=main_menu_keyboard())


@router.callback_query(F.data == "menu:my_bookings")
async def my_bookings_callback_handler(callback: CallbackQuery) -> None:
    async with SessionLocal() as session:
        bookings = await list_client_bookings(session, callback.from_user.id)
    await safe_answer_callback(callback)
    if not bookings:
        await safe_edit_text(callback.message, "У тебя пока нет активных записей.", reply_markup=main_menu_keyboard())
        return
    items = [(booking.id, f"{booking.start_at.strftime('%d.%m %H:%M')} • {booking.master.name if booking.master else 'Мастер'} • {booking.service.name} • {booking_status_label(booking.status)}") for booking in bookings]
    await safe_edit_text(callback.message, "Твои ближайшие записи:", reply_markup=my_bookings_keyboard(items))


@router.callback_query(F.data.startswith("my:booking:"))
async def my_booking_view_callback_handler(callback: CallbackQuery) -> None:
    booking_id = int(callback.data.rsplit(":", 1)[-1])
    async with SessionLocal() as session:
        booking = await get_client_booking(session, callback.from_user.id, booking_id)
        can_cancel = await can_cancel_booking(session, booking) if booking else False
    await safe_answer_callback(callback)
    if booking is None:
        await safe_edit_text(callback.message, "Запись не найдена.", reply_markup=main_menu_keyboard())
        return
    await safe_edit_text(callback.message, format_booking_details(booking), reply_markup=booking_actions_keyboard(booking.id, can_cancel))


@router.callback_query(F.data.startswith("my:cancel:ask:"))
async def my_booking_cancel_ask_callback_handler(callback: CallbackQuery) -> None:
    booking_id = int(callback.data.rsplit(":", 1)[-1])
    async with SessionLocal() as session:
        booking = await get_client_booking(session, callback.from_user.id, booking_id)
    await safe_answer_callback(callback)
    if booking is None:
        await safe_edit_text(callback.message, "Запись не найдена.", reply_markup=main_menu_keyboard())
        return
    await safe_edit_text(callback.message, f"Ты точно хочешь отменить запись?\n\n{format_booking_details(booking)}", reply_markup=cancel_booking_confirm_keyboard(booking_id))


@router.callback_query(F.data.startswith("my:cancel:confirm:"))
async def my_booking_cancel_callback_handler(callback: CallbackQuery) -> None:
    booking_id = int(callback.data.rsplit(":", 1)[-1])
    async with SessionLocal() as session:
        _, text = await cancel_booking(session, callback.from_user.id, booking_id)
    await safe_answer_callback(callback, text)
    await safe_edit_text(callback.message, text, reply_markup=main_menu_keyboard())
