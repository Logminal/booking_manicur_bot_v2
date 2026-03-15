from __future__ import annotations

from enum import StrEnum


class BookingStatus(StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    COMPLETED = "completed"


class NotificationType(StrEnum):
    REMINDER_DAY = "reminder_day"
    REMINDER_HOUR = "reminder_hour"


class SettingKey(StrEnum):
    AUTO_CONFIRM_BOOKINGS = "auto_confirm_bookings"
    SLOT_MINUTES = "slot_minutes"
    CANCEL_LIMIT_MINUTES = "cancel_limit_minutes"
    GREETING_TEXT = "greeting_text"
    MASTER_CONTACT_NAME = "master_contact_name"
    MASTER_CONTACT_PHONE = "master_contact_phone"
    MASTER_CONTACT_TELEGRAM = "master_contact_telegram"
    MASTER_CONTACT_INSTAGRAM = "master_contact_instagram"
    DEFAULT_WORK_START = "default_work_start"
    DEFAULT_WORK_END = "default_work_end"
