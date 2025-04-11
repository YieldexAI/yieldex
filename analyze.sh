#!/bin/bash
set -e

# Проверяем наличие виртуального окружения
if [ ! -d ".venv" ]; then
  echo "Виртуальное окружение не найдено. Создаем..."
  uv venv .venv
fi

# Активируем виртуальное окружение
source .venv/bin/activate

# Устанавливаем необходимые пакеты, если они еще не установлены
if ! uv pip list | grep -q "yieldex-common"; then
  echo "Устанавливаем yieldex-common..."
  (cd services/common && uv pip install -e .)
fi

if ! uv pip list | grep -q "yieldex-analyzer"; then
  echo "Устанавливаем yieldex-analyzer..."
  (cd services/analyzer && uv pip install -e .)
fi

# Запускаем анализатор с переданными аргументами
echo "Запускаем анализатор с аргументами: $@"
uv run python -m analyzer.analyzer "$@" 