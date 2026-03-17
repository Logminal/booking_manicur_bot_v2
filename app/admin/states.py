from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class ServiceCreateStates(StatesGroup):
    waiting_for_name = State()
    waiting_for_price = State()
    waiting_for_duration = State()
    waiting_for_description = State()


class ServiceEditStates(StatesGroup):
    waiting_for_name = State()
    waiting_for_price = State()
    waiting_for_duration = State()
    waiting_for_description = State()


class MasterCreateStates(StatesGroup):
    waiting_for_name = State()


class MasterEditStates(StatesGroup):
    waiting_for_name = State()


class ScheduleCreateStates(StatesGroup):
    waiting_for_date = State()
    waiting_for_mode = State()
    waiting_for_start_time = State()
    waiting_for_end_time = State()
    waiting_for_note = State()
    waiting_for_default_start = State()
    waiting_for_default_end = State()
    waiting_for_block_start = State()
    waiting_for_block_end = State()
    waiting_for_block_reason = State()


class BookingAdminStates(StatesGroup):
    waiting_for_reschedule_time = State()
    waiting_for_client_note = State()


class SettingsStates(StatesGroup):
    waiting_for_greeting_text = State()
    waiting_for_master_name = State()
    waiting_for_master_phone = State()
    waiting_for_master_telegram = State()
    waiting_for_master_instagram = State()
