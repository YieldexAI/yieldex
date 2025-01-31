import logging
import time
from typing import Dict, List

import requests
from supabase import create_client

from src.yieldex.config import SUPABASE_KEY, SUPABASE_URL

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
WHITE_LIST_PROTOCOLS = ['aave-v3', 'aave-v2', 'lendle', 'venus-core-pool']
WHITE_LIST_TOKENS = ['USDT', 'USDC', 'DAI', 'GHO', 'AUSD', 'TUSD', 'USD₮0', "FRAX", 'LUSD']

def fetch_pools() -> List[Dict]:
    """Fetch pools data from DeFiLlama API"""
    try:
        response = requests.get("https://yields.llama.fi/pools")
        response.raise_for_status()
        data = response.json()['data']
        logger.info(f"Fetched {len(data)} pools from DeFiLlama")

        filtered_pools = [
            pool for pool in data
            if pool['project'] in WHITE_LIST_PROTOCOLS and pool['symbol'] in WHITE_LIST_TOKENS
        ]
        logger.info(f"Filtered to {len(filtered_pools)} relevant pools")

        return filtered_pools
    except Exception as e:
        logger.error(f"Error fetching pools: {e}")
        return []

def save_apy_data(pools: List[Dict]):
    """Save APY data to Supabase database"""
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
    
    supabase.table('apy_history').upsert(
        list(records.values()),
        on_conflict='pool_id,timestamp'
    ).execute()
    logger.info(f"Saved {len(records)} APY records to database")

def run_data_collection():
    """Main data collection workflow"""
    try:
        pools = fetch_pools()
        if pools:
            save_apy_data(pools)
        return pools
    except Exception as e:
        logger.critical(f"Data collection failed: {str(e)}", exc_info=True)

if __name__ == "__main__":
    run_data_collection()