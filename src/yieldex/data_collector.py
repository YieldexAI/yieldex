import logging
import time
from typing import Dict, List

import requests
from supabase import create_client
from web3 import Web3

from src.yieldex.config import (MANTLE_RPC_URL, PRIVATE_KEY, SUPABASE_KEY,
                                SUPABASE_URL, YIELDEX_ORACLE_ABI,
                                YIELDEX_ORACLE_ADDRESS)
from src.yieldex.protocol_fabric import YieldexOracleOperator

from .analytics import analyze_apy_differences, get_recommendations
from .notifications import TelegramNotifier, send_telegram_alert

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
WHITE_LIST_PROTOCOLS = ['aave-v3', 'aave-v2', 'lendle']
WHITE_LIST_TOKENS = ['USDT', 'USDC', 'DAI', 'GHO', 'AUSD']
# SUPPORTED_CHAINS = ['Polygon', 'Arbitrum', 'Optimism', 'Base', 'Avalanche', 'Ethereum']

def fetch_aave_pools() -> List[Dict]:
    """Fetch AAVE v3 pools data from DeFiLlama API"""
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
        logger.error(f"Error fetching AAVE pools: {e}")
        return []

def save_apy_data(pools: List[Dict]):
    """
    Save historical APY data with timestamp, then update multiple APYs in the
    YieldexOracleOperator on Mantle with all records (ignoring
    the chain name).
    """
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    
    records = {}
    current_time = int(time.time())
    
    # 1) Gather records
    for pool in pools:
        base_id = f"{pool['symbol']}_{pool['chain']}_{pool['project']}"
        pool_id = f"{base_id}_{pool['poolMeta']}" if pool.get('poolMeta') else base_id
        
        records[pool_id] = {
            "pool_id": pool_id,
            "asset": pool['symbol'],
            "chain": pool['chain'],
            "apy": pool['apy'],
            "timestamp": current_time
        }
    
    # 2) Write records to Supabase
    supabase.table('apy_history').upsert(
        list(records.values()),
        on_conflict='pool_id,timestamp'
    ).execute()
    
    # 3) Regardless of chain, update them all on Mantle

    pool_ids = [r["pool_id"] for r in records.values()]
    apys = [r["apy"] for r in records.values()]
    
    try:
        oracle = YieldexOracleOperator("Mantle")
        tx_hash = oracle.update_multiple_apys(pool_ids, apys)
        if tx_hash:
            logger.info(f"Mantle: Updated {len(pool_ids)} APYs in the Yieldex Oracle, tx hash={tx_hash}")
        else:
            logger.warning("Mantle: update_multiple_apys call returned None or failed")
    except Exception as e:
        logger.error(f"Error updating Mantle oracle: {str(e)}")

def save_my_pool_balance(pool_id: str, balance: float):
    """Save or update balance of my funds in specific pool"""
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    
    record = {
        "pool_id": pool_id,
        "balance": balance,  # My pool balance in USD
        "timestamp": int(time.time())
    }
    
    try:
        response = supabase.table('pool_balances').upsert(
            [record],
            on_conflict='pool_id'  # Update existing record if exists
        ).execute()
        logger.info(f"Successfully updated balance for pool {pool_id}")
        return True
    except Exception as e:
        logger.error(f"Error saving pool balance: {e}")
        return False

if __name__ == "__main__":
    try:
        pools = fetch_aave_pools()
        if pools:
            save_apy_data(pools)
            
            # Get recommendations based on current positions
            recommendations = get_recommendations(min_profit=0.7)  # Filter 0.7%
            
            if recommendations:
                notifier = TelegramNotifier()
                success = notifier.send_alert(recommendations)
                
                if not success:
                    logger.error("Failed to send Telegram notification")
    except Exception as e:
        logger.critical(f"Critical error: {str(e)}", exc_info=True)