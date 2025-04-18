import json
import logging
import os
import sys
import time
from datetime import datetime
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import Dict, List, Optional, TypedDict, Union, Any

import requests
from supabase import create_client, Client
from yieldex_data_collector.config import (
    get_filter_lists,
    load_config,
    validate_env_vars,
)

# ----- parameters from env -----
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_TO_FILE: bool = os.getenv("LOG_TO_FILE", "false").lower() in {"1", "true", "yes"}
LOG_DIR: Path = Path(os.getenv("LOG_DIR", "/app/logs"))

# ----- base format -----
LOG_FMT: str = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"
DATE_FMT: str = "%Y-%m-%d %H:%M:%S"

logger: logging.Logger = logging.getLogger("yieldex.data_collector")
logger.setLevel(LOG_LEVEL)
logger.handlers.clear()  # in case of reinitialisation
logger.propagate = False

# ----- stdout (main for container) -----
console: logging.StreamHandler = logging.StreamHandler(sys.stdout)
console.setFormatter(logging.Formatter(LOG_FMT, DATE_FMT))
logger.addHandler(console)

# ----- file with rotation (optional) -----
if LOG_TO_FILE:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    file_handler: TimedRotatingFileHandler = TimedRotatingFileHandler(
        LOG_DIR / "collector.log",
        when="midnight",  # each day new file
        backupCount=7,  # keep one week
        encoding="utf-8",
    )
    file_handler.setFormatter(logging.Formatter(LOG_FMT, DATE_FMT))
    logger.addHandler(file_handler)

# ----- ready -----
logger.info("Logger initialised (level=%s, file=%s)", LOG_LEVEL, LOG_TO_FILE)


class PoolData(TypedDict):
    symbol: str
    chain: str
    project: str
    apy: float
    tvlUsd: float
    poolMeta: Optional[str]
    apyBase: Optional[float]
    apyReward: Optional[float]
    apyMean30d: Optional[float]
    apyPct1D: Optional[float]
    apyPct7D: Optional[float]
    apyPct30D: Optional[float]


class ApyRecord(TypedDict):
    pool_id: str
    asset: str
    chain: str
    apy: float
    tvl: float
    timestamp: int
    apy_base: float
    apy_reward: float
    apy_mean_30d: float
    apy_change_1d: float
    apy_change_7d: float
    apy_change_30d: float
    data_source: str


def fetch_pools() -> List[PoolData]:
    """Fetch pools data from DeFiLlama API"""
    try:
        logger.info("Starting to fetch pools from DeFiLlama API...")
        response: requests.Response = requests.get("https://yields.llama.fi/pools")
        response.raise_for_status()
        data: List[PoolData] = response.json()["data"]
        logger.info(f"Successfully fetched {len(data)} pools from DeFiLlama")

        filter_lists: Dict[str, Dict[str, List[str]]] = get_filter_lists()
        filtered_pools: List[PoolData] = [
            pool for pool in data 
            if pool["symbol"] in filter_lists["white_list"]["tokens"] 
            and pool["project"] not in filter_lists["black_list"]["protocols"]
        ]

        # Add detailed logging for found pools
        logger.info(f"Filtered to {len(filtered_pools)} relevant pools")
        for pool in filtered_pools:
            logger.info(
                f"Found pool: {pool['symbol']} on {pool['chain']} in {pool['project']} "
                f"(APY: {pool['apy']:.2f}%, TVL: ${pool['tvlUsd']:,.2f})"
            )
        return filtered_pools
    except requests.RequestException as e:
        logger.error(f"Network error while fetching pools: {e}")
        return []
    except Exception as e:
        logger.error(f"Unexpected error while fetching pools: {e}", exc_info=True)
        return []


def save_apy_data(pools: List[PoolData], config: Dict[str, Any]) -> None:
    """Save APY data to Supabase database"""
    try:
        logger.info("Connecting to Supabase...")
        supabase: Client = create_client(config["supabase"]["url"], config["supabase"]["key"])

        records: Dict[str, ApyRecord] = {}
        current_time: int = int(time.time())

        for pool in pools:
            base_id: str = f"{pool['symbol']}_{pool['chain']}_{pool['project']}"
            pool_id: str = (
                f"{base_id}_{pool['poolMeta']}" if pool.get("poolMeta") else base_id
            )

            record: ApyRecord = {
                "pool_id": pool_id,
                "asset": pool["symbol"],
                "chain": pool["chain"],
                "apy": pool.get("apy", 0),
                "tvl": pool.get("tvlUsd", 0),
                "timestamp": current_time,
                "apy_base": pool.get("apyBase", 0),
                "apy_reward": pool.get("apyReward", 0),
                "apy_mean_30d": pool.get("apyMean30d", 0),
                "apy_change_1d": pool.get("apyPct1D", 0),
                "apy_change_7d": pool.get("apyPct7D", 0),
                "apy_change_30d": pool.get("apyPct30D", 0),
                "data_source": "Defillama",
            }

            records[pool_id] = record
            logger.debug(f"Prepared record for {pool_id}")

        logger.info(f"Attempting to save {len(records)} records to database...")
        supabase.table("apy_history").upsert(
            list(records.values()), on_conflict="pool_id,timestamp"
        ).execute()
        logger.info(f"Successfully saved {len(records)} APY records to database")

    except Exception as e:
        logger.error(f"Failed to save data to Supabase: {e}", exc_info=True)
        raise


def run_data_collection() -> Optional[int]:
    """Main data collection workflow"""
    try:
        if not validate_env_vars():
            logger.error("Cannot start data collection: missing required configuration")
            return None
        config: Dict[str, Any] = load_config()
        logger.info(
            f"Starting data collector with protocols: {config['white_list']['protocols']}"
        )
        logger.info(f"Monitoring tokens: {config['white_list']['tokens']}")

        pools: List[PoolData] = fetch_pools()
        if pools:
            save_apy_data(pools, config)
            logger.info("Data collection cycle completed successfully")
        else:
            logger.warning("No pools were fetched, skipping database update")
        return len(pools)
    except Exception as e:
        logger.critical(f"Data collection failed: {str(e)}", exc_info=True)
        return None


if __name__ == "__main__":
    logger.info("Starting data collection cycle...")
    run_data_collection()
