# syntax=docker/dockerfile:1
# Pip cache сохраняется между сборками (BuildKit)
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt

COPY . .

# Ensure Python can find modules when run from project root
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# Default command (override per service in docker-compose)
CMD ["python", "run_telegram_bot.py"]
