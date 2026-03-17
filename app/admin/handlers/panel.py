from __future__ import annotations

from datetime import date, datetime

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.admin.keyboards import admin_back_keyboard, admin_menu_keyboard, blocked_period_keyboard, blocked_periods_keyboard, booking_actions_keyboard, bookings_keyboard, bookings_menu_keyboard, cancel_creation_keyboard, contacts_keyboard, date_picker_keyboard, master_actions_keyboard, masters_menu_keyboard, reschedule_slots_keyboard, schedule_day_keyboard, schedule_master_keyboard, schedule_menu_keyboard, schedule_mode_keyboard, schedule_overrides_keyboard, service_actions_keyboard, services_menu_keyboard, settings_keyboard
from app.admin.service import DEFAULT_GREETING_TEXT, DEFAULT_MASTER_CONTACT_INSTAGRAM, DEFAULT_MASTER_CONTACT_NAME, DEFAULT_MASTER_CONTACT_PHONE, DEFAULT_MASTER_CONTACT_TELEGRAM, cancel_booking_by_admin, complete_booking, confirm_booking, create_blocked_period, create_master, create_service, delete_blocked_period, delete_master, delete_schedule_override, delete_service_by_id, ensure_core_data, get_blocked_period, get_booking, get_default_work_hours, get_master, get_master_contacts, get_schedule_day, get_service, get_setting_value, list_available_reschedule_slots, list_blocked_periods, list_bookings_for_date, list_masters, list_schedule_days, list_services, list_upcoming_bookings, rename_master, reschedule_booking, set_client_note, set_default_work_hours, set_setting_value, toggle_auto_confirm, toggle_master, toggle_service, update_service, upsert_schedule_day
from app.admin.states import BookingAdminStates, MasterCreateStates, MasterEditStates, ScheduleCreateStates, ServiceCreateStates, ServiceEditStates, SettingsStates
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


def format_master(master) -> str:
    status = "активен" if master.is_active else "выключен"
    return f"Мастер: {master.name}\nСтатус: {status}"


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


async def render_masters(callback: CallbackQuery) -> None:
    async with SessionLocal() as session:
        masters = await list_masters(session)
    text = "Мастера\n\nВыбери мастера или добавь нового."
    if not masters:
        text += "\n\nСписок пока пуст."
    await safe_edit_text(callback.message, text, reply_markup=masters_menu_keyboard(masters))


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
        masters = await list_masters(session)
    text = (
        "\u0413\u0440\u0430\u0444\u0438\u043a\n\n"
        f"\u041e\u0431\u0449\u0438\u0435 \u0447\u0430\u0441\u044b \u0440\u0430\u0431\u043e\u0442\u044b: {start_time.strftime('%H:%M')} - {end_time.strftime('%H:%M')}\n"
        "\u041f\u043e \u0443\u043c\u043e\u043b\u0447\u0430\u043d\u0438\u044e \u043a\u0430\u0436\u0434\u044b\u0439 \u043c\u0430\u0441\u0442\u0435\u0440 \u0440\u0430\u0431\u043e\u0442\u0430\u0435\u0442 \u0435\u0436\u0435\u0434\u043d\u0435\u0432\u043d\u043e \u043f\u043e \u044d\u0442\u0438\u043c \u0447\u0430\u0441\u0430\u043c.\n\n"
        "\u0412\u044b\u0431\u0435\u0440\u0438 \u043c\u0430\u0441\u0442\u0435\u0440\u0430, \u0447\u0442\u043e\u0431\u044b \u043d\u0430\u0441\u0442\u0440\u043e\u0438\u0442\u044c \u0435\u0433\u043e \u0438\u0441\u043a\u043b\u044e\u0447\u0435\u043d\u0438\u044f \u0438 \u0431\u043b\u043e\u043a\u0438\u0440\u043e\u0432\u043a\u0438."
    )
    await safe_edit_text(callback.message, text, reply_markup=schedule_master_keyboard(masters))


async def render_schedule_master(callback: CallbackQuery, master_id: int) -> None:
    async with SessionLocal() as session:
        master = await get_master(session, master_id)
        overrides = await list_schedule_days(session, limit=5, master_id=master_id)
        blocked_periods = await list_blocked_periods(session, limit=5, master_id=master_id)
    if master is None:
        await safe_edit_text(callback.message, "\u041c\u0430\u0441\u0442\u0435\u0440 \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d.", reply_markup=admin_back_keyboard())
        return
    text = (
        f"\u0413\u0440\u0430\u0444\u0438\u043a \u043c\u0430\u0441\u0442\u0435\u0440\u0430: {master.name}\n\n"
        f"\u0418\u0441\u043a\u043b\u044e\u0447\u0435\u043d\u0438\u0439 \u0432\u043f\u0435\u0440\u0435\u0434\u0438: {len(overrides)}\n"
        f"\u0410\u043a\u0442\u0438\u0432\u043d\u044b\u0445 \u0431\u043b\u043e\u043a\u0438\u0440\u043e\u0432\u043e\u043a: {len(blocked_periods)}\n\n"
        "\u0412\u044b\u0431\u0435\u0440\u0438 \u043d\u0443\u0436\u043d\u044b\u0439 \u0440\u0430\u0437\u0434\u0435\u043b."
    )
    await safe_edit_text(callback.message, text, reply_markup=schedule_menu_keyboard(master_id))


async def render_schedule_overrides(callback: CallbackQuery, master_id: int) -> None:
    async with SessionLocal() as session:
        master = await get_master(session, master_id)
        overrides = await list_schedule_days(session, master_id=master_id)
    if master is None:
        await safe_edit_text(callback.message, "\u041c\u0430\u0441\u0442\u0435\u0440 \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d.", reply_markup=admin_back_keyboard())
        return
    text = f"\u0418\u0441\u043a\u043b\u044e\u0447\u0435\u043d\u0438\u044f \u043f\u043e \u0434\u0430\u0442\u0430\u043c\n\n\u041c\u0430\u0441\u0442\u0435\u0440: {master.name}\n\n\u0412\u044b\u0431\u0435\u0440\u0438 \u0434\u0430\u0442\u0443 \u0438\u0437 \u0441\u043f\u0438\u0441\u043a\u0430 \u0438\u043b\u0438 \u0434\u043e\u0431\u0430\u0432\u044c \u043d\u043e\u0432\u043e\u0435 \u0438\u0441\u043a\u043b\u044e\u0447\u0435\u043d\u0438\u0435."
    if not overrides:
        text += "\n\n\u0418\u0441\u043a\u043b\u044e\u0447\u0435\u043d\u0438\u0439 \u043f\u043e\u043a\u0430 \u043d\u0435\u0442."
    await safe_edit_text(callback.message, text, reply_markup=schedule_overrides_keyboard(master_id, overrides))


async def render_schedule_blocks(callback: CallbackQuery, master_id: int) -> None:
    async with SessionLocal() as session:
        master = await get_master(session, master_id)
        blocked_periods = await list_blocked_periods(session, master_id=master_id)
    if master is None:
        await safe_edit_text(callback.message, "\u041c\u0430\u0441\u0442\u0435\u0440 \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d.", reply_markup=admin_back_keyboard())
        return
    text = f"\u0420\u0443\u0447\u043d\u044b\u0435 \u0431\u043b\u043e\u043a\u0438\u0440\u043e\u0432\u043a\u0438\n\n\u041c\u0430\u0441\u0442\u0435\u0440: {master.name}\n\n\u0417\u0434\u0435\u0441\u044c \u043c\u043e\u0436\u043d\u043e \u0437\u0430\u043a\u0440\u044b\u0432\u0430\u0442\u044c \u043f\u0440\u043e\u0438\u0437\u0432\u043e\u043b\u044c\u043d\u044b\u0435 \u043f\u0440\u043e\u043c\u0435\u0436\u0443\u0442\u043a\u0438 \u0432\u0440\u0435\u043c\u0435\u043d\u0438."
    if not blocked_periods:
        text += "\n\n\u0410\u043a\u0442\u0438\u0432\u043d\u044b\u0445 \u0431\u043b\u043e\u043a\u0438\u0440\u043e\u0432\u043e\u043a \u043f\u043e\u043a\u0430 \u043d\u0435\u0442."
    await safe_edit_text(callback.message, text, reply_markup=blocked_periods_keyboard(master_id, blocked_periods))


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


@router.callback_query(F.data == "admin:masters")
async def admin_masters_callback(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await safe_answer_callback(callback)
    await render_masters(callback)


@router.callback_query(F.data == "admin:master:add")
async def admin_master_add_callback(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(MasterCreateStates.waiting_for_name)
    await safe_answer_callback(callback)
    await safe_edit_text(callback.message, "Введи имя мастера.", reply_markup=cancel_creation_keyboard("masters"))


@router.message(MasterCreateStates.waiting_for_name)
async def master_name_create_input(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if len(text) < 2:
        await message.answer("Имя мастера слишком короткое.")
        return
    async with SessionLocal() as session:
        master = await create_master(session, text)
    await state.clear()
    await message.answer(f"Мастер создан.\n\n{format_master(master)}")


@router.callback_query(F.data.startswith("admin:master:view:"))
async def admin_master_view_callback(callback: CallbackQuery) -> None:
    master_id = int(callback.data.rsplit(":", 1)[-1])
    async with SessionLocal() as session:
        master = await get_master(session, master_id)
    await safe_answer_callback(callback)
    if master is None:
        await safe_edit_text(callback.message, "Мастер не найден.", reply_markup=admin_back_keyboard())
        return
    await safe_edit_text(callback.message, format_master(master), reply_markup=master_actions_keyboard(master.id, master.is_active))


@router.callback_query(F.data.startswith("admin:master:toggle:"))
async def admin_master_toggle_callback(callback: CallbackQuery) -> None:
    master_id = int(callback.data.rsplit(":", 1)[-1])
    async with SessionLocal() as session:
        master = await toggle_master(session, master_id)
    await safe_answer_callback(callback)
    if master is None:
        await safe_edit_text(callback.message, "Мастер не найден.", reply_markup=admin_back_keyboard())
        return
    await safe_edit_text(callback.message, format_master(master), reply_markup=master_actions_keyboard(master.id, master.is_active))



@router.callback_query(F.data.startswith("admin:master:edit:"))
async def admin_master_edit_callback(callback: CallbackQuery, state: FSMContext) -> None:
    master_id = int(callback.data.rsplit(":", 1)[-1])
    await state.clear()
    await state.update_data(master_id=master_id)
    await state.set_state(MasterEditStates.waiting_for_name)
    await safe_answer_callback(callback)
    await safe_edit_text(callback.message, "????? ????? ??? ???????.", reply_markup=cancel_creation_keyboard("masters"))


@router.message(MasterEditStates.waiting_for_name)
async def master_name_edit_input(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if len(text) < 2:
        await message.answer("\u0418\u043c\u044f \u043c\u0430\u0441\u0442\u0435\u0440\u0430 \u0441\u043b\u0438\u0448\u043a\u043e\u043c \u043a\u043e\u0440\u043e\u0442\u043a\u043e\u0435.")
        return
    payload = await state.get_data()
    async with SessionLocal() as session:
        master = await rename_master(session, payload["master_id"], text)
    await state.clear()
    if master is None:
        await message.answer("\u041c\u0430\u0441\u0442\u0435\u0440 \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d.")
        return
    await message.answer(f"\u041c\u0430\u0441\u0442\u0435\u0440 \u043f\u0435\u0440\u0435\u0438\u043c\u0435\u043d\u043e\u0432\u0430\u043d.\n\n{format_master(master)}")


@router.callback_query(F.data.startswith("admin:master:delete:"))
async def admin_master_delete_callback(callback: CallbackQuery) -> None:
    master_id = int(callback.data.rsplit(":", 1)[-1])
    async with SessionLocal() as session:
        deleted, reason = await delete_master(session, master_id)
    if deleted:
        await safe_answer_callback(callback, "?????? ??????")
        await render_masters(callback)
        return
    if reason == "last_master":
        await safe_answer_callback(callback, "?????? ??????? ?????????? ???????", show_alert=True)
    elif reason == "has_related":
        await safe_answer_callback(callback, "?????? ??????? ??????? ? ????????, ???????? ??? ????????", show_alert=True)
    else:
        await safe_answer_callback(callback, "?????? ?? ??????", show_alert=True)


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
    await safe_edit_text(callback.message, "\u0412\u0432\u0435\u0434\u0438 \u043e\u0431\u0449\u0435\u0435 \u0432\u0440\u0435\u043c\u044f \u043d\u0430\u0447\u0430\u043b\u0430 \u0440\u0430\u0431\u043e\u0442\u044b \u0432 \u0444\u043e\u0440\u043c\u0430\u0442\u0435 \u0427\u0427:\u041c\u041c. \u041d\u0430\u043f\u0440\u0438\u043c\u0435\u0440: 09:00", reply_markup=cancel_creation_keyboard("schedule"))


@router.callback_query(F.data.startswith("admin:schedule:master:"))
async def admin_schedule_master_callback(callback: CallbackQuery, state: FSMContext) -> None:
    master_id = int(callback.data.rsplit(":", 1)[-1])
    await state.clear()
    await safe_answer_callback(callback)
    await render_schedule_master(callback, master_id)


@router.callback_query(F.data.startswith("admin:schedule:overrides:"))
async def admin_schedule_overrides_callback(callback: CallbackQuery, state: FSMContext) -> None:
    master_id = int(callback.data.rsplit(":", 1)[-1])
    await state.clear()
    await safe_answer_callback(callback)
    await render_schedule_overrides(callback, master_id)


@router.callback_query(F.data.startswith("admin:schedule:override:add:"))
async def admin_schedule_override_add_callback(callback: CallbackQuery, state: FSMContext) -> None:
    master_id = int(callback.data.rsplit(":", 1)[-1])
    await state.clear()
    await safe_answer_callback(callback)
    await safe_edit_text(callback.message, "\u0412\u044b\u0431\u0435\u0440\u0438 \u0434\u0430\u0442\u0443 \u0434\u043b\u044f \u0438\u0441\u043a\u043b\u044e\u0447\u0435\u043d\u0438\u044f.", reply_markup=date_picker_keyboard(f"admin:schedule:override:date:{master_id}", back_callback=f"admin:schedule:overrides:{master_id}"))


@router.callback_query(F.data.startswith("admin:schedule:override:date:"))
async def admin_schedule_override_date_callback(callback: CallbackQuery, state: FSMContext) -> None:
    _, _, _, _, master_id_raw, date_raw = callback.data.split(":")
    master_id = int(master_id_raw)
    target_date = date.fromisoformat(date_raw)
    await state.clear()
    await state.update_data(schedule_date=target_date.isoformat(), schedule_master_id=master_id)
    await state.set_state(ScheduleCreateStates.waiting_for_mode)
    await safe_answer_callback(callback)
    await safe_edit_text(callback.message, f"\u0414\u0430\u0442\u0430: {target_date.strftime('%d.%m.%Y')}\n\n\u0412\u044b\u0431\u0435\u0440\u0438 \u0440\u0435\u0436\u0438\u043c \u0434\u043b\u044f \u044d\u0442\u043e\u0439 \u0434\u0430\u0442\u044b.", reply_markup=schedule_mode_keyboard(master_id, target_date))


@router.callback_query(F.data.startswith("admin:schedule:mode:off:"))
async def admin_schedule_mode_off_callback(callback: CallbackQuery, state: FSMContext) -> None:
    _, _, _, _, master_id_raw, date_raw = callback.data.split(":")
    master_id = int(master_id_raw)
    target_date = date.fromisoformat(date_raw)
    async with SessionLocal() as session:
        await upsert_schedule_day(session, target_date=target_date, is_working_day=False, start_time=None, end_time=None, note="\u0412\u044b\u0445\u043e\u0434\u043d\u043e\u0439 \u0434\u0435\u043d\u044c", master_id=master_id)
    await state.clear()
    await safe_answer_callback(callback, "\u0412\u044b\u0445\u043e\u0434\u043d\u043e\u0439 \u0441\u043e\u0445\u0440\u0430\u043d\u0435\u043d")
    await render_schedule_overrides(callback, master_id)


@router.callback_query(F.data.startswith("admin:schedule:mode:work:"))
async def admin_schedule_mode_work_callback(callback: CallbackQuery, state: FSMContext) -> None:
    _, _, _, _, master_id_raw, date_raw = callback.data.split(":")
    master_id = int(master_id_raw)
    target_date = date.fromisoformat(date_raw)
    await state.clear()
    await state.update_data(schedule_date=target_date.isoformat(), schedule_master_id=master_id)
    await state.set_state(ScheduleCreateStates.waiting_for_start_time)
    await safe_answer_callback(callback)
    await safe_edit_text(callback.message, f"\u0414\u0430\u0442\u0430: {target_date.strftime('%d.%m.%Y')}\n\n\u0412\u0432\u0435\u0434\u0438 \u0432\u0440\u0435\u043c\u044f \u043d\u0430\u0447\u0430\u043b\u0430 \u0440\u0430\u0431\u043e\u0442\u044b \u0432 \u0444\u043e\u0440\u043c\u0430\u0442\u0435 \u0427\u0427:\u041c\u041c.", reply_markup=cancel_creation_keyboard(f"schedule:{master_id}"))


@router.message(ScheduleCreateStates.waiting_for_default_start)
async def schedule_default_start_input(message: Message, state: FSMContext) -> None:
    raw_time = (message.text or "").strip()
    try:
        start_value = datetime.strptime(raw_time, "%H:%M").time()
    except ValueError:
        await message.answer("\u041d\u0435 \u0441\u043c\u043e\u0433 \u0440\u0430\u0441\u043f\u043e\u0437\u043d\u0430\u0442\u044c \u0432\u0440\u0435\u043c\u044f. \u0418\u0441\u043f\u043e\u043b\u044c\u0437\u0443\u0439 \u0444\u043e\u0440\u043c\u0430\u0442 \u0427\u0427:\u041c\u041c")
        return
    await state.update_data(default_start_time=start_value.strftime("%H:%M"))
    await state.set_state(ScheduleCreateStates.waiting_for_default_end)
    await message.answer("\u0422\u0435\u043f\u0435\u0440\u044c \u0432\u0432\u0435\u0434\u0438 \u043e\u0431\u0449\u0435\u0435 \u0432\u0440\u0435\u043c\u044f \u043e\u043a\u043e\u043d\u0447\u0430\u043d\u0438\u044f \u0440\u0430\u0431\u043e\u0442\u044b \u0432 \u0444\u043e\u0440\u043c\u0430\u0442\u0435 \u0427\u0427:\u041c\u041c. \u041d\u0430\u043f\u0440\u0438\u043c\u0435\u0440: 20:00")


@router.message(ScheduleCreateStates.waiting_for_default_end)
async def schedule_default_end_input(message: Message, state: FSMContext) -> None:
    raw_time = (message.text or "").strip()
    try:
        end_value = datetime.strptime(raw_time, "%H:%M").time()
    except ValueError:
        await message.answer("\u041d\u0435 \u0441\u043c\u043e\u0433 \u0440\u0430\u0441\u043f\u043e\u0437\u043d\u0430\u0442\u044c \u0432\u0440\u0435\u043c\u044f. \u0418\u0441\u043f\u043e\u043b\u044c\u0437\u0443\u0439 \u0444\u043e\u0440\u043c\u0430\u0442 \u0427\u0427:\u041c\u041c")
        return
    payload = await state.get_data()
    start_value = datetime.strptime(payload["default_start_time"], "%H:%M").time()
    if end_value <= start_value:
        await message.answer("\u0412\u0440\u0435\u043c\u044f \u043e\u043a\u043e\u043d\u0447\u0430\u043d\u0438\u044f \u0434\u043e\u043b\u0436\u043d\u043e \u0431\u044b\u0442\u044c \u043f\u043e\u0437\u0436\u0435 \u0432\u0440\u0435\u043c\u0435\u043d\u0438 \u043d\u0430\u0447\u0430\u043b\u0430.")
        return
    async with SessionLocal() as session:
        await set_default_work_hours(session, start_value, end_value)
    await state.clear()
    await message.answer(f"\u041e\u0431\u0449\u0438\u0435 \u0447\u0430\u0441\u044b \u0440\u0430\u0431\u043e\u0442\u044b \u043e\u0431\u043d\u043e\u0432\u043b\u0435\u043d\u044b: {start_value.strftime('%H:%M')} - {end_value.strftime('%H:%M')}")


@router.message(ScheduleCreateStates.waiting_for_start_time)
async def schedule_start_input(message: Message, state: FSMContext) -> None:
    raw_time = (message.text or "").strip()
    try:
        start_value = datetime.strptime(raw_time, "%H:%M").time()
    except ValueError:
        await message.answer("\u041d\u0435 \u0441\u043c\u043e\u0433 \u0440\u0430\u0441\u043f\u043e\u0437\u043d\u0430\u0442\u044c \u0432\u0440\u0435\u043c\u044f. \u0418\u0441\u043f\u043e\u043b\u044c\u0437\u0443\u0439 \u0444\u043e\u0440\u043c\u0430\u0442 \u0427\u0427:\u041c\u041c")
        return
    await state.update_data(start_time=start_value.strftime("%H:%M"))
    await state.set_state(ScheduleCreateStates.waiting_for_end_time)
    await message.answer("\u0422\u0435\u043f\u0435\u0440\u044c \u0432\u0432\u0435\u0434\u0438 \u0432\u0440\u0435\u043c\u044f \u043e\u043a\u043e\u043d\u0447\u0430\u043d\u0438\u044f \u0440\u0430\u0431\u043e\u0442\u044b \u0432 \u0444\u043e\u0440\u043c\u0430\u0442\u0435 \u0427\u0427:\u041c\u041c. \u041d\u0430\u043f\u0440\u0438\u043c\u0435\u0440: 19:30")


@router.message(ScheduleCreateStates.waiting_for_end_time)
async def schedule_end_input(message: Message, state: FSMContext) -> None:
    raw_time = (message.text or "").strip()
    try:
        end_value = datetime.strptime(raw_time, "%H:%M").time()
    except ValueError:
        await message.answer("\u041d\u0435 \u0441\u043c\u043e\u0433 \u0440\u0430\u0441\u043f\u043e\u0437\u043d\u0430\u0442\u044c \u0432\u0440\u0435\u043c\u044f. \u0418\u0441\u043f\u043e\u043b\u044c\u0437\u0443\u0439 \u0444\u043e\u0440\u043c\u0430\u0442 \u0427\u0427:\u041c\u041c")
        return
    payload = await state.get_data()
    start_value = datetime.strptime(payload["start_time"], "%H:%M").time()
    if end_value <= start_value:
        await message.answer("\u0412\u0440\u0435\u043c\u044f \u043e\u043a\u043e\u043d\u0447\u0430\u043d\u0438\u044f \u0434\u043e\u043b\u0436\u043d\u043e \u0431\u044b\u0442\u044c \u043f\u043e\u0437\u0436\u0435 \u0432\u0440\u0435\u043c\u0435\u043d\u0438 \u043d\u0430\u0447\u0430\u043b\u0430.")
        return
    await state.update_data(end_time=end_value.strftime("%H:%M"))
    await state.set_state(ScheduleCreateStates.waiting_for_note)
    await message.answer("\u0414\u043e\u0431\u0430\u0432\u044c \u043a\u043e\u043c\u043c\u0435\u043d\u0442\u0430\u0440\u0438\u0439 \u0434\u043b\u044f \u044d\u0442\u043e\u0439 \u0434\u0430\u0442\u044b \u0438\u043b\u0438 \u043e\u0442\u043f\u0440\u0430\u0432\u044c '-' \u0435\u0441\u043b\u0438 \u043d\u0435 \u043d\u0443\u0436\u043d\u043e.")


@router.message(ScheduleCreateStates.waiting_for_note)
async def schedule_note_input(message: Message, state: FSMContext) -> None:
    note = (message.text or "").strip()
    payload = await state.get_data()
    async with SessionLocal() as session:
        day = await upsert_schedule_day(
            session,
            target_date=date.fromisoformat(payload["schedule_date"]),
            is_working_day=True,
            start_time=datetime.strptime(payload["start_time"], "%H:%M").time(),
            end_time=datetime.strptime(payload["end_time"], "%H:%M").time(),
            note=None if note == "-" else note,
            master_id=payload.get("schedule_master_id"),
        )
        master = await get_master(session, payload.get("schedule_master_id"))
    await state.clear()
    master_name = master.name if master is not None else "\u043c\u0430\u0441\u0442\u0435\u0440"
    await message.answer(f"\u0421\u043e\u0445\u0440\u0430\u043d\u0435\u043d\u043e \u0434\u043b\u044f {master_name}: {day.work_date.strftime('%d.%m.%Y')}\n\u0412\u0440\u0435\u043c\u044f: {day.start_time.strftime('%H:%M')} - {day.end_time.strftime('%H:%M')}")


@router.callback_query(F.data.startswith("admin:schedule:view:"))
async def admin_schedule_view_callback(callback: CallbackQuery) -> None:
    _, _, _, master_id_raw, date_raw = callback.data.split(":")
    master_id = int(master_id_raw)
    target_date = date.fromisoformat(date_raw)
    async with SessionLocal() as session:
        day = await get_schedule_day(session, target_date, master_id=master_id)
    await safe_answer_callback(callback)
    if day is None:
        await safe_edit_text(callback.message, "\u0418\u0441\u043a\u043b\u044e\u0447\u0435\u043d\u0438\u0435 \u0434\u043b\u044f \u044d\u0442\u043e\u0439 \u0434\u0430\u0442\u044b \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d\u043e.", reply_markup=admin_back_keyboard())
        return
    await safe_edit_text(callback.message, format_schedule_day(day), reply_markup=schedule_day_keyboard(master_id, target_date))


@router.callback_query(F.data.startswith("admin:schedule:delete:"))
async def admin_schedule_delete_callback(callback: CallbackQuery) -> None:
    _, _, _, master_id_raw, date_raw = callback.data.split(":")
    master_id = int(master_id_raw)
    target_date = date.fromisoformat(date_raw)
    async with SessionLocal() as session:
        deleted = await delete_schedule_override(session, target_date, master_id=master_id)
    await safe_answer_callback(callback, "\u0418\u0441\u043a\u043b\u044e\u0447\u0435\u043d\u0438\u0435 \u0443\u0434\u0430\u043b\u0435\u043d\u043e" if deleted else "\u0418\u0441\u043a\u043b\u044e\u0447\u0435\u043d\u0438\u0435 \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d\u043e")
    await render_schedule_overrides(callback, master_id)


@router.callback_query(F.data.startswith("admin:schedule:blocks:"))
async def admin_schedule_blocks_callback(callback: CallbackQuery, state: FSMContext) -> None:
    master_id = int(callback.data.rsplit(":", 1)[-1])
    await state.clear()
    await safe_answer_callback(callback)
    await render_schedule_blocks(callback, master_id)


@router.callback_query(F.data.startswith("admin:schedule:block:add:"))
async def admin_schedule_block_add_callback(callback: CallbackQuery, state: FSMContext) -> None:
    master_id = int(callback.data.rsplit(":", 1)[-1])
    await state.clear()
    await safe_answer_callback(callback)
    await safe_edit_text(callback.message, "\u0412\u044b\u0431\u0435\u0440\u0438 \u0434\u0430\u0442\u0443 \u0434\u043b\u044f \u0431\u043b\u043e\u043a\u0438\u0440\u043e\u0432\u043a\u0438.", reply_markup=date_picker_keyboard(f"admin:schedule:block:date:{master_id}", back_callback=f"admin:schedule:blocks:{master_id}"))


@router.callback_query(F.data.startswith("admin:schedule:block:date:"))
async def admin_schedule_block_date_callback(callback: CallbackQuery, state: FSMContext) -> None:
    _, _, _, _, master_id_raw, date_raw = callback.data.split(":")
    master_id = int(master_id_raw)
    target_date = date.fromisoformat(date_raw)
    await state.clear()
    await state.update_data(block_date=target_date.isoformat(), block_master_id=master_id)
    await state.set_state(ScheduleCreateStates.waiting_for_block_start)
    await safe_answer_callback(callback)
    await safe_edit_text(callback.message, f"\u0414\u0430\u0442\u0430: {target_date.strftime('%d.%m.%Y')}\n\n\u0412\u0432\u0435\u0434\u0438 \u0432\u0440\u0435\u043c\u044f \u043d\u0430\u0447\u0430\u043b\u0430 \u0431\u043b\u043e\u043a\u0438\u0440\u043e\u0432\u043a\u0438 \u0432 \u0444\u043e\u0440\u043c\u0430\u0442\u0435 \u0427\u0427:\u041c\u041c.", reply_markup=cancel_creation_keyboard(f"schedule_blocks:{master_id}"))


@router.message(ScheduleCreateStates.waiting_for_block_start)
async def schedule_block_start_input(message: Message, state: FSMContext) -> None:
    raw_time = (message.text or "").strip()
    try:
        start_value = datetime.strptime(raw_time, "%H:%M").time()
    except ValueError:
        await message.answer("\u041d\u0435 \u0441\u043c\u043e\u0433 \u0440\u0430\u0441\u043f\u043e\u0437\u043d\u0430\u0442\u044c \u0432\u0440\u0435\u043c\u044f. \u0418\u0441\u043f\u043e\u043b\u044c\u0437\u0443\u0439 \u0444\u043e\u0440\u043c\u0430\u0442 \u0427\u0427:\u041c\u041c")
        return
    await state.update_data(block_start_time=start_value.strftime("%H:%M"))
    await state.set_state(ScheduleCreateStates.waiting_for_block_end)
    await message.answer("\u0422\u0435\u043f\u0435\u0440\u044c \u0432\u0432\u0435\u0434\u0438 \u0432\u0440\u0435\u043c\u044f \u043e\u043a\u043e\u043d\u0447\u0430\u043d\u0438\u044f \u0431\u043b\u043e\u043a\u0438\u0440\u043e\u0432\u043a\u0438 \u0432 \u0444\u043e\u0440\u043c\u0430\u0442\u0435 \u0427\u0427:\u041c\u041c.")


@router.message(ScheduleCreateStates.waiting_for_block_end)
async def schedule_block_end_input(message: Message, state: FSMContext) -> None:
    raw_time = (message.text or "").strip()
    try:
        end_value = datetime.strptime(raw_time, "%H:%M").time()
    except ValueError:
        await message.answer("\u041d\u0435 \u0441\u043c\u043e\u0433 \u0440\u0430\u0441\u043f\u043e\u0437\u043d\u0430\u0442\u044c \u0432\u0440\u0435\u043c\u044f. \u0418\u0441\u043f\u043e\u043b\u044c\u0437\u0443\u0439 \u0444\u043e\u0440\u043c\u0430\u0442 \u0427\u0427:\u041c\u041c")
        return
    payload = await state.get_data()
    start_value = datetime.strptime(payload["block_start_time"], "%H:%M").time()
    if end_value <= start_value:
        await message.answer("\u0412\u0440\u0435\u043c\u044f \u043e\u043a\u043e\u043d\u0447\u0430\u043d\u0438\u044f \u0434\u043e\u043b\u0436\u043d\u043e \u0431\u044b\u0442\u044c \u043f\u043e\u0437\u0436\u0435 \u0432\u0440\u0435\u043c\u0435\u043d\u0438 \u043d\u0430\u0447\u0430\u043b\u0430.")
        return
    await state.update_data(block_end_time=end_value.strftime("%H:%M"))
    await state.set_state(ScheduleCreateStates.waiting_for_block_reason)
    await message.answer("\u0423\u043a\u0430\u0436\u0438 \u043f\u0440\u0438\u0447\u0438\u043d\u0443 \u0431\u043b\u043e\u043a\u0438\u0440\u043e\u0432\u043a\u0438 \u0438\u043b\u0438 \u043e\u0442\u043f\u0440\u0430\u0432\u044c '-' \u0435\u0441\u043b\u0438 \u043d\u0435 \u043d\u0443\u0436\u043d\u043e.")


@router.message(ScheduleCreateStates.waiting_for_block_reason)
async def schedule_block_reason_input(message: Message, state: FSMContext) -> None:
    reason = (message.text or "").strip()
    payload = await state.get_data()
    async with SessionLocal() as session:
        blocked_period = await create_blocked_period(
            session,
            target_date=date.fromisoformat(payload["block_date"]),
            start_time=datetime.strptime(payload["block_start_time"], "%H:%M").time(),
            end_time=datetime.strptime(payload["block_end_time"], "%H:%M").time(),
            reason=None if reason == "-" else reason,
            master_id=payload.get("block_master_id"),
        )
        master = await get_master(session, payload.get("block_master_id"))
    await state.clear()
    master_name = master.name if master is not None else "\u043c\u0430\u0441\u0442\u0435\u0440"
    await message.answer(f"\u0411\u043b\u043e\u043a\u0438\u0440\u043e\u0432\u043a\u0430 \u0441\u043e\u0445\u0440\u0430\u043d\u0435\u043d\u0430 \u0434\u043b\u044f {master_name}:\n{blocked_period.start_at.strftime('%d.%m.%Y %H:%M')} - {blocked_period.end_at.strftime('%H:%M')}")


@router.callback_query(F.data.startswith("admin:schedule:block:view:"))
async def admin_schedule_block_view_callback(callback: CallbackQuery) -> None:
    _, _, _, _, master_id_raw, blocked_period_id_raw = callback.data.split(":")
    master_id = int(master_id_raw)
    blocked_period_id = int(blocked_period_id_raw)
    async with SessionLocal() as session:
        blocked_period = await get_blocked_period(session, blocked_period_id)
    await safe_answer_callback(callback)
    if blocked_period is None:
        await safe_edit_text(callback.message, "\u0411\u043b\u043e\u043a\u0438\u0440\u043e\u0432\u043a\u0430 \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d\u0430.", reply_markup=admin_back_keyboard())
        return
    await safe_edit_text(callback.message, format_blocked_period(blocked_period), reply_markup=blocked_period_keyboard(master_id, blocked_period.id))


@router.callback_query(F.data.startswith("admin:schedule:block:delete:"))
async def admin_schedule_block_delete_callback(callback: CallbackQuery) -> None:
    _, _, _, _, master_id_raw, blocked_period_id_raw = callback.data.split(":")
    master_id = int(master_id_raw)
    blocked_period_id = int(blocked_period_id_raw)
    async with SessionLocal() as session:
        deleted = await delete_blocked_period(session, blocked_period_id)
    await safe_answer_callback(callback, "\u0411\u043b\u043e\u043a\u0438\u0440\u043e\u0432\u043a\u0430 \u0443\u0434\u0430\u043b\u0435\u043d\u0430" if deleted else "\u0411\u043b\u043e\u043a\u0438\u0440\u043e\u0432\u043a\u0430 \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d\u0430")
    await render_schedule_blocks(callback, master_id)


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
    await state.clear()
    await safe_answer_callback(callback, "\u0414\u0435\u0439\u0441\u0442\u0432\u0438\u0435 \u043e\u0442\u043c\u0435\u043d\u0435\u043d\u043e")
    if callback.data == "admin:cancel:services":
        await render_services(callback)
        return
    if callback.data == "admin:cancel:masters":
        await render_masters(callback)
        return
    if callback.data == "admin:cancel:schedule":
        await render_schedule(callback)
        return
    if callback.data.startswith("admin:cancel:schedule_blocks:"):
        master_id = int(callback.data.rsplit(":", 1)[-1])
        await render_schedule_blocks(callback, master_id)
        return
    if callback.data.startswith("admin:cancel:schedule:"):
        master_id = int(callback.data.rsplit(":", 1)[-1])
        await render_schedule_master(callback, master_id)
        return
    if callback.data == "admin:cancel:contacts":
        await render_contacts(callback)
        return
    if callback.data == "admin:cancel:settings":
        await render_settings(callback)
        return
    if callback.data == "admin:cancel:bookings":
        await render_bookings_menu(callback)
        return
    await render_admin_menu(callback)


@router.callback_query(F.data == "admin:close")
async def admin_close_callback(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await safe_answer_callback(callback)
    await safe_edit_text(callback.message, "Админ-панель закрыта.")

