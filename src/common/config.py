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
PRIVATE_KEY = os.getenv("PRIVATE_KEY")

# Web3 конфигурация
RPC_URLS = {
    'Polygon': os.getenv('POLYGON_RPC_URL'),
    'Mantle': os.getenv('MANTLE_RPC_URL'),
    'Ethereum': os.getenv("ETHEREUM_RPC_URL"),
    'Arbitrum': os.getenv("ARBITRUM_RPC_URL"),
    'Optimism': os.getenv("OPTIMISM_RPC_URL"),
    'Base': os.getenv("BASE_RPC_URL"),
    'Avalanche': os.getenv("AVALANCHE_RPC_URL"),
    'Sonic': os.getenv("SONIC_RPC_URL"),
    'Scroll': os.getenv("SCROLL_RPC_URL")
}


# Список известных Silo для тестирования
# Market ID => list of Silo addresses по типу (0 - standard, 1 - protected)
SILO_VAULTS = {
    'Sonic': {
        '20': {
            0: '0xf55902DE87Bd80c6a35614b48d7f8B612a083C12',  # Standard Silo для маркета 20
            1: '0x322e1d5384aa4ED66AeCa770B95686271de61dc3'   # Protected Silo для маркета 20
        },
    }
}

BLOCK_EXPLORERS = {
    'Arbitrum': 'https://arbiscan.io',
    'Polygon': 'https://polygonscan.com', 
    'Optimism': 'https://optimistic.etherscan.io',
    'Mantle': 'https://explorer.mantle.xyz',
    'Base': 'https://basescan.org',
    'Ethereum': 'https://etherscan.io',
    'Avalanche': 'https://snowtrace.io',
    'Sonic': 'https://sonicscan.org',
    'Scroll': 'https://scrollscan.com'
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
def validate_env_vars(service_type="collector"):
    """Validate required environment variables"""
    if service_type == "collector":
        required_vars = {
            'SUPABASE_URL': os.getenv('SUPABASE_URL'),
            'SUPABASE_KEY': os.getenv('SUPABASE_KEY'),
        }
    else:
        # Полная валидация для других сервисов
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
                'Avalanche': os.getenv('AVALANCHE_RPC_URL'),
                'Sonic': os.getenv('SONIC_RPC_URL')
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


TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
TELEGRAM_THREAD_ID = os.getenv("TELEGRAM_THREAD_ID", "")

# Add validation
if not all([TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID]):
    logging.warning("Telegram credentials not properly configured!")



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
        'Mantle': '0x09bc4e0d864854c6afb6eb9a9cdf58ac190d0df9',
        'Scroll': '0x06eFdBFf2a14a7c8E15944D1F4A48F9F95F663A4'
    },
    'USDC.E': {
        'Sonic': '0x29219dd400f2Bf60E5a23d13Be72B486D4038894'
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

SILOS_ADDRESSES = {
    'Sonic': '0xa42001D6d2237d2c74108FE360403C4b796B7170' # SiloFactory
}

SILO_MARKETS = {
    'Sonic': {
        '1': '0x16775bA977e48a67819b302bA5E1D2E9c954F421',
        '2': '0x875bE2b0AeF69589A21C9eF73CD92D8E71b20043',
        '3': '0x78C246f67c8A6cE03a1d894d4Cf68004Bd55Deea',
        '4': '0x2CE93450Af4293626010DeC277F7BAa2005d868a',
        '5': '0x79CFEdda2323C467fec034621CCdB4d3B1F6f444',
        '6': '0xd663B1994F6f7e80c886c5baD6d4153779548211',
        '7': '0x45C218Eb1E22d565227969478CF5D35c737eF4a4',
        '8': '0x4915F6d3C9a7B20CedFc5d3854f2802f30311d13',
        '9': '0x9603Af53dC37F4BB6386f358A51a04fA8f599101',
        '10': '0xcdE453450d830bA284943C3AAb49F19Dc7904b76',
        '11': '0xc180A042D4d408bA5847fa36000F031B3C239470',
        '12': '0xa9e974074D2ebD950F742449200A56A5097C928e',
        '13': '0xC1F3d4F5f734d6Dc9E7D4f639EbE489Acd4542ab',
        '14': '0x2CeCAb227BE8dEd256b74D9196d697bCae91d5aC',
        '15': '0xFe514E71F0933F63B374056557AED3dBB381C646',
        '16': '0xcA6179510ad0672b9d5576029Bb1Bd5c6C0F58B5',
        '17': '0x876F0Cd8A0cEe21390fBb64AF3A4F410F8F1A164',
        '18': '0xc3eEe3C25Bc9bEF998332428cDFF81D1F0D1F201',
        '19': '0x18eA6ee9a2f9D40e4893E01E3E842B335dd82a2F',
        '20': '0x062A36Bbe0306c2Fd7aecdf25843291fBAB96AD2',
        '21': '0x4307732833A3112b66C7B6D9737336538BB0214A',
        '22': '0x1A030F39a8cf9f0b2649e97cF6d0C7853AeaCf78',
        '23': '0xbC24c0F594ECA381956895957c771437D61400D3',
        '24': '0xDF32c1dcf2B73e214C394954F744213945e27Cf8',
        '25': '0x6BdF0D12d4B534d5F46c53a90ddDFBe6C0e85dC7',
        '26': '0xefA367570B11f8745B403c0D458b9D2EAf424686',
        '27': '0xaaF2F78f5eA77bF4EA150E869C54eEb73185a3BF',
        '28': '0xA3BF8b1eE377bBe6152A6885eaeE8747dcBEa35D',
        '29': '0x9DEe0665dEA998Dc33942215A06b36E278eb8b7f',
        '30': '0xA3904721824D8b96A4a47c8Dc5c93e8a89f7435E',
        '31': '0x91D87099fA714a201297856D29380195adB62962',
        '32': '0xe67cce118e9CcEaE51996E4d290f9B77D960E3d7',
        '33': '0x11BBa83002915bB204B348C2174626612260DDaa',
        '34': '0x3605509B2C8Bff9808da5dd5c81547d9EDC4Ffa2',
        '35': '0x4BB15418ef55367c638CA376b50276FACB4A30Ca',
        '36': '0xDace786ceF546C258C67B3EF68AeD91B887BE0f0'
    }
}

# Адреса Compound III на Scroll
COMPOUND_ADDRESSES = {
    'Scroll': '0xB2f97c1Bd3bf02f5e74d13f02E3e26F93D77CE44'
}


SUPPORTED_PROTOCOLS = {
    'aave-v3': AAVE_V3_ADDRESSES,
    'aave-v2': AAVE_V2_ADDRESSES,
    'lendle': LENDLE_POOL_ADDRESS,
    'yieldex-oracle': YIELDEX_ORACLE_ADDRESS,
    'curve': CURVE_POOLS,
    'uniswap-v3': UNISWAP_V3_ROUTER,
    'silo-v2': SILOS_ADDRESSES,
    'compound-v3': COMPOUND_ADDRESSES
}

YIELDEX_ORACLE_ABI = 'YieldexOracle.sol'


