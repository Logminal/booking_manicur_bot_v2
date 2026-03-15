# MVP Architecture

## Core modules

- `app/config.py` reads environment settings.
- `app/db/` stores database bootstrap and async session setup.
- `app/models/` contains domain entities for clients, admins, services, schedules, bookings, and reminders.
- `app/services/booking_slots.py` calculates available start times with a 30-minute step and arbitrary service duration.
- `app/bot/` is reserved for client Telegram handlers.
- `app/admin/` is reserved for admin Telegram workflows.

## Main business rules

- Services are managed by admins and define price plus duration in minutes.
- Working time is configured by concrete dates, not weekdays.
- The visible schedule step is 30 minutes by default.
- A service can occupy several consecutive 30-minute slots.
- A client may have multiple active bookings.
- Client cancellation is allowed only earlier than 60 minutes before start.
- Booking confirmation can be automatic or manual.
- Reminders should be sent 24 hours and 1 hour before start.

## Data model overview

- `admins`: Telegram admins with access to management flows.
- `clients`: Telegram users who create bookings.
- `masters`: one master for now, but schema supports several.
- `services`: editable manicure services with duration and price.
- `schedule_days`: working day settings for each date.
- `blocked_periods`: manual pauses, breaks, vacations, or ad hoc locks.
- `bookings`: client appointments with start, end, and status.
- `notification_logs`: sent reminder history.
- `app_settings`: runtime toggles such as auto confirmation.

## Booking flow draft

1. Client opens the bot.
2. Client selects a service.
3. Bot shows available dates with configured work hours.
4. Bot calculates available start times for the selected duration.
5. Client confirms the slot.
6. Booking becomes `confirmed` or `pending` depending on settings.
7. Reminders are sent before the appointment.

## Next implementation steps

1. Add database repositories and seed logic for the first admin/master.
2. Build basic `/start` and main menu handlers.
3. Implement admin service management.
4. Implement admin date schedule management.
5. Connect slot calculation to database queries.
