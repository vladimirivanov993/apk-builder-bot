"""
Модуль для сборки APK из ZIP-архива с поддержкой параллельных сборок.
Ограничения: один пользователь — одна активная сборка.
Добавлена проверка безопасности: только статические файлы, очистка HTML, запрет внешних ссылок и изображений.
"""

import asyncio
import docker
import os
import shutil
import threading
import time
import zipfile
import re
from queue import Queue
from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler, CommandHandler, MessageHandler, filters
import bleach

from ..config.settings import settings
from ..db.database import (
    record_build_start,
    record_build_complete,
    record_build_failed,
    get_user_active_build,
    get_maintenance_mode
)

ASK_NAME, ASK_PACKAGE, ASK_VERSION, ASK_ZIP = range(4)

_active_builds = 0
_build_queue = Queue()
_build_lock = threading.Lock()
_send_queue = Queue()
_active_builds_details = {}
_active_builds_details_lock = threading.Lock()

_docker = docker.from_env()

BASE_BUILDS_DIR = "/it-wiki/builds"
BASE_OUTPUT_DIR = "/it-wiki/output"
ARCHIVE_PATH = "/it-wiki/archive"
KEYSTORE_PATH = settings.keystore_path

os.makedirs(BASE_BUILDS_DIR, exist_ok=True)
os.makedirs(BASE_OUTPUT_DIR, exist_ok=True)
os.makedirs(ARCHIVE_PATH, exist_ok=True)

_app = None
_loop = None
MEMORY_PER_BUILDER = int(settings.builder_memory_gb * 1024 * 1024 * 1024)

def set_application(app):
    global _app, _loop
    _app = app
    _loop = asyncio.get_event_loop()

def get_free_memory():
    try:
        info = _docker.info()
        return info.get('MemAvailable', info.get('MemFree', 0))
    except:
        return MEMORY_PER_BUILDER

def can_start_builder():
    return get_free_memory() >= MEMORY_PER_BUILDER

def get_active_builds_count():
    with _build_lock:
        return _active_builds

def get_build_queue_size():
    return _build_queue.qsize()

def get_active_builds_details():
    with _active_builds_details_lock:
        return _active_builds_details.copy()

def _add_build_detail(build_id, chat_id, user_id, app_name, package, version, container_id, start_time):
    with _active_builds_details_lock:
        _active_builds_details[build_id] = {
            'chat_id': chat_id,
            'user_id': user_id,
            'app_name': app_name,
            'package': package,
            'version': version,
            'container_id': container_id,
            'start_time': start_time
        }

def _remove_build_detail(build_id):
    with _active_builds_details_lock:
        _active_builds_details.pop(build_id, None)

def validate_site_files(wiki_path: str) -> tuple[bool, str]:
    """
    Проверяет все файлы в папке wiki_path:
    - Разрешены только статические расширения (текст, код, но без изображений).
    - Для HTML: очистка через bleach, запрет внешних ссылок, запрет data:image.
    """
    allowed_extensions = {
        '.html', '.htm', '.css', '.txt', '.md', '.xml', '.json'
    }

    allowed_tags = {
        'html', 'head', 'title', 'body',
        'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
        'p', 'div', 'span', 'section', 'article', 'header', 'footer', 'nav',
        'a', 'img', 'ul', 'ol', 'li', 'table', 'tr', 'td', 'th',
        'br', 'hr', 'strong', 'em', 'b', 'i', 'u',
        'form', 'input', 'button', 'label'
    }

    allowed_attributes = {
        'a': {'href', 'title', 'target'},
        'img': {'src', 'alt', 'title', 'width', 'height'},
        '*': {'id', 'class', 'style'}
    }

    allowed_protocols = {'http', 'https', 'mailto', 'ftp'}

    for root, dirs, files in os.walk(wiki_path):
        for file in files:
            ext = os.path.splitext(file)[1].lower()
            if ext not in allowed_extensions:
                return False, f"Запрещённый тип файла: {file}. Разрешены только {', '.join(allowed_extensions)}"

            if ext in ('.html', '.htm'):
                file_path = os.path.join(root, file)
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                except Exception as e:
                    return False, f"Не удалось прочитать {file}: {e}"

                # Запрет data:image
                data_image_pattern = re.compile(r'(src|href|background-image)\s*=\s*["\']?\s*url\(?["\']?data:image/', re.IGNORECASE)
                if data_image_pattern.search(content):
                    return False, f"Файл {file} содержит встроенные изображения (data:image). Загрузите архив без изображений."

                try:
                    cleaned = bleach.clean(
                        content,
                        tags=allowed_tags,
                        attributes=allowed_attributes,
                        protocols=allowed_protocols,
                        strip=False,
                        strip_comments=True
                    )
                    if cleaned != content:
                        return False, f"Файл {file} содержит небезопасный HTML (скрипты или опасные атрибуты)."

                    # Поиск внешних ссылок
                    pattern = r'(href|src|action)\s*=\s*["\']([^"\']*://[^"\']*)["\']'
                    matches = re.findall(pattern, content, re.IGNORECASE)
                    if matches:
                        bad_links = [value for _, value in matches]
                        if bad_links:
                            return False, f"Файл {file} содержит внешние ссылки: {', '.join(bad_links[:3])}."
                except Exception as e:
                    return False, f"Ошибка обработки HTML в {file}: {e}"

    return True, ""

def _run_builder(chat_id, user_id, app_name, package, version, bot, wiki_path, output_path, build_id):
    global _active_builds
    with _build_lock:
        _active_builds += 1

    try:
        env = {
            "APP_NAME": app_name,
            "PACKAGE": package,
            "VERSION": version,
            "BUILD_TYPE": "release",
            "KEYSTORE_PASS": settings.keystore_pass,
            "KEY_PASS": settings.key_pass,
        }
        volumes = {
            wiki_path: {"bind": "/wiki", "mode": "ro"},
            output_path: {"bind": "/output"},
            KEYSTORE_PATH: {"bind": "/keystore", "mode": "ro"}
        }
        container = _docker.containers.run(
            "sber-wiki-builder",
            volumes=volumes,
            environment=env,
            mem_limit=f"{MEMORY_PER_BUILDER // (1024*1024)}m",
            remove=True,
            detach=True
        )
        _add_build_detail(build_id, chat_id, user_id, app_name, package, version, container.id, time.time())

        result = container.wait()
        if result['StatusCode'] == 0:
            apk_path = os.path.join(output_path, "app.apk")
            if os.path.exists(apk_path):
                timestamp = int(time.time())
                new_apk_name = f"{app_name}_{version}_{timestamp}.apk"
                new_apk_name = "".join(c for c in new_apk_name if c.isalnum() or c in "._-")
                final_apk_path = os.path.join(ARCHIVE_PATH, new_apk_name)
                shutil.move(apk_path, final_apk_path)
                asyncio.run_coroutine_threadsafe(
                    record_build_complete(build_id, new_apk_name),
                    _loop
                )
                _send_queue.put((chat_id, final_apk_path, None, (wiki_path, output_path), build_id))
            else:
                asyncio.run_coroutine_threadsafe(
                    record_build_failed(build_id, "APK не найден после сборки."),
                    _loop
                )
                _send_queue.put((chat_id, None, "APK не найден после сборки.", (wiki_path, output_path), build_id))
        else:
            error_msg = f"Сборка завершилась с ошибкой (код {result['StatusCode']})."
            asyncio.run_coroutine_threadsafe(
                record_build_failed(build_id, error_msg),
                _loop
            )
            _send_queue.put((chat_id, None, error_msg, (wiki_path, output_path), build_id))
    except Exception as e:
        error_msg = f"Ошибка при запуске сборщика: {e}"
        asyncio.run_coroutine_threadsafe(
            record_build_failed(build_id, error_msg),
            _loop
        )
        _send_queue.put((chat_id, None, error_msg, (wiki_path, output_path), build_id))
    finally:
        _remove_build_detail(build_id)
        with _build_lock:
            _active_builds -= 1
        if not _build_queue.empty() and can_start_builder():
            next_task = _build_queue.get()
            threading.Thread(target=_run_builder, args=next_task).start()

def schedule_build(chat_id, user_id, app_name, package, version, bot, wiki_path, output_path, build_id):
    if can_start_builder():
        threading.Thread(target=_run_builder, args=(chat_id, user_id, app_name, package, version, bot, wiki_path, output_path, build_id)).start()
    else:
        _build_queue.put((chat_id, user_id, app_name, package, version, bot, wiki_path, output_path, build_id))
        asyncio.run_coroutine_threadsafe(
            bot.send_message(chat_id, "Сервер загружен, ваша сборка поставлена в очередь. Дождитесь завершения."),
            _loop
        )

async def _process_send_queue():
    while True:
        item = await asyncio.get_event_loop().run_in_executor(None, _send_queue.get)
        if item is None:
            break
        chat_id, file_path, error_msg, dirs, build_id = item
        try:
            if file_path:
                with open(file_path, 'rb') as f:
                    await _app.bot.send_document(chat_id=chat_id, document=f)
            else:
                await _app.bot.send_message(chat_id=chat_id, text=error_msg)
        except Exception as e:
            await _app.bot.send_message(chat_id=chat_id, text=f"Не удалось отправить: {e}")
        finally:
            for d in dirs:
                shutil.rmtree(d, ignore_errors=True)
        await asyncio.sleep(0.5)

async def start_build(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if await get_maintenance_mode():
        await update.message.reply_text("🛠 Сервер на техническом обслуживании. Сборка временно недоступна.")
        return ConversationHandler.END
    active_build_id = await get_user_active_build(user_id)
    if active_build_id:
        await update.message.reply_text("У вас уже есть активная сборка. Дождитесь её завершения.")
        return ConversationHandler.END
    await update.message.reply_text("Введите название приложения (например, MyApp):")
    return ASK_NAME

async def ask_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['app_name'] = update.message.text
    await update.message.reply_text("Введите package (например, com.example.app):")
    return ASK_PACKAGE

async def ask_package(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['package'] = update.message.text
    await update.message.reply_text("Введите версию (например, 1.0.0):")
    return ASK_VERSION

async def ask_version(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['version'] = update.message.text
    await update.message.reply_text("Теперь отправьте ZIP-архив с файлами вашего сайта (index.html и остальные).\nУбедитесь, что index.html находится в корне архива.")
    return ASK_ZIP

async def handle_zip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username

    if await get_maintenance_mode():
        await update.message.reply_text("🛠 Сервер на техническом обслуживании. Сборка временно недоступна.")
        return ConversationHandler.END
    if await get_user_active_build(user_id):
        await update.message.reply_text("У вас уже есть активная сборка. Дождитесь её завершения.")
        return ConversationHandler.END

    document = update.message.document
    if not document or not document.file_name.endswith('.zip'):
        await update.message.reply_text("Пожалуйста, отправьте ZIP-файл.")
        return ASK_ZIP

    unique_id = f"{user_id}_{int(time.time())}"
    wiki_path = os.path.join(BASE_BUILDS_DIR, unique_id)
    output_path = os.path.join(BASE_OUTPUT_DIR, unique_id)
    os.makedirs(wiki_path, exist_ok=True)
    os.makedirs(output_path, exist_ok=True)

    file = await context.bot.get_file(document.file_id)
    zip_path = os.path.join(wiki_path, "upload.zip")
    await file.download_to_drive(zip_path)

    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            zf.extractall(wiki_path)
        os.remove(zip_path)
    except Exception as e:
        await update.message.reply_text(f"Ошибка распаковки архива: {e}")
        shutil.rmtree(wiki_path, ignore_errors=True)
        shutil.rmtree(output_path, ignore_errors=True)
        return ConversationHandler.END

    # Если внутри архива одна папка, перемещаем её содержимое наверх
    items = os.listdir(wiki_path)
    if len(items) == 1 and os.path.isdir(os.path.join(wiki_path, items[0])):
        subdir = os.path.join(wiki_path, items[0])
        for f in os.listdir(subdir):
            shutil.move(os.path.join(subdir, f), wiki_path)
        os.rmdir(subdir)

    # Проверяем наличие index.html
    index_path = os.path.join(wiki_path, "index.html")
    if not os.path.exists(index_path):
        await update.message.reply_text("В архиве не найден index.html. Убедитесь, что файл находится в корне архива.")
        shutil.rmtree(wiki_path, ignore_errors=True)
        shutil.rmtree(output_path, ignore_errors=True)
        return ConversationHandler.END

    # Проверка безопасности
    valid, error_msg = validate_site_files(wiki_path)
    if not valid:
        await update.message.reply_text(f"❌ Проверка безопасности не пройдена: {error_msg}\n"
                                        "Сборка отменена. Пожалуйста, убедитесь, что архив содержит только статические файлы и не содержит внешних ссылок или скриптов.")
        shutil.rmtree(wiki_path, ignore_errors=True)
        shutil.rmtree(output_path, ignore_errors=True)
        return ConversationHandler.END

    build_id = await record_build_start(
        user_id=user_id,
        username=username,
        app_name=context.user_data['app_name'],
        package=context.user_data['package'],
        version=context.user_data['version']
    )

    schedule_build(
        chat_id=update.effective_chat.id,
        user_id=user_id,
        app_name=context.user_data['app_name'],
        package=context.user_data['package'],
        version=context.user_data['version'],
        bot=context.bot,
        wiki_path=wiki_path,
        output_path=output_path,
        build_id=build_id
    )

    await update.message.reply_text("Сборка запущена. Я уведомлю, когда APK будет готов.")
    return ConversationHandler.END

async def cancel_build(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Сборка отменена.")
    return ConversationHandler.END

build_handlers = [
    ConversationHandler(
        entry_points=[CommandHandler("build", start_build)],
        states={
            ASK_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_name)],
            ASK_PACKAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_package)],
            ASK_VERSION: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_version)],
            ASK_ZIP: [MessageHandler(filters.Document.ALL, handle_zip)],
        },
        fallbacks=[CommandHandler("cancel", cancel_build)],
    ),
]

def register_handlers(app):
    for handler in build_handlers:
        app.add_handler(handler)
    asyncio.get_event_loop().create_task(_process_send_queue())