# Yieldex Onchain Module

Модуль для взаимодействия с блокчейном и DeFi-протоколами.

## Функциональность

- Взаимодействие с популярными DeFi-протоколами (Aave, Compound, Silo, и др.)
- Выполнение транзакций (депозиты, вывод средств, обмен токенов)
- Получение информации о балансах и APY
- Поддержка множества блокчейнов (Ethereum, Arbitrum, Optimism и др.)

## Установка

```bash
# Из корня монорепозитория
uv pip install -e packages/common
uv pip install -e packages/onchain
```

## Примеры использования

```python
from yieldex_onchain.protocol_fabric import get_protocol_operator

# Инициализация оператора Aave на сети Arbitrum
aave = get_protocol_operator("Arbitrum", "aave-v3")

# Депозит USDC
tx_hash = aave.supply("USDC", 100.0)
print(f"Транзакция депозита: {tx_hash}")

# Вывод средств
tx_hash = aave.withdraw("USDC", 50.0)
print(f"Транзакция вывода: {tx_hash}")
```

## Разработка

```bash
# Установка зависимостей для разработки
uv pip install -e packages/onchain[dev]

# Запуск тестов
pytest
```

## Docker

Для сборки Docker-образа:

```bash
docker build -t yieldex/onchain -f packages/onchain/docker/Dockerfile .
```
