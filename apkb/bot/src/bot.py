#!/usr/bin/env python3
"""
Точка входа Telegram-бота.
Инициализирует базу данных, регистрирует обработчики, запускает polling.
"""

import sys
import os
import logging
import signal
import asyncio

from dotenv import load_dotenv
load_dotenv()

from telegram.ext import Application

from src.config.settings import settings
from src.handlers import commands, error
from src.handlers.apk_builder import register_handlers, set_application
from src.handlers.storage import storage
from src.db.database import init_db, close_db

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def signal_handler(signum, frame):
    """Обработчик сигналов для graceful shutdown."""
    logger.info(f"📩 Получен сигнал {signum}, завершаем работу...")
    storage.save()
    asyncio.create_task(close_db())

async def main():
    """Основная асинхронная функция."""
    try:
        logger.info("🤖 Инициализация бота...")
        if not settings.bot_token:
            logger.error("❌ Токен бота не найден в настройках!")
            sys.exit(1)

        # Инициализация PostgreSQL
        await init_db(settings.database_url)

        # Создание приложения Telegram
        app = Application.builder().token(settings.bot_token).build()
        set_application(app)  # для доступа к bot из фоновых потоков

        # Регистрация обработчиков сборки APK
        register_handlers(app)

        # Регистрация остальных обработчиков (задачи, админка)
        app.add_handlers(commands.handlers)
        app.add_error_handler(error.error_handler)

        # Настройка команд меню
        app.post_init = commands.setup_bot_commands

        # Обработка сигналов
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        logger.info("✅ Обработчики зарегистрированы")
        logger.info(f"💾 Загружено {storage.get_task_count()} задач из хранилища")
        deleted = storage.delete_old_tasks(days=90)
        if deleted:
            logger.info(f"🗑️ Удалено {deleted} старых задач")

        logger.info("🚀 Запуск бота...")
        await app.run_polling(drop_pending_updates=True, close_loop=True)

    except KeyboardInterrupt:
        logger.info("🛑 Бот остановлен пользователем")
    except Exception as e:
        logger.error(f"💥 Критическая ошибка: {e}", exc_info=True)
    finally:
        await close_db()
        storage.save()

if __name__ == "__main__":
    asyncio.run(main())