import os
from dotenv import load_dotenv
import logging
from web3 import Web3
# from moccasin import NetworkConfig

load_dotenv()

logger = logging.getLogger(__name__)

# Block explorers configuration
BLOCK_EXPLORERS = {
    'Arbitrum': 'https://arbiscan.io',
    'Polygon': 'https://polygonscan.com', 
    'Optimism': 'https://optimistic.etherscan.io',
    'Mantle': 'https://explorer.mantle.xyz',
    'Base': 'https://basescan.org',
    'Ethereum': 'https://etherscan.io',
    'Avalanche': 'https://snowtrace.io'
}

# RPC URLs for different networks
RPC_URLS = {
    'Polygon': os.getenv('POLYGON_RPC_URL'),
    'Mantle': os.getenv('MANTLE_RPC_URL'),
    'Ethereum': os.getenv("ETHEREUM_RPC_URL"),
    'Arbitrum': os.getenv("ARBITRUM_RPC_URL"),
    'Optimism': os.getenv("OPTIMISM_RPC_URL"),
    'Base': os.getenv("BASE_RPC_URL"),
    'Avalanche': os.getenv("AVALANCHE_RPC_URL")
}


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

# Validate required environment variables
def validate_env_vars():
    required_vars = {
        'SUPABASE_URL': os.getenv('SUPABASE_URL'),
        'SUPABASE_KEY': os.getenv('SUPABASE_KEY'),
        'RPC_URLs': {
            'Polygon': os.getenv('POLYGON_RPC_URL'),
            'Mantle': os.getenv('MANTLE_RPC_URL'),
            'Ethereum': os.getenv('ETHEREUM_RPC_URL'),
            'Arbitrum': os.getenv('ARBITRUM_RPC_URL'),
            'Optimism': os.getenv('OPTIMISM_RPC_URL'),
            'Base': os.getenv('BASE_RPC_URL'),
            'Avalanche': os.getenv('AVALANCHE_RPC_URL')
        }
    }

    missing_vars = []
    for var, value in required_vars.items():
        if isinstance(value, dict):
            for sub_var, sub_value in value.items():
                if not sub_value:
                    missing_vars.append(f"{var}[{sub_var}]")
        elif not value:
            missing_vars.append(var)

    if missing_vars:
        logger.error(f"Missing required environment variables: {', '.join(missing_vars)}")
        return False
    return True

# Load and validate configuration
if not validate_env_vars():
    logger.warning("Required environment variables not properly configured!")
else:
    validate_rpc_connection()

SUPABASE_URL = os.getenv("SUPABASE_URL", "your-url")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "your-key")
POLYGON_RPC_URL = os.getenv("POLYGON_RPC_URL")
MANTLE_RPC_URL = os.getenv("MANTLE_RPC_URL")
PRIVATE_KEY = os.getenv("PRIVATE_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
TELEGRAM_THREAD_ID = os.getenv("TELEGRAM_THREAD_ID", "")

# Add validation
if not all([TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID]):
    logging.warning("Telegram credentials not properly configured!")



# Add validation for required RPCs
if not all([POLYGON_RPC_URL, MANTLE_RPC_URL]):
    logging.warning("Required RPC URLs not properly configured!")

logger.info(f"Telegram Bot Token: {TELEGRAM_BOT_TOKEN}")
logger.info(f"Telegram Chat ID: {TELEGRAM_CHAT_ID}")
logger.info(f"Telegram Thread ID: {TELEGRAM_THREAD_ID}")

# Configuration of addresses for all supported stablecoins
STABLECOINS = {

    'USD₮0': {
        'Arbitrum': '0xFd086bC7CD5C481DCC9C85ebE478A1C0b69FCbb9',
    },
    'USDT': {
        'Polygon': '0xc2132D05D31c914a87C6611C10748AEb04B58e8F',
        'Arbitrum': '0xFd086bC7CD5C481DCC9C85ebE478A1C0b69FCbb9',
        'Optimism': '0x94b008aA00579c1307B0EF2c499aD98a8ce58e58',
        'Base': None,  # USDC on Base, USDT not available yet
        'Avalanche': '0x9702230A8Ea53601f5cD2dc00fDBc13d4dF4A8c7',
        'Ethereum': '0xdAC17F958D2ee523a2206206994597C13D831ec7',
        'Mantle': '0x201EBa5CC46D216Ce6DC03F6a759e8E766e956aE'
    },
    'USDC': {
        'Polygon': '0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359',
        'Arbitrum': '0xaf88d065e77c8cC2239327C5EDb3A432268e5831',
        'Optimism': '0x7F5c764cBc14f9669B88837ca1490cCa17c31607',
        'Base': '0x833589fCD6eDb6E08B4DF7441424273dE8F059F7',
        'Avalanche': '0xB97EF9Ef8734C71904D8002F8b6Bc66Dd9c48a6E',
        'Ethereum': '0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48',
        'Mantle': '0x09bc4e0d864854c6afb6eb9a9cdf58ac190d0df9'
    },
    'DAI': {
        'Polygon': '0x8f3Cf7ad23Cd3CaDbD9735AFf958023239c6A063',
        'Arbitrum': '0xDA10009cBd5D07dd0CeCc66161FC93D7c9000da1',
        'Optimism': '0xDA10009cBd5D07dd0CeCc66161FC93D7c9000da1',
        'Base': '0x50c5725949A6F0c72E6C4a641F24049A917DB0Cb',
        'Avalanche': '0xd586E7F844cEa2F87f50152665BCbc2C279D8d70',
        'Ethereum': '0x6B175474E89094C44Da98b954EedeAC495271d0F'
    },
    'GHO': {
        'Ethereum': '0x40D16dC0816bEfC3AeBf2FeA6B4141AFD461Fb94',  # Ethereum only
        'Polygon': None,
        'Arbitrum': '0x7dfF72693f6A4149b17e7C6314655f6A9F7c8B33',
        'Optimism': None,
        'Base': None,
        'Avalanche': None
    },
    'AUSD': {
        'Polygon': '0x221836a597948Dce8F3568E044fF123108a46714',  # Example, check for relevance
        'Arbitrum': None,  # No data
        'Optimism': None,
        'Base': None,
        'Avalanche': None,
        'Ethereum': None
    },
    'FRAX': {
        'Polygon': '0x45c32fA6DF82ead1e2EF74d17b76547EDdFaFF89',
        'Arbitrum': '0x17FC002b466eEc40DaE837Fc4bE5c67993ddBd6F',
        'Ethereum': '0x853d955aCEf822Db058eb8505911ED77F175b99e',
        'Mantle': '0x7EAdA816Fd377ab6a0e8bB6B1c8d042aA4984E1C'
    }
}

# AAVE V3 pool addresses for different networks
AAVE_V3_ADDRESSES = {
    'Polygon': '0x794a61358D6845594F94dc1DB02A252b5b4814aD',
    'Arbitrum': '0x794a61358D6845594F94dc1DB02A252b5b4814aD',
    'Optimism': '0x794a61358D6845594F94dc1DB02A252b5b4814aD',
    'Base': '0xA238Dd80C259a72e81d7e4664a9801593F98d1c5',
    'Avalanche': '0x794a61358D6845594F94dc1DB02A252b5b4814aD',
    'Ethereum': '0x87870Bca3F3fD6335C3F4ce8392D69350B4fA4E2'
}

LENDLE_POOL_ADDRESS = {'Mantle': '0xCFa5aE7c2CE8Fadc6426C1ff872cA45378Fb7cF3'}


AAVE_V3_ADDRESSES = {
    'Ethereum': '0x87870Bca3F3fD6335C3F4ce8392D69350B4fA4E2',
    'Polygon': '0x794a61358D6845594F94dc1DB02A252b5b4814aD',
    'Avalanche': '0x794a61358D6845594F94dc1DB02A252b5b4814aD',
    'Arbitrum': '0x794a61358D6845594F94dc1DB02A252b5b4814aD',
    'Optimism': '0x794a61358D6845594F94dc1DB02A252b5b4814aD',
    'Base': '0xA238Dd80C259a72e81d7e4664a9801593F98d1c5',
    'Mantle': '0xCFa5aE7c2CE8Fadc6426C1ff872cA45378Fb7cF3'  # Lendle
}

AAVE_V2_ADDRESSES = {
    'Ethereum': '0x7d2768dE32b0b80b7a3454c06BdAc94A69DDc7A9',
    'Polygon': '0x8dFf5E27EA6b7AC08EbFdf9eB090F32ee9a30fcf',
    'Avalanche': '0x4F01AeD16D97E3aB5ab2B501154DC9bb0F1A5A2C'
}

YIELDEX_ORACLE_ADDRESS = {'Mantle': '0xe325591Ba3e44ee4a0f8D8e4c18c7C474e256C0c'}

CURVE_POOLS = {
    'USDT_FRAX': {
        'Polygon': '0xBea9F78090bDB9e662d8CB301A00ad09A5b756e9',
        'Ethereum': '0x0fCDAeDFb8D7EfD2525Eb653BDa49F7D03B5c5Ae'
    }
}

UNISWAP_V3_ROUTER = {
    'Ethereum': '0xE592427A0AEce92De3Edee1F18E0157C05861564',
    'Polygon': '0xE592427A0AEce92De3Edee1F18E0157C05861564',
    'Arbitrum': '0xE592427A0AEce92De3Edee1F18E0157C05861564',
    'Optimism': '0xE592427A0AEce92De3Edee1F18E0157C05861564',
    'Base': '0x2626664c2603336E57B271c5C9b86f4DfA5ecA44'
}

UNISWAP_CONTRACTS = {
    'Arbitrum': {
        'router': '0xE592427A0AEce92De3Edee1F18E0157C05861564',
        'quoter': '0xb27308f9F90D607463bb33eA1BeBb41C27CE5AB6'
    }
}

SUPPORTED_PROTOCOLS = {
    'aave-v3': AAVE_V3_ADDRESSES,
    'aave-v2': AAVE_V2_ADDRESSES,
    'lendle': LENDLE_POOL_ADDRESS,
    'yieldex-oracle': YIELDEX_ORACLE_ADDRESS,
    'curve': CURVE_POOLS,
    'uniswap-v3': UNISWAP_V3_ROUTER
}

YIELDEX_ORACLE_ABI = 'YieldexOracle.sol'


