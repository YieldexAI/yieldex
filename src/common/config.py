import os
from dotenv import load_dotenv
import logging
import json
from pathlib import Path
from web3 import Web3

load_dotenv()

logger = logging.getLogger(__name__)

# Базовые переменные окружения
SUPABASE_URL = os.getenv("SUPABASE_URL", "your-url")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "your-key")

# Web3 конфигурация
RPC_URLS = {
    'Polygon': os.getenv('POLYGON_RPC_URL'),
    'Mantle': os.getenv('MANTLE_RPC_URL'),
    'Ethereum': os.getenv("ETHEREUM_RPC_URL"),
    'Arbitrum': os.getenv("ARBITRUM_RPC_URL"),
    'Optimism': os.getenv("OPTIMISM_RPC_URL"),
    'Base': os.getenv("BASE_RPC_URL"),
    'Avalanche': os.getenv("AVALANCHE_RPC_URL")
}

BLOCK_EXPLORERS = {
    'Arbitrum': 'https://arbiscan.io',
    'Polygon': 'https://polygonscan.com', 
    'Optimism': 'https://optimistic.etherscan.io',
    'Mantle': 'https://explorer.mantle.xyz',
    'Base': 'https://basescan.org',
    'Ethereum': 'https://etherscan.io',
    'Avalanche': 'https://snowtrace.io'
}

# Общие функции
def load_abi(contract_name: str) -> dict:
    """Load ABI from file"""
    abi_path = Path('/app/abi') / f'{contract_name}.json'
    try:
        with open(abi_path) as f:
            return json.load(f)
    except FileNotFoundError:
        logger.error(f"ABI file not found: {contract_name}.json")
        raise
    except json.JSONDecodeError:
        logger.error(f"Invalid JSON in ABI file: {contract_name}.json")
        raise

def get_web3(chain: str) -> Web3:
    """Get Web3 instance for specified chain"""
    if chain not in RPC_URLS:
        raise ValueError(f"Unsupported chain: {chain}")
    
    url = RPC_URLS[chain]
    if not url:
        raise ValueError(f"Missing RPC URL for chain: {chain}")
    
    return Web3(Web3.HTTPProvider(url))

def validate_base_env_vars(require_web3: bool = False) -> bool:
    """
    Validate base environment variables
    Args:
        require_web3: If True, also validate RPC URLs
    """
    required_vars = [
        'SUPABASE_URL',
        'SUPABASE_KEY'
    ]
    
    if require_web3:
        missing_rpcs = [chain for chain, url in RPC_URLS.items() if not url]
        if missing_rpcs:
            logger.error(f"Missing RPC URLs for chains: {', '.join(missing_rpcs)}")
            return False
    
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    if missing_vars:
        logger.error(f"Missing required environment variables: {', '.join(missing_vars)}")
        return False
    
    return True 