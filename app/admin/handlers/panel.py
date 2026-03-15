from __future__ import annotations

from datetime import date, datetime

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.admin.keyboards import admin_back_keyboard, admin_menu_keyboard, blocked_period_keyboard, blocked_periods_keyboard, booking_actions_keyboard, bookings_keyboard, bookings_menu_keyboard, cancel_creation_keyboard, contacts_keyboard, date_picker_keyboard, reschedule_slots_keyboard, schedule_day_keyboard, schedule_menu_keyboard, schedule_mode_keyboard, schedule_overrides_keyboard, service_actions_keyboard, services_menu_keyboard, settings_keyboard
from app.admin.service import DEFAULT_GREETING_TEXT, DEFAULT_MASTER_CONTACT_INSTAGRAM, DEFAULT_MASTER_CONTACT_NAME, DEFAULT_MASTER_CONTACT_PHONE, DEFAULT_MASTER_CONTACT_TELEGRAM, cancel_booking_by_admin, complete_booking, confirm_booking, create_blocked_period, create_service, delete_blocked_period, delete_schedule_override, delete_service_by_id, ensure_core_data, get_blocked_period, get_booking, get_default_work_hours, get_master_contacts, get_schedule_day, get_service, get_setting_value, list_available_reschedule_slots, list_blocked_periods, list_bookings_for_date, list_schedule_days, list_services, list_upcoming_bookings, reschedule_booking, set_client_note, set_default_work_hours, set_setting_value, toggle_auto_confirm, toggle_service, update_service, upsert_schedule_day
from app.admin.states import BookingAdminStates, ScheduleCreateStates, ServiceCreateStates, ServiceEditStates, SettingsStates
from app.bot.utils import safe_answer_callback, safe_edit_text
from app.config import get_settings
from app.db.session import SessionLocal
from app.formatters import booking_status_label
from app.models.enums import BookingStatus, SettingKey

router = Router(name="admin")


def is_admin(telegram_id: int | None) -> bool:
    return telegram_id is not None and telegram_id in get_settings().admin_ids


def format_service(service) -> str:
    status = "активна" if service.is_active else "выключена"
    description = service.description or "Без описания"
    return f"Услуга: {service.name}\nЦена: {service.price_rub} руб.\nДлительность: {service.duration_minutes} минут\nСтатус: {status}\nОписание: {description}"


def format_booking(booking) -> str:
    client = booking.client
    client_name = client.first_name or "Без имени" if client else "Без имени"
    username = f"@{client.username}" if client and client.username else "не указан"
    service_name = booking.service.name if booking.service else "Услуга"
    client_note = client.note if client and client.note else "нет"
    return (
        f"Запись #{booking.id}\n"
        f"Услуга: {service_name}\n"
        f"Дата: {booking.start_at.strftime('%d.%m.%Y')}\n"
        f"Время: {booking.start_at.strftime('%H:%M')} - {booking.end_at.strftime('%H:%M')}\n"
        f"Статус: {booking_status_label(booking.status)}\n\n"
        f"Клиент: {client_name}\n"
        f"Ник: {username}\n"
        f"Telegram ID: {client.telegram_id if client else '-'}\n"
        f"Заметка: {client_note}"
    )


def format_master_contacts(contacts: dict[str, str]) -> str:
    return f"Контакты мастера\n\nИмя: {contacts['name']}\nТелефон: {contacts['phone']}\nTelegram: {contacts['telegram']}\nInstagram: {contacts['instagram']}"


def format_schedule_day(day) -> str:
    if not day.is_working_day:
        return f"Дата: {day.work_date.strftime('%d.%m.%Y')}\nСтатус: выходной\nКомментарий: {day.note or 'нет'}"
    return f"Дата: {day.work_date.strftime('%d.%m.%Y')}\nЧасы: {day.start_time.strftime('%H:%M')} - {day.end_time.strftime('%H:%M')}\nКомментарий: {day.note or 'нет'}"


def format_blocked_period(blocked_period) -> str:
    return f"Блокировка времени\n\nДата: {blocked_period.start_at.strftime('%d.%m.%Y')}\nВремя: {blocked_period.start_at.strftime('%H:%M')} - {blocked_period.end_at.strftime('%H:%M')}\nПричина: {blocked_period.reason or 'не указана'}"


async def notify_client_about_booking_update(callback: CallbackQuery, booking, action_text: str) -> None:
    if booking.client is None:
        return
    service_name = booking.service.name if booking.service else "Услуга"
    text = (
        f"Обновление по записи\n\n"
        f"{action_text}\n"
        f"Услуга: {service_name}\n"
        f"Дата: {booking.start_at.strftime('%d.%m.%Y')}\n"
        f"Время: {booking.start_at.strftime('%H:%M')}\n"
        f"Статус: {booking_status_label(booking.status)}"
    )
    try:
        await callback.bot.send_message(booking.client.telegram_id, text)
    except Exception:
        return


async def render_admin_menu(message: Message | CallbackQuery) -> None:
    text = "Админ-панель\n\nВыбери раздел для управления."
    if isinstance(message, CallbackQuery):
        await safe_edit_text(message.message, text, reply_markup=admin_menu_keyboard())
    else:
        await message.answer(text, reply_markup=admin_menu_keyboard())


async def render_services(callback: CallbackQuery) -> None:
    async with SessionLocal() as session:
        services = await list_services(session)
    text = "Услуги\n\nВыбери существующую услугу или добавь новую."
    if not services:
        text += "\n\nСписок пока пуст."
    await safe_edit_text(callback.message, text, reply_markup=services_menu_keyboard(services))


async def render_schedule(callback: CallbackQuery) -> None:
    async with SessionLocal() as session:
        start_time, end_time = await get_default_work_hours(session)
        overrides = await list_schedule_days(session, limit=5)
        blocked_periods = await list_blocked_periods(session, limit=5)
    text = (
        "График\n\n"
        f"Общие часы работы: {start_time.strftime('%H:%M')} - {end_time.strftime('%H:%M')}\n"
        "По умолчанию мастер работает каждый день по этим часам.\n"
        f"Исключений впереди: {len(overrides)}\n"
        f"Активных блокировок: {len(blocked_periods)}"
    )
    await safe_edit_text(callback.message, text, reply_markup=schedule_menu_keyboard())


async def render_schedule_overrides(callback: CallbackQuery) -> None:
    async with SessionLocal() as session:
        overrides = await list_schedule_days(session)
    text = "Исключения по датам\n\nВыбери дату из списка или добавь новое исключение."
    if not overrides:
        text += "\n\nИсключений пока нет."
    await safe_edit_text(callback.message, text, reply_markup=schedule_overrides_keyboard(overrides))


async def render_schedule_blocks(callback: CallbackQuery) -> None:
    async with SessionLocal() as session:
        blocked_periods = await list_blocked_periods(session)
    text = "Ручные блокировки\n\nЗдесь можно закрывать произвольные промежутки времени."
    if not blocked_periods:
        text += "\n\nАктивных блокировок пока нет."
    await safe_edit_text(callback.message, text, reply_markup=blocked_periods_keyboard(blocked_periods))


async def render_bookings_menu(callback: CallbackQuery) -> None:
    await safe_edit_text(callback.message, "Записи\n\nВыбери режим просмотра.", reply_markup=bookings_menu_keyboard())


async def render_bookings_list(callback: CallbackQuery) -> None:
    async with SessionLocal() as session:
        bookings = await list_upcoming_bookings(session)
    text = "Ближайшие записи\n\nВыбери запись для просмотра и действий." if bookings else "Ближайших записей пока нет."
    await safe_edit_text(callback.message, text, reply_markup=bookings_keyboard(bookings, back_callback="admin:bookings:list"))


async def render_bookings_for_date(callback: CallbackQuery, target_date: date) -> None:
    async with SessionLocal() as session:
        bookings = await list_bookings_for_date(session, target_date)
    text = f"Записи на {target_date.strftime('%d.%m.%Y')}\n\n"
    text += "Выбери запись для просмотра." if bookings else "На эту дату записей пока нет."
    await safe_edit_text(callback.message, text, reply_markup=bookings_keyboard(bookings, back_callback=f"admin:bookings:date:{target_date.isoformat()}"))


async def render_contacts(callback: CallbackQuery) -> None:
    async with SessionLocal() as session:
        contacts = await get_master_contacts(session)
    await safe_edit_text(callback.message, format_master_contacts(contacts), reply_markup=contacts_keyboard())


async def render_settings(callback: CallbackQuery) -> None:
    async with SessionLocal() as session:
        auto_confirm = await get_setting_value(session, SettingKey.AUTO_CONFIRM_BOOKINGS, "true" if get_settings().auto_confirm_bookings else "false")
        slot_minutes = await get_setting_value(session, SettingKey.SLOT_MINUTES, str(get_settings().slot_minutes))
        cancel_limit = await get_setting_value(session, SettingKey.CANCEL_LIMIT_MINUTES, str(get_settings().cancel_limit_minutes))
        greeting = await get_setting_value(session, SettingKey.GREETING_TEXT, DEFAULT_GREETING_TEXT)
    auto_confirm_enabled = auto_confirm.lower() == "true"
    auto_confirm_text = "включено" if auto_confirm_enabled else "выключено"
    text = f"Настройки\n\nАвтоподтверждение: {auto_confirm_text}\nШаг слотов: {slot_minutes} минут\nОтмена записи клиентом: не позже чем за {cancel_limit} минут\n\nПриветствие:\n{greeting}"
    await safe_edit_text(callback.message, text, reply_markup=settings_keyboard(auto_confirm_enabled))

@router.message(Command("admin"))
async def admin_panel_handler(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id if message.from_user else None):
        await message.answer("У вас нет доступа к админ-панели.")
        return
    await state.clear()
    async with SessionLocal() as session:
        await ensure_core_data(session)
    await render_admin_menu(message)


@router.callback_query(F.data == "admin:menu")
async def admin_menu_callback(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await safe_answer_callback(callback, "Нет доступа", show_alert=True)
        return
    await state.clear()
    await safe_answer_callback(callback)
    await render_admin_menu(callback)


@router.callback_query(F.data == "admin:services")
async def admin_services_callback(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await safe_answer_callback(callback, "Нет доступа", show_alert=True)
        return
    await state.clear()
    await safe_answer_callback(callback)
    await render_services(callback)


@router.callback_query(F.data == "admin:service:add")
async def admin_service_add_callback(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await safe_answer_callback(callback, "Нет доступа", show_alert=True)
        return
    await state.clear()
    await state.set_state(ServiceCreateStates.waiting_for_name)
    await safe_answer_callback(callback)
    await safe_edit_text(callback.message, "Введи название услуги.", reply_markup=cancel_creation_keyboard("services"))


@router.message(ServiceCreateStates.waiting_for_name)
async def service_name_input(message: Message, state: FSMContext) -> None:
    name = (message.text or "").strip()
    if len(name) < 2:
        await message.answer("Название слишком короткое. Введи нормальное название услуги.")
        return
    await state.update_data(service_name=name)
    await state.set_state(ServiceCreateStates.waiting_for_price)
    await message.answer("Теперь введи цену в рублях, только число. Например: 1500")


@router.message(ServiceCreateStates.waiting_for_price)
async def service_price_input(message: Message, state: FSMContext) -> None:
    raw_price = (message.text or "").strip()
    if not raw_price.isdigit():
        await message.answer("Цена должна быть числом. Например: 1500")
        return
    await state.update_data(service_price=int(raw_price))
    await state.set_state(ServiceCreateStates.waiting_for_duration)
    await message.answer("Теперь введи длительность услуги в минутах. Например: 90")


@router.message(ServiceCreateStates.waiting_for_duration)
async def service_duration_input(message: Message, state: FSMContext) -> None:
    raw_duration = (message.text or "").strip()
    if not raw_duration.isdigit() or int(raw_duration) <= 0:
        await message.answer("Длительность должна быть положительным числом в минутах.")
        return
    await state.update_data(service_duration=int(raw_duration))
    await state.set_state(ServiceCreateStates.waiting_for_description)
    await message.answer("Введи описание услуги или отправь '-' если описание не нужно.", reply_markup=cancel_creation_keyboard("services"))


@router.message(ServiceCreateStates.waiting_for_description)
async def service_description_input(message: Message, state: FSMContext) -> None:
    description = (message.text or "").strip()
    payload = await state.get_data()
    async with SessionLocal() as session:
        service = await create_service(session, name=payload["service_name"], price_rub=payload["service_price"], duration_minutes=payload["service_duration"], description=None if description == "-" else description)
    await state.clear()
    await message.answer(f"Услуга создана.\n\n{format_service(service)}")
    await message.answer("Вернись в /admin и открой раздел услуг для продолжения.")


@router.callback_query(F.data.startswith("admin:service:view:"))
async def admin_service_view_callback(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await safe_answer_callback(callback, "Нет доступа", show_alert=True)
        return
    service_id = int(callback.data.rsplit(":", 1)[-1])
    async with SessionLocal() as session:
        service = await get_service(session, service_id)
    await safe_answer_callback(callback)
    if service is None:
        await safe_edit_text(callback.message, "Услуга не найдена.", reply_markup=admin_back_keyboard())
        return
    await safe_edit_text(callback.message, format_service(service), reply_markup=service_actions_keyboard(service.id, service.is_active))


@router.callback_query(F.data.startswith("admin:service:edit:name:"))
async def admin_service_edit_name_callback(callback: CallbackQuery, state: FSMContext) -> None:
    service_id = int(callback.data.rsplit(":", 1)[-1])
    await state.clear()
    await state.update_data(service_id=service_id)
    await state.set_state(ServiceEditStates.waiting_for_name)
    await safe_answer_callback(callback)
    await safe_edit_text(callback.message, "Введи новое название услуги.", reply_markup=cancel_creation_keyboard("services"))


@router.callback_query(F.data.startswith("admin:service:edit:price:"))
async def admin_service_edit_price_callback(callback: CallbackQuery, state: FSMContext) -> None:
    service_id = int(callback.data.rsplit(":", 1)[-1])
    await state.clear()
    await state.update_data(service_id=service_id)
    await state.set_state(ServiceEditStates.waiting_for_price)
    await safe_answer_callback(callback)
    await safe_edit_text(callback.message, "Введи новую цену услуги.", reply_markup=cancel_creation_keyboard("services"))


@router.callback_query(F.data.startswith("admin:service:edit:duration:"))
async def admin_service_edit_duration_callback(callback: CallbackQuery, state: FSMContext) -> None:
    service_id = int(callback.data.rsplit(":", 1)[-1])
    await state.clear()
    await state.update_data(service_id=service_id)
    await state.set_state(ServiceEditStates.waiting_for_duration)
    await safe_answer_callback(callback)
    await safe_edit_text(callback.message, "Введи новую длительность услуги в минутах.", reply_markup=cancel_creation_keyboard("services"))


@router.callback_query(F.data.startswith("admin:service:edit:description:"))
async def admin_service_edit_description_callback(callback: CallbackQuery, state: FSMContext) -> None:
    service_id = int(callback.data.rsplit(":", 1)[-1])
    await state.clear()
    await state.update_data(service_id=service_id)
    await state.set_state(ServiceEditStates.waiting_for_description)
    await safe_answer_callback(callback)
    await safe_edit_text(callback.message, "Введи новое описание услуги или '-' чтобы очистить.", reply_markup=cancel_creation_keyboard("services"))


@router.message(ServiceEditStates.waiting_for_name)
async def service_edit_name_input(message: Message, state: FSMContext) -> None:
    payload = await state.get_data()
    text = (message.text or "").strip()
    if len(text) < 2:
        await message.answer("Название слишком короткое.")
        return
    async with SessionLocal() as session:
        service = await update_service(session, payload["service_id"], name=text)
    await state.clear()
    await message.answer(f"Услуга обновлена.\n\n{format_service(service)}")


@router.message(ServiceEditStates.waiting_for_price)
async def service_edit_price_input(message: Message, state: FSMContext) -> None:
    payload = await state.get_data()
    text = (message.text or "").strip()
    if not text.isdigit():
        await message.answer("Цена должна быть числом.")
        return
    async with SessionLocal() as session:
        service = await update_service(session, payload["service_id"], price_rub=int(text))
    await state.clear()
    await message.answer(f"Цена обновлена.\n\n{format_service(service)}")

@router.message(ServiceEditStates.waiting_for_duration)
async def service_edit_duration_input(message: Message, state: FSMContext) -> None:
    payload = await state.get_data()
    text = (message.text or "").strip()
    if not text.isdigit() or int(text) <= 0:
        await message.answer("Длительность должна быть положительным числом.")
        return
    async with SessionLocal() as session:
        service = await update_service(session, payload["service_id"], duration_minutes=int(text))
    await state.clear()
    await message.answer(f"Длительность обновлена.\n\n{format_service(service)}")


@router.message(ServiceEditStates.waiting_for_description)
async def service_edit_description_input(message: Message, state: FSMContext) -> None:
    payload = await state.get_data()
    text = (message.text or "").strip()
    async with SessionLocal() as session:
        service = await update_service(session, payload["service_id"], description="" if text == "-" else text)
    await state.clear()
    await message.answer(f"Описание обновлено.\n\n{format_service(service)}")


@router.callback_query(F.data.startswith("admin:service:toggle:"))
async def admin_service_toggle_callback(callback: CallbackQuery) -> None:
    service_id = int(callback.data.rsplit(":", 1)[-1])
    async with SessionLocal() as session:
        service = await toggle_service(session, service_id)
    await safe_answer_callback(callback)
    if service is None:
        await safe_edit_text(callback.message, "Услуга не найдена.", reply_markup=admin_back_keyboard())
        return
    await safe_edit_text(callback.message, format_service(service), reply_markup=service_actions_keyboard(service.id, service.is_active))


@router.callback_query(F.data.startswith("admin:service:delete:"))
async def admin_service_delete_callback(callback: CallbackQuery) -> None:
    service_id = int(callback.data.rsplit(":", 1)[-1])
    async with SessionLocal() as session:
        deleted = await delete_service_by_id(session, service_id)
    await safe_answer_callback(callback)
    if not deleted:
        await safe_edit_text(callback.message, "Услуга не найдена.", reply_markup=admin_back_keyboard())
        return
    await render_services(callback)


@router.callback_query(F.data == "admin:schedule")
async def admin_schedule_callback(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await safe_answer_callback(callback)
    await render_schedule(callback)


@router.callback_query(F.data == "admin:schedule:defaults")
async def admin_schedule_defaults_callback(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(ScheduleCreateStates.waiting_for_default_start)
    await safe_answer_callback(callback)
    await safe_edit_text(callback.message, "Введи общее время начала работы в формате ЧЧ:ММ. Например: 09:00", reply_markup=cancel_creation_keyboard("schedule"))


@router.callback_query(F.data == "admin:schedule:overrides")
async def admin_schedule_overrides_callback(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await safe_answer_callback(callback)
    await render_schedule_overrides(callback)


@router.callback_query(F.data == "admin:schedule:override:add")
async def admin_schedule_override_add_callback(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await safe_answer_callback(callback)
    await safe_edit_text(callback.message, "Выбери дату для исключения.", reply_markup=date_picker_keyboard("admin:schedule:override:date", back_callback="admin:schedule:overrides"))


@router.callback_query(F.data.startswith("admin:schedule:override:date:"))
async def admin_schedule_override_date_callback(callback: CallbackQuery, state: FSMContext) -> None:
    target_date = date.fromisoformat(callback.data.rsplit(":", 1)[-1])
    await state.clear()
    await state.update_data(schedule_date=target_date.isoformat())
    await state.set_state(ScheduleCreateStates.waiting_for_mode)
    await safe_answer_callback(callback)
    await safe_edit_text(callback.message, f"Дата: {target_date.strftime('%d.%m.%Y')}\n\nВыбери режим для этой даты.", reply_markup=schedule_mode_keyboard(target_date))


@router.callback_query(F.data.startswith("admin:schedule:mode:off:"))
async def admin_schedule_mode_off_callback(callback: CallbackQuery, state: FSMContext) -> None:
    target_date = date.fromisoformat(callback.data.rsplit(":", 1)[-1])
    async with SessionLocal() as session:
        await upsert_schedule_day(session, target_date=target_date, is_working_day=False, start_time=None, end_time=None, note="Выходной день")
    await state.clear()
    await safe_answer_callback(callback, "Выходной сохранен")
    await render_schedule_overrides(callback)


@router.callback_query(F.data.startswith("admin:schedule:mode:work:"))
async def admin_schedule_mode_work_callback(callback: CallbackQuery, state: FSMContext) -> None:
    target_date = date.fromisoformat(callback.data.rsplit(":", 1)[-1])
    await state.clear()
    await state.update_data(schedule_date=target_date.isoformat())
    await state.set_state(ScheduleCreateStates.waiting_for_start_time)
    await safe_answer_callback(callback)
    await safe_edit_text(callback.message, f"Дата: {target_date.strftime('%d.%m.%Y')}\n\nВведи время начала работы в формате ЧЧ:ММ.", reply_markup=cancel_creation_keyboard("schedule"))


@router.message(ScheduleCreateStates.waiting_for_default_start)
async def schedule_default_start_input(message: Message, state: FSMContext) -> None:
    raw_time = (message.text or "").strip()
    try:
        start_value = datetime.strptime(raw_time, "%H:%M").time()
    except ValueError:
        await message.answer("Не смог распознать время. Используй формат ЧЧ:ММ")
        return
    await state.update_data(default_start_time=start_value.strftime("%H:%M"))
    await state.set_state(ScheduleCreateStates.waiting_for_default_end)
    await message.answer("Теперь введи общее время окончания работы в формате ЧЧ:ММ. Например: 20:00")


@router.message(ScheduleCreateStates.waiting_for_default_end)
async def schedule_default_end_input(message: Message, state: FSMContext) -> None:
    raw_time = (message.text or "").strip()
    try:
        end_value = datetime.strptime(raw_time, "%H:%M").time()
    except ValueError:
        await message.answer("Не смог распознать время. Используй формат ЧЧ:ММ")
        return
    payload = await state.get_data()
    start_value = datetime.strptime(payload["default_start_time"], "%H:%M").time()
    if end_value <= start_value:
        await message.answer("Время окончания должно быть позже времени начала.")
        return
    async with SessionLocal() as session:
        await set_default_work_hours(session, start_value, end_value)
    await state.clear()
    await message.answer(f"Общие часы работы обновлены: {start_value.strftime('%H:%M')} - {end_value.strftime('%H:%M')}")


@router.message(ScheduleCreateStates.waiting_for_start_time)
async def schedule_start_input(message: Message, state: FSMContext) -> None:
    raw_time = (message.text or "").strip()
    try:
        start_value = datetime.strptime(raw_time, "%H:%M").time()
    except ValueError:
        await message.answer("Не смог распознать время. Используй формат ЧЧ:ММ")
        return
    await state.update_data(start_time=start_value.strftime("%H:%M"))
    await state.set_state(ScheduleCreateStates.waiting_for_end_time)
    await message.answer("Теперь введи время окончания работы в формате ЧЧ:ММ. Например: 19:30")


@router.message(ScheduleCreateStates.waiting_for_end_time)
async def schedule_end_input(message: Message, state: FSMContext) -> None:
    raw_time = (message.text or "").strip()
    try:
        end_value = datetime.strptime(raw_time, "%H:%M").time()
    except ValueError:
        await message.answer("Не смог распознать время. Используй формат ЧЧ:ММ")
        return
    payload = await state.get_data()
    start_value = datetime.strptime(payload["start_time"], "%H:%M").time()
    if end_value <= start_value:
        await message.answer("Время окончания должно быть позже времени начала.")
        return
    await state.update_data(end_time=end_value.strftime("%H:%M"))
    await state.set_state(ScheduleCreateStates.waiting_for_note)
    await message.answer("Добавь комментарий для этой даты или отправь '-' если не нужно.")

@router.message(ScheduleCreateStates.waiting_for_note)
async def schedule_note_input(message: Message, state: FSMContext) -> None:
    note = (message.text or "").strip()
    payload = await state.get_data()
    async with SessionLocal() as session:
        day = await upsert_schedule_day(session, target_date=date.fromisoformat(payload["schedule_date"]), is_working_day=True, start_time=datetime.strptime(payload["start_time"], "%H:%M").time(), end_time=datetime.strptime(payload["end_time"], "%H:%M").time(), note=None if note == "-" else note)
    await state.clear()
    await message.answer(f"Сохранено: {day.work_date.strftime('%d.%m.%Y')}\nВремя: {day.start_time.strftime('%H:%M')} - {day.end_time.strftime('%H:%M')}")


@router.callback_query(F.data.startswith("admin:schedule:view:"))
async def admin_schedule_view_callback(callback: CallbackQuery) -> None:
    target_date = date.fromisoformat(callback.data.rsplit(":", 1)[-1])
    async with SessionLocal() as session:
        day = await get_schedule_day(session, target_date)
    await safe_answer_callback(callback)
    if day is None:
        await safe_edit_text(callback.message, "Исключение для этой даты не найдено.", reply_markup=admin_back_keyboard())
        return
    await safe_edit_text(callback.message, format_schedule_day(day), reply_markup=schedule_day_keyboard(target_date))


@router.callback_query(F.data.startswith("admin:schedule:delete:"))
async def admin_schedule_delete_callback(callback: CallbackQuery) -> None:
    target_date = date.fromisoformat(callback.data.rsplit(":", 1)[-1])
    async with SessionLocal() as session:
        deleted = await delete_schedule_override(session, target_date)
    await safe_answer_callback(callback, "Исключение удалено" if deleted else "Исключение не найдено")
    await render_schedule_overrides(callback)


@router.callback_query(F.data == "admin:schedule:blocks")
async def admin_schedule_blocks_callback(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await safe_answer_callback(callback)
    await render_schedule_blocks(callback)


@router.callback_query(F.data == "admin:schedule:block:add")
async def admin_schedule_block_add_callback(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await safe_answer_callback(callback)
    await safe_edit_text(callback.message, "Выбери дату для блокировки.", reply_markup=date_picker_keyboard("admin:schedule:block:date", back_callback="admin:schedule:blocks"))


@router.callback_query(F.data.startswith("admin:schedule:block:date:"))
async def admin_schedule_block_date_callback(callback: CallbackQuery, state: FSMContext) -> None:
    target_date = date.fromisoformat(callback.data.rsplit(":", 1)[-1])
    await state.clear()
    await state.update_data(block_date=target_date.isoformat())
    await state.set_state(ScheduleCreateStates.waiting_for_block_start)
    await safe_answer_callback(callback)
    await safe_edit_text(callback.message, f"Дата: {target_date.strftime('%d.%m.%Y')}\n\nВведи время начала блокировки в формате ЧЧ:ММ.", reply_markup=cancel_creation_keyboard("schedule_blocks"))


@router.message(ScheduleCreateStates.waiting_for_block_start)
async def schedule_block_start_input(message: Message, state: FSMContext) -> None:
    raw_time = (message.text or "").strip()
    try:
        start_value = datetime.strptime(raw_time, "%H:%M").time()
    except ValueError:
        await message.answer("Не смог распознать время. Используй формат ЧЧ:ММ")
        return
    await state.update_data(block_start_time=start_value.strftime("%H:%M"))
    await state.set_state(ScheduleCreateStates.waiting_for_block_end)
    await message.answer("Теперь введи время окончания блокировки в формате ЧЧ:ММ.")


@router.message(ScheduleCreateStates.waiting_for_block_end)
async def schedule_block_end_input(message: Message, state: FSMContext) -> None:
    raw_time = (message.text or "").strip()
    try:
        end_value = datetime.strptime(raw_time, "%H:%M").time()
    except ValueError:
        await message.answer("Не смог распознать время. Используй формат ЧЧ:ММ")
        return
    payload = await state.get_data()
    start_value = datetime.strptime(payload["block_start_time"], "%H:%M").time()
    if end_value <= start_value:
        await message.answer("Время окончания должно быть позже времени начала.")
        return
    await state.update_data(block_end_time=end_value.strftime("%H:%M"))
    await state.set_state(ScheduleCreateStates.waiting_for_block_reason)
    await message.answer("Укажи причину блокировки или отправь '-' если не нужно.")


@router.message(ScheduleCreateStates.waiting_for_block_reason)
async def schedule_block_reason_input(message: Message, state: FSMContext) -> None:
    reason = (message.text or "").strip()
    payload = await state.get_data()
    async with SessionLocal() as session:
        blocked_period = await create_blocked_period(session, target_date=date.fromisoformat(payload["block_date"]), start_time=datetime.strptime(payload["block_start_time"], "%H:%M").time(), end_time=datetime.strptime(payload["block_end_time"], "%H:%M").time(), reason=None if reason == "-" else reason)
    await state.clear()
    await message.answer(f"Блокировка сохранена:\n{blocked_period.start_at.strftime('%d.%m.%Y %H:%M')} - {blocked_period.end_at.strftime('%H:%M')}")


@router.callback_query(F.data.startswith("admin:schedule:block:view:"))
async def admin_schedule_block_view_callback(callback: CallbackQuery) -> None:
    blocked_period_id = int(callback.data.rsplit(":", 1)[-1])
    async with SessionLocal() as session:
        blocked_period = await get_blocked_period(session, blocked_period_id)
    await safe_answer_callback(callback)
    if blocked_period is None:
        await safe_edit_text(callback.message, "Блокировка не найдена.", reply_markup=admin_back_keyboard())
        return
    await safe_edit_text(callback.message, format_blocked_period(blocked_period), reply_markup=blocked_period_keyboard(blocked_period.id))


@router.callback_query(F.data.startswith("admin:schedule:block:delete:"))
async def admin_schedule_block_delete_callback(callback: CallbackQuery) -> None:
    blocked_period_id = int(callback.data.rsplit(":", 1)[-1])
    async with SessionLocal() as session:
        deleted = await delete_blocked_period(session, blocked_period_id)
    await safe_answer_callback(callback, "Блокировка удалена" if deleted else "Блокировка не найдена")
    await render_schedule_blocks(callback)


@router.callback_query(F.data == "admin:bookings")
async def admin_bookings_callback(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await safe_answer_callback(callback)
    await render_bookings_menu(callback)


@router.callback_query(F.data == "admin:bookings:list")
async def admin_bookings_list_callback(callback: CallbackQuery) -> None:
    await safe_answer_callback(callback)
    await render_bookings_list(callback)


@router.callback_query(F.data == "admin:bookings:pick_date")
async def admin_bookings_pick_date_callback(callback: CallbackQuery) -> None:
    await safe_answer_callback(callback)
    await safe_edit_text(callback.message, "Выбери дату для просмотра записей.", reply_markup=date_picker_keyboard("admin:bookings:date", back_callback="admin:bookings"))


@router.callback_query(F.data.startswith("admin:bookings:date:"))
async def admin_bookings_date_callback(callback: CallbackQuery) -> None:
    target_date = date.fromisoformat(callback.data.rsplit(":", 1)[-1])
    await safe_answer_callback(callback)
    await render_bookings_for_date(callback, target_date)


@router.callback_query(F.data.startswith("admin:booking:view:"))
async def admin_booking_view_callback(callback: CallbackQuery) -> None:
    booking_id = int(callback.data.rsplit(":", 1)[-1])
    async with SessionLocal() as session:
        booking = await get_booking(session, booking_id)
    await safe_answer_callback(callback)
    if booking is None:
        await safe_edit_text(callback.message, "Запись не найдена.", reply_markup=admin_back_keyboard())
        return
    await safe_edit_text(callback.message, format_booking(booking), reply_markup=booking_actions_keyboard(booking.id, booking.status.value))

@router.callback_query(F.data.startswith("admin:booking:confirm:"))
async def admin_booking_confirm_callback(callback: CallbackQuery) -> None:
    booking_id = int(callback.data.rsplit(":", 1)[-1])
    async with SessionLocal() as session:
        booking = await confirm_booking(session, booking_id)
    await safe_answer_callback(callback, "Запись подтверждена")
    if booking is None:
        await safe_edit_text(callback.message, "Запись не найдена.", reply_markup=admin_back_keyboard())
        return
    await notify_client_about_booking_update(callback, booking, "Администратор подтвердил твою запись.")
    await safe_edit_text(callback.message, format_booking(booking), reply_markup=booking_actions_keyboard(booking.id, booking.status.value))


@router.callback_query(F.data.startswith("admin:booking:cancel:"))
async def admin_booking_cancel_callback(callback: CallbackQuery) -> None:
    booking_id = int(callback.data.rsplit(":", 1)[-1])
    async with SessionLocal() as session:
        booking = await cancel_booking_by_admin(session, booking_id)
    await safe_answer_callback(callback, "Запись отменена")
    if booking is None:
        await safe_edit_text(callback.message, "Запись не найдена.", reply_markup=admin_back_keyboard())
        return
    await notify_client_about_booking_update(callback, booking, "Администратор отменил твою запись.")
    await safe_edit_text(callback.message, format_booking(booking), reply_markup=booking_actions_keyboard(booking.id, booking.status.value))


@router.callback_query(F.data.startswith("admin:booking:complete:"))
async def admin_booking_complete_callback(callback: CallbackQuery) -> None:
    booking_id = int(callback.data.rsplit(":", 1)[-1])
    async with SessionLocal() as session:
        booking = await complete_booking(session, booking_id)
    await safe_answer_callback(callback, "Запись завершена")
    if booking is None:
        await safe_edit_text(callback.message, "Запись не найдена.", reply_markup=admin_back_keyboard())
        return
    await safe_edit_text(callback.message, format_booking(booking), reply_markup=booking_actions_keyboard(booking.id, booking.status.value))


@router.callback_query(F.data.startswith("admin:booking:note:"))
async def admin_booking_note_callback(callback: CallbackQuery, state: FSMContext) -> None:
    booking_id = int(callback.data.rsplit(":", 1)[-1])
    await state.clear()
    await state.update_data(booking_id=booking_id)
    await state.set_state(BookingAdminStates.waiting_for_client_note)
    await safe_answer_callback(callback)
    await safe_edit_text(callback.message, "Введи заметку к клиенту или '-' чтобы очистить заметку.", reply_markup=cancel_creation_keyboard("bookings"))


@router.message(BookingAdminStates.waiting_for_client_note)
async def admin_booking_note_input(message: Message, state: FSMContext) -> None:
    payload = await state.get_data()
    booking_id = payload["booking_id"]
    text = (message.text or "").strip()
    async with SessionLocal() as session:
        booking = await get_booking(session, booking_id)
        if booking is None or booking.client is None:
            await state.clear()
            await message.answer("Запись не найдена.")
            return
        await set_client_note(session, booking.client.id, None if text == "-" else text)
        booking = await get_booking(session, booking_id)
    await state.clear()
    await message.answer(f"Заметка сохранена.\n\n{format_booking(booking)}")


@router.callback_query(F.data.startswith("admin:booking:reschedule:"))
async def admin_booking_reschedule_callback(callback: CallbackQuery, state: FSMContext) -> None:
    booking_id = int(callback.data.rsplit(":", 1)[-1])
    await state.clear()
    await state.update_data(booking_id=booking_id)
    await safe_answer_callback(callback)
    await safe_edit_text(callback.message, "Выбери новую дату для переноса.", reply_markup=date_picker_keyboard(f"admin:booking:reschedule_date:{booking_id}", back_callback=f"admin:booking:view:{booking_id}"))


@router.callback_query(F.data.startswith("admin:booking:reschedule_date:"))
async def admin_booking_reschedule_date_callback(callback: CallbackQuery) -> None:
    _, _, _, booking_id_raw, date_raw = callback.data.split(":")
    booking_id = int(booking_id_raw)
    target_date = date.fromisoformat(date_raw)
    async with SessionLocal() as session:
        slots = await list_available_reschedule_slots(session, booking_id, target_date)
    await safe_answer_callback(callback)
    if not slots:
        await safe_edit_text(callback.message, f"На {target_date.strftime('%d.%m.%Y')} свободных слотов нет.", reply_markup=date_picker_keyboard(f"admin:booking:reschedule_date:{booking_id}", back_callback=f"admin:booking:view:{booking_id}"))
        return
    await safe_edit_text(callback.message, f"Перенос записи\n\nДата: {target_date.strftime('%d.%m.%Y')}\nВыбери новое время.", reply_markup=reschedule_slots_keyboard(booking_id, target_date, slots))


@router.callback_query(F.data.startswith("admin:booking:reslot:"))
async def admin_booking_reslot_callback(callback: CallbackQuery) -> None:
    _, _, _, booking_id_raw, date_raw, time_raw = callback.data.split(":")
    booking_id = int(booking_id_raw)
    new_start = datetime.combine(date.fromisoformat(date_raw), datetime.strptime(time_raw, "%H-%M").time())
    async with SessionLocal() as session:
        booking = await reschedule_booking(session, booking_id, new_start)
    await safe_answer_callback(callback, "Запись перенесена")
    if booking is None:
        await safe_edit_text(callback.message, "Не удалось перенести запись. Попробуй выбрать другое время.", reply_markup=admin_back_keyboard())
        return
    await notify_client_about_booking_update(callback, booking, "Администратор перенес твою запись.")
    await safe_edit_text(callback.message, format_booking(booking), reply_markup=booking_actions_keyboard(booking.id, booking.status.value))


@router.callback_query(F.data == "admin:contacts")
async def admin_contacts_callback(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await safe_answer_callback(callback)
    await render_contacts(callback)


@router.callback_query(F.data == "admin:contacts:name")
async def admin_contact_name_callback(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(SettingsStates.waiting_for_master_name)
    await safe_answer_callback(callback)
    await safe_edit_text(callback.message, "Отправь имя мастера.", reply_markup=cancel_creation_keyboard("contacts"))


@router.callback_query(F.data == "admin:contacts:phone")
async def admin_contact_phone_callback(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(SettingsStates.waiting_for_master_phone)
    await safe_answer_callback(callback)
    await safe_edit_text(callback.message, "Отправь номер телефона мастера.", reply_markup=cancel_creation_keyboard("contacts"))


@router.callback_query(F.data == "admin:contacts:telegram")
async def admin_contact_telegram_callback(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(SettingsStates.waiting_for_master_telegram)
    await safe_answer_callback(callback)
    await safe_edit_text(callback.message, "Отправь Telegram мастера, например @master.", reply_markup=cancel_creation_keyboard("contacts"))


@router.callback_query(F.data == "admin:contacts:instagram")
async def admin_contact_instagram_callback(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(SettingsStates.waiting_for_master_instagram)
    await safe_answer_callback(callback)
    await safe_edit_text(callback.message, "Отправь ссылку на Instagram мастера.", reply_markup=cancel_creation_keyboard("contacts"))


@router.message(SettingsStates.waiting_for_master_name)
async def master_name_input(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if len(text) < 2:
        await message.answer("Имя слишком короткое.")
        return
    async with SessionLocal() as session:
        await set_setting_value(session, SettingKey.MASTER_CONTACT_NAME, text, DEFAULT_MASTER_CONTACT_NAME)
    await state.clear()
    await message.answer("Имя мастера обновлено.")

@router.message(SettingsStates.waiting_for_master_phone)
async def master_phone_input(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if len(text) < 5:
        await message.answer("Телефон слишком короткий.")
        return
    async with SessionLocal() as session:
        await set_setting_value(session, SettingKey.MASTER_CONTACT_PHONE, text, DEFAULT_MASTER_CONTACT_PHONE)
    await state.clear()
    await message.answer("Телефон мастера обновлен.")


@router.message(SettingsStates.waiting_for_master_telegram)
async def master_telegram_input(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if len(text) < 2:
        await message.answer("Telegram слишком короткий.")
        return
    async with SessionLocal() as session:
        await set_setting_value(session, SettingKey.MASTER_CONTACT_TELEGRAM, text, DEFAULT_MASTER_CONTACT_TELEGRAM)
    await state.clear()
    await message.answer("Telegram мастера обновлен.")


@router.message(SettingsStates.waiting_for_master_instagram)
async def master_instagram_input(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if len(text) < 2:
        await message.answer("Instagram слишком короткий.")
        return
    async with SessionLocal() as session:
        await set_setting_value(session, SettingKey.MASTER_CONTACT_INSTAGRAM, text, DEFAULT_MASTER_CONTACT_INSTAGRAM)
    await state.clear()
    await message.answer("Instagram мастера обновлен.")


@router.callback_query(F.data == "admin:settings")
async def admin_settings_callback(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await safe_answer_callback(callback)
    await render_settings(callback)


@router.callback_query(F.data == "admin:settings:toggle_auto_confirm")
async def admin_toggle_auto_confirm_callback(callback: CallbackQuery) -> None:
    async with SessionLocal() as session:
        await toggle_auto_confirm(session)
    await safe_answer_callback(callback)
    await render_settings(callback)


@router.callback_query(F.data == "admin:settings:greeting")
async def admin_greeting_edit_callback(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(SettingsStates.waiting_for_greeting_text)
    await safe_answer_callback(callback)
    await safe_edit_text(callback.message, "Отправь новый текст приветствия. Можно использовать {name} для имени пользователя.", reply_markup=cancel_creation_keyboard("settings"))


@router.message(SettingsStates.waiting_for_greeting_text)
async def greeting_text_input(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if len(text) < 5:
        await message.answer("Текст слишком короткий. Отправь более полное приветствие.")
        return
    async with SessionLocal() as session:
        await set_setting_value(session, SettingKey.GREETING_TEXT, text, DEFAULT_GREETING_TEXT)
    await state.clear()
    await message.answer("Приветствие обновлено. Проверь /start у бота.")


@router.callback_query(F.data.startswith("admin:cancel:"))
async def admin_cancel_creation_callback(callback: CallbackQuery, state: FSMContext) -> None:
    target = callback.data.rsplit(":", 1)[-1]
    await state.clear()
    await safe_answer_callback(callback, "Действие отменено")
    if target == "services":
        await render_services(callback)
        return
    if target == "schedule":
        await render_schedule(callback)
        return
    if target == "schedule_blocks":
        await render_schedule_blocks(callback)
        return
    if target == "contacts":
        await render_contacts(callback)
        return
    if target == "settings":
        await render_settings(callback)
        return
    if target == "bookings":
        await render_bookings_menu(callback)
        return
    await render_admin_menu(callback)


@router.callback_query(F.data == "admin:close")
async def admin_close_callback(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await safe_answer_callback(callback)
    await safe_edit_text(callback.message, "Админ-панель закрыта.")

