FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Ensure Python can find modules when run from project root
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# Default command (override per service in docker-compose)
CMD ["python", "run_telegram_bot.py"]
