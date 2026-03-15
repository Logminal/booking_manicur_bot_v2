from __future__ import annotations

from datetime import date, timedelta

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.formatters import booking_status_label
from app.models.booking import Booking
from app.models.schedule import BlockedPeriod, ScheduleDay
from app.models.service import Service


DATE_PICKER_DAYS = 21


def admin_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Услуги", callback_data="admin:services")],
        [InlineKeyboardButton(text="График", callback_data="admin:schedule")],
        [InlineKeyboardButton(text="Записи", callback_data="admin:bookings")],
        [InlineKeyboardButton(text="Контакты мастера", callback_data="admin:contacts")],
        [InlineKeyboardButton(text="Настройки", callback_data="admin:settings")],
        [InlineKeyboardButton(text="Закрыть", callback_data="admin:close")],
    ])


def admin_back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Назад", callback_data="admin:menu")]])


def services_menu_keyboard(services: list[Service]) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text="Добавить услугу", callback_data="admin:service:add")]]
    for service in services:
        status = "ON" if service.is_active else "OFF"
        rows.append([InlineKeyboardButton(text=f"{service.name} [{status}]", callback_data=f"admin:service:view:{service.id}")])
    rows.append([InlineKeyboardButton(text="Назад", callback_data="admin:menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def service_actions_keyboard(service_id: int, is_active: bool) -> InlineKeyboardMarkup:
    toggle_text = "Выключить" if is_active else "Включить"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Изменить название", callback_data=f"admin:service:edit:name:{service_id}")],
        [InlineKeyboardButton(text="Изменить цену", callback_data=f"admin:service:edit:price:{service_id}")],
        [InlineKeyboardButton(text="Изменить длительность", callback_data=f"admin:service:edit:duration:{service_id}")],
        [InlineKeyboardButton(text="Изменить описание", callback_data=f"admin:service:edit:description:{service_id}")],
        [InlineKeyboardButton(text=toggle_text, callback_data=f"admin:service:toggle:{service_id}")],
        [InlineKeyboardButton(text="Удалить", callback_data=f"admin:service:delete:{service_id}")],
        [InlineKeyboardButton(text="К списку услуг", callback_data="admin:services")],
    ])


def settings_keyboard(auto_confirm_enabled: bool) -> InlineKeyboardMarkup:
    toggle_text = "Выключить автоподтверждение" if auto_confirm_enabled else "Включить автоподтверждение"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=toggle_text, callback_data="admin:settings:toggle_auto_confirm")],
        [InlineKeyboardButton(text="Изменить приветствие", callback_data="admin:settings:greeting")],
        [InlineKeyboardButton(text="Назад", callback_data="admin:menu")],
    ])


def schedule_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Общие часы работы", callback_data="admin:schedule:defaults")],
        [InlineKeyboardButton(text="Исключения по датам", callback_data="admin:schedule:overrides")],
        [InlineKeyboardButton(text="Ручные блокировки", callback_data="admin:schedule:blocks")],
        [InlineKeyboardButton(text="Назад", callback_data="admin:menu")],
    ])


def schedule_overrides_keyboard(overrides: list[ScheduleDay]) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text="Добавить исключение", callback_data="admin:schedule:override:add")]]
    for day in overrides:
        label = day.work_date.strftime("%d.%m.%Y")
        if not day.is_working_day:
            label = f"{label} • выходной"
        elif day.start_time and day.end_time:
            label = f"{label} • {day.start_time.strftime('%H:%M')}-{day.end_time.strftime('%H:%M')}"
        rows.append([InlineKeyboardButton(text=label, callback_data=f"admin:schedule:view:{day.work_date.isoformat()}")])
    rows.append([InlineKeyboardButton(text="К графику", callback_data="admin:schedule")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def schedule_day_keyboard(target_date: date) -> InlineKeyboardMarkup:
    iso_date = target_date.isoformat()
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Изменить", callback_data=f"admin:schedule:override:date:{iso_date}")],
        [InlineKeyboardButton(text="Удалить исключение", callback_data=f"admin:schedule:delete:{iso_date}")],
        [InlineKeyboardButton(text="К исключениям", callback_data="admin:schedule:overrides")],
    ])


def schedule_mode_keyboard(target_date: date) -> InlineKeyboardMarkup:
    iso_date = target_date.isoformat()
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Выходной", callback_data=f"admin:schedule:mode:off:{iso_date}")],
        [InlineKeyboardButton(text="Особые часы", callback_data=f"admin:schedule:mode:work:{iso_date}")],
        [InlineKeyboardButton(text="Назад", callback_data="admin:schedule:overrides")],
    ])


def date_picker_keyboard(prefix: str, *, back_callback: str) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    today = date.today()
    for offset in range(0, DATE_PICKER_DAYS, 3):
        row: list[InlineKeyboardButton] = []
        for inner in range(3):
            index = offset + inner
            if index >= DATE_PICKER_DAYS:
                continue
            target_date = today + timedelta(days=index)
            label = target_date.strftime("%d.%m")
            if index == 0:
                label = f"Сегодня\n{label}"
            elif index == 1:
                label = f"Завтра\n{label}"
            row.append(InlineKeyboardButton(text=label, callback_data=f"{prefix}:{target_date.isoformat()}"))
        if row:
            rows.append(row)
    rows.append([InlineKeyboardButton(text="Назад", callback_data=back_callback)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def blocked_periods_keyboard(blocked_periods: list[BlockedPeriod]) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text="Добавить блокировку", callback_data="admin:schedule:block:add")]]
    for blocked_period in blocked_periods:
        label = f"{blocked_period.start_at.strftime('%d.%m %H:%M')} - {blocked_period.end_at.strftime('%H:%M')}"
        rows.append([InlineKeyboardButton(text=label, callback_data=f"admin:schedule:block:view:{blocked_period.id}")])
    rows.append([InlineKeyboardButton(text="К графику", callback_data="admin:schedule")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def blocked_period_keyboard(blocked_period_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Удалить блокировку", callback_data=f"admin:schedule:block:delete:{blocked_period_id}")],
        [InlineKeyboardButton(text="К блокировкам", callback_data="admin:schedule:blocks")],
    ])


def bookings_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Ближайшие записи", callback_data="admin:bookings:list")],
        [InlineKeyboardButton(text="Выбрать дату", callback_data="admin:bookings:pick_date")],
        [InlineKeyboardButton(text="Назад", callback_data="admin:menu")],
    ])


def bookings_keyboard(bookings: list[Booking], *, back_callback: str = "admin:bookings") -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for booking in bookings:
        when = booking.start_at.strftime("%d.%m %H:%M")
        rows.append([InlineKeyboardButton(text=f"#{booking.id} • {when} • {booking_status_label(booking.status)}", callback_data=f"admin:booking:view:{booking.id}")])
    rows.append([InlineKeyboardButton(text="Обновить", callback_data=back_callback)])
    rows.append([InlineKeyboardButton(text="Назад", callback_data="admin:bookings")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def booking_actions_keyboard(booking_id: int, status: str) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if status == "pending":
        rows.append([InlineKeyboardButton(text="Подтвердить", callback_data=f"admin:booking:confirm:{booking_id}")])
        rows.append([InlineKeyboardButton(text="Отклонить", callback_data=f"admin:booking:cancel:{booking_id}")])
    elif status == "confirmed":
        rows.append([InlineKeyboardButton(text="Перенести", callback_data=f"admin:booking:reschedule:{booking_id}")])
        rows.append([InlineKeyboardButton(text="Завершить", callback_data=f"admin:booking:complete:{booking_id}")])
        rows.append([InlineKeyboardButton(text="Отменить запись", callback_data=f"admin:booking:cancel:{booking_id}")])
    rows.append([InlineKeyboardButton(text="Заметка к клиенту", callback_data=f"admin:booking:note:{booking_id}")])
    rows.append([InlineKeyboardButton(text="К списку записей", callback_data="admin:bookings")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def reschedule_slots_keyboard(booking_id: int, target_date: date, slots: list[date | object]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for slot in slots:
        rows.append([InlineKeyboardButton(text=slot.strftime("%H:%M"), callback_data=f"admin:booking:reslot:{booking_id}:{target_date.isoformat()}:{slot.strftime('%H-%M')}")])
    rows.append([InlineKeyboardButton(text="К выбору даты", callback_data=f"admin:booking:reschedule:{booking_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def contacts_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Изменить имя", callback_data="admin:contacts:name")],
        [InlineKeyboardButton(text="Изменить телефон", callback_data="admin:contacts:phone")],
        [InlineKeyboardButton(text="Изменить Telegram", callback_data="admin:contacts:telegram")],
        [InlineKeyboardButton(text="Изменить Instagram", callback_data="admin:contacts:instagram")],
        [InlineKeyboardButton(text="Назад", callback_data="admin:menu")],
    ])


def cancel_creation_keyboard(section: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Отмена", callback_data=f"admin:cancel:{section}")]])
