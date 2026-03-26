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
