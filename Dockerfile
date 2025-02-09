# Dockerfile для data collector
FROM python:3.11-slim

# Добавляем метки
LABEL maintainer="exectrogod@gmail.com"
LABEL description="Data collector for Yieldex"
LABEL version="1.0"

# Устанавливаем рабочую директорию
WORKDIR /app

# Создаем директорию для логов
RUN mkdir -p /app/logs

# Копируем только файлы зависимостей
COPY requirements.txt .

# Устанавливаем зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Копируем код приложения
COPY src/ ./src/

# Healthcheck с проверкой конфигурации
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "from src.yieldex.config import validate_env_vars; from src.yieldex.data_collector import fetch_pools; assert validate_env_vars() and fetch_pools()"

# Запускаем data collector при старте контейнера
CMD ["python", "-u", "-m", "src.yieldex.data_collector"] 