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
