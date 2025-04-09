FROM python:3.11-slim

# Установить uv
RUN pip install --no-cache-dir uv

WORKDIR /app

# Скопировать корневые файлы для резолвинга зависимостей
COPY pyproject.toml uv.lock ./

# Скопировать файлы для data-collector и общего пакета
COPY services/data_collector ./services/data_collector
COPY services/common ./services/common

# Установить зависимости только для yieldex-data-collector
RUN uv sync --package yieldex-data-collector --python=/usr/local/bin/python

# Обновить PATH, чтобы использовать виртуальное окружение (.venv)
ENV PATH="/app/.venv/bin:$PATH"

# Установить переменную окружения для логов и создать директорию
ENV LOG_DIR=./logs
RUN mkdir -p $LOG_DIR

CMD ["python", "-m", "yieldex_data_collector.collector"]