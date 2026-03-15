from __future__ import annotations

from sqlalchemy import Enum, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin
from app.models.enums import SettingKey


class AppSetting(TimestampMixin, Base):
    __tablename__ = "app_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[SettingKey] = mapped_column(Enum(SettingKey), unique=True, nullable=False)
    value: Mapped[str] = mapped_column(String(255), nullable=False)
