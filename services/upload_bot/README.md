# Upload Bot

> **Telegram-бот для загрузки учебных материалов в RAG**

Отдельный бот (собственный токен) для администраторов: приём документов через Telegram и постановка в очередь Ingestion Service для индексации в **глобальную** коллекцию Qdrant (`bstu_materials`).

> Для материалов **конкретного курса** платформы используйте загрузку в UI преподавателя или `POST /api/platform/courses/{id}/upload` — там создаётся per-course коллекция.

---

## Сценарий работы

1. Админ отправляет документ(ы) в бот  
2. Бот запрашивает список предметов у Ingestion Service (`GET /api/subjects`)  
3. Показывает кнопки выбора предмета (из Qdrant) или «Добавить новый»  
4. Пользователь выбирает предмет или вводит новый  
5. Файл отправляется в Ingestion Service (`POST /api/upload`) → Celery `process_document`  
6. Бот сообщает об успехе или ошибке  

Поддерживается **пакетная загрузка**: несколько документов в одном сообщении — один выбор предмета на всю пачку.

---

## Конфигурация

| Переменная | Описание |
|------------|----------|
| `UPLOAD_BOT_TOKEN` | Токен бота (отдельный от `TELEGRAM_BOT_TOKEN`) |
| `INGESTION_SERVICE_URL` | URL Ingestion Service (например, `http://localhost:8001`) |
| `ALLOWED_UPLOAD_USER_IDS` | Telegram user ID через запятую (пусто = доступ всем) |

---

## Поддерживаемые форматы

Соответствуют парсеру Ingestion Service (Docling + plain TXT):

| Категория | Расширения |
|-----------|------------|
| Документы | `.pdf`, `.docx`, `.doc`, `.pptx`, `.xlsx` |
| Разметка / данные | `.md`, `.html`, `.htm`, `.csv` |
| Изображения | `.png`, `.jpg`, `.jpeg`, `.tiff`, `.bmp`, `.webp` |
| Текст | `.txt` |

PDF обрабатывается через Docling VLM (OpenRouter); требуется `OPENROUTER_API_KEY` на стороне Ingestion Service / Celery worker.

---

## Запуск

### Локально

```bash
python -m services.upload_bot.main
```

Перед запуском убедитесь, что Ingestion Service и Celery worker доступны.

### Docker Compose

```bash
make bots          # профиль bots: telegram-bot + upload-bot
# или
make stack-full    # все профили
```

В compose:

```
INGESTION_SERVICE_URL=http://ingestion-service:8001
```

---

## Развёртывание

Бот использует **long polling** (вебхук не требуется). Запускается отдельным процессом или контейнером (`profiles: [bots]` в `docker-compose.yml`).

Код: `services/upload_bot/bot.py`, точка входа: `services/upload_bot/main.py`.
