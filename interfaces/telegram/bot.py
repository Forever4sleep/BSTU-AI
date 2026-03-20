"""
Telegram Bot Implementation

Receives messages and routes them through the orchestrator.
Classifies intents and displays results (agents to be implemented).
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

from orchestrator import IntentClassifier, IntentRouter
from shared.intents.schemas import IntentClassification

logger = logging.getLogger(__name__)


class TelegramBot:
    """Telegram bot that handles user messages and routes them through the system."""

    def __init__(
        self,
        token: str,
        intent_classifier: Optional[IntentClassifier] = None,
    ):
        """
        Initialize the Telegram bot.

        Args:
            token: Telegram bot token from BotFather
            intent_classifier: Optional IntentClassifier instance. If None, will create one.
        """
        self.token = token
        self.application = Application.builder().token(token).build()
        self.intent_classifier = intent_classifier or IntentClassifier()
        self.intent_router = IntentRouter()

        self._setup_handlers()

    def _setup_handlers(self):
        """Set up command and message handlers."""
        self.application.add_handler(CommandHandler("start", self._handle_start))
        self.application.add_handler(CommandHandler("help", self._handle_help))
        self.application.add_handler(CommandHandler("menu", self._handle_menu))
        self.application.add_handler(CallbackQueryHandler(self._handle_button_click))
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
            [InlineKeyboardButton("❓ Помощь", callback_data="help")],
        ]
        return InlineKeyboardMarkup(keyboard)

    async def _handle_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command."""
        welcome_message = (
            "👋 Добро пожаловать в BSTU-AI!\n\n"
            "Я здесь, чтобы помочь вам с:\n"
            "• Учебными материалами и объяснениями\n"
            "• Академической информацией (преподаватели, курсы)\n\n"
            "Выберите раздел для получения подробной информации:"
        )
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🤖 AI-репетитор", callback_data="faq_learning")],
            [InlineKeyboardButton("📋 Главное меню", callback_data="main_menu")]
        ])
        await update.message.reply_text(welcome_message, reply_markup=keyboard, parse_mode=ParseMode.HTML)

    async def _handle_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /menu command - show FAQ menu."""
        menu_message = (
            "❓ Помощь\n\n"
            "Команды:\n"
            "/start - Запустить бота\n"
            "/menu - Показать главное меню\n"
            "/help - Показать справку\n\n"
            "Выберите раздел для получения подробной информации:"
        )
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🤖 AI-репетитор", callback_data="faq_learning")],
            [InlineKeyboardButton("📋 Главное меню", callback_data="main_menu")]
        ])
        await update.message.reply_text(menu_message, reply_markup=keyboard, parse_mode=ParseMode.HTML)

    async def _handle_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command."""
        help_message = (
            "❓ Помощь\n\n"
            "Команды:\n"
            "/start - Запустить бота\n"
            "/menu - Показать главное меню\n"
            "/help - Показать справку\n\n"
            "Выберите раздел для получения подробной информации:"
        )
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🤖 AI-репетитор", callback_data="faq_learning")],
            [InlineKeyboardButton("🔙 Главное меню", callback_data="main_menu")]
        ])
        await update.message.reply_text(help_message, reply_markup=keyboard, parse_mode=ParseMode.HTML)

    async def _handle_button_click(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        """Handle button clicks from inline keyboard."""
        query = update.callback_query
        await query.answer()

        callback_data = query.data
        logger.info(f"Button clicked: {callback_data}")

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

        elif callback_data == "help":
            response = (
                "❓ Помощь\n\n"
                "Команды:\n"
                "/start - Запустить бота\n"
                "/menu - Показать главное меню\n"
                "/help - Показать справку\n\n"
                "Выберите раздел для получения подробной информации:"
            )
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🤖 AI-репетитор", callback_data="faq_learning")],
                [InlineKeyboardButton("🔙 Главное меню", callback_data="main_menu")]
            ])
            await query.edit_message_text(response, reply_markup=keyboard, parse_mode=ParseMode.HTML)

        elif callback_data == "faq_learning":
            response = (
                "🤖 AI-репетитор\n\n"
                "Я могу помочь вам изучать предметы быстрее, используя материалы БГТУ.\n\n"
                "<b>Объяснение тем:</b>\n"
                "Спросите меня о любой учебной теме. Например: \"Объясни квантовую физику\" или \"Что такое интегралы?\"\n\n"
                "<b>Краткое изложение:</b>\n"
                "Попросите сделать краткое изложение материала. Например: \"Сделай краткое изложение темы про электромагнетизм\"\n\n"
                "<b>Тесты:</b>\n"
                "Я могу создать тест по любой теме. Скажите: \"Создай тест по математике\" или \"Проверь мои знания по физике\"\n\n"
                "<b>План повторения:</b>\n"
                "Я могу составить план повторения на основе ваших слабых мест."
            )
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Назад", callback_data="help")]
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

        Routes messages through the intent classifier and then to appropriate agents.
        """
        user_message = update.message.text
        user_id = update.effective_user.id
        username = update.effective_user.username or "User"

        logger.info(f"Received message from {username} ({user_id}): {user_message}")

        try:
            classification = await self.intent_classifier.classify(user_message)

            router_response = await self.intent_router.route(
                classification, user_message, user_id
            )
            if router_response:
                await update.message.reply_text(
                    router_response.message,
                    parse_mode=ParseMode.HTML
                )
                return

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
        """Format the response showing detected intents."""
        intents = classification.intents
        confidence = classification.confidence

        if not intents:
            return (
                "🔍 <b>Результат классификации:</b>\n\n"
                "❌ Интенты не обнаружены.\n\n"
                "Возможно, ваше сообщение является приветствием или "
                "не содержит четкого запроса. Попробуйте спросить более конкретно!"
            )

        intent_icons = {
            "learning.explain": "📖",
            "learning.summarize": "📝",
            "learning.quiz.generate": "📋",
            "learning.quiz.grade": "✅",
            "learning.plan.revision": "📅",
            "academic.professor.profile": "👨‍🏫",
            "academic.course.requirements": "📚",
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
        import asyncio

        async def run_async():
            await self.start()
            try:
                await asyncio.Event().wait()
            except KeyboardInterrupt:
                logger.info("Received keyboard interrupt")
            finally:
                await self.stop()

        try:
            asyncio.run(run_async())
        except KeyboardInterrupt:
            logger.info("Bot stopped by user")
