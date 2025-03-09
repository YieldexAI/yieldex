#!/usr/bin/env python3
"""
Скрипт для взаимодействия с SiloFactory контрактом на Sonic.
Позволяет динамически получать адреса Silo для любого маркета.
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

# Адрес SiloFactory на Sonic
SILO_FACTORY_ADDRESS = "0xa42001D6d2237d2c74108FE360403C4b796B7170"

# Конфигурация для Silo контрактов (для примера)
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

# Стейблкоины на Sonic
STABLECOINS = {
    "USDC.E": "0xF319945907d66fA17AD5d4D622F9Ab8e5D5bAd29",
    "USDC": "0x29219dd400f2Bf60E5a23d13Be72B486D4038894"  # Это адрес, который мы получили ранее
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

def create_minimal_factory_abi():
    """Создаем минимальный ABI для SiloFactory, если файл не существует"""
    # Проверяем, существует ли уже файл
    factory_abi_path = ABI_DIR / "SiloFactory.json"
    if factory_abi_path.exists():
        logger.info(f"Используем существующий ABI-файл: {factory_abi_path}")
        with open(factory_abi_path) as f:
            return json.load(f)
    
    # Если файл не существует, создаем минимальный ABI
    minimal_abi = [
        {
            "inputs": [
                {"internalType": "address", "name": "silo", "type": "address"}
            ],
            "name": "isSilo",
            "outputs": [
                {"internalType": "bool", "name": "", "type": "bool"}
            ],
            "stateMutability": "view",
            "type": "function"
        },
        {
            "inputs": [
                {"internalType": "uint256", "name": "id", "type": "uint256"}
            ],
            "name": "idToSiloConfig",
            "outputs": [
                {"internalType": "address", "name": "siloConfig", "type": "address"}
            ],
            "stateMutability": "view",
            "type": "function"
        },
        {
            "inputs": [
                {"internalType": "address", "name": "_silo", "type": "address"}
            ],
            "name": "getFeeReceivers",
            "outputs": [
                {"internalType": "address", "name": "dao", "type": "address"},
                {"internalType": "address", "name": "deployer", "type": "address"}
            ],
            "stateMutability": "view",
            "type": "function"
        },
        {
            "inputs": [],
            "name": "getNextSiloId",
            "outputs": [
                {"internalType": "uint256", "name": "", "type": "uint256"}
            ],
            "stateMutability": "view",
            "type": "function"
        }
    ]
    
    # Сохраняем ABI в файл
    factory_abi_path = ABI_DIR / "SiloFactory.json"
    if not factory_abi_path.exists():
        os.makedirs(os.path.dirname(factory_abi_path), exist_ok=True)
        with open(factory_abi_path, 'w') as f:
            json.dump(minimal_abi, f, indent=2)
        logger.info(f"Создан файл с минимальным ABI для SiloFactory: {factory_abi_path}")
    
    return minimal_abi

def create_minimal_erc20_abi():
    """Создаем минимальный ABI для ERC20, если файл не существует"""
    minimal_abi = [
        {
            "constant": True,
            "inputs": [],
            "name": "name",
            "outputs": [{"name": "", "type": "string"}],
            "payable": False,
            "stateMutability": "view",
            "type": "function"
        },
        {
            "constant": True,
            "inputs": [],
            "name": "symbol",
            "outputs": [{"name": "", "type": "string"}],
            "payable": False,
            "stateMutability": "view",
            "type": "function"
        },
        {
            "constant": True,
            "inputs": [],
            "name": "decimals",
            "outputs": [{"name": "", "type": "uint8"}],
            "payable": False,
            "stateMutability": "view",
            "type": "function"
        },
        {
            "constant": True,
            "inputs": [{"name": "owner", "type": "address"}],
            "name": "balanceOf",
            "outputs": [{"name": "", "type": "uint256"}],
            "payable": False,
            "stateMutability": "view",
            "type": "function"
        },
        {
            "constant": True,
            "inputs": [],
            "name": "totalSupply",
            "outputs": [{"name": "", "type": "uint256"}],
            "payable": False,
            "stateMutability": "view",
            "type": "function"
        }
    ]
    
    # Сохраняем ABI в файл
    erc20_abi_path = ABI_DIR / "ERC20.json"
    if not erc20_abi_path.exists():
        os.makedirs(os.path.dirname(erc20_abi_path), exist_ok=True)
        with open(erc20_abi_path, 'w') as f:
            json.dump(minimal_abi, f, indent=2)
        logger.info(f"Создан файл с минимальным ABI для ERC20: {erc20_abi_path}")
    
    return minimal_abi

def create_minimal_silo_abi():
    """Создаем минимальный ABI для Silo, если файл не существует"""
    minimal_abi = [
        {
            "inputs": [],
            "name": "name",
            "outputs": [{"internalType": "string", "name": "", "type": "string"}],
            "stateMutability": "view",
            "type": "function"
        },
        {
            "inputs": [],
            "name": "symbol",
            "outputs": [{"internalType": "string", "name": "", "type": "string"}],
            "stateMutability": "view",
            "type": "function"
        },
        {
            "inputs": [],
            "name": "decimals",
            "outputs": [{"internalType": "uint8", "name": "", "type": "uint8"}],
            "stateMutability": "view",
            "type": "function"
        },
        {
            "inputs": [],
            "name": "asset",
            "outputs": [{"internalType": "address", "name": "assetTokenAddress", "type": "address"}],
            "stateMutability": "view",
            "type": "function"
        },
        {
            "inputs": [],
            "name": "totalAssets",
            "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
            "stateMutability": "view",
            "type": "function"
        },
        {
            "inputs": [],
            "name": "getLiquidity",
            "outputs": [{"internalType": "uint256", "name": "liquidity", "type": "uint256"}],
            "stateMutability": "view",
            "type": "function"
        },
        {
            "inputs": [],
            "name": "getCollateralAndDebtTotalsStorage",
            "outputs": [
                {"internalType": "uint256", "name": "totalCollateralAssets", "type": "uint256"},
                {"internalType": "uint256", "name": "totalDebtAssets", "type": "uint256"}
            ],
            "stateMutability": "view",
            "type": "function"
        }
    ]
    
    # Сохраняем ABI в файл
    silo_abi_path = ABI_DIR / "Silo.json"
    if not silo_abi_path.exists():
        os.makedirs(os.path.dirname(silo_abi_path), exist_ok=True)
        with open(silo_abi_path, 'w') as f:
            json.dump(minimal_abi, f, indent=2)
        logger.info(f"Создан файл с минимальным ABI для Silo: {silo_abi_path}")
    
    return minimal_abi

def load_abis():
    """Загружаем или создаем необходимые ABI файлы"""
    factory_abi = create_minimal_factory_abi()
    erc20_abi = create_minimal_erc20_abi()
    silo_abi = create_minimal_silo_abi()
    
    return {
        "factory": factory_abi,
        "erc20": erc20_abi,
        "silo": silo_abi
    }

def query_silo_factory(network: str):
    """
    Запрашивает информацию из SiloFactory
    """
    try:
        logger.info(f"Запрашиваем информацию из SiloFactory на сети {network}")
        
        # Получаем Web3 подключение
        w3 = get_web3_connection(network)
        
        # Загружаем ABI
        abis = load_abis()
        
        # Создаем контракт SiloFactory
        factory_address = w3.to_checksum_address(SILO_FACTORY_ADDRESS)
        factory = w3.eth.contract(address=factory_address, abi=abis["factory"])
        
        # Получаем следующий Silo ID
        try:
            next_silo_id = factory.functions.getNextSiloId().call()
            logger.info(f"Следующий Silo ID: {next_silo_id}")
            
            # Проверяем известные нам Silo контракты
            markets_info = []
            
            # Для интересующих нас маркетов
            market_addresses = [
                "0x062A36Bbe0306c2Fd7aecdf25843291fBAB96AD2",  # Market 20
                # Другие маркеты...
            ]
            
            # Проверяем, является ли этот адрес Silo
            for market_address in market_addresses:
                try:
                    is_silo = factory.functions.isSilo(w3.to_checksum_address(market_address)).call()
                    logger.info(f"Адрес {market_address} является Silo: {is_silo}")
                    
                    if is_silo:
                        # Если это Silo, получаем информацию о нем
                        fee_receivers = factory.functions.getFeeReceivers(w3.to_checksum_address(market_address)).call()
                        dao_fee_receiver = fee_receivers[0]
                        deployer_fee_receiver = fee_receivers[1]
                        
                        logger.info(f"Получатель DAO комиссии: {dao_fee_receiver}")
                        logger.info(f"Получатель комиссии разработчика: {deployer_fee_receiver}")
                except Exception as e:
                    logger.warning(f"Не удалось проверить, является ли {market_address} Silo: {str(e)}")
            
            # Проверяем сами Silo из известной нам конфигурации
            for network_key, markets in SILO_CONFIG.items():
                if network_key != network:
                    continue
                
                for market_key, market_info in markets.items():
                    silo0_address = market_info.get("silo0_address")
                    silo1_address = market_info.get("silo1_address")
                    
                    # Проверяем Silo0
                    if silo0_address:
                        try:
                            is_silo = factory.functions.isSilo(w3.to_checksum_address(silo0_address)).call()
                            logger.info(f"Silo0 {silo0_address} является Silo: {is_silo}")
                            
                            if is_silo:
                                # Если это Silo, получаем информацию о нем
                                fee_receivers = factory.functions.getFeeReceivers(w3.to_checksum_address(silo0_address)).call()
                                dao_fee_receiver = fee_receivers[0]
                                deployer_fee_receiver = fee_receivers[1]
                                
                                logger.info(f"Получатель DAO комиссии для Silo0: {dao_fee_receiver}")
                                logger.info(f"Получатель комиссии разработчика для Silo0: {deployer_fee_receiver}")
                        except Exception as e:
                            logger.warning(f"Не удалось проверить, является ли Silo0 {silo0_address} Silo: {str(e)}")
                    
                    # Проверяем Silo1
                    if silo1_address:
                        try:
                            is_silo = factory.functions.isSilo(w3.to_checksum_address(silo1_address)).call()
                            logger.info(f"Silo1 {silo1_address} является Silo: {is_silo}")
                            
                            if is_silo:
                                # Если это Silo, получаем информацию о нем
                                fee_receivers = factory.functions.getFeeReceivers(w3.to_checksum_address(silo1_address)).call()
                                dao_fee_receiver = fee_receivers[0]
                                deployer_fee_receiver = fee_receivers[1]
                                
                                logger.info(f"Получатель DAO комиссии для Silo1: {dao_fee_receiver}")
                                logger.info(f"Получатель комиссии разработчика для Silo1: {deployer_fee_receiver}")
                        except Exception as e:
                            logger.warning(f"Не удалось проверить, является ли Silo1 {silo1_address} Silo: {str(e)}")
            
            # Проверяем конфигурацию Silo для известных ID
            silo_configs = {}
            for i in range(1, 30):  # Проверяем первые 30 ID для примера
                try:
                    config_address = factory.functions.idToSiloConfig(i).call()
                    if config_address and config_address != "0x0000000000000000000000000000000000000000":
                        logger.info(f"SiloConfig для ID {i}: {config_address}")
                        silo_configs[i] = config_address
                except Exception as e:
                    logger.debug(f"Не удалось получить SiloConfig для ID {i}: {str(e)}")
            
            return {
                "factory_address": factory_address,
                "next_silo_id": next_silo_id,
                "silo_configs": silo_configs
            }
            
        except Exception as e:
            logger.error(f"Ошибка при запросе к SiloFactory: {str(e)}")
            return {
                "factory_address": factory_address,
                "error": str(e)
            }
    
    except Exception as e:
        logger.error(f"Ошибка при запросе к SiloFactory: {str(e)}", exc_info=True)
        return {"error": str(e)}

def query_silos_for_market(network: str, market_id: str):
    """
    Получает информацию о Silo для указанного маркета
    """
    try:
        logger.info(f"Запрашиваем информацию для маркета {market_id} на сети {network}")
        
        # Получаем Web3 подключение
        w3 = get_web3_connection(network)
        
        # Загружаем ABI
        abis = load_abis()
        
        # Получаем адрес маркета в правильном формате
        market_address = None
        
        if market_id.lower().startswith("0x") and len(market_id) == 42:
            # Если это адрес в формате 0x..., используем его напрямую
            market_address = w3.to_checksum_address(market_id)
        else:
            # Если это числовой ID, пробуем получить адрес из конфигурации
            market_key = f"Market_{market_id}"
            if network in SILO_CONFIG and market_key in SILO_CONFIG[network]:
                market_address = SILO_CONFIG[network][market_key]["market_address"]
                market_address = w3.to_checksum_address(market_address)
        
        if not market_address:
            raise ValueError(f"Не удалось определить адрес маркета для {market_id}")
        
        logger.info(f"Используем адрес маркета: {market_address}")
        
        # Здесь мы знаем, что для Market 20:
        # silo0_address = "0xf55902DE87Bd80c6a35614b48d7f8B612a083C12"
        # silo1_address = "0x322e1d5384aa4ED66AeCa770B95686271de61dc3"
        
        # Используем адреса из конфигурации
        market_key = f"Market_{market_id}"
        if network in SILO_CONFIG and market_key in SILO_CONFIG[network]:
            silo0_address = SILO_CONFIG[network][market_key]["silo0_address"]
            silo1_address = SILO_CONFIG[network][market_key]["silo1_address"]
            
            # Проверяем, являются ли эти адреса Silo
            try:
                # Создаем контракт SiloFactory
                factory_address = w3.to_checksum_address(SILO_FACTORY_ADDRESS)
                factory = w3.eth.contract(address=factory_address, abi=abis["factory"])
                
                # Проверяем Silo0
                is_silo0 = factory.functions.isSilo(w3.to_checksum_address(silo0_address)).call()
                logger.info(f"Silo0 {silo0_address} является Silo: {is_silo0}")
                
                # Проверяем Silo1
                is_silo1 = factory.functions.isSilo(w3.to_checksum_address(silo1_address)).call()
                logger.info(f"Silo1 {silo1_address} является Silo: {is_silo1}")
                
            except Exception as e:
                logger.warning(f"Не удалось проверить, являются ли адреса Silo: {str(e)}")
            
            # Получаем информацию о токенах
            silo0_token = get_token_info(w3, silo0_address, abis)
            silo1_token = get_token_info(w3, silo1_address, abis)
            
            return {
                "market_id": market_id,
                "market_address": market_address,
                "silo0_address": silo0_address,
                "silo1_address": silo1_address,
                "silo0_token": silo0_token,
                "silo1_token": silo1_token
            }
        else:
            raise ValueError(f"Информация о маркете {market_id} не найдена в конфигурации")
            
    except Exception as e:
        logger.error(f"Ошибка при запросе информации о маркете {market_id}: {str(e)}", exc_info=True)
        return {"error": str(e)}

def get_token_info(w3, silo_address: str, abis: Dict):
    """
    Получает информацию о токене из Silo контракта
    """
    try:
        # Создаем контракт Silo
        silo = w3.eth.contract(address=w3.to_checksum_address(silo_address), abi=abis["silo"])
        
        # Получаем адрес токена
        token_address = silo.functions.asset().call()
        
        # Создаем контракт токена
        token = w3.eth.contract(address=w3.to_checksum_address(token_address), abi=abis["erc20"])
        
        # Получаем информацию о токене
        try:
            name = token.functions.name().call()
        except:
            name = "Unknown"
        
        try:
            symbol = token.functions.symbol().call()
        except:
            symbol = "Unknown"
        
        try:
            decimals = token.functions.decimals().call()
        except:
            decimals = 18
        
        # Получаем информацию о Silo
        try:
            silo_name = silo.functions.name().call()
        except:
            silo_name = "Unknown"
        
        try:
            silo_symbol = silo.functions.symbol().call()
        except:
            silo_symbol = "Unknown"
        
        return {
            "address": token_address,
            "name": name,
            "symbol": symbol,
            "decimals": decimals,
            "silo_name": silo_name,
            "silo_symbol": silo_symbol
        }
    except Exception as e:
        logger.warning(f"Не удалось получить информацию о токене для Silo {silo_address}: {str(e)}")
        return {
            "address": None,
            "error": str(e)
        }

def find_silo_for_token(network: str, market_id: str, token_symbol: str):
    """
    Находит подходящий Silo для указанного токена
    """
    try:
        logger.info(f"Ищем Silo для токена {token_symbol} в маркете {market_id}")
        
        # Получаем информацию о маркете
        market_info = query_silos_for_market(network, market_id)
        
        if "error" in market_info:
            raise ValueError(f"Не удалось получить информацию о маркете: {market_info['error']}")
        
        # Проверяем символы токенов в Silo0 и Silo1
        silo0_token = market_info["silo0_token"]
        silo1_token = market_info["silo1_token"]
        
        logger.info(f"Токен в Silo0: {silo0_token.get('symbol', 'Unknown')}")
        logger.info(f"Токен в Silo1: {silo1_token.get('symbol', 'Unknown')}")
        
        # Находим подходящий Silo
        if token_symbol.lower() in silo0_token.get("symbol", "").lower():
            logger.info(f"Токен {token_symbol} найден в Silo0")
            return {
                "silo_address": market_info["silo0_address"],
                "token_address": silo0_token["address"],
                "token_info": silo0_token
            }
        elif token_symbol.lower() in silo1_token.get("symbol", "").lower():
            logger.info(f"Токен {token_symbol} найден в Silo1")
            return {
                "silo_address": market_info["silo1_address"],
                "token_address": silo1_token["address"],
                "token_info": silo1_token
            }
        else:
            # Не нашли точное совпадение по символу, попробуем по имени
            if token_symbol.lower() in silo0_token.get("name", "").lower():
                logger.info(f"Токен {token_symbol} найден в имени Silo0")
                return {
                    "silo_address": market_info["silo0_address"],
                    "token_address": silo0_token["address"],
                    "token_info": silo0_token
                }
            elif token_symbol.lower() in silo1_token.get("name", "").lower():
                logger.info(f"Токен {token_symbol} найден в имени Silo1")
                return {
                    "silo_address": market_info["silo1_address"],
                    "token_address": silo1_token["address"],
                    "token_info": silo1_token
                }
            else:
                # Последняя попытка - по имени Silo
                if token_symbol.lower() in silo0_token.get("silo_name", "").lower() or token_symbol.lower() in silo0_token.get("silo_symbol", "").lower():
                    logger.info(f"Токен {token_symbol} найден в имени или символе Silo0")
                    return {
                        "silo_address": market_info["silo0_address"],
                        "token_address": silo0_token["address"],
                        "token_info": silo0_token
                    }
                elif token_symbol.lower() in silo1_token.get("silo_name", "").lower() or token_symbol.lower() in silo1_token.get("silo_symbol", "").lower():
                    logger.info(f"Токен {token_symbol} найден в имени или символе Silo1")
                    return {
                        "silo_address": market_info["silo1_address"],
                        "token_address": silo1_token["address"],
                        "token_info": silo1_token
                    }
                else:
                    raise ValueError(f"Токен {token_symbol} не найден ни в одном из Silo маркета {market_id}")
    
    except Exception as e:
        logger.error(f"Ошибка при поиске Silo для токена {token_symbol}: {str(e)}", exc_info=True)
        return {"error": str(e)}

def main():
    try:
        # Параметры Silo
        network = "Sonic"
        market_id = "8"  # Или адрес маркета: "0x062A36Bbe0306c2Fd7aecdf25843291fBAB96AD2"
        token_symbol = "USDC.E"  # Токен, для которого ищем Silo
        
        print(f"Получение информации о маркете {market_id} на сети {network}")
        
        # # Получаем информацию о фабрике
        # print("\n----- ИНФОРМАЦИЯ О ФАБРИКЕ -----")
        # factory_info = query_silo_factory(network)
        # print(json.dumps(factory_info, indent=2))


        
        # Получаем информацию о конкретном маркете
        print(f"\n----- ИНФОРМАЦИЯ О МАРКЕТЕ {market_id} -----")
        market_info = query_silos_for_market(network, market_id)
        print(json.dumps(market_info, indent=2))


    except Exception as e:
        logger.error(f"Ошибка при выполнении скрипта: {str(e)}", exc_info=True)
        print(f"\nОШИБКА: {str(e)}")
        return 1
        
        # # Находим подходящий Silo для токена
        # print(f"\n----- ПОИСК SILO ДЛЯ ТОКЕНА {token_symbol} -----")
        # silo_info = find_silo_for_token(network, market_id, token_symbol)
        # print(json.dumps(silo_info, indent=2))
        
    #     # Выводим итоговую информацию
    #     print("\n----- ИТОГОВАЯ ИНФОРМАЦИЯ -----")
    #     if "error" not in silo_info:
    #         print(f"Для депозита токена {token_symbol} в маркет {market_id} используйте:")
    #         print(f"Silo адрес: {silo_info['silo_address']}")
    #         print(f"Токен адрес: {silo_info['token_address']}")
    #         print(f"Токен символ: {silo_info['token_info'].get('symbol', 'Unknown')}")
    #         print(f"Токен имя: {silo_info['token_info'].get('name', 'Unknown')}")
    #         print(f"Токен decimals: {silo_info['token_info'].get('decimals', 18)}")
    #     else:
    #         print(f"Ошибка: {silo_info['error']}")
        
    #     return 0
    # except Exception as e:
    #     logger.error(f"Ошибка при выполнении скрипта: {str(e)}", exc_info=True)
    #     print(f"\nОШИБКА: {str(e)}")
    #     return 1

if __name__ == "__main__":
    sys.exit(main()) 