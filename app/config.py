from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    bot_token: str = Field(default="", alias="BOT_TOKEN")
    database_url: str = Field(
        default="sqlite+aiosqlite:///booking_bot.db",
        alias="DATABASE_URL",
    )
    timezone: str = Field(default="Asia/Yekaterinburg", alias="TIMEZONE")
    slot_minutes: int = Field(default=30, alias="SLOT_MINUTES")
    cancel_limit_minutes: int = Field(default=60, alias="CANCEL_LIMIT_MINUTES")
    auto_confirm_bookings: bool = Field(
        default=True,
        alias="AUTO_CONFIRM_BOOKINGS",
    )
    admin_ids_raw: str = Field(default="", alias="ADMIN_IDS")

    @property
    def admin_ids(self) -> tuple[int, ...]:
        items = [item.strip() for item in self.admin_ids_raw.split(",") if item.strip()]
        return tuple(int(item) for item in items)


@lru_cache
def get_settings() -> Settings:
    return Settings()
