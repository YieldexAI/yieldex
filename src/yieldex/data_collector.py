import logging
import time
from typing import Dict, List
import os
from datetime import datetime
import sys

import requests
from supabase import create_client

from src.yieldex.config import SUPABASE_KEY, SUPABASE_URL, validate_env_vars

# Configure logging
LOG_DIR = "logs"
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

# Формируем имя файла лога с текущей датой
log_filename = os.path.join(LOG_DIR, f"collector_{datetime.now().strftime('%Y%m%d')}.log")

# Настраиваем форматирование логов
log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
formatter = logging.Formatter(log_format)

# Создаем logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Очищаем существующие handlers
logger.handlers = []

# Handler для файла
file_handler = logging.FileHandler(log_filename)
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

# Handler для консоли
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

# Отключаем propagation логов, чтобы избежать дублирования
logger.propagate = False

# Получаем списки из переменных окружения
WHITE_LIST_PROTOCOLS = os.getenv('WHITE_LIST_PROTOCOLS', 'aave-v3,aave-v2,lendle,venus-core-pool').split(',')
WHITE_LIST_TOKENS = os.getenv('WHITE_LIST_TOKENS', 'USDT,USDC,DAI,GHO,AUSD,TUSD,USD₮0,FRAX,LUSD').split(',')

def fetch_pools() -> List[Dict]:
    """Fetch pools data from DeFiLlama API"""
    try:
        logger.info("Starting to fetch pools from DeFiLlama API...")
        response = requests.get("https://yields.llama.fi/pools")
        response.raise_for_status()
        data = response.json()['data']
        logger.info(f"Successfully fetched {len(data)} pools from DeFiLlama")

        filtered_pools = [
            pool for pool in data
            if pool['project'] in WHITE_LIST_PROTOCOLS and pool['symbol'] in WHITE_LIST_TOKENS
        ]
        
        # Добавляем детальное логирование найденных пулов
        logger.info(f"Filtered to {len(filtered_pools)} relevant pools")
        for pool in filtered_pools:
            logger.info(f"Found pool: {pool['symbol']} on {pool['chain']} in {pool['project']} "
                       f"(APY: {pool['apy']:.2f}%, TVL: ${pool['tvlUsd']:,.2f})")

        return filtered_pools
    except requests.RequestException as e:
        logger.error(f"Network error while fetching pools: {e}")
        return []
    except Exception as e:
        logger.error(f"Unexpected error while fetching pools: {e}", exc_info=True)
        return []

def save_apy_data(pools: List[Dict]):
    """Save APY data to Supabase database"""
    try:
        logger.info("Connecting to Supabase...")
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        
        records = {}
        current_time = int(time.time())
        
        for pool in pools:
            base_id = f"{pool['symbol']}_{pool['chain']}_{pool['project']}"
            pool_id = f"{base_id}_{pool['poolMeta']}" if pool.get('poolMeta') else base_id
            
            records[pool_id] = {
                "pool_id": pool_id,
                "asset": pool['symbol'],
                "chain": pool['chain'],
                "apy": pool['apy'],
                "tvl": pool['tvlUsd'],
                "timestamp": current_time
            }
            logger.debug(f"Prepared record for {pool_id}")
        
        logger.info(f"Attempting to save {len(records)} records to database...")
        supabase.table('apy_history').upsert(
            list(records.values()),
            on_conflict='pool_id,timestamp'
        ).execute()
        logger.info(f"Successfully saved {len(records)} APY records to database")
        
    except Exception as e:
        logger.error(f"Failed to save data to Supabase: {e}", exc_info=True)
        raise

def run_data_collection():
    """Main data collection workflow"""
    logger.info(f"Starting data collector with protocols: {WHITE_LIST_PROTOCOLS}")
    logger.info(f"Monitoring tokens: {WHITE_LIST_TOKENS}")
    
    try:
        # Проверяем конфигурацию перед запуском
        if not validate_env_vars():
            logger.error("Cannot start data collection: missing required configuration")
            return None

        pools = fetch_pools()
        if pools:
            save_apy_data(pools)
            logger.info("Data collection cycle completed successfully")
        else:
            logger.warning("No pools were fetched, skipping database update")
        return pools
    except Exception as e:
        logger.critical(f"Data collection failed: {str(e)}", exc_info=True)
        return None

if __name__ == "__main__":
    run_data_collection()