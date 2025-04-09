# Yieldex Data Collector

Компонент для сбора данных о пулах ликвидности и APY с различных протоколов DeFi.

## Установка

```bash
# Из корня монорепозитория
uv pip install -e packages/common
uv pip install -e packages/data_collector
```

## Разработка

```bash
# Установка зависимостей для разработки
uv pip install -e packages/data_collector[dev]

# Запуск тестов
pytest
```

## Docker

Для сборки Docker-образа:

```bash
docker build -t yieldex/data-collector -f packages/data_collector/docker/Dockerfile .
```

Для запуска:

```bash
docker run -d --name data-collector \
  -e SUPABASE_URL=your_supabase_url \
  -e SUPABASE_KEY=your_supabase_key \
  -e RPC_ETHEREUM=your_ethereum_rpc \
  -e RPC_ARBITRUM=your_arbitrum_rpc \
  yieldex/data-collector
```
