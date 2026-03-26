"""
Обработчики команд для Telegram бота.
"""

import time
from telegram import Update, BotCommand
from telegram.ext import ContextTypes, CommandHandler, MessageHandler, filters

from src.config.settings import settings
from src.handlers.task_dialog import (
    start_task_dialog, 
    handle_dialog_step, 
    cancel_task_dialog,
    task_info_command,
    get_task_handlers
)
from src.handlers.apk_builder import (
    start_build,
    get_active_builds_count,
    get_build_queue_size,
    get_active_builds_details,
    get_free_memory
)
from src.db.database import get_maintenance_mode, set_maintenance_mode

# ============================================================================
# ОСНОВНЫЕ КОМАНДЫ БОТА (не относящиеся к сборке APK)
# ============================================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    welcome_text = f"""
👋 Привет, {user.first_name}!

🤖 Я бот для управления задачами и сборки Android APK из веб-сайтов.

📊 **Основные команды:**
• /newtask - создать задачу (проект, заявитель, описание, приоритет)
• /build - собрать Android APK из ZIP-архива
• /task [ID] - информация о задаче
• /help - полная справка

💡 **Для сборки APK:**
Отправьте /build, затем следуйте инструкциям. Бот примет ZIP-архив с сайтом и вернёт готовое приложение.
"""
    await update.message.reply_text(welcome_text, parse_mode='Markdown')

async def help_commands(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = """
📚 **ДОСТУПНЫЕ КОМАНДЫ:**

**Управление задачами:**
  /newtask - Создать задачу
  /task [ID] - Информация о задаче
  /cancel - Отменить активный диалог

**Сборка APK:**
  /build - Начать сборку Android приложения из ZIP-архива

**Информационные:**
  /start - Начать работу с ботом
  /id - Показать ID чата и пользователя
  /help - Показать эту справку
  /ping - Проверить работу бота

**Административные:**
  /maintenance [on|off] - Включить/выключить режим обслуживания
  /admin_status - Показать состояние сервера (память, очередь, активные сборки)
"""
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def id_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    response = f"""
📋 **ИНФОРМАЦИЯ О ID**

👤 **Пользователь:** `{user.id}`
💬 **Чат:** `{chat.id}`
"""
    await update.message.reply_text(response, parse_mode='Markdown')

async def ping_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    start_time = time.time()
    message = await update.message.reply_text("🏓 Pong! Измеряем задержку...")
    end_time = time.time()
    latency = (end_time - start_time) * 1000
    await message.edit_text(f"🏓 PONG!\nЗадержка: `{latency:.0f} мс`", parse_mode='Markdown')

async def newtask_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('task_in_progress'):
        await update.message.reply_text("⚠️ У вас уже есть активный диалог.")
        return
    await start_task_dialog(update, context)

async def taskinfo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await task_info_command(update, context)

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from .storage import storage
    total = storage.get_task_count()
    await update.message.reply_text(f"📊 Всего задач: {total}")

async def sync_admins_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Для совместимости со старой логикой (можно оставить заглушку)
    await update.message.reply_text("Команда не реализована в текущей версии.")

# ============================================================================
# АДМИНИСТРАТИВНЫЕ КОМАНДЫ (для сборки APK)
# ============================================================================

async def maintenance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not settings.is_admin(user_id):
        await update.message.reply_text("⛔ У вас нет прав.")
        return
    args = context.args
    current = await get_maintenance_mode()
    if args and args[0].lower() in ('on','1','true'):
        new_mode = True
    elif args and args[0].lower() in ('off','0','false'):
        new_mode = False
    else:
        new_mode = not current
    await set_maintenance_mode(new_mode)
    status = "включён" if new_mode else "выключен"
    await update.message.reply_text(f"🛠 Режим технического обслуживания {status}.")

async def admin_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not settings.is_admin(user_id):
        await update.message.reply_text("⛔ У вас нет прав.")
        return
    maintenance = await get_maintenance_mode()
    active_count = get_active_builds_count()
    queue_size = get_build_queue_size()
    free_mem = get_free_memory()
    free_mem_gb = free_mem / (1024**3)
    active_details = get_active_builds_details()
    text = (
        f"🛠 **Режим обслуживания:** {'Включён' if maintenance else 'Выключен'}\n"
        f"🏗 **Активных сборок:** {active_count}\n"
        f"⏳ **Задач в очереди:** {queue_size}\n"
        f"💾 **Свободно памяти:** {free_mem_gb:.1f} ГБ\n\n"
        "**Активные сборки:**\n"
    )
    if not active_details:
        text += "Нет активных сборок.\n"
    else:
        for build_id, details in active_details.items():
            elapsed = time.time() - details['start_time']
            text += (
                f"• **ID:** {build_id}\n"
                f"  Пользователь: {details['user_id']}\n"
                f"  Приложение: {details['app_name']}\n"
                f"  Package: {details['package']}\n"
                f"  Версия: {details['version']}\n"
                f"  Контейнер: {details['container_id'][:12]}\n"
                f"  Время работы: {elapsed:.0f} сек\n\n"
            )
    await update.message.reply_text(text, parse_mode='Markdown')

# ============================================================================
# ПЕРЕСЫЛКА БЫСТРЫХ СООБЩЕНИЙ (старая логика)
# ============================================================================

async def forward_task_to_devs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Проверяем диалог
    if context.user_data.get('task_in_progress'):
        is_dialog_handled = await handle_dialog_step(update, context)
        if is_dialog_handled:
            return
    # Обычная пересылка (заглушка)
    await update.message.reply_text("Быстрые сообщения не пересылаются в этой версии.")

# ============================================================================
# НАСТРОЙКА МЕНЮ КОМАНД
# ============================================================================

async def setup_bot_commands(application):
    commands = [
        BotCommand("start", "Запустить бота"),
        BotCommand("help", "Справка"),
        BotCommand("newtask", "Создать задачу"),
        BotCommand("task", "Информация о задаче"),
        BotCommand("build", "Собрать Android APK из ZIP"),
        BotCommand("cancel", "Отменить диалог"),
        BotCommand("id", "Показать ID"),
        BotCommand("ping", "Проверить бота"),
        BotCommand("stats", "Статистика задач"),
    ]
    if settings.admin_ids:
        commands.extend([
            BotCommand("maintenance", "Режим обслуживания (админ)"),
            BotCommand("admin_status", "Статус сервера (админ)"),
        ])
    await application.bot.set_my_commands(commands)

# ============================================================================
# СПИСОК ОБРАБОТЧИКОВ
# ============================================================================

handlers = [
    CommandHandler("start", start),
    CommandHandler("help", help_commands),
    CommandHandler("id", id_command),
    CommandHandler("ping", ping_command),
    CommandHandler("stats", stats_command),
    CommandHandler("syncadmins", sync_admins_command),
    CommandHandler("newtask", newtask_command),
    CommandHandler("task", taskinfo_command),
    CommandHandler("cancel", cancel_task_dialog),
    CommandHandler("build", start_build),   # команда сборки APK
    CommandHandler("maintenance", maintenance_command),
    CommandHandler("admin_status", admin_status),
    *get_task_handlers(),
    MessageHandler(
        filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE,
        forward_task_to_devs
    ),
]