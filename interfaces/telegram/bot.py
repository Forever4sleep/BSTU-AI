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

            # Route to appropriate agent via router
            if self.intent_router:
                router_response = await self.intent_router.route(
                    classification, user_message, user_id
                )
                if router_response:
                    if router_response.needs_confirmation:
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
