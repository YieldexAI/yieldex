import os
from web3 import Web3
from common.config import validate_base_env_vars, logger, load_abi, RPC_URLS, BLOCK_EXPLORERS

# Contract addresses
AAVE_V3_ADDRESSES = {...}
AAVE_V2_ADDRESSES = {...}
LENDLE_POOL_ADDRESS = {...}
YIELDEX_ORACLE_ADDRESS = {...}
CURVE_POOLS = {...}
UNISWAP_V3_ROUTER = {...}

SUPPORTED_PROTOCOLS = {
    'aave-v3': AAVE_V3_ADDRESSES,
    'aave-v2': AAVE_V2_ADDRESSES,
    'lendle': LENDLE_POOL_ADDRESS,
    'yieldex-oracle': YIELDEX_ORACLE_ADDRESS,
    'curve': CURVE_POOLS,
    'uniswap-v3': UNISWAP_V3_ROUTER
}

def validate_env_vars() -> bool:
    """Validate environment variables for onchain operations"""
    if not validate_base_env_vars(require_web3=True):
        return False
    return True

def validate_rpc_connection():
    """Validate RPC connections"""
    for chain, url in RPC_URLS.items():
        try:
            w3 = Web3(Web3.HTTPProvider(url))
            if not w3.is_connected():
                logger.error(f"Failed to connect to {chain} RPC")
            else:
                logger.info(f"Successfully connected to {chain}")
        except Exception as e:
            logger.error(f"Error connecting to {chain} RPC: {str(e)}") 