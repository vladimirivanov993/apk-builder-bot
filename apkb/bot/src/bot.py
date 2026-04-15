#!/usr/bin/env python3
"""
Telegram бот для управления задачами с сохранением состояния в файл.
"""

import sys
import os
import logging
import signal
import asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

try:
    from telegram.ext import Application
    from src.config.settings import settings
    from src.handlers import commands
    from src.handlers.apk_builder import register_handlers, set_application, graceful_shutdown, restore_state
    from src.handlers.storage import storage
    from src.db.database import init_db, close_db
except ImportError as e:
    print(f"❌ Ошибка импорта: {e}")
    sys.exit(1)

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

logger = logging.getLogger(__name__)

# Глобальная ссылка на приложение для обработчика сигналов
app = None

def main():
    global app
    try:
        logger.info("🤖 Инициализация бота...")
        
        if not settings.bot_token:
            logger.error("❌ Токен бота не найден!")
            sys.exit(1)
        
        logger.info(f"✅ Токен получен (первые 10 символов): {settings.bot_token[:10]}...")
        logger.info(f"👑 Администраторы: {settings.admin_ids}")
        
        # Инициализация БД
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(init_db(settings.database_url))
        
        # Создание приложения
        app = Application.builder().token(settings.bot_token).build()
        set_application(app)
        
        # Восстановление очереди и сброс зависших сборок
        loop.run_until_complete(restore_state())
        
        # Регистрация обработчиков
        register_handlers(app)
        app.add_handlers(commands.handlers)
        app.add_error_handler(commands.error_handler)
        
        # Настройка команд меню
        app.post_init = commands.setup_bot_commands
        
        # Обработчики сигналов (определяем внутри main, чтобы захватить app)
        def signal_handler(signum, frame):
            logger.info(f"📩 Получен сигнал {signum}, завершаем работу...")
            storage.save()
            loop = asyncio.get_event_loop()
            loop.create_task(shutdown(app))
            loop.call_later(30, lambda: loop.stop())
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        logger.info("✅ Обработчики зарегистрированы")
        logger.info(f"💾 Загружено {storage.get_task_count()} задач из хранилища")
        
        # Автоматическая очистка старых задач
        deleted = storage.delete_old_tasks(days=90)
        if deleted > 0:
            logger.info(f"🗑️ Удалено {deleted} старых задач")
        
        logger.info("🚀 Запуск бота...")
        app.run_polling(
            drop_pending_updates=True,
            close_loop=True
        )
        
        loop.run_until_complete(close_db())
        
    except KeyboardInterrupt:
        logger.info("🛑 Бот остановлен пользователем")
        storage.save()
        sys.exit(0)
    except Exception as e:
        logger.error(f"💥 Критическая ошибка: {e}")
        import traceback
        traceback.print_exc()
        storage.save()
        sys.exit(1)

async def shutdown(application):
    logger.info("🛑 Начинаем graceful shutdown...")
    await graceful_shutdown()
    logger.info("✅ Все сборки завершены, очередь сохранена")
    await application.stop()
    await close_db()

if __name__ == "__main__":
    main()
