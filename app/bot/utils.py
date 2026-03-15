from __future__ import annotations

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, Message


async def safe_answer_callback(
    callback: CallbackQuery,
    text: str | None = None,
    *,
    show_alert: bool = False,
) -> None:
    try:
        await callback.answer(text=text, show_alert=show_alert)
    except TelegramBadRequest as error:
        message = str(error).lower()
        if "query is too old" in message or "query id is invalid" in message:
            return
        raise


async def safe_edit_text(
    message: Message,
    text: str,
    **kwargs: object,
) -> None:
    try:
        await message.edit_text(text, **kwargs)
    except TelegramBadRequest as error:
        details = str(error).lower()
        if "message is not modified" in details:
            return
        raise
