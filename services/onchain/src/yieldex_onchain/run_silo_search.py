#!/usr/bin/env python3
"""
Скрипт для поиска Silo контрактов для определенного маркета.
"""

import logging
from src.onchain.protocol_fabric import SiloOperator, find_silos_for_market

# Настраиваем логирование
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

if __name__ == "__main__":
    try:
        network = "Sonic"
        market_id = "8"  # Интересует маркет 8

        print(f"Поиск Silo контрактов для маркета {market_id} в сети {network}...")

        # Находим все силосы для маркета 8
        silos = find_silos_for_market(network, market_id)

        print(f"Найдено {len(silos)} Silo контрактов:")
        for i, silo in enumerate(silos):
            token_info = silo.get("token_info", {})
            print(f"{i + 1}. Silo адрес: {silo.get('silo_address')}")
            print(f"   Токен: {token_info.get('symbol')} ({token_info.get('name')})")
            print(f"   Адрес токена: {token_info.get('address')}")

            # Если есть информация о total_assets, выводим ее
            if "total_assets" in silo:
                decimals = token_info.get("decimals", 18)
                total_assets = silo["total_assets"] / (10**decimals)
                print(f"   Общие активы: {total_assets} {token_info.get('symbol', '')}")

            print("")

    except Exception as e:
        print(f"Ошибка при тестировании: {str(e)}")
