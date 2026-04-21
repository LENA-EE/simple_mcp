# Используем официальный Python образ slim версии
FROM python:3.11-slim

# Устанавливаем рабочую директорию
WORKDIR /app

# Копируем файлы зависимостей
COPY pyproject.toml .

# Устанавливаем Python зависимости напрямую
RUN pip install --no-cache-dir fastapi uvicorn

# Копируем исходный код
COPY server.py .

# Открываем порт для SSE соединений
EXPOSE 8000

# Запускаем SSE сервер
CMD ["python", "server.py"]
