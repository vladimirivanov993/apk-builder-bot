pk-builder-bot
# Запустите в пустой директории

set -e

echo "📁 Создаю структуру репозитория..."

# Корневые файлы
touch README.md
cat > README.md << 'EOF'
# APK Builder Bot

Telegram-бот для автоматической сборки Android APK из ZIP-архивов с веб-сайтами (только текст, HTML/CSS, диаграммы).  
Подробное описание будет добавлено позже.
EOF

touch LICENSE
cat > LICENSE << 'EOF'
MIT License

Copyright (c) 2025 [ваше имя]

Permission is hereby granted...
EOF

touch .gitignore
cat > .gitignore << 'EOF'
# Python
__pycache__/
*.py[cod]
.env
*.log

# Project
bot/data/
bot/logs/
it-wiki/
output/
archive/
builds/
keystore/
EOF

# Создаём папку bot и её подструктуру
mkdir -p bot/src/config bot/src/db bot/src/handlers

# bot/Dockerfile
cat > bot/Dockerfile << 'EOF'
# Dockerfile для контейнера бота (Python 3.11 Alpine)
# Используется как основа для Telegram-бота
FROM python:3.11-alpine

WORKDIR /app

RUN apk add --no-cache tini curl

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY .env .
COPY src/ ./src/

ENTRYPOINT ["/sbin/tini", "--"]
CMD ["python", "src/bot.py"]
EOF

# bot/requirements.txt
cat > bot/requirements.txt << 'EOF'
# Зависимости Python-бота
python-telegram-bot==20.7
docker==7.0.0
asyncpg==0.29.0
python-dotenv==1.0.0
bleach==6.3.0
EOF

# bot/.env.example
cat > bot/.env.example << 'EOF'
# Пример файла .env – скопируйте и заполните реальными данными
TELEGRAM_TOKEN=your_bot_token_here
POSTGRES_USER=bot_user
POSTGRES_PASSWORD=change_me
POSTGRES_DB=builds_db
DATABASE_URL=postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@postgres:5432/${POSTGRES_DB}
ADMIN_IDS=123456789,987654321
WIKI_PATH=/it-wiki
OUTPUT_PATH=/output
KEYSTORE_PATH=/keystore
KEYSTORE_PASS=your_keystore_password
KEY_PASS=your_key_password
BUILDER_MEMORY_GB=2.5
EOF

# bot/docker-compose.yml
cat > bot/docker-compose.yml << 'EOF'
# Оркестрация: бот + PostgreSQL
services:
  telegram_bot:
      build: .
          container_name: apk_builder_bot
	      env_file: .env
	          volumes:
		        - ./data:/app/data
			      - ./src:/app/src
			            - /var/run/docker.sock:/var/run/docker.sock
				          - ../it-wiki:/it-wiki
    depends_on:
      - postgres
  postgres:
    image: postgres:15-alpine
    container_name: apk_builder_db
    environment:
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: ${POSTGRES_DB}
    volumes:
      - postgres_data:/var/lib/postgresql/data
volumes:
  postgres_data:
EOF

# bot/src/__init__.py
touch bot/src/__init__.py

# bot/src/bot.py
cat > bot/src/bot.py << 'EOF'
# Точка входа бота: инициализация, регистрация обработчиков, запуск polling.
import asyncio
from telegram.ext import Application
from src.config.settings import settings
from src.handlers import commands, error
from src.handlers.apk_builder import register_handlers, set_application
from src.db.database import init_db, close_db
# ... (здесь будет полный код)
EOF

# bot/src/config/__init__.py
touch bot/src/config/__init__.py

# bot/src/config/settings.py
cat > bot/src/config/settings.py << 'EOF'
# Загрузка настроек из переменных окружения.
import os

class Settings:
    def __init__(self):
        self.bot_token = os.getenv("TELEGRAM_TOKEN", "")
        self.admin_ids = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x]
        self.database_url = os.getenv("DATABASE_URL")
        self.wiki_path = os.getenv("WIKI_PATH", "/it-wiki")
        self.output_path = os.getenv("OUTPUT_PATH", "/output")
        self.keystore_path = os.getenv("KEYSTORE_PATH", "/keystore")
        self.keystore_pass = os.getenv("KEYSTORE_PASS", "")
        self.key_pass = os.getenv("KEY_PASS", "")
        self.builder_memory_gb = float(os.getenv("BUILDER_MEMORY_GB", "2.5"))
    def is_admin(self, user_id):
        return user_id in self.admin_ids

settings = Settings()
EOF

# bot/src/db/__init__.py
touch bot/src/db/__init__.py

# bot/src/db/database.py
cat > bot/src/db/database.py << 'EOF'
# Работа с PostgreSQL: инициализация, запись сборок, получение статуса, режим обслуживания.
import asyncpg
# ... (здесь будет полный код)
EOF

# bot/src/handlers/__init__.py
touch bot/src/handlers/__init__.py

# bot/src/handlers/apk_builder.py
cat > bot/src/handlers/apk_builder.py << 'EOF'
# Основная логика сборки APK: диалог, проверка архива, запуск контейнера, очередь, отправка результата.
# Здесь реализованы validate_site_files, schedule_build, обработчики диалога.
# ... (здесь будет полный код)
EOF

# bot/src/handlers/commands.py
cat > bot/src/handlers/commands.py << 'EOF'
# Обработчики команд бота: /start, /help, /id, /build, /maintenance, /admin_status и др.
# ... (здесь будет полный код)
EOF

# bot/src/handlers/error.py
cat > bot/src/handlers/error.py << 'EOF'
# Глобальный обработчик ошибок для бота.
# ... (здесь будет полный код)
EOF

# bot/src/handlers/storage.py
cat > bot/src/handlers/storage.py << 'EOF'
# Хранение данных задач (файл tasks.json) – используется в основной логике бота.
# ... (здесь будет полный код)
EOF

# bot/src/handlers/task_dialog.py
cat > bot/src/handlers/task_dialog.py << 'EOF'
# Диалог для создания задачи (не относится к сборке APK, но оставлено для совместимости).
# ... (здесь будет полный код)
EOF

# Создаём папку builder
mkdir -p builder

# builder/Dockerfile
cat > builder/Dockerfile << 'EOF'
# Образ сборщика APK: Node 16 + Cordova + Android SDK + JDK 17.
# Используется для запуска контейнеров, которые собирают APK.
FROM dockerhub.timeweb.cloud/library/node:16-buster
# ... (здесь будет полный код)
EOF

# builder/entrypoint.sh
cat > builder/entrypoint.sh << 'EOF'
#!/bin/sh
# Скрипт внутри контейнера сборщика: создаёт проект Cordova, копирует файлы, запускает сборку.
# ... (здесь будет полный код)
EOF
chmod +x builder/entrypoint.sh

echo "✅ Готово! Структура репозитория создана."
echo "Теперь нужно заполнить содержимое файлов, используя предоставленные ранее фрагменты кода."
