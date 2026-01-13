# Reminder Service

Standalone microservice that polls the PostgreSQL database for due reminders and sends them via Telegram Bot API.

## Overview

This service runs independently from the main Telegram bot application. It continuously polls the database for reminders that are due and sends them to users via Telegram.

## Configuration

The service requires the following environment variables:

- `TELEGRAM_BOT_TOKEN` - Telegram bot token for sending reminder messages
- `DATABASE_URL` - PostgreSQL connection URL (e.g., `postgresql://user:password@localhost:5432/dbname`)
- `REMINDER_POLL_INTERVAL` - Poll interval in seconds (default: 60)

## Running the Service

```bash
python -m services.reminder_service.main
```

Or from the project root:

```bash
python services/reminder_service/main.py
```

## Architecture

The service follows a microservice pattern:

- **Independent deployment**: Can be deployed separately from the main bot
- **Database connection**: Connects directly to PostgreSQL
- **Telegram integration**: Uses Telegram Bot API to send messages
- **Polling mechanism**: Checks for due reminders at configured intervals
- **Recurring reminders**: Handles recurring reminders by creating next occurrences

## Components

- `service.py` - Main service class that handles polling and sending reminders
- `database.py` - Database operations for reminders
- `config.py` - Configuration management from environment variables
- `main.py` - Entry point for the standalone service

## Future Enhancements

- Docker containerization
- Health check endpoints
- Metrics and monitoring
- Retry logic for failed message sends
- Rate limiting for Telegram API
