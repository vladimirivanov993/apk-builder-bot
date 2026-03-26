"""
Хранение данных задач (tasks.json) – используется в основной логике бота.
Для совместимости оставляем класс-заглушку.
"""

import json
import os
import time

class TaskStorage:
    def __init__(self, filename='tasks.json'):
        self.filename = filename
        self.tasks = {}
        self.load()

    def load(self):
        if os.path.exists(self.filename):
            with open(self.filename, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.tasks = data.get('tasks', {})
        else:
            self.tasks = {}

    def save(self):
        with open(self.filename, 'w', encoding='utf-8') as f:
            json.dump({'tasks': self.tasks}, f, ensure_ascii=False, indent=2)

    def get_task_count(self):
        return len(self.tasks)

    def delete_old_tasks(self, days=90):
        # Удаляем задачи старше дней (если есть поле updated_at)
        # Заглушка
        return 0

storage = TaskStorage()