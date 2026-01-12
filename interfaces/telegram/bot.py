"""
Telegram Bot Implementation

A simple Telegram bot that can receive messages and eventually route them
through the orchestrator. Currently set up for easy experimentation.
"""

import json
import logging
from typing import Optional

import asyncpg
from telegram import Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

from agents.scheduler import ReminderDatabaseService, SchedulerAgent
from agents.scheduler.telegram import ReminderService
from config.database import create_connection_pool, ensure_reminders_table
from orchestrator import IntentClassifier, IntentRouter
from orchestrator.router import RouterResponse
from shared.intents.schemas import IntentClassification
from shared.models.reminder import ReminderCreate

logger = logging.getLogger(__name__)


class TelegramBot:
    """Telegram bot that handles user messages and routes them through the system."""

    def __init__(
        self,
        token: str,
        intent_classifier: Optional[IntentClassifier] = None,
        database_pool: Optional[asyncpg.Pool] = None,
    ):
        """
        Initialize the Telegram bot.

        Args:
            token: Telegram bot token from BotFather
            intent_classifier: Optional IntentClassifier instance. If None, will create one.
            database_pool: Optional database connection pool. If None, will create one.
        """
        self.token = token
        self.application = Application.builder().token(token).build()
        self.intent_classifier = intent_classifier or IntentClassifier()

        # Database and services
        self.database_pool = database_pool
        self.database_service: Optional[ReminderDatabaseService] = None
        self.scheduler_agent: Optional[SchedulerAgent] = None
        self.intent_router: Optional[IntentRouter] = None
        self.reminder_service: Optional[ReminderService] = None

        # State management for reminder editing
        self.editing_reminders: dict[int, str] = {}  # user_id -> reminder_id

        self._setup_handlers()

    def _setup_handlers(self):
        """Set up command and message handlers."""
        # Command handlers
        self.application.add_handler(CommandHandler("start", self._handle_start))
        self.application.add_handler(CommandHandler("help", self._handle_help))
        self.application.add_handler(CommandHandler("menu", self._handle_menu))

        # Callback query handler for button clicks
        self.application.add_handler(CallbackQueryHandler(self._handle_button_click))

        # Message handler for all text messages
        self.application.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_message)
        )

    def _get_main_menu_keyboard(self) -> InlineKeyboardMarkup:
        """Create main menu keyboard with buttons."""
        keyboard = [
            [
                InlineKeyboardButton("📚 Учебные материалы", callback_data="learning"),
                InlineKeyboardButton("👨‍🏫 Академическая информация", callback_data="academic"),
            ],
            [
                InlineKeyboardButton("📅 Расписание и дедлайны", callback_data="schedule"),
            ],
            [
                InlineKeyboardButton("❓ Помощь", callback_data="help"),
            ],
        ]
        return InlineKeyboardMarkup(keyboard)

    async def _handle_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command."""
        welcome_message = (
            "👋 Добро пожаловать в BSTU-AI!\n\n"
            "Я здесь, чтобы помочь вам с:\n"
            "• Учебными материалами и объяснениями\n"
            "• Академической информацией (преподаватели, курсы)\n"
            "• Расписанием и дедлайнами\n\n"
            "Выберите раздел ниже или просто напишите вопрос!"
        )
        keyboard = self._get_main_menu_keyboard()
        await update.message.reply_text(welcome_message, reply_markup=keyboard, parse_mode=ParseMode.HTML)

    async def _handle_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /menu command - show main menu."""
        menu_message = "📋 Главное меню\n\nВыберите раздел:"
        keyboard = self._get_main_menu_keyboard()
        await update.message.reply_text(menu_message, reply_markup=keyboard, parse_mode=ParseMode.HTML)

    async def _handle_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command."""
        help_message = (
            "📚 Справка BSTU-AI\n\n"
            "Команды:\n"
            "/start - Запустить бота\n"
            "/menu - Показать главное меню\n"
            "/help - Показать это сообщение справки\n\n"
            "Вы можете спросить меня о:\n"
            "• Учебных темах и объяснениях\n"
            "• Информации о преподавателях\n"
            "• Требованиях к курсам\n"
            "• Расписании и дедлайнах\n\n"
            "Используйте кнопки меню или просто напишите вопрос!"
        )
        keyboard = self._get_main_menu_keyboard()
        await update.message.reply_text(help_message, reply_markup=keyboard, parse_mode=ParseMode.HTML)

    async def _handle_button_click(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        """Handle button clicks from inline keyboard."""
        query = update.callback_query
        await query.answer()

        callback_data = query.data
        user_id = query.from_user.id
        username = query.from_user.username or "User"

        logger.info(f"Button clicked by {username} ({user_id}): {callback_data}")

        if callback_data == "learning":
            response = (
                "📚 Учебные материалы\n\n"
                "Я могу помочь вам с:\n"
                "• Объяснением учебных тем\n"
                "• Кратким изложением материала\n"
                "• Созданием тестов для проверки знаний\n"
                "• Планом повторения материала\n\n"
                "Напишите тему или вопрос, и я помогу!"
            )
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Главное меню", callback_data="main_menu")]
            ])
            await query.edit_message_text(response, reply_markup=keyboard, parse_mode=ParseMode.HTML)

        elif callback_data == "academic":
            response = (
                "👨‍🏫 Академическая информация\n\n"
                "Я могу предоставить информацию о:\n"
                "• Преподавателях и их курсах\n"
                "• Требованиях к курсам\n"
                "• Критериях оценки\n"
                "• Условиях допуска к экзаменам\n\n"
                "Напишите имя преподавателя или название курса!"
            )
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Главное меню", callback_data="main_menu")]
            ])
            await query.edit_message_text(response, reply_markup=keyboard, parse_mode=ParseMode.HTML)

        elif callback_data == "schedule":
            response = (
                "📅 Расписание и дедлайны\n\n"
                "Я могу помочь с:\n"
                "• Поиском расписания занятий\n"
                "• Информацией о дедлайнах курсовых работ\n"
                "• Датами экзаменов\n"
                "• Созданием напоминаний\n\n"
                "Спросите о конкретном событии или дедлайне!"
            )
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Главное меню", callback_data="main_menu")]
            ])
            await query.edit_message_text(response, reply_markup=keyboard, parse_mode=ParseMode.HTML)

        elif callback_data == "help":
            response = (
                "❓ Помощь\n\n"
                "Команды:\n"
                "/start - Запустить бота\n"
                "/menu - Показать главное меню\n"
                "/help - Показать справку\n\n"
                "Вы можете использовать кнопки меню или просто написать вопрос естественным образом!"
            )
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Главное меню", callback_data="main_menu")]
            ])
            await query.edit_message_text(response, reply_markup=keyboard, parse_mode=ParseMode.HTML)

        elif callback_data == "main_menu":
            response = "📋 Главное меню\n\nВыберите раздел:"
            keyboard = self._get_main_menu_keyboard()
            await query.edit_message_text(response, reply_markup=keyboard, parse_mode=ParseMode.HTML)

        elif callback_data == "confirm_reminder":
            # Handle reminder confirmation
            pending_data = context.user_data.get("pending_reminder")
            if not pending_data or pending_data.get("type") != "reminder":
                await query.answer("Ошибка: данные напоминания не найдены", show_alert=True)
                return

            try:
                # Parse reminder from JSON
                reminder_json = pending_data.get("reminder")
                reminder_dict = json.loads(reminder_json)
                
                # Parse datetime string to datetime object
                if "reminder_date" in reminder_dict and isinstance(reminder_dict["reminder_date"], str):
                    from datetime import datetime
                    reminder_dict["reminder_date"] = datetime.fromisoformat(
                        reminder_dict["reminder_date"].replace("Z", "+00:00")
                    )
                
                reminder = ReminderCreate(**reminder_dict)

                # Save to database
                if self.scheduler_agent:
                    reminder_id = await self.scheduler_agent.create_reminder(reminder)
                    
                    # Clear pending reminder
                    context.user_data.pop("pending_reminder", None)
                    
                    # Format success message
                    date_str = reminder.reminder_date.strftime("%Y-%m-%d %H:%M")
                    recurring_str = ""
                    if reminder.recurring and reminder.recurring.value != "NOT SPECIFIED":
                        recurring_str = f" (recurring: {reminder.recurring.value})"
                    
                    success_message = (
                        f"✅ Напоминание создано!\n\n"
                        f"📝 Сообщение: {reminder.message}\n"
                        f"📅 Дата: {date_str} ({reminder.timezone}){recurring_str}"
                    )
                    
                    await query.edit_message_text(success_message, parse_mode=ParseMode.HTML)
                    await query.answer("Напоминание создано!")
                else:
                    await query.answer("Ошибка: агент не инициализирован", show_alert=True)
            except Exception as e:
                logger.error(f"Error confirming reminder: {e}", exc_info=True)
                await query.answer("Ошибка при создании напоминания", show_alert=True)
                await query.edit_message_text(
                    "❌ Произошла ошибка при создании напоминания. Попробуйте еще раз.",
                    parse_mode=ParseMode.HTML
                )

        elif callback_data == "cancel_reminder":
            # Handle reminder cancellation
            context.user_data.pop("pending_reminder", None)
            await query.edit_message_text(
                "❌ Создание напоминания отменено.",
                parse_mode=ParseMode.HTML
            )
            await query.answer("Напоминание отменено")

        elif callback_data.startswith("reminder_"):
            # Handle reminder selection: reminder_<reminder_id>_<action>
            parts = callback_data.split("_")
            if len(parts) >= 3:
                reminder_id = parts[1]
                action = parts[2]
                await self._handle_reminder_action(query, user_id, reminder_id, action)

        elif callback_data.startswith("edit_reminder_"):
            # Handle edit reminder button: edit_reminder_<reminder_id>
            reminder_id = callback_data.replace("edit_reminder_", "")
            self.editing_reminders[user_id] = reminder_id
            await query.edit_message_text(
                "✏️ Опишите, что вы хотите изменить в напоминании.\n\n"
                "Например: \"Измени дату на завтра в 15:00\" или \"Измени сообщение на 'Сдать курсовую'\"",
                parse_mode=ParseMode.HTML
            )

        elif callback_data.startswith("delete_reminder_"):
            # Handle delete reminder button: delete_reminder_<reminder_id>
            reminder_id = callback_data.replace("delete_reminder_", "")
            await self._handle_reminder_delete(query, user_id, reminder_id)

        elif callback_data.startswith("confirm_delete_"):
            # Handle delete confirmation: confirm_delete_<reminder_id>
            reminder_id = callback_data.replace("confirm_delete_", "")
            await self._confirm_delete_reminder(query, user_id, reminder_id)

        elif callback_data == "cancel_reminder_menu" or callback_data == "cancel_delete":
            # Handle menu cancellation
            await query.edit_message_text(
                "❌ Операция отменена.",
                parse_mode=ParseMode.HTML,
            )
            await query.answer("Операция отменена")

    async def _handle_message(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        """
        Handle incoming text messages.

        Routes messages through the intent classifier and then to appropriate agents.
        """
        user_message = update.message.text
        user_id = update.effective_user.id
        username = update.effective_user.username or "User"

        logger.info(f"Received message from {username} ({user_id}): {user_message}")

        try:
            # Classify intents using the orchestrator
            classification = await self.intent_classifier.classify(user_message)

            # Check if user is in editing state
            if user_id in self.editing_reminders:
                reminder_id = self.editing_reminders[user_id]
                await self._handle_reminder_edit_text(
                    update, context, reminder_id, user_message
                )
                return

            # Route to appropriate agent via router
            if self.intent_router:
                router_response = await self.intent_router.route(
                    classification, user_message, user_id
                )
                if router_response:
                    if router_response.show_reminder_menu:
                        # Show reminder selection menu
                        await self._show_reminder_menu(
                            update, router_response.message, router_response.confirmation_data.get("action")
                        )
                    elif router_response.needs_confirmation:
                        # Store pending reminder in user_data for confirmation
                        context.user_data["pending_reminder"] = router_response.confirmation_data
                        
                        # Create confirmation keyboard
                        keyboard = InlineKeyboardMarkup([
                            [
                                InlineKeyboardButton("✅ Да", callback_data="confirm_reminder"),
                                InlineKeyboardButton("❌ Нет", callback_data="cancel_reminder"),
                            ]
                        ])
                        
                        await update.message.reply_text(
                            router_response.message,
                            reply_markup=keyboard,
                            parse_mode=ParseMode.HTML
                        )
                    else:
                        await update.message.reply_text(
                            router_response.message,
                            parse_mode=ParseMode.HTML
                        )
                    return

            # Fallback to showing intent classification if no agent handled it
            response = self._format_intent_response(user_message, classification)
            await update.message.reply_text(response, parse_mode=ParseMode.HTML)

        except Exception as e:
            logger.error(f"Error processing message: {e}", exc_info=True)
            response = (
                "❌ Произошла ошибка при обработке вашего сообщения. "
                "Попробуйте еще раз."
            )
            await update.message.reply_text(response, parse_mode=ParseMode.HTML)

    def _format_intent_response(
        self, message: str, classification: IntentClassification
    ) -> str:
        """
        Format the response showing detected intents.

        Args:
            message: Original user message
            classification: IntentClassification object

        Returns:
            Formatted response text
        """
        intents = classification.intents
        confidence = classification.confidence

        # Handle empty intents
        if not intents:
            response = (
                "🔍 **Результат классификации:**\n\n"
                "❌ Интенты не обнаружены.\n\n"
                "Возможно, ваше сообщение является приветствием или "
                "не содержит четкого запроса. Попробуйте спросить более конкретно!"
            )
            return response

        # Format detected intents
        intent_icons = {
            "learning.explain": "📖",
            "learning.summarize": "📝",
            "learning.quiz.generate": "📋",
            "learning.quiz.grade": "✅",
            "learning.plan.revision": "📅",
            "academic.professor.profile": "👨‍🏫",
            "academic.course.requirements": "📚",
            "schedule.lookup": "🔍",
            "schedule.deadline.lookup": "⏰",
            "schedule.reminder.create": "🔔",
        }

        response = (
            "🔍 <b>Результат классификации:</b>\n\n"
            "<b>Обнаруженные интенты:</b>\n"
        )

        for intent in intents:
            icon = intent_icons.get(intent, "•")
            response += f"{icon} {intent}\n"

        response += f"\n📊 <b>Уверенность:</b> {confidence:.1%}"

        return response

    async def _initialize_services(self) -> None:
        """Initialize database, agents, and services."""
        if self.database_pool is None:
            logger.info("Creating database connection pool...")
            self.database_pool = await create_connection_pool()
            await ensure_reminders_table(self.database_pool)

        # Initialize database service
        self.database_service = ReminderDatabaseService(self.database_pool)

        # Initialize scheduler agent
        self.scheduler_agent = SchedulerAgent(self.database_service)

        # Initialize intent router
        self.intent_router = IntentRouter(scheduler_agent=self.scheduler_agent)

        # Initialize reminder service
        bot_instance = Bot(token=self.token)
        self.reminder_service = ReminderService(
            database_service=self.database_service,
            telegram_bot=bot_instance,
            poll_interval=60,  # Poll every 60 seconds
        )

        logger.info("Initialized all services")

    async def _show_reminder_menu(
        self, update: Update, message: str, action: str
    ):
        """Show reminder selection menu with buttons."""
        user_id = update.effective_user.id
        reminders = await self.database_service.get_user_reminders(user_id, limit=5)

        if not reminders:
            await update.message.reply_text(
                "📋 У вас нет напоминаний.", parse_mode=ParseMode.HTML
            )
            return

        keyboard = []
        for reminder in reminders:
            date_str = reminder.reminder_date.strftime("%Y-%m-%d %H:%M")
            button_text = f"{reminder.message[:30]}... ({date_str})"
            if len(reminder.message) <= 30:
                button_text = f"{reminder.message} ({date_str})"
            keyboard.append([
                InlineKeyboardButton(
                    button_text,
                    callback_data=f"reminder_{reminder.id}_{action}",
                )
            ])

        keyboard.append([
            InlineKeyboardButton("❌ Отмена", callback_data="cancel_reminder_menu")
        ])

        await update.message.reply_text(
            message,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML,
        )

    async def _handle_reminder_action(
        self, query, user_id: int, reminder_id: str, action: str
    ):
        """Handle reminder selection - show edit/delete buttons."""
        from uuid import UUID

        try:
            reminder_uuid = UUID(reminder_id)
            reminder = await self.database_service.get_reminder_by_id(
                reminder_uuid, user_id
            )

            if not reminder:
                await query.answer("Напоминание не найдено", show_alert=True)
                return

            date_str = reminder.reminder_date.strftime("%Y-%m-%d %H:%M")
            message = (
                f"📝 Напоминание:\n\n"
                f"💬 {reminder.message}\n"
                f"📅 {date_str}\n"
                f"🆔 ID: {reminder.id}\n\n"
                f"Выберите действие:"
            )

            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "✏️ Изменить", callback_data=f"edit_reminder_{reminder_id}"
                    ),
                    InlineKeyboardButton(
                        "🗑️ Удалить", callback_data=f"delete_reminder_{reminder_id}"
                    ),
                ],
                [InlineKeyboardButton("❌ Отмена", callback_data="cancel_reminder_menu")],
            ])

            await query.edit_message_text(message, reply_markup=keyboard)

        except Exception as e:
            logger.error(f"Error handling reminder action: {e}", exc_info=True)
            await query.answer("Ошибка при обработке запроса", show_alert=True)

    async def _handle_reminder_edit_text(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE, reminder_id: str, user_message: str
    ):
        """Handle text input for editing reminder."""
        from uuid import UUID

        user_id = update.effective_user.id

        try:
            reminder_uuid = UUID(reminder_id)
            # Extract edit information using agent
            reminder = await self.scheduler_agent.extract_reminder_info(
                user_message, user_id
            )

            # Update reminder in database
            updated = await self.database_service.update_reminder(
                reminder_id=reminder_uuid,
                user_id=user_id,
                message=reminder.message if reminder.message else None,
                reminder_date=reminder.reminder_date if reminder.reminder_date else None,
                timezone=reminder.timezone if reminder.timezone != "GMT+3" else None,
                recurring_pattern=reminder.recurring.value if reminder.recurring else None,
            )

            # Clear editing state
            self.editing_reminders.pop(user_id, None)

            if updated:
                date_str = reminder.reminder_date.strftime("%Y-%m-%d %H:%M")
                await update.message.reply_text(
                    f"✅ Напоминание успешно обновлено!\n\n"
                    f"📝 Сообщение: {reminder.message}\n"
                    f"📅 Дата: {date_str}",
                    parse_mode=ParseMode.HTML,
                )
            else:
                await update.message.reply_text(
                    "❌ Не удалось обновить напоминание.",
                    parse_mode=ParseMode.HTML,
                )

        except Exception as e:
            logger.error(f"Error editing reminder: {e}", exc_info=True)
            self.editing_reminders.pop(user_id, None)
            await update.message.reply_text(
                "❌ Произошла ошибка при редактировании напоминания. Попробуйте еще раз.",
                parse_mode=ParseMode.HTML,
            )

    async def _handle_reminder_delete(self, query, user_id: int, reminder_id: str):
        """Show delete confirmation."""
        from uuid import UUID

        try:
            reminder_uuid = UUID(reminder_id)
            reminder = await self.database_service.get_reminder_by_id(
                reminder_uuid, user_id
            )

            if not reminder:
                await query.answer("Напоминание не найдено", show_alert=True)
                return

            message = (
                f"⚠️ Вы уверены, что хотите удалить это напоминание?\n\n"
                f"💬 {reminder.message}\n"
                f"📅 {reminder.reminder_date.strftime('%Y-%m-%d %H:%M')}\n\n"
                f"Это действие нельзя отменить."
            )

            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "✅ Да, удалить", callback_data=f"confirm_delete_{reminder_id}"
                    ),
                    InlineKeyboardButton("❌ Отмена", callback_data="cancel_delete"),
                ]
            ])

            await query.edit_message_text(message, reply_markup=keyboard)

        except Exception as e:
            logger.error(f"Error handling delete: {e}", exc_info=True)
            await query.answer("Ошибка при обработке запроса", show_alert=True)

    async def _confirm_delete_reminder(self, query, user_id: int, reminder_id: str):
        """Actually delete the reminder."""
        from uuid import UUID

        try:
            reminder_uuid = UUID(reminder_id)
            reminder = await self.database_service.get_reminder_by_id(
                reminder_uuid, user_id
            )

            if not reminder:
                await query.answer("Напоминание не найдено", show_alert=True)
                return

            deleted = await self.database_service.delete_reminder(reminder_uuid, user_id)

            if deleted:
                await query.edit_message_text(
                    f"✅ Напоминание успешно удалено!\n\n"
                    f"Удалено: {reminder.message}",
                    parse_mode=ParseMode.HTML,
                )
            else:
                await query.edit_message_text(
                    "❌ Не удалось удалить напоминание.",
                    parse_mode=ParseMode.HTML,
                )

        except Exception as e:
            logger.error(f"Error deleting reminder: {e}", exc_info=True)
            await query.edit_message_text(
                "❌ Произошла ошибка при удалении напоминания.",
                parse_mode=ParseMode.HTML,
            )

    async def start(self):
        """Start the bot and all services."""
        logger.info("Starting Telegram bot...")

        # Initialize services
        await self._initialize_services()

        # Start reminder service
        if self.reminder_service:
            await self.reminder_service.start()

        # Start bot
        await self.application.initialize()
        await self.application.start()
        await self.application.updater.start_polling()
        logger.info("Telegram bot is running!")

    async def stop(self):
        """Stop the bot and all services."""
        logger.info("Stopping Telegram bot...")

        # Stop reminder service
        if self.reminder_service:
            await self.reminder_service.stop()

        # Stop bot
        await self.application.updater.stop()
        await self.application.stop()
        await self.application.shutdown()

        # Close database pool
        if self.database_pool:
            await self.database_pool.close()

        logger.info("Telegram bot stopped.")

    def run(self):
        """Run the bot (blocking)."""
        import asyncio

        async def run_async():
            await self.start()
            try:
                # Keep running until interrupted
                await asyncio.Event().wait()
            except KeyboardInterrupt:
                logger.info("Received keyboard interrupt")
            finally:
                await self.stop()

        try:
            asyncio.run(run_async())
        except KeyboardInterrupt:
            logger.info("Bot stopped by user")
