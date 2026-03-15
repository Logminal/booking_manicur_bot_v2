from __future__ import annotations

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class Master(TimestampMixin, Base):
    __tablename__ = "masters"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    services = relationship("Service", back_populates="master")
    schedule_days = relationship("ScheduleDay", back_populates="master")
    bookings = relationship("Booking", back_populates="master")
    blocked_periods = relationship("BlockedPeriod", back_populates="master")
