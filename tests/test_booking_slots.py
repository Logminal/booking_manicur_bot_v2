from datetime import date, datetime, time

from app.models.enums import BookingStatus
from app.services.booking_slots import SlotCalculationInput, SlotCalculator, TimeRange, build_busy_ranges


def test_slot_calculator_respects_busy_ranges() -> None:
    payload = SlotCalculationInput(
        target_date=date(2026, 3, 16),
        day_start=time(10, 0),
        day_end=time(14, 0),
        slot_minutes=30,
        service_duration_minutes=60,
        busy_ranges=[
            TimeRange(
                start_at=datetime(2026, 3, 16, 11, 0),
                end_at=datetime(2026, 3, 16, 12, 0),
            )
        ],
        blocked_ranges=[],
    )

    slots = SlotCalculator(payload).build_available_slots()

    assert slots == [
        datetime(2026, 3, 16, 10, 0),
        datetime(2026, 3, 16, 12, 0),
        datetime(2026, 3, 16, 12, 30),
        datetime(2026, 3, 16, 13, 0),
    ]


def test_build_busy_ranges_ignores_cancelled_bookings() -> None:
    busy_ranges = build_busy_ranges(
        [
            (
                datetime(2026, 3, 16, 10, 0),
                datetime(2026, 3, 16, 11, 0),
                BookingStatus.CONFIRMED,
            ),
            (
                datetime(2026, 3, 16, 12, 0),
                datetime(2026, 3, 16, 13, 0),
                BookingStatus.CANCELLED,
            ),
        ]
    )

    assert busy_ranges == [
        TimeRange(
            start_at=datetime(2026, 3, 16, 10, 0),
            end_at=datetime(2026, 3, 16, 11, 0),
        )
    ]
