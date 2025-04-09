FROM python:3.11-slim

WORKDIR /app

# Установка зависимостей
COPY packages/common/pyproject.toml packages/common/
COPY packages/onchain/pyproject.toml packages/onchain/

RUN pip install --no-cache-dir --upgrade pip uv && \
    uv pip install -e packages/common/ && \
    uv pip install -e packages/onchain/

# Копирование кода
COPY packages/common/src/ packages/common/src/
COPY packages/onchain/src/ packages/onchain/src/

# Переменные окружения
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# Запуск приложения
CMD ["python", "-m", "yieldex_onchain.onchain_operator"]
