#!/usr/bin/env python3
"""
Скрипт для прямого взаимодействия с контрактами Silo0 и Silo1 в сети Sonic.
Правильная архитектура Silo V2: каждый рынок состоит из двух контрактов Silo.
"""

import sys
import os
import json
import logging
from enum import Enum
from pathlib import Path
from typing import Dict, Any, Optional
import requests

# Настраиваем логирование
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Определяем базовые константы
ABI_DIR = Path(os.path.dirname(__file__)) / ".." / "common" / "abi"

# Конфигурация для Silo контрактов
SILO_CONFIG = {
    "Sonic": {
        "Market_20": {
            "market_address": "0x062A36Bbe0306c2Fd7aecdf25843291fBAB96AD2",
            "silo0_address": "0xf55902DE87Bd80c6a35614b48d7f8B612a083C12",
            "silo1_address": "0x322e1d5384aa4ED66AeCa770B95686271de61dc3",
            "token": "USDC.E",
            "token_address": "0xF319945907d66fA17AD5d4D622F9Ab8e5D5bAd29"
        }
    }
}

# RPC URLs для различных сетей
RPC_URLS = {
    "Sonic": [
        "https://sonic.drpc.org",  # dRPC - надежный RPC для Sonic
    ]
}

# Определяем класс CollateralType
class CollateralType(Enum):
    STANDARD = 0
    PROTECTED = 1

def get_web3_connection(network: str):
    """Устанавливает подключение к сети через Web3"""
    from web3 import Web3
    
    # Получаем список RPC URLs для сети
    rpc_urls = RPC_URLS.get(network, [])
    if not rpc_urls:
        raise ValueError(f"RPC URL не найден для сети {network}")
    
    # Пробуем подключиться к каждому URL из списка
    for rpc_url in rpc_urls:
        logger.info(f"Проверка подключения к RPC: {rpc_url}")
        try:
            # Проверяем RPC через прямой запрос
            response = requests.post(
                rpc_url,
                json={"jsonrpc": "2.0", "method": "eth_blockNumber", "params": [], "id": 1},
                timeout=5
            )
            if response.status_code == 200:
                # Проверяем Web3 подключение
                w3 = Web3(Web3.HTTPProvider(rpc_url))
                block = w3.eth.get_block('latest')
                logger.info(f"Подключено к {rpc_url}, последний блок: {block.number}")
                return w3
            else:
                logger.warning(f"RPC {rpc_url} вернул статус {response.status_code}")
        except Exception as e:
            logger.warning(f"Не удалось подключиться к {rpc_url}: {str(e)}")
    
    raise ConnectionError(f"Не удалось подключиться ни к одному RPC для сети {network}")

def get_contract_info(network: str, market_id: str):
    """Получает информацию о контрактах Silo для указанного рынка"""
    if network not in SILO_CONFIG:
        raise ValueError(f"Сеть {network} не найдена в конфигурации")
    
    market_key = f"Market_{market_id}"
    if market_key not in SILO_CONFIG[network]:
        raise ValueError(f"Рынок {market_id} не найден в конфигурации для сети {network}")
    
    return SILO_CONFIG[network][market_key]

def read_basic_info_from_silo(network: str, market_id: str):
    """
    Чтение базовой информации из контрактов Silo0 и Silo1
    
    Args:
        network: Сеть (например, 'Sonic')
        market_id: ID рынка (например, '20')
    
    Returns:
        Dict: Словарь с данными о Silo
    """
    try:
        logger.info(f"Чтение базовой информации из Silo для market_id: {market_id} в сети {network}")
        
        # Получаем Web3 подключение
        w3 = get_web3_connection(network)
        
        # Получаем информацию о контрактах
        contract_info = get_contract_info(network, market_id)
        logger.info(f"Информация о контрактах: {contract_info}")
        
        # Загружаем ABI
        silo_abi_path = ABI_DIR / "Silo.json"
        erc20_abi_path = ABI_DIR / "ERC20.json"
        
        if not silo_abi_path.exists():
            raise FileNotFoundError(f"ABI-файл не найден: {silo_abi_path}")
        if not erc20_abi_path.exists():
            raise FileNotFoundError(f"ABI-файл не найден: {erc20_abi_path}")
        
        with open(silo_abi_path) as f:
            silo_abi = json.load(f)
        
        with open(erc20_abi_path) as f:
            erc20_abi = json.load(f)
        
        # Конвертируем адреса в формат с правильной контрольной суммой
        silo0_address = w3.to_checksum_address(contract_info["silo0_address"])
        silo1_address = w3.to_checksum_address(contract_info["silo1_address"])
        token_address = w3.to_checksum_address(contract_info["token_address"])
        
        # Создаем контракты
        silo0_contract = w3.eth.contract(address=silo0_address, abi=silo_abi)
        silo1_contract = w3.eth.contract(address=silo1_address, abi=silo_abi)
        token_contract = w3.eth.contract(address=token_address, abi=erc20_abi)
        
        # Попробуем получить базовую информацию из Silo0
        silo0_info = {}
        try:
            # Базовые функции ERC-20
            silo0_info["name"] = silo0_contract.functions.name().call()
            silo0_info["symbol"] = silo0_contract.functions.symbol().call()
            silo0_info["decimals"] = silo0_contract.functions.decimals().call()
            
            # Пробуем получить данные активов
            silo0_info["asset"] = silo0_contract.functions.asset().call()
            
            # Проверяем совпадение адреса актива с нашим токеном
            if silo0_info["asset"].lower() == token_address.lower():
                logger.info(f"Silo0 использует правильный токен: {token_address}")
            else:
                logger.warning(f"Silo0 использует другой токен: {silo0_info['asset']}, ожидался: {token_address}")
            
            # Пробуем получить общее количество активов и ликвидность
            try:
                silo0_info["totalAssets"] = silo0_contract.functions.totalAssets().call()
            except Exception as e:
                logger.warning(f"Не удалось получить totalAssets из Silo0: {str(e)}")
            
            try:
                silo0_info["getLiquidity"] = silo0_contract.functions.getLiquidity().call()
            except Exception as e:
                logger.warning(f"Не удалось получить getLiquidity из Silo0: {str(e)}")
            
            try:
                storage_data = silo0_contract.functions.getCollateralAndDebtTotalsStorage().call()
                silo0_info["collateralAssets"] = storage_data[0]
                silo0_info["debtAssets"] = storage_data[1]
            except Exception as e:
                logger.warning(f"Не удалось получить данные о коллатерале и долге из Silo0: {str(e)}")
            
        except Exception as e:
            logger.error(f"Ошибка при получении данных из Silo0: {str(e)}")
            silo0_info["error"] = str(e)
        
        # Попробуем получить базовую информацию из Silo1
        silo1_info = {}
        try:
            # Базовые функции ERC-20
            silo1_info["name"] = silo1_contract.functions.name().call()
            silo1_info["symbol"] = silo1_contract.functions.symbol().call()
            silo1_info["decimals"] = silo1_contract.functions.decimals().call()
            
            # Пробуем получить данные активов
            silo1_info["asset"] = silo1_contract.functions.asset().call()
            
            # Проверяем совпадение адреса актива с нашим токеном
            if silo1_info["asset"].lower() == token_address.lower():
                logger.info(f"Silo1 использует правильный токен: {token_address}")
            else:
                logger.warning(f"Silo1 использует другой токен: {silo1_info['asset']}, ожидался: {token_address}")
            
            # Пробуем получить общее количество активов и ликвидность
            try:
                silo1_info["totalAssets"] = silo1_contract.functions.totalAssets().call()
            except Exception as e:
                logger.warning(f"Не удалось получить totalAssets из Silo1: {str(e)}")
            
            try:
                silo1_info["getLiquidity"] = silo1_contract.functions.getLiquidity().call()
            except Exception as e:
                logger.warning(f"Не удалось получить getLiquidity из Silo1: {str(e)}")
            
            try:
                storage_data = silo1_contract.functions.getCollateralAndDebtTotalsStorage().call()
                silo1_info["collateralAssets"] = storage_data[0]
                silo1_info["debtAssets"] = storage_data[1]
            except Exception as e:
                logger.warning(f"Не удалось получить данные о коллатерале и долге из Silo1: {str(e)}")
            
        except Exception as e:
            logger.error(f"Ошибка при получении данных из Silo1: {str(e)}")
            silo1_info["error"] = str(e)
        
        # Получаем информацию о токене
        token_info = {}
        try:
            token_info["name"] = token_contract.functions.name().call()
            token_info["symbol"] = token_contract.functions.symbol().call()
            token_info["decimals"] = token_contract.functions.decimals().call()
            token_info["totalSupply"] = token_contract.functions.totalSupply().call()
        except Exception as e:
            logger.error(f"Ошибка при получении данных о токене: {str(e)}")
            token_info["error"] = str(e)
        
        # Человекочитаемые значения
        result = {
            "network": network,
            "market_id": market_id,
            "token": contract_info["token"],
            "token_address": token_address,
            "token_info": token_info,
            "silo0_address": silo0_address,
            "silo0_info": silo0_info,
            "silo1_address": silo1_address,
            "silo1_info": silo1_info,
        }
        
        # Если есть информация о decimals и totalAssets, добавим человекочитаемые значения
        if "decimals" in token_info and "error" not in token_info:
            decimals = token_info["decimals"]
            
            # Функция для перевода из wei в обычные значения
            def from_wei(value):
                if value is None:
                    return None
                return value / (10 ** decimals)
            
            # Добавляем человекочитаемые значения для silo0
            if "totalAssets" in silo0_info:
                silo0_info["totalAssets_human"] = from_wei(silo0_info["totalAssets"])
            if "getLiquidity" in silo0_info:
                silo0_info["getLiquidity_human"] = from_wei(silo0_info["getLiquidity"])
            if "collateralAssets" in silo0_info:
                silo0_info["collateralAssets_human"] = from_wei(silo0_info["collateralAssets"])
            if "debtAssets" in silo0_info:
                silo0_info["debtAssets_human"] = from_wei(silo0_info["debtAssets"])
            
            # Добавляем человекочитаемые значения для silo1
            if "totalAssets" in silo1_info:
                silo1_info["totalAssets_human"] = from_wei(silo1_info["totalAssets"])
            if "getLiquidity" in silo1_info:
                silo1_info["getLiquidity_human"] = from_wei(silo1_info["getLiquidity"])
            if "collateralAssets" in silo1_info:
                silo1_info["collateralAssets_human"] = from_wei(silo1_info["collateralAssets"])
            if "debtAssets" in silo1_info:
                silo1_info["debtAssets_human"] = from_wei(silo1_info["debtAssets"])
            
            # Добавляем человекочитаемое значение для totalSupply токена
            token_info["totalSupply_human"] = from_wei(token_info["totalSupply"])
        
        return result
    
    except Exception as e:
        logger.error(f"Ошибка при чтении базовой информации из Silo: {str(e)}", exc_info=True)
        return {"error": str(e)}

def main():
    try:
        # Параметры Silo
        network = "Sonic"
        market_id = "20"
        
        print(f"Получение базовой информации из Silo для market_id: {market_id} в сети {network}")
        
        # Получаем базовую информацию
        data = read_basic_info_from_silo(network, market_id)
        
        # Выводим результаты в консоль в формате JSON
        print("\n----- РЕЗУЛЬТАТЫ -----")
        print(json.dumps(data, indent=2))
        
        # Выводим сводку
        print("\n----- СВОДКА -----")
        print(f"Сеть: {network}")
        print(f"Market ID: {market_id}")
        print(f"Токен: {data['token']} ({data['token_address']})")
        
        if "error" not in data["token_info"]:
            print(f"\nИнформация о токене:")
            print(f"  Имя: {data['token_info']['name']}")
            print(f"  Символ: {data['token_info']['symbol']}")
            print(f"  Decimals: {data['token_info']['decimals']}")
            if "totalSupply_human" in data["token_info"]:
                print(f"  Общий запас: {data['token_info']['totalSupply_human']}")
        
        if "error" not in data["silo0_info"]:
            print(f"\nИнформация о Silo0 ({data['silo0_address']}):")
            print(f"  Имя: {data['silo0_info']['name']}")
            print(f"  Символ: {data['silo0_info']['symbol']}")
            
            # Выводим информацию о активах и ликвидности, если она доступна
            if "totalAssets_human" in data["silo0_info"]:
                print(f"  Общие активы: {data['silo0_info']['totalAssets_human']} {data['token']}")
            if "getLiquidity_human" in data["silo0_info"]:
                print(f"  Ликвидность: {data['silo0_info']['getLiquidity_human']} {data['token']}")
            if "collateralAssets_human" in data["silo0_info"] and "debtAssets_human" in data["silo0_info"]:
                collateral = data["silo0_info"]["collateralAssets_human"]
                debt = data["silo0_info"]["debtAssets_human"]
                utilization = (debt / collateral * 100) if collateral > 0 else 0
                print(f"  Коллатеральные активы: {collateral} {data['token']}")
                print(f"  Долговые активы: {debt} {data['token']}")
                print(f"  Утилизация: {utilization:.2f}%")
        
        if "error" not in data["silo1_info"]:
            print(f"\nИнформация о Silo1 ({data['silo1_address']}):")
            print(f"  Имя: {data['silo1_info']['name']}")
            print(f"  Символ: {data['silo1_info']['symbol']}")
            
            # Выводим информацию о активах и ликвидности, если она доступна
            if "totalAssets_human" in data["silo1_info"]:
                print(f"  Общие активы: {data['silo1_info']['totalAssets_human']} {data['token']}")
            if "getLiquidity_human" in data["silo1_info"]:
                print(f"  Ликвидность: {data['silo1_info']['getLiquidity_human']} {data['token']}")
            if "collateralAssets_human" in data["silo1_info"] and "debtAssets_human" in data["silo1_info"]:
                collateral = data["silo1_info"]["collateralAssets_human"]
                debt = data["silo1_info"]["debtAssets_human"]
                utilization = (debt / collateral * 100) if collateral > 0 else 0
                print(f"  Коллатеральные активы: {collateral} {data['token']}")
                print(f"  Долговые активы: {debt} {data['token']}")
                print(f"  Утилизация: {utilization:.2f}%")
        
        return 0
    except Exception as e:
        logger.error(f"Ошибка при выполнении скрипта: {str(e)}", exc_info=True)
        print(f"\nОШИБКА: {str(e)}")
        return 1

if __name__ == "__main__":
    sys.exit(main()) 