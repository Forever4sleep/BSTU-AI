"""
Upload Bot Implementation

Telegram bot for subject-specific document uploads to Ingestion Service.
User sends document(s), selects subject via buttons, then document(s) are indexed.
Supports batch upload: multiple documents sent as album share one subject selection.
"""

import logging
import tempfile
from pathlib import Path

import httpx
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from services.upload_bot.config import (
    get_allowed_upload_user_ids,
    get_ingestion_service_url,
)

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".doc", ".txt"}
CALLBACK_SUBJECT_PREFIX = "subject:"
CALLBACK_NEW_SUBJECT = "subject:__new__"
MEDIA_GROUP_DELAY_SEC = 2


class UploadBot:
    """Telegram bot for subject-specific document uploads to Ingestion Service."""

    def __init__(
        self,
        token: str,
        ingestion_service_url: str | None = None,
        allowed_user_ids: list[int] | None = None,
    ):
        self.token = token
        self.ingestion_service_url = ingestion_service_url or get_ingestion_service_url()
        self.allowed_user_ids = allowed_user_ids if allowed_user_ids is not None else get_allowed_upload_user_ids()

        self.application = Application.builder().token(token).build()
        self._setup_handlers()

    def _setup_handlers(self) -> None:
        """Set up command and message handlers."""
        self.application.add_handler(CommandHandler("start", self._handle_start))
        self.application.add_handler(CommandHandler("help", self._handle_help))
        self.application.add_handler(CallbackQueryHandler(self._handle_subject_callback))
        self.application.add_handler(
            MessageHandler(filters.Document.ALL, self._handle_document)
        )
        self.application.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_text)
        )

    def _is_user_allowed(self, user_id: int) -> bool:
        """Check if user is allowed to upload documents."""
        if not self.allowed_user_ids:
            return True
        return user_id in self.allowed_user_ids

    async def _handle_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /start command."""
        if not self._is_user_allowed(update.effective_user.id):
            await update.message.reply_text("У вас нет доступа к этому боту.")
            return

        await update.message.reply_text(
            "Добро пожаловать в бот загрузки материалов BSTU-AI.\n\n"
            "1. Отправьте документ или пачку документов (PDF, DOCX или TXT)\n"
            "2. Выберите предмет (для пачки — один раз на всю пачку)\n\n"
            "Команды:\n"
            "/help - справка"
        )

    async def _handle_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /help command."""
        if not self._is_user_allowed(update.effective_user.id):
            await update.message.reply_text("У вас нет доступа к этому боту.")
            return

        await update.message.reply_text(
            "Загрузка материалов BSTU-AI\n\n"
            "Поддерживаемые форматы: PDF, DOCX, TXT\n\n"
            "Отправьте документ или пачку документов, затем выберите предмет "
            "(для пачки — один раз на всю пачку)."
        )

    async def _fetch_subjects(self) -> list[str]:
        """Fetch unique subjects from Ingestion Service."""
        url = f"{self.ingestion_service_url}/api/subjects"
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url)
            if response.status_code != 200:
                return []
            data = response.json()
            return data.get("subjects", [])

    def _build_subject_keyboard(self, subjects: list[str]) -> InlineKeyboardMarkup:
        """Build inline keyboard with subject buttons (index-based for callback_data limit)."""
        buttons = []
        for i, subj in enumerate(subjects):
            buttons.append([
                InlineKeyboardButton(subj, callback_data=f"{CALLBACK_SUBJECT_PREFIX}{i}")
            ])
        buttons.append([
            InlineKeyboardButton("➕ Добавить новый предмет", callback_data=CALLBACK_NEW_SUBJECT)
        ])
        return InlineKeyboardMarkup(buttons)

    async def _handle_document(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle document - single or batch (media group)."""
        if not update.message or not update.message.document:
            return

        user_id = update.effective_user.id
        if not self._is_user_allowed(user_id):
            await update.message.reply_text("У вас нет доступа к загрузке документов.")
            return

        document = update.message.document
        file_name = document.file_name or "document"
        suffix = Path(file_name).suffix.lower()
        if suffix == ".doc":
            suffix = ".docx"

        if suffix not in SUPPORTED_EXTENSIONS:
            await update.message.reply_text(
                f"Неподдерживаемый формат: {suffix}. "
                f"Поддерживаются: PDF, DOCX, TXT"
            )
            return

        file_info = {"file_id": document.file_id, "file_name": file_name}

        if update.message.media_group_id and context.job_queue:
            # Batch: collect and schedule job
            mg_id = update.message.media_group_id
            jobs = context.job_queue.get_jobs_by_name(str(mg_id))
            if jobs:
                jobs[0].data["files"].append(file_info)
            else:
                context.job_queue.run_once(
                    callback=self._process_media_group_batch,
                    when=MEDIA_GROUP_DELAY_SEC,
                    data={"files": [file_info]},
                    chat_id=update.effective_chat.id,
                    user_id=user_id,
                    name=str(mg_id),
                )
            return

        # Single document: show subject selection immediately
        context.user_data["pending_upload"] = [file_info]
        context.user_data["awaiting_subject"] = False
        await self._show_subject_picker(context, update.message.reply_text, "этого документа")

    async def _process_media_group_batch(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Job callback: after delay, show subject picker for collected batch."""
        data = context.job.data
        files = data["files"]
        chat_id = context.job.chat_id

        if not files:
            return

        # context.user_data is writable when user_id was passed to run_once
        context.user_data["pending_upload"] = files
        context.user_data["awaiting_subject"] = False

        async def send(text: str):
            return await context.bot.send_message(chat_id=chat_id, text=text)

        status_msg = await send("Загрузка списка предметов...")
        try:
            subjects = await self._fetch_subjects()
        except httpx.ConnectError:
            await status_msg.edit_text(
                "Не удалось подключиться к сервису индексации. "
                "Проверьте, что Ingestion Service запущен."
            )
            context.user_data.pop("pending_upload", None)
            return

        context.user_data["subjects"] = subjects
        keyboard = self._build_subject_keyboard(subjects)

        label = "пачки документов" if len(files) > 1 else "документа"
        await status_msg.edit_text(
            f"Выберите предмет для {label} ({len(files)} файл(ов)):",
            reply_markup=keyboard,
        )

    async def _show_subject_picker(
        self,
        context: ContextTypes.DEFAULT_TYPE,
        reply_fn,
        doc_label: str,
    ) -> None:
        """Fetch subjects and show inline keyboard. reply_fn gets status text, returns message."""
        status_msg = await reply_fn("Загрузка списка предметов...")
        try:
            subjects = await self._fetch_subjects()
        except httpx.ConnectError:
            await status_msg.edit_text(
                "Не удалось подключиться к сервису индексации. "
                "Проверьте, что Ingestion Service запущен."
            )
            context.user_data.pop("pending_upload", None)
            return

        context.user_data["subjects"] = subjects
        keyboard = self._build_subject_keyboard(subjects)
        await status_msg.edit_text(
            f"Выберите предмет для {doc_label}:",
            reply_markup=keyboard,
        )

    async def _handle_subject_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle subject button click."""
        query = update.callback_query
        await query.answer()
        if not query.data:
            return

        user_id = update.effective_user.id
        if not self._is_user_allowed(user_id):
            await query.edit_message_text("У вас нет доступа к загрузке документов.")
            return

        pending = context.user_data.get("pending_upload")
        if not pending or not isinstance(pending, list):
            await query.edit_message_text("Документ не найден. Отправьте документ заново.")
            return

        if query.data == CALLBACK_NEW_SUBJECT:
            context.user_data["awaiting_subject"] = True
            await query.edit_message_text("Введите название нового предмета:")
            return

        if query.data.startswith(CALLBACK_SUBJECT_PREFIX):
            idx_str = query.data[len(CALLBACK_SUBJECT_PREFIX):]
            try:
                idx = int(idx_str)
            except ValueError:
                await query.edit_message_text("Ошибка выбора предмета.")
                return

            subjects = context.user_data.get("subjects", [])
            if idx < 0 or idx >= len(subjects):
                await query.edit_message_text("Неверный предмет.")
                return

            subject = subjects[idx]
            await self._do_upload(context, query, pending, subject)

    async def _handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle text - used for 'Add new subject' flow."""
        if not update.message or not update.message.text:
            return

        user_id = update.effective_user.id
        if not self._is_user_allowed(user_id):
            return

        if not context.user_data.get("awaiting_subject"):
            return

        pending = context.user_data.get("pending_upload")
        if not pending or not isinstance(pending, list):
            context.user_data["awaiting_subject"] = False
            await update.message.reply_text("Документ не найден. Отправьте документ заново.")
            return

        subject = update.message.text.strip()
        if not subject:
            await update.message.reply_text("Название предмета не может быть пустым. Введите название:")
            return

        context.user_data["awaiting_subject"] = False
        status_msg = await update.message.reply_text("Загружаю документ(ы)...")
        await self._do_upload(context, None, pending, subject, status_msg=status_msg)

    async def _do_upload(
        self,
        context: ContextTypes.DEFAULT_TYPE,
        query,
        pending: list[dict],
        subject: str,
        status_msg=None,
    ) -> None:
        """Download file(s) and POST to Ingestion Service with subject. pending is list of {file_id, file_name}."""
        if query:
            status_msg = await query.edit_message_text("Загружаю документ(ы)...")

        upload_url = f"{self.ingestion_service_url}/api/upload"
        results: list[tuple[str, int]] = []  # (filename, chunks_indexed)
        errors: list[str] = []

        try:
            for i, item in enumerate(pending):
                file_id = item["file_id"]
                file_name = item["file_name"]
                suffix = Path(file_name).suffix.lower()
                if suffix == ".doc":
                    suffix = ".docx"

                if len(pending) > 1:
                    await status_msg.edit_text(
                        f"Загружаю документ(ы)... ({i + 1}/{len(pending)})"
                    )

                try:
                    bot_file = await context.bot.get_file(file_id)
                    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                        await bot_file.download_to_drive(tmp.name)
                        tmp_path = Path(tmp.name)

                    try:
                        with open(tmp_path, "rb") as f:
                            files = {"file": (file_name, f, "application/octet-stream")}
                            data = {"subject": subject}
                            async with httpx.AsyncClient(timeout=180.0) as client:
                                response = await client.post(upload_url, files=files, data=data)

                        if response.status_code == 200:
                            resp_data = response.json()
                            results.append((
                                resp_data.get("filename", file_name),
                                resp_data.get("chunks_indexed", 0),
                            ))
                        else:
                            error_detail = response.json().get("detail", response.text)
                            errors.append(f"{file_name}: {error_detail}")
                    finally:
                        tmp_path.unlink(missing_ok=True)
                except Exception as e:
                    logger.error(f"Error uploading {file_name}: {e}", exc_info=True)
                    errors.append(f"{file_name}: {str(e)}")

            if errors:
                msg = "Произошли ошибки:\n\n" + "\n".join(errors)
                if results:
                    total = sum(c for _, c in results)
                    msg = f"Успешно: {len(results)} файл(ов), {total} чанков.\n\n{msg}"
                await status_msg.edit_text(msg)
            elif results:
                total_chunks = sum(c for _, c in results)
                if len(results) == 1:
                    await status_msg.edit_text(
                        f"Документ успешно проиндексирован.\n\n"
                        f"Файл: {results[0][0]}\n"
                        f"Предмет: {subject}\n"
                        f"Чанков: {total_chunks}"
                    )
                else:
                    lines = [f"• {fn} ({c} чанков)" for fn, c in results]
                    await status_msg.edit_text(
                        f"Пачка успешно проиндексирована.\n\n"
                        f"Предмет: {subject}\n"
                        f"Файлов: {len(results)}, всего чанков: {total_chunks}\n\n"
                        + "\n".join(lines)
                    )
            else:
                await status_msg.edit_text("Не удалось загрузить ни один документ.")

        except httpx.ConnectError:
            logger.error("Failed to connect to Ingestion Service")
            await status_msg.edit_text(
                "Не удалось подключиться к сервису индексации. "
                "Проверьте, что Ingestion Service запущен."
            )
        except Exception as e:
            logger.error(f"Error processing upload: {e}", exc_info=True)
            await status_msg.edit_text(f"Произошла ошибка: {str(e)}")
        finally:
            context.user_data.pop("pending_upload", None)
            context.user_data.pop("subjects", None)
