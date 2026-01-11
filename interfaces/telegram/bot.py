"""
Telegram Bot Implementation

A simple Telegram bot that can receive messages and eventually route them
through the orchestrator. Currently set up for easy experimentation.
"""

import logging
from typing import Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

from orchestrator import IntentClassifier
from shared.intents.schemas import IntentClassification

logger = logging.getLogger(__name__)


class TelegramBot:
    """Telegram bot that handles user messages and routes them through the system."""

    def __init__(self, token: str, intent_classifier: Optional[IntentClassifier] = None):
        """
        Initialize the Telegram bot.

        Args:
            token: Telegram bot token from BotFather
            intent_classifier: Optional IntentClassifier instance. If None, will create one.
        """
        self.token = token
        self.application = Application.builder().token(token).build()
        self.intent_classifier = intent_classifier or IntentClassifier()
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

    async def _handle_message(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        """
        Handle incoming text messages.

        Routes messages through the intent classifier and responds with detected intents.
        """
        user_message = update.message.text
        user_id = update.effective_user.id
        username = update.effective_user.username or "User"

        logger.info(f"Received message from {username} ({user_id}): {user_message}")

        try:
            # Classify intents using the orchestrator
            classification = await self.intent_classifier.classify(user_message)
            response = self._format_intent_response(user_message, classification)
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

    async def start(self):
        """Start the bot."""
        logger.info("Starting Telegram bot...")
        await self.application.initialize()
        await self.application.start()
        await self.application.updater.start_polling()
        logger.info("Telegram bot is running!")

    async def stop(self):
        """Stop the bot."""
        logger.info("Stopping Telegram bot...")
        await self.application.updater.stop()
        await self.application.stop()
        await self.application.shutdown()
        logger.info("Telegram bot stopped.")

    def run(self):
        """Run the bot (blocking)."""
        self.application.run_polling(allowed_updates=Update.ALL_TYPES)
