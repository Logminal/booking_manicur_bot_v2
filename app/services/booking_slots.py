from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from math import ceil

from app.models.enums import BookingStatus


@dataclass(slots=True)
class TimeRange:
    start_at: datetime
    end_at: datetime

    def overlaps(self, other: "TimeRange") -> bool:
        return self.start_at < other.end_at and other.start_at < self.end_at


@dataclass(slots=True)
class SlotCalculationInput:
    target_date: date
    day_start: time
    day_end: time
    slot_minutes: int
    service_duration_minutes: int
    busy_ranges: list[TimeRange]
    blocked_ranges: list[TimeRange]


class SlotCalculator:
    def __init__(self, payload: SlotCalculationInput) -> None:
        self.payload = payload

    def build_available_slots(self) -> list[datetime]:
        step = timedelta(minutes=self.payload.slot_minutes)
        service_delta = timedelta(minutes=self.payload.service_duration_minutes)

        current = datetime.combine(self.payload.target_date, self.payload.day_start)
        day_end = datetime.combine(self.payload.target_date, self.payload.day_end)
        available_slots: list[datetime] = []

        while current + service_delta <= day_end:
            candidate = TimeRange(start_at=current, end_at=current + service_delta)
            if self._is_range_available(candidate):
                available_slots.append(current)
            current += step

        return available_slots

    def required_slot_count(self) -> int:
        return ceil(self.payload.service_duration_minutes / self.payload.slot_minutes)

    def _is_range_available(self, candidate: TimeRange) -> bool:
        ranges = [*self.payload.busy_ranges, *self.payload.blocked_ranges]
        return not any(candidate.overlaps(existing) for existing in ranges)


def build_busy_ranges(bookings: list[tuple[datetime, datetime, BookingStatus]]) -> list[TimeRange]:
    active_statuses = {BookingStatus.PENDING, BookingStatus.CONFIRMED}
    return [
        TimeRange(start_at=start_at, end_at=end_at)
        for start_at, end_at, status in bookings
        if status in active_statuses
    ]
