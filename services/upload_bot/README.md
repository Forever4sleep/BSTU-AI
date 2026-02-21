# Upload Bot

Telegram bot for admins to upload documents to the Ingestion Service. Receives files from Telegram and POSTs them to the Ingestion Service API.

## Overview

The Upload Bot is a lightweight microservice that:
1. Receives document uploads from admins via Telegram
2. Fetches subjects from Ingestion Service (`GET /api/subjects`)
3. Shows subject selection buttons (from Qdrant payloads) or "Add new subject"
4. User selects subject (or types new one)
5. POSTs the file with subject to Ingestion Service `/api/upload`
6. Replies with success or error

## Configuration

Environment variables:

| Variable | Description |
|----------|-------------|
| `UPLOAD_BOT_TOKEN` | Telegram bot token (separate from main bot) |
| `INGESTION_SERVICE_URL` | Base URL of Ingestion Service (e.g. `http://localhost:8001`) |
| `ALLOWED_UPLOAD_USER_IDS` | Optional comma-separated Telegram user IDs (empty = all allowed) |

## Supported Formats

- PDF
- DOCX
- TXT

## Running the Bot

```bash
python -m services.upload_bot.main
```

Ensure the Ingestion Service is running and reachable at `INGESTION_SERVICE_URL` before starting the bot.

## Deployment

The bot uses polling (no webhook required). Deploy as a separate process/container. In Docker Compose, use the Ingestion Service hostname:

```
INGESTION_SERVICE_URL=http://ingestion-service:8001
```
