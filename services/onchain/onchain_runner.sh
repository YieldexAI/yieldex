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
for package in "yieldex-common" "yieldex-analyzer" "yieldex-onchain"; do
  if ! uv pip list | grep -q "${package}"; then
    echo "Устанавливаем ${package}..."
    if [[ "$package" == "yieldex-common" ]]; then
      (cd services/common && uv pip install -e .)
    elif [[ "$package" == "yieldex-analyzer" ]]; then
      (cd services/analyzer && uv pip install -e .)
    elif [[ "$package" == "yieldex-onchain" ]]; then
      (cd services/onchain && uv pip install -e .)
    fi
  fi
done

function usage() {
  echo "Использование: $0 <команда> [аргументы]"
  echo ""
  echo "Доступные команды:"
  echo "  aave-rates <chain> <asset>             - Просмотр ставок Aave V3 для указанного актива на указанной сети"
  echo "  token-check <chain> <asset>            - Проверка поддержки токена на указанной сети"
  echo "  supported-pools <chain>                - Просмотр поддерживаемых пулов на указанной сети"
  echo "  silo-markets <chain>                   - Просмотр доступных рынков Silo на указанной сети"
  echo "  test                                   - Запуск тестов функций onchain"
  echo ""
  echo "Примеры:"
  echo "  $0 aave-rates Arbitrum USDC"
  echo "  $0 token-check Sonic USDT"
  echo "  $0 supported-pools Optimism"
  echo "  $0 silo-markets Sonic"
  echo "  $0 test"
  exit 1
}

function run_aave_rates() {
  local chain=$1
  local asset=$2
  
  if [[ -z "$chain" || -z "$asset" ]]; then
    echo "Ошибка: необходимо указать цепь и актив"
    usage
  fi
  
  python -c "
from yieldex_onchain.protocol_fabric import AaveOperator
from yieldex_common.utils import get_token_address
from web3 import Web3
import logging
logging.basicConfig(level=logging.INFO)

network = '$chain'
asset = '$asset'
try:
    aave_operator = AaveOperator(network, 'aave-v3')
    token_address = get_token_address(asset, network)
    checksum_address = Web3.to_checksum_address(token_address)
    reserve_data = aave_operator.contract.functions.getReserveData(checksum_address).call()
    
    print(f'\n{asset} on {network} Aave V3 Rates:')
    print(f'  Supply APY:    {reserve_data[2] / 10**27:.4%}')
    print(f'  Variable APY:  {reserve_data[4] / 10**27:.4%}')
    print(f'  Stable APY:    {reserve_data[5] / 10**27:.4%}')
    print(f'  aToken:        {reserve_data[8]}')
    print(f'  debtToken:     {reserve_data[10]}')
except Exception as e:
    print(f'Ошибка при получении данных: {str(e)}')
"
}

function run_token_check() {
  local chain=$1
  local asset=$2
  
  if [[ -z "$chain" || -z "$asset" ]]; then
    echo "Ошибка: необходимо указать цепь и актив"
    usage
  fi
  
  python -c "
from yieldex_onchain.protocol_fabric import get_protocol_operator
from yieldex_common.utils import get_token_address
import logging
logging.basicConfig(level=logging.INFO)

network = '$chain'
asset = '$asset'
try:
    aave_operator = get_protocol_operator(network, 'aave-v3')
    token_address = get_token_address(asset, network)
    is_supported = aave_operator._check_token_support(token_address)
    print(f'\nТокен {asset} на {network}:')
    print(f'  Адрес:      {token_address}')
    print(f'  Поддержка:  {\"ПОДДЕРЖИВАЕТСЯ\" if is_supported else \"НЕ ПОДДЕРЖИВАЕТСЯ\"}')
except Exception as e:
    print(f'Ошибка при проверке токена: {str(e)}')
"
}

function run_supported_pools() {
  local chain=$1
  
  if [[ -z "$chain" ]]; then
    echo "Ошибка: необходимо указать цепь"
    usage
  fi
  
  python -c "
from yieldex_common.config import (
    AAVE_V3_ADDRESSES, AAVE_V2_ADDRESSES, COMPOUND_ADDRESSES, 
    RHO_ADDRESSES, FLUID_ADDRESSES, SILOS_ADDRESSES
)
import logging
logging.basicConfig(level=logging.INFO)

network = '$chain'
print(f'\nПоддерживаемые протоколы на {network}:')

protocols = [
    ('Aave V3', AAVE_V3_ADDRESSES),
    ('Aave V2', AAVE_V2_ADDRESSES),
    ('Compound V3', COMPOUND_ADDRESSES),
    ('Rho Markets', RHO_ADDRESSES),
    ('Fluid', FLUID_ADDRESSES),
    ('Silo Finance', SILOS_ADDRESSES),
]

for name, addresses in protocols:
    if network in addresses:
        print(f'  + {name}: {addresses[network]}')
    else:
        print(f'  - {name}: не поддерживается')
"
}

function run_silo_markets() {
  local chain=$1
  
  if [[ -z "$chain" ]]; then
    echo "Ошибка: необходимо указать цепь"
    usage
  fi
  
  python -c "
from yieldex_common.config import SILO_MARKETS
import logging
logging.basicConfig(level=logging.INFO)

network = '$chain'
print(f'\nДоступные рынки Silo на {network}:')

if network in SILO_MARKETS:
    markets = SILO_MARKETS[network]
    for market_id, address in markets.items():
        print(f'  + Market {market_id}: {address}')
    print(f'\nВсего рынков: {len(markets)}')
else:
    print(f'  - Рынки Silo не найдены для сети {network}')
"
}

function run_test() {
  echo "Запуск тестов функций onchain..."
  python test_onchain_functions.py
}

# Основная логика
case "$1" in
  "aave-rates")
    run_aave_rates "$2" "$3"
    ;;
  "token-check")
    run_token_check "$2" "$3"
    ;;
  "supported-pools")
    run_supported_pools "$2"
    ;;
  "silo-markets")
    run_silo_markets "$2"
    ;;
  "test")
    run_test
    ;;
  *)
    usage
    ;;
esac 