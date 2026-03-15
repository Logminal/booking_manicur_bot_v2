from __future__ import annotations

from app.models.enums import BookingStatus


def booking_status_label(status: BookingStatus | str) -> str:
    value = status.value if isinstance(status, BookingStatus) else str(status)
    mapping = {
        BookingStatus.PENDING.value: "Ожидает подтверждения",
        BookingStatus.CONFIRMED.value: "Подтверждена",
        BookingStatus.CANCELLED.value: "Отменена",
        BookingStatus.COMPLETED.value: "Завершена",
    }
    return mapping.get(value, value)
