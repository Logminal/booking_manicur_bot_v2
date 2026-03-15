from __future__ import annotations

from datetime import date, datetime, timedelta

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Записаться", callback_data="menu:book")],
            [InlineKeyboardButton(text="Мои записи", callback_data="menu:my_bookings")],
            [InlineKeyboardButton(text="Контакты", callback_data="menu:contacts")],
            [InlineKeyboardButton(text="Помощь", callback_data="menu:help")],
        ]
    )


def services_keyboard(services: list[tuple[int, str, int, int]]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for service_id, name, price_rub, duration_minutes in services:
        rows.append([InlineKeyboardButton(text=f"{name} • {price_rub} руб. • {duration_minutes} мин", callback_data=f"book:service:{service_id}")])
    rows.append([InlineKeyboardButton(text="Назад", callback_data="menu:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def dates_keyboard(service_id: int, dates: list[date]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for index in range(0, len(dates), 3):
        row: list[InlineKeyboardButton] = []
        for target_date in dates[index:index + 3]:
            label = target_date.strftime("%d.%m")
            delta = (target_date - date.today()).days
            if delta == 0:
                label = f"Сегодня\n{label}"
            elif delta == 1:
                label = f"Завтра\n{label}"
            elif delta == 2:
                label = f"Послезавтра\n{label}"
            row.append(InlineKeyboardButton(text=label, callback_data=f"book:date:{service_id}:{target_date.isoformat()}"))
        rows.append(row)
    rows.append([InlineKeyboardButton(text="К услугам", callback_data="menu:book")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def slots_keyboard(service_id: int, target_date: date, slots: list[datetime]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for index in range(0, len(slots), 3):
        row = [InlineKeyboardButton(text=slot.strftime("%H:%M"), callback_data=f"book:slot:{service_id}:{target_date.isoformat()}:{slot.strftime('%H-%M')}") for slot in slots[index:index + 3]]
        rows.append(row)
    rows.append([InlineKeyboardButton(text="К датам", callback_data=f"book:service:{service_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def booking_confirm_keyboard(service_id: int, target_date: date, slot: datetime) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Подтвердить запись", callback_data=f"book:confirm:{service_id}:{target_date.isoformat()}:{slot.strftime('%H-%M')}")],
        [InlineKeyboardButton(text="К слотам", callback_data=f"book:date:{service_id}:{target_date.isoformat()}")],
    ])


def my_bookings_keyboard(items: list[tuple[int, str]]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for booking_id, label in items:
        rows.append([InlineKeyboardButton(text=label, callback_data=f"my:booking:{booking_id}")])
    rows.append([InlineKeyboardButton(text="Назад", callback_data="menu:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def booking_actions_keyboard(booking_id: int, can_cancel: bool) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if can_cancel:
        rows.append([InlineKeyboardButton(text="Отменить запись", callback_data=f"my:cancel:ask:{booking_id}")])
    rows.append([InlineKeyboardButton(text="К моим записям", callback_data="menu:my_bookings")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def cancel_booking_confirm_keyboard(booking_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Да, отменить", callback_data=f"my:cancel:confirm:{booking_id}")],
        [InlineKeyboardButton(text="Нет, оставить", callback_data=f"my:booking:{booking_id}")],
    ])


def _build_url(value: str, *, prefix: str) -> str | None:
    normalized = value.strip()
    if not normalized:
        return None
    if normalized.startswith("http://") or normalized.startswith("https://"):
        return normalized
    if normalized.startswith("@"):
        return f"{prefix}{normalized[1:]}"
    return f"{prefix}{normalized}"


def contacts_actions_keyboard(contacts: dict[str, str]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    telegram_url = _build_url(contacts.get("telegram", ""), prefix="https://t.me/")
    instagram_url = _build_url(contacts.get("instagram", ""), prefix="https://instagram.com/")
    if telegram_url:
        rows.append([InlineKeyboardButton(text="Открыть Telegram", url=telegram_url)])
    if instagram_url:
        rows.append([InlineKeyboardButton(text="Открыть Instagram", url=instagram_url)])
    rows.append([InlineKeyboardButton(text="Назад", callback_data="menu:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
