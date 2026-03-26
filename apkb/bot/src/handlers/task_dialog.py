"""
Диалог для создания задачи (не относится к сборке APK, но оставлено для совместимости).
"""

from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

# Состояния диалога (пример)
TASK_NAME, TASK_DESC = range(2)

async def start_task_dialog(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Функция создания задачи временно отключена.")
    return ConversationHandler.END

async def task_info_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Информация о задаче недоступна.")

async def cancel_task_dialog(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Диалог отменён.")
    return ConversationHandler.END

async def handle_dialog_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Заглушка
    return False

def get_task_handlers():
    # Возвращает пустой список, чтобы не ломать импорты
    return []