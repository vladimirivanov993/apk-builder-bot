#!/usr/bin/env python3
"""
Telegram бот для управления задачами с сохранением состояния в файл.
"""

import sys
import os
import logging
import signal

# Добавляем пути для импорта
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Загружаем переменные окружения из .env файла
from dotenv import load_dotenv
load_dotenv()

try:
    from telegram.ext import Application
    from src.config.settings import settings
    from src.handlers import commands, error
    from src.handlers.apk_builder import register_handlers, set_application
    from src.handlers.storage import storage
    from src.db.database import init_db, close_db
except ImportError as e:
    print(f"❌ Ошибка импорта: {e}")
    print("Убедитесь, что установлены все зависимости:")
    print("  pip install python-telegram-bot python-dotenv")
    sys.exit(1)

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

logger = logging.getLogger(__name__)

def signal_handler(signum, frame):
    """Обработчик сигналов для graceful shutdown"""
    logger.info(f"📩 Получен сигнал {signum}, завершаем работу...")
    storage.save()
    # Убираем sys.exit(0) - позволим библиотеке корректно завершить работу
    # python-telegram-bot сам вызовет exit после остановки polling

def main():
    """Точка входа приложения"""
    try:
        logger.info("🤖 Инициализация бота...")
        
        # Проверка токена через settings
        if not settings.bot_token:
            logger.error("❌ Токен бота не найден в настройках!")
            logger.error("Добавьте BOT_TOKEN в .env файл или переменные окружения")
            sys.exit(1)
        
        logger.info(f"✅ Токен получен (первые 10 символов): {settings.bot_token[:10]}...")
        logger.info(f"👑 Администраторы: {settings.admin_ids}")
        
        # Инициализация БД
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(init_db(settings.database_url))
        
        # Создание приложения
        app = Application.builder().token(settings.bot_token).build()
        set_application(app)
        
        # Регистрация обработчиков
        register_handlers(app)
        app.add_handlers(commands.handlers)
        app.add_error_handler(error.error_handler)
        
        # Настройка команд меню
        app.post_init = commands.setup_bot_commands
        
        # Регистрация обработчиков сигналов
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        logger.info("✅ Обработчики зарегистрированы")
        logger.info(f"💾 Загружено {storage.get_task_count()} задач из хранилища")
        
        # Автоматическая очистка старых задач
        deleted = storage.delete_old_tasks(days=90)
        if deleted > 0:
            logger.info(f"🗑️ Удалено {deleted} старых задач")
        
        logger.info("🚀 Запуск бота...")
        
        # Ключевые изменения здесь: правильные параметры для run_polling
        app.run_polling(
            drop_pending_updates=True,
            close_loop=True,  # Изменили с False на True - это позволяет корректно закрыть event loop
            # Убрали stop_signals=None - теперь библиотека использует свою обработку сигналов
            # и корректно завершает работу при получении SIGTERM/SIGINT
        )
        
        # Закрываем БД после завершения
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

if __name__ == "__main__":
    main()
