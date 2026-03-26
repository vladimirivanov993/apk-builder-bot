"""
Глобальный обработчик ошибок Telegram бота.
"""

import logging
from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик ошибок."""
    logger.error(f"Ошибка при обновлении {update}: {context.error}", exc_info=context.error)
    # Отправляем сообщение пользователю, если возможно
    if update and update.effective_message:
        await update.effective_message.reply_text(
            "Произошла непредвиденная ошибка. Администратор уже уведомлён."
        )