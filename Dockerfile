# Используем официальный Python образ slim версии
FROM python:3.11-slim

# Устанавливаем рабочую директорию
WORKDIR /app

# Устанавливаем Perl и cpanminus
RUN apt-get update && apt-get install -y \
    perl \
    cpanminus \
    && rm -rf /var/lib/apt/lists/*

# Устанавливаем Perl::Critic через cpanm (быстро и тихо)
RUN cpanm --notest --quiet Perl::Critic && \
    # Проверяем установку
    perlcritic --version && \
    # Создаем симлинк для гарантированного доступа
    ln -sf /usr/local/bin/perlcritic /usr/bin/perlcritic

# Копируем файлы зависимостей
COPY pyproject.toml .

# Устанавливаем Python зависимости напрямую
RUN pip install --no-cache-dir fastapi uvicorn

# Копируем исходный код (включая модуль tools)
COPY server.py .
COPY tools/ ./tools/

# Создаем тестовый Perl файл для проверки
RUN echo '#!/usr/bin/perl\nuse strict;\nuse warnings;\nprint "Test Perl\\n";' > /app/test_perl.pl && \
    chmod +x /app/test_perl.pl

# Открываем порт для SSE соединений
EXPOSE 8000

# Запускаем SSE сервер
CMD ["python", "server.py"]