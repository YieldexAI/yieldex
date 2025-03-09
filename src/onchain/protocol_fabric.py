import json
import logging
import sys
import os
from pathlib import Path
from typing import Any, Dict, Optional, List
from enum import Enum
from web3 import Web3
from web3.contract import Contract

# Добавляем путь к корню проекта для импортов
current_dir = Path(__file__).parent
project_root = current_dir.parent.parent
sys.path.insert(0, str(project_root))

from src.common.utils import get_token_address
from src.common.config import (PRIVATE_KEY, RPC_URLS, STABLECOINS, 
                     SUPPORTED_PROTOCOLS, BLOCK_EXPLORERS, YIELDEX_ORACLE_ADDRESS,
                     SILO_MARKETS, SILO_VAULTS)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

ABI_DIR = Path(__file__).parent.parent / "common" / "abi"

class BaseProtocolOperator:
    """Base class for interacting with DeFi protocols"""
    
    def __init__(self, network: str, protocol: str):
        self.network = network
        self.protocol = protocol
        self.w3 = Web3(Web3.HTTPProvider(RPC_URLS.get(network)))
        
        if not self.w3.is_connected():
            raise ConnectionError(f"Failed to connect to {network} RPC")
            
        self.contract_address = SUPPORTED_PROTOCOLS[protocol][network]
        self.contract = self._load_contract()
        self.account = self.w3.eth.account.from_key(PRIVATE_KEY)
        self.explorer_url = BLOCK_EXPLORERS.get(self.network)
        
    def _load_contract(self) -> Contract:
        """Load ABI based on protocol"""
        try:
            abi_map = {
                'aave-v3': 'AaveV3Pool.json',
                'aave-v2': 'AaveV2LendingPool.json',
                'lendle': 'LendleLendingPool.json',
                'yieldex-oracle': 'YieldexOracle.json',
                'uniswap-v3': 'UniswapV3Router.json',
                'silo-v2': 'SiloFactory.json'
            }
            
            # Протоколы, которые не требуют проверки методом getReserveData
            no_reserve_data_protocols = ['yieldex-oracle', 'uniswap-v3', 'silo-v2']
            
            if self.protocol not in abi_map:
                raise ValueError(f"Unsupported protocol: {self.protocol}")
            
            abi_path = ABI_DIR / abi_map[self.protocol]
            
            if not abi_path.exists():
                logger.warning(f"ABI file not found at {abi_path}, trying to locate in parent directory")
                # Попробуем найти файл в родительской директории (для запуска из командной строки)
                alt_path = Path("src/common/abi") / abi_map[self.protocol]
                if alt_path.exists():
                    abi_path = alt_path
                else:
                    alt_path = Path("common/abi") / abi_map[self.protocol]
                    if alt_path.exists():
                        abi_path = alt_path
                    else:
                        raise FileNotFoundError(f"ABI file not found: {abi_path}")
            
            with open(abi_path) as f:
                abi = json.load(f)
                logger.info(f"ABI loaded: {abi_path}")
            
            # Check if contract address is valid
            if not Web3.is_checksum_address(self.contract_address):
                self.contract_address = Web3.to_checksum_address(self.contract_address)
            
            # Create contract
            contract = self.w3.eth.contract(
                address=self.contract_address,
                abi=abi
            )
            
            # Check if contract is accessible
            try:
                # Try calling a view method, but only for protocols that support it
                if self.protocol not in no_reserve_data_protocols:
                    contract.functions.getReserveData(
                        self.w3.to_checksum_address(
                            STABLECOINS['USDT'][self.network]
                        )
                    ).call()
                elif self.protocol == 'silo-v2':
                    # Для Silo проверяем другим методом
                    contract.functions.getNextSiloId().call()
                elif self.protocol == 'yieldex-oracle':
                    # Для oracle проверяем getApy
                    contract.functions.getApy("test").call()
                elif self.protocol == 'uniswap-v3':
                    # Для Uniswap мы можем просто проверить, что байткод контракта не пустой
                    if self.w3.eth.get_code(self.contract_address) == b'':
                        raise ValueError(f"No contract at address {self.contract_address}")
            except Exception as e:
                logger.warning(f"Contract verification warning: {str(e)}")
                # Не выбрасываем исключение, так как контракт всё равно может быть рабочим
            
            return contract
            
        except Exception as e:
            logger.error(f"Error loading contract for {self.protocol} on {self.network}: {str(e)}")
            raise
        
    def _get_gas_params(self) -> Dict[str, Any]:
        """Get gas parameters optimized for L2 networks"""
        base_params = {
            'from': self.account.address,
            'nonce': self.w3.eth.get_transaction_count(self.account.address),
            'chainId': self.w3.eth.chain_id
        }

        # For L2 networks use gasPrice
        if self.network in ['Arbitrum', 'Optimism', 'Mantle']:
            base_params['gasPrice'] = self.w3.eth.gas_price
        else:
            # For EVM-networks use EIP-1559 with base parameters
            try:
                latest_block = self.w3.eth.get_block('latest')
                base_fee = latest_block['baseFeePerGas']
                priority_fee = self.w3.eth.max_priority_fee or self.w3.to_wei(1, 'gwei')
                
                base_params['maxFeePerGas'] = base_fee + priority_fee
                base_params['maxPriorityFeePerGas'] = priority_fee
            except:
                base_params['gasPrice'] = self.w3.eth.gas_price

        return base_params

    def _send_transaction(self, tx_function) -> str:
        """Universal method for sending transactions"""
        try:
            tx_params = self._get_gas_params()
            
            # Base gas estimation with fixed multiplier
            estimated_gas = tx_function.estimate_gas(tx_params)
            tx_params['gas'] = int(estimated_gas * 1.3)  # 30% buffer
            
            signed_tx = self.account.sign_transaction(
                tx_function.build_transaction(tx_params)
            )
            
            tx_hash = self.w3.eth.send_raw_transaction(signed_tx.raw_transaction)
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)
            
            if receipt.status != 1:
                raise Exception("Transaction reverted")
                
            tx_hash_hex = tx_hash.hex()
            logger.info(f"Transaction successful: {tx_hash_hex}")
            
            return f'{self.explorer_url}/tx/0x{tx_hash_hex}'
            
        except Exception as e:
            logger.error(f"Transaction failed: {str(e)}")
            raise

    def _call_contract(self, function) -> Any:
        """Execute contract call with proper gas estimation"""
        try:
            params = {
                'from': self.account.address,
                'chainId': self.w3.eth.chain_id,
            }
            
            # Special handling for Arbitrum
            if self.network == 'Arbitrum':
                gas_price = self.w3.eth.gas_price
                params['gasPrice'] = int(gas_price * 1.2)  # +20% to base gas price
                params['gas'] = 3000000  # Increased gas limit for Arbitrum
            else:
                gas_estimate = function.estimate_gas(params)
                params['gas'] = int(gas_estimate * 1.5)
            
            return function.call(params)
            
        except Exception as e:
            logger.error(f"Contract call failed: {str(e)}")
            raise

    def _convert_to_wei(self, token_address: str, amount: float) -> int:
        """Convert amount to wei based on token decimals"""
        try:
            if not Web3.is_checksum_address(token_address):
                token_address = Web3.to_checksum_address(token_address)
            
            if not self.w3.is_connected():
                raise ConnectionError(f"Not connected to {self.network}")
                
            if self.w3.eth.get_code(token_address) == b'':
                raise ValueError(f"No contract at address {token_address}")
            
            with open(ABI_DIR / 'ERC20.json') as f:
                abi = json.load(f)
            
            erc20 = self.w3.eth.contract(address=token_address, abi=abi)
            
            try:
                # Use _call_contract for decimals
                decimals = erc20.functions.decimals().call()
                logger.info(f"Got decimals for {token_address}: {decimals}")
            except Exception as e:
                logger.warning(f"Failed to get decimals, using default (18): {str(e)}")
                decimals = 18
            
            return int(amount * 10 ** decimals)
            
        except Exception as e:
            logger.error(f"Error in _convert_to_wei: {str(e)}")
            raise

    def _check_token_support(self, token_address: str) -> bool:
        """Check if token is supported in the pool"""
        try:
            # Use _call_contract instead of direct call
            reserve_data = self._call_contract(
                self.contract.functions.getReserveData(token_address)
            )
            
            configuration = reserve_data[0]
            is_active = (configuration >> 56) & 1
            is_frozen = (configuration >> 57) & 1
            
            if not is_active:
                raise ValueError(f"Token {token_address} is not active in the pool")
            if is_frozen:
                raise ValueError(f"Token {token_address} is frozen in the pool")
                
            return True
            
        except Exception as e:
            logger.error(f"Token support check failed: {str(e)}")
            return False

class AaveOperator(BaseProtocolOperator):
    """Class for working with AAVE across networks"""
    
    def supply(self, token: str, amount: float) -> str:
        """Deposit funds into protocol"""
        token_address = STABLECOINS[token][self.network]
        amount_wei = self._convert_to_wei(token_address, amount)
        
        # Create token contract
        with open(ABI_DIR / 'ERC20.json') as f:
            token_contract = self.w3.eth.contract(
                address=token_address,
                abi=json.load(f)
            )
        
        # Get and log balance
        decimals = token_contract.functions.decimals().call()
        balance = token_contract.functions.balanceOf(self.account.address).call()
        balance_human = balance / 10**decimals
        
        logger.info(f"Current balance: {balance_human} {token}")
        logger.info(f"Attempting to supply: {amount} {token}")
        
        if balance < amount_wei:
            raise ValueError(f"Insufficient balance: have {balance_human}, need {amount} {token}")
        
        # Rest of the supply logic...
        allowance = token_contract.functions.allowance(
            self.account.address,
            self.contract_address
        ).call()
        
        if allowance < amount_wei:
            approve_tx = token_contract.functions.approve(
                self.contract_address,
                amount_wei
            )
            logger.info(f"Approving {token} for Aave V3")
            self._send_transaction(approve_tx)
        
        if self.protocol == 'aave-v3':
            tx_func = self.contract.functions.supply(
                token_address,
                amount_wei,
                self.account.address,
                0
            )
        elif self.protocol == 'aave-v2':
            tx_func = self.contract.functions.deposit(
                token_address,
                amount_wei,
                self.account.address,
                0
            )
            
        return self._send_transaction(tx_func)
        
    def withdraw(self, token: str, amount: float) -> str:
        """Withdraw funds from protocol"""
        try:
            token_address = get_token_address(token, self.network)
            
            # Check token support in pool
            logger.info(f"Checking if token {token} ({token_address}) is supported in {self.network} pool")
            reserve_data = self.contract.functions.getReserveData(token_address).call()
            
            # Check reserve configuration
            configuration = reserve_data[0]
            is_active = (configuration >> 56) & 1
            is_frozen = (configuration >> 57) & 1
            
            if not is_active:
                raise ValueError(f"Token {token} is not active in the pool")
            if is_frozen:
                raise ValueError(f"Token {token} is frozen in the pool")
                
            atoken_address = reserve_data[8]
            if not Web3.is_address(atoken_address) or atoken_address == '0x0000000000000000000000000000000000000000':
                raise ValueError(f"Invalid aToken address for {token}: {atoken_address}")
                
            logger.info(f"Token is supported, aToken address: {atoken_address}")
            
                
            # Create aToken contract and get balance
            atoken_contract = self.w3.eth.contract(
                address=atoken_address,
                abi=json.load(open(ABI_DIR / 'ERC20.json'))
            )
            
            # Use direct call() as in get_balance
            decimals = atoken_contract.functions.decimals().call()
            balance = atoken_contract.functions.balanceOf(self.account.address).call()
            logger.info(f"Current balance: {balance/10**decimals} {token}")

            amount_wei = self._convert_to_wei(token_address, amount)
            
            if balance < amount_wei:
                raise ValueError(f"Insufficient balance: have {balance / 10 ** decimals}, need {amount_wei / 10 ** decimals}")
            
            # Execute withdrawal
            tx_func = self.contract.functions.withdraw(
                token_address,
                amount_wei,
                self.account.address
            )
            
            return self._send_transaction(tx_func)
            
        except Exception as e:
            logger.error(f"Withdrawal failed for {token} on {self.network}: {str(e)}")
            raise

class LendleOperator(BaseProtocolOperator):
    """Class for working with Lendle on Mantle"""
    
    def deposit(self, token: str, amount: float) -> str:
        token_address = STABLECOINS[token][self.network]
        amount_wei = self._convert_to_wei(token_address, amount)
        
        tx_func = self.contract.functions.deposit(
            token_address,
            amount_wei,
            self.account.address,
            0
        )
        return self._send_transaction(tx_func)
        
    def withdraw(self, token: str, amount: float) -> str:
        token_address = STABLECOINS[token][self.network]
        amount_wei = self._convert_to_wei(token_address, amount)
        
        tx_func = self.contract.functions.withdraw(
            token_address,
            amount_wei,
            self.account.address
        )
        return self._send_transaction(tx_func)
    
class YieldexOracleOperator(BaseProtocolOperator):
    def __init__(self, network: str):
        if network != 'Mantle':
            raise ValueError("Oracle only available on Mantle")
        super().__init__(network, 'yieldex-oracle')
        self.contract_address = Web3.to_checksum_address(YIELDEX_ORACLE_ADDRESS[network])
            

    def update_apy(self, pool_id: str, apy: float) -> Optional[str]:
        """Update APY in the oracle contract"""
        try:
            # Conversion to contract format (2 decimal places)
            apy_scaled = int(apy * 100)
            
            tx_func = self.contract.functions.updateApy(
                pool_id,
                apy_scaled
            )
            
            return self._send_transaction(tx_func)
            
        except Exception as e:
            logger.error(f"Failed to update APY for {pool_id}: {str(e)}")
            return None
        
    def update_multiple_apys(self, pool_ids: List[str], apys: List[float]) -> Optional[str]:
        """Update APY for multiple pools"""
        try:
            apy_scaled = [int(apy * 100) for apy in apys]
            tx_func = self.contract.functions.updateMultipleApys(pool_ids, apy_scaled)
            return self._send_transaction(tx_func)
        except Exception as e:
            logger.error(f"Failed to update multiple APYs: {str(e)}")
            return None


    def get_apy(self, pool_id: str) -> Optional[float]:
        try:
            # Explicit string encoding and unpacking values
            apy_scaled, timestamp = self.contract.functions.getApy(
                pool_id
            ).call()
            return apy_scaled / 100
        except Exception as e:
            logger.error(f"Ошибка при получении APY: {str(e)}")
            return None

class CrossChainManager:
    """Management of cross-chain operations"""
    
    def __init__(self):
        self.bridge_contracts = {
            'Polygon': '0x...',
            'Arbitrum': '0x...',
            'Mantle': '0x...'
        }
        
    def bridge_assets(self, token: str, amount: float, from_chain: str, to_chain: str):
        """Transfer tokens between chains via official bridge"""
        operator = AaveOperator(from_chain, 'aave-v3')
        operator.withdraw(token, amount)
        
        # Bridging logic
        bridge_contract = self.w3.eth.contract(
            address=self.bridge_contracts[from_chain],
            abi=json.load(open(ABI_DIR / 'Bridge.json'))
        )
        
        tx_hash = bridge_contract.functions.deposit(
            STABLECOINS[token][from_chain],
            amount,
            to_chain
        ).transact()
        
        return tx_hash.hex()

class CurveOperator(BaseProtocolOperator):
    """Class for working with Curve.fi pools"""
    
    def __init__(self, network: str, pool_name: str):
        self.pool_name = pool_name
        super().__init__(network, 'curve')
        
    def swap(self, from_token: str, to_token: str, amount: float) -> str:
        """Execute swap between two stablecoins in Curve pool"""
        from_address = STABLECOINS[from_token][self.network]
        to_address = STABLECOINS[to_token][self.network]
        
        # Get pool contract with Curve-specific ABI
        pool_contract = self.w3.eth.contract(
            address=self.contract_address,
            abi=json.load(open(ABI_DIR / 'CurvePool.json'))
        )
        
        amount_wei = self._convert_to_wei(from_address, amount)
        
        # Get pool coins index
        coins = pool_contract.functions.coins().call()
        from_idx = coins.index(Web3.to_checksum_address(from_address))
        to_idx = coins.index(Web3.to_checksum_address(to_address))
        
        tx_func = pool_contract.functions.exchange(
            from_idx,
            to_idx,
            amount_wei,
            0  # min_received_amount (will calculate properly in real scenario)
        )
        
        return self._send_transaction(tx_func)

class UniswapV3Operator(BaseProtocolOperator):
    """Class for working with Uniswap V3 swaps"""
    
    # Add dictionary with Quoter contract addresses
    QUOTER_ADDRESSES = {
        'Arbitrum': '0xb27308f9F90D607463bb33eA1BeBb41C27CE5AB6',
        'Optimism': '0x7637DcE4704b41Bf52BF338C650Dc46A586f7cF38',
    }
    
    # Available fee tiers in Uniswap V3
    FEE_TIERS = {
        100: '0064',  # 0.01%
        500: '01f4',  # 0.05%
        3000: '0bb8', # 0.3%
        10000: '2710' # 1%
    }

    def _get_token_decimals(self, token_address: str) -> int:
        """Get token decimals using existing ERC20 contract"""
        with open(ABI_DIR / 'ERC20.json') as f:
            erc20 = self.w3.eth.contract(
                address=token_address,
                abi=json.load(f)
            )
        return erc20.functions.decimals().call()

    def _get_optimal_fee_tier(self, token_in: str, token_out: str) -> str:
        """
        Determine optimal fee tier for token pair based on liquidity
        Returns hex representation of fee tier
        """
        try:
            # Here you can add logic to determine the optimal fee tier
            # based on liquidity in pools or other metrics
            return self.FEE_TIERS[500]  # Return default 0.05%
        except Exception as e:
            logger.warning(f"Failed to get optimal fee tier: {e}. Using default 0.05%")
            return self.FEE_TIERS[500]

    def _validate_token_address(self, token_address: str) -> str:
        """Validate and return checksum address"""
        if not Web3.is_address(token_address):
            raise ValueError(f"Invalid token address: {token_address}")
        return Web3.to_checksum_address(token_address)

    def _get_quote(self, token_in_addr: str, token_out_addr: str, amount_wei: int, fee_tier: Optional[str] = None) -> int:
        """
        Get quote for swap from Uniswap V3 Quoter contract
        
        Args:
            token_in: Input token address
            token_out: Output token address
            amount_wei: Amount in wei to swap
            fee_tier: Optional fee tier, if None will use optimal
        
        Returns:
            int: Expected output amount in wei
        """
        try:
            # Get quoter contract
            quoter_address = self.QUOTER_ADDRESSES.get(self.network)
            if not quoter_address:
                raise ValueError(f"Quoter address not configured for network {self.network}")

            quoter_abi = json.load(open(ABI_DIR / 'UniswapV3Quoter.json'))
            quoter = self.w3.eth.contract(address=quoter_address, abi=quoter_abi)
            
            # Get fee tier if not provided
            if not fee_tier:
                fee_tier = self._get_optimal_fee_tier(token_in_addr, token_out_addr)
            
            # Build path
            print(fee_tier)
            path = self._build_path(token_in_addr, token_out_addr, fee_tier)
            logger.info(f"Quote path: {path.hex()}")
            
            # Get decimals for output formatting
            decimals_out = self._get_token_decimals(token_out_addr)
            
            # Get quote
            quote_amount = quoter.functions.quoteExactInput(
                path,
                amount_wei
            ).call()
            
            logger.info(f"Quote successful: {quote_amount / 10**decimals_out} tokens")
            return quote_amount
            
        except Exception as e:
            logger.error(f"Failed to get quote: {str(e)}")
            raise

    def swap(self, token_in: str, token_out: str, amount_in: float, slippage: float = 0.5) -> str:
        """Execute swap using Uniswap V3 Router"""
        try:
            # Validate addresses
            token_in_addr = self._validate_token_address(get_token_address(token_in, self.network))
            token_out_addr = self._validate_token_address(get_token_address(token_out, self.network))

            logger.info(f"Tokens: {token_in} -> {token_out} ({token_in_addr} -> {token_out_addr})")
            
            # Get decimals
            decimals_in = self._get_token_decimals(token_in_addr)
            decimals_out = self._get_token_decimals(token_out_addr)
            
            # Convert amount to wei
            amount_wei = self._convert_to_wei(token_in_addr, amount_in)
            
            # Handle approvals
            self._handle_token_approval(token_in_addr, amount_wei)
            
            # Get optimal fee tier
            fee_tier = self._get_optimal_fee_tier(token_in, token_out)
            
            # Get quote and calculate minimum output
            try:
                quote_amount = self._get_quote(token_in_addr, token_out_addr, amount_wei, fee_tier)
                min_amount_out = int(quote_amount * (1 - slippage/100))
            except Exception as e:
                logger.warning(f"Using fallback slippage calculation: {str(e)}")
                min_amount_out = int(amount_wei * 0.95)  # 5% slippage as fallback
            
            # Build path and execute swap
            path = self._build_path(token_in_addr, token_out_addr, fee_tier)
            
            # Execute swap
            deadline = self.w3.eth.get_block('latest')['timestamp'] + 600
            params = {
                'path': path,
                'recipient': self.account.address,
                'deadline': deadline,
                'amountIn': amount_wei,
                'amountOutMinimum': min_amount_out
            }
            
            swap_func = self.contract.functions.exactInput(params)
            return self._send_transaction(swap_func)
            
        except Exception as e:
            logger.error(f"Swap failed: {str(e)}")
            raise

    def _handle_token_approval(self, token_address: str, amount: int) -> None:
        """Handle token approval for Uniswap"""
        with open(ABI_DIR / 'ERC20.json') as f:
            token_contract = self.w3.eth.contract(
                address=token_address,
                abi=json.load(f)
            )
        
        allowance = token_contract.functions.allowance(
            self.account.address,
            self.contract_address
        ).call()
        
        if allowance < amount:
            logger.info(f"Approving token {token_address}")
            approve_func = token_contract.functions.approve(
                self.contract_address,
                amount
            )
            tx_hash = self._send_transaction(approve_func)
            logger.info(f"Approval transaction: {tx_hash}")

    def _build_path(self, token_in: str, token_out: str, fee_tier: str) -> bytes:
        """Build path for Uniswap swap"""
        # Remove '0x' prefix if present and ensure addresses are 20 bytes (40 hex chars)
        token_in_clean = token_in[2:].zfill(40) if token_in.startswith('0x') else token_in.zfill(40)
        token_out_clean = token_out[2:].zfill(40) if token_out.startswith('0x') else token_out.zfill(40)
        
        # Ensure fee tier is 3 bytes (6 hex chars)
        fee_hex = fee_tier.zfill(6)
        
        # Concatenate and convert to bytes
        path_hex = f"{token_in_clean}{fee_hex}{token_out_clean}"
        return bytes.fromhex(path_hex)

class SiloOperator(BaseProtocolOperator):
    """Class for working with Silo-v2 protocol across networks
    
    Silo-v2 is a lending protocol that uses ERC4626 vault standard.
    Each market is identified by a unique market_id.
    Collateral can be of two types: standard collateral (0) or protected collateral (1).
    """
    
    # Add an enum for collateral types
    class CollateralType(Enum):
        STANDARD = 0
        PROTECTED = 1
    
    def __init__(self, network: str, market_id: str = None):
        """
        Initialize Silo operator
        
        Args:
            network: Network name (e.g. 'Sonic')
            market_id: Market ID (e.g. '20' for USDC.E_Sonic_silo-v2_20)
        """
        super().__init__(network, 'silo-v2')
        self.market_id = market_id
        
        # The Silo contracts are deployed per market and token
        # We'll get the specific contract address either from configuration or
        # from a SiloFactory lookup
    
    def _get_silo_address(self, token: str) -> str:
        """
        Get the Silo address for a token by market ID
        
        Args:
            token: Token symbol or address
            
        Returns:
            Silo contract address
        """
        try:
            # Проверяем токен
            token_address = get_token_address(token, self.network)
            logger.debug(f"Getting Silo address for token {token} ({token_address}) on market {self.market_id}")
            
            # Если нет market_id, невозможно найти Silo
            if not self.market_id:
                raise ValueError("Market ID is required to get Silo address")
            
            # Проверяем наличие маркета в SILO_MARKETS
            if self.network not in SILO_MARKETS or self.market_id not in SILO_MARKETS[self.network]:
                logger.warning(f"Маркет {self.market_id} не найден в SILO_MARKETS для сети {self.network}")
                # Обновляем список маркетов
                markets = get_all_silo_markets(self.network)
                if self.market_id not in markets:
                    raise ValueError(f"Маркет {self.market_id} не существует в сети {self.network}")
            
            # Проверяем кэш SILO_VAULTS для известных Silo
            silo_address = None
            
            # По умолчанию используем Standard Silo (тип 0)
            silo_type = 0
            
            if (self.network in SILO_VAULTS and 
                self.market_id in SILO_VAULTS[self.network] and 
                silo_type in SILO_VAULTS[self.network][self.market_id]):
                
                silo_address = SILO_VAULTS[self.network][self.market_id][silo_type]
                logger.info(f"Найден адрес Silo для маркета {self.market_id} в кэше: {silo_address}")
                return silo_address
            
            # Если в кэше нет, получаем адрес Silo через find_silos_for_market
            silos = self.find_silos_for_market(self.market_id)
            
            # Ищем Silo соответствующего типа
            for silo in silos:
                if silo.get("silo_type") == silo_type:
                    silo_address = silo.get("silo_address")
                    break
            
            if not silo_address:
                # Если не нашли Silo нужного типа, берем первый доступный
                if silos:
                    silo_address = silos[0].get("silo_address")
                    logger.warning(f"Не найден Silo типа {silo_type}, используем первый доступный: {silo_address}")
                else:
                    raise ValueError(f"No Silo found for market {self.market_id} on {self.network}")
            
            return silo_address
            
        except Exception as e:
            logger.error(f"Error getting Silo address: {str(e)}")
            raise

    def find_silos_for_market(self, market_id: str) -> list:
        """
        Find all Silo vaults for a specific market ID
        
        Args:
            market_id: Market ID (e.g. '20')
            
        Returns:
            List of dictionaries with Silo information:
            - silo_address: Silo contract address
            - token_info: Token information including symbol, name, decimals
        """
        try:
            logger.info(f"Finding Silo vaults for market {market_id} on network {self.network}")
            
            # Check if market exists in SILO_MARKETS
            if self.network not in SILO_MARKETS or market_id not in SILO_MARKETS[self.network]:
                logger.warning(f"Market {market_id} not found in SILO_MARKETS for network {self.network}")
                
                # If market not in SILO_MARKETS, get new list of markets
                markets = get_all_silo_markets(self.network)
                if market_id not in markets:
                    raise ValueError(f"Market {market_id} does not exist in network {self.network}")
            
            # Get SiloConfig address from SILO_MARKETS
            silo_config_address = SILO_MARKETS[self.network][market_id]
            if not silo_config_address or silo_config_address == "0x0000000000000000000000000000000000000000":
                raise ValueError(f"Invalid SiloConfig address for market {market_id}")
                
            logger.info(f"Using SiloConfig address for market {market_id}: {silo_config_address}")
            
            # Check if there are known Silos in SILO_VAULTS cache
            silos_result = []
            if (self.network in SILO_VAULTS and 
                market_id in SILO_VAULTS[self.network] and 
                SILO_VAULTS[self.network][market_id]):
                
                logger.info(f"Found cached Silos for market {market_id}")
                silo_types = SILO_VAULTS[self.network][market_id]
                
                for silo_type, silo_address in silo_types.items():
                    if silo_address and silo_address != "0x0000000000000000000000000000000000000000":
                        token_info = self.get_silo_info(silo_address)
                        if token_info:
                            silos_result.append({
                                "silo_address": silo_address,
                                "token_info": token_info,
                                "silo_type": silo_type
                            })
            
            # If not in cache, get Silos from SiloConfig
            if not silos_result:
                try:
                    # Load ABI for SiloConfig
                    with open(ABI_DIR / "SiloConfig.json") as f:
                        config_abi = json.load(f)
                    
                    # Create SiloConfig contract
                    silo_config = self.w3.eth.contract(
                        address=silo_config_address,
                        abi=config_abi
                    )
                    
                    # Initialize cache if needed
                    if self.network not in SILO_VAULTS:
                        SILO_VAULTS[self.network] = {}
                    if market_id not in SILO_VAULTS[self.network]:
                        SILO_VAULTS[self.network][market_id] = {}
                    
                    # Try to get Silo0 address (standard Silo)
                    try:
                        silo0_address = silo_config.functions.getSilo(0).call()
                        logger.info(f"Found Silo0 address: {silo0_address}")
                        
                        if silo0_address != "0x0000000000000000000000000000000000000000":
                            # Save to cache
                            SILO_VAULTS[self.network][market_id][0] = silo0_address
                            
                            silo0_info = self.get_silo_info(silo0_address)
                            if silo0_info:
                                silos_result.append({
                                    "silo_address": silo0_address,
                                    "token_info": silo0_info,
                                    "silo_type": 0
                                })
                    except Exception as e:
                        logger.warning(f"Error getting Silo0 address: {str(e)}")
                    
                    # Try to get Silo1 address (protected Silo)
                    try:
                        silo1_address = silo_config.functions.getSilo(1).call()
                        logger.info(f"Found Silo1 address: {silo1_address}")
                        
                        if silo1_address != "0x0000000000000000000000000000000000000000":
                            # Save to cache
                            SILO_VAULTS[self.network][market_id][1] = silo1_address
                            
                            silo1_info = self.get_silo_info(silo1_address)
                            if silo1_info:
                                silos_result.append({
                                    "silo_address": silo1_address,
                                    "token_info": silo1_info,
                                    "silo_type": 1
                                })
                    except Exception as e:
                        logger.warning(f"Error getting Silo1 address: {str(e)}")
                        
                    # If failed to find Silos through getSilo, try alternative methods
                    if not silos_result:
                        logger.info("Trying alternative methods to get Silo addresses")
                        
                        # 1. Try silos(uint256) method
                        try:
                            for i in range(0, 5):  # Check first 5 indices
                                try:
                                    silo_address = silo_config.functions.silos(i).call()
                                    if silo_address and silo_address != "0x0000000000000000000000000000000000000000":
                                        logger.info(f"Found Silo through silos({i}): {silo_address}")
                                        
                                        # Determine Silo type (assume even - standard, odd - protected)
                                        silo_type = 0 if i % 2 == 0 else 1
                                        SILO_VAULTS[self.network][market_id][silo_type] = silo_address
                                        
                                        silo_info = self.get_silo_info(silo_address)
                                        if silo_info:
                                            silos_result.append({
                                                "silo_address": silo_address,
                                                "token_info": silo_info,
                                                "silo_type": silo_type
                                            })
                                except Exception:
                                    pass
                        except Exception as e:
                            logger.debug(f"silos method not found: {str(e)}")
                            
                        # 2. Try getSilos() method
                        if not silos_result:
                            try:
                                silo_addresses = silo_config.functions.getSilos().call()
                                if silo_addresses and len(silo_addresses) > 0:
                                    logger.info(f"Found Silos through getSilos(): {silo_addresses}")
                                    
                                    for i, silo_address in enumerate(silo_addresses):
                                        if silo_address and silo_address != "0x0000000000000000000000000000000000000000":
                                            # Determine Silo type
                                            silo_type = 0 if i % 2 == 0 else 1
                                            SILO_VAULTS[self.network][market_id][silo_type] = silo_address
                                            
                                            silo_info = self.get_silo_info(silo_address)
                                            if silo_info:
                                                silos_result.append({
                                                    "silo_address": silo_address,
                                                    "token_info": silo_info,
                                                    "silo_type": silo_type
                                                })
                            except Exception as e:
                                logger.debug(f"getSilos method not found: {str(e)}")
                                
                            # 3. Try direct getStandardSilo() and getProtectedSilo() methods
                            if not silos_result:
                                try:
                                    # Standard Silo
                                    try:
                                        silo0_address = silo_config.functions.getStandardSilo().call()
                                        if silo0_address and silo0_address != "0x0000000000000000000000000000000000000000":
                                            logger.info(f"Found Standard Silo: {silo0_address}")
                                            SILO_VAULTS[self.network][market_id][0] = silo0_address
                                            
                                            silo0_info = self.get_silo_info(silo0_address)
                                            if silo0_info:
                                                silos_result.append({
                                                    "silo_address": silo0_address,
                                                    "token_info": silo0_info,
                                                    "silo_type": 0
                                                })
                                    except Exception as e:
                                        logger.debug(f"getStandardSilo method not found: {str(e)}")
                                    
                                    # Protected Silo
                                    try:
                                        silo1_address = silo_config.functions.getProtectedSilo().call()
                                        if silo1_address and silo1_address != "0x0000000000000000000000000000000000000000":
                                            logger.info(f"Found Protected Silo: {silo1_address}")
                                            SILO_VAULTS[self.network][market_id][1] = silo1_address
                                            
                                            silo1_info = self.get_silo_info(silo1_address)
                                            if silo1_info:
                                                silos_result.append({
                                                    "silo_address": silo1_address,
                                                    "token_info": silo1_info,
                                                    "silo_type": 1
                                                })
                                    except Exception as e:
                                        logger.debug(f"getProtectedSilo method not found: {str(e)}")
                                except Exception as e:
                                    logger.debug(f"Error trying to use getStandardSilo/getProtectedSilo methods: {str(e)}")
                except Exception as e:
                    logger.warning(f"Error working with SiloConfig: {str(e)}")
            
            # Clean up result - remove entries with None token_info
            silos_result = [s for s in silos_result if s.get("token_info") is not None]
            
            return silos_result
                
        except Exception as e:
            logger.error(f"Error finding Silos for market {market_id}: {str(e)}")
            raise
            
    def get_silo_info(self, silo_address: str) -> dict:
        """
        Get information about a Silo vault
        
        Args:
            silo_address: Silo contract address
            
        Returns:
            Dictionary with token information including symbol, name, decimals
        """
        try:
            # Load Silo ABI
            with open(ABI_DIR / "Silo.json") as f:
                silo_abi = json.load(f)
            
            # Create Silo contract
            silo = self.w3.eth.contract(address=silo_address, abi=silo_abi)
            
            # Get asset token address
            try:
                token_address = silo.functions.asset().call()
            except Exception as e:
                logger.warning(f"Error getting asset token from Silo {silo_address}: {str(e)}")
                return None
            
            # Get token information
            token_info = self.get_token_info(token_address)
            
            # Add Silo-specific information
            try:
                token_info["silo_name"] = silo.functions.name().call()
                token_info["silo_symbol"] = silo.functions.symbol().call()
            except Exception as e:
                logger.warning(f"Error getting Silo name/symbol from {silo_address}: {str(e)}")
            
            return token_info
            
        except Exception as e:
            logger.error(f"Error getting Silo info for {silo_address}: {str(e)}")
            return None
            
    def get_token_info(self, token_address: str) -> dict:
        """
        Get information about a token
        
        Args:
            token_address: Token contract address
            
        Returns:
            Dictionary with token information including symbol, name, decimals
        """
        try:
            # Load ERC20 ABI
            with open(ABI_DIR / "ERC20.json") as f:
                erc20_abi = json.load(f)
            
            # Create token contract
            token = self.w3.eth.contract(address=token_address, abi=erc20_abi)
            
            # Get token information
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
            
            return {
                "address": token_address,
                "name": name,
                "symbol": symbol,
                "decimals": decimals
            }
            
        except Exception as e:
            logger.error(f"Error getting token info for {token_address}: {str(e)}")
            return None

    def deposit(self, token: str, amount: float, collateral_type: str = 'standard') -> str:
        """
        Deposit assets into Silo vault
        
        Args:
            token: Token symbol (e.g. 'USDC.E')
            amount: Amount to deposit
            collateral_type: Type of collateral ('standard' or 'protected')
            
        Returns:
            Transaction hash
        """
        token_address = STABLECOINS[token][self.network]
        amount_wei = self._convert_to_wei(token_address, amount)
        silo_address = self._get_silo_address(token)
        
        # Verify collateral type
        if collateral_type not in self.COLLATERAL_TYPE:
            raise ValueError(f"Invalid collateral type: {collateral_type}. Must be one of: {list(self.COLLATERAL_TYPE.keys())}")
        
        collateral_type_value = self.COLLATERAL_TYPE[collateral_type]
        
        # Create ERC20 token contract
        with open(ABI_DIR / 'ERC20.json') as f:
            token_contract = self.w3.eth.contract(
                address=token_address,
                abi=json.load(f)
            )
        
        # Create Silo contract
        with open(ABI_DIR / 'Silo.json') as f:
            silo_contract = self.w3.eth.contract(
                address=silo_address,
                abi=json.load(f)
            )
        
        # First, approve tokens for the silo contract
        approve_tx = self._send_transaction(
            token_contract.functions.approve(silo_address, amount_wei)
        )
        logger.info(f"Approved {amount} {token} for Silo vault: {approve_tx}")
        
        # Deposit into the silo contract with specified collateral type
        deposit_tx = self._send_transaction(
            silo_contract.functions.deposit(
                amount_wei, 
                self.account.address, 
                collateral_type_value
            )
        )
        
        logger.info(f"Deposited {amount} {token} into Silo vault with collateral type {collateral_type}: {deposit_tx}")
        
        return deposit_tx
    
    def withdraw(self, token: str, amount: float = None, collateral_type: str = 'standard') -> str:
        """
        Withdraw assets from Silo vault
        
        Args:
            token: Token symbol (e.g. 'USDC.E')
            amount: Amount to withdraw, if None - withdraw all
            collateral_type: Type of collateral ('standard' or 'protected')
            
        Returns:
            Transaction hash
        """
        token_address = STABLECOINS[token][self.network]
        silo_address = self._get_silo_address(token)
        
        # Verify collateral type
        if collateral_type not in self.COLLATERAL_TYPE:
            raise ValueError(f"Invalid collateral type: {collateral_type}. Must be one of: {list(self.COLLATERAL_TYPE.keys())}")
        
        collateral_type_value = self.COLLATERAL_TYPE[collateral_type]
        
        # Create Silo contract
        with open(ABI_DIR / 'Silo.json') as f:
            silo_contract = self.w3.eth.contract(
                address=silo_address,
                abi=json.load(f)
            )
        
        if amount is None:
            # Get the user's max withdrawable amount
            max_withdraw = silo_contract.functions.maxWithdraw(
                self.account.address,
                collateral_type_value
            ).call()
            
            if max_withdraw == 0:
                raise ValueError(f"No withdrawable balance available for {token} in this vault with collateral type {collateral_type}")
            
            # Withdraw all available
            tx = self._send_transaction(
                silo_contract.functions.withdraw(
                    max_withdraw,
                    self.account.address,
                    self.account.address,
                    collateral_type_value
                )
            )
            logger.info(f"Withdrew all available {token} from Silo vault with collateral type {collateral_type}: {tx}")
        else:
            # Convert amount to wei
            amount_wei = self._convert_to_wei(token_address, amount)
            
            # Withdraw specific amount
            tx = self._send_transaction(
                silo_contract.functions.withdraw(
                    amount_wei,
                    self.account.address,
                    self.account.address,
                    collateral_type_value
                )
            )
            logger.info(f"Withdrew {amount} {token} from Silo vault with collateral type {collateral_type}: {tx}")
        
        return tx
    
    def get_balance(self, token: str) -> float:
        """Get the current balance of token in the Silo vault"""
        token_address = STABLECOINS[token][self.network]
        silo_address = self._get_silo_address(token)
        
        with open(ABI_DIR / 'Silo.json') as f:
            silo_contract = self.w3.eth.contract(
                address=silo_address,
                abi=json.load(f)
            )
        
        # Get user's balance in shares
        balance_wei = silo_contract.functions.balanceOf(self.account.address).call()
        
        # Convert shares to assets
        assets_wei = silo_contract.functions.convertToAssets(balance_wei).call()
        
        # Convert wei to float
        return self._convert_from_wei(token_address, assets_wei)
    
    def build_deposit_calldata(self, token: str, amount: float, collateral_type: str = 'standard') -> str:
        """
        Build calldata for deposit function
        
        Args:
            token: Token symbol
            amount: Amount to deposit
            collateral_type: Type of collateral ('standard' or 'protected')
            
        Returns:
            Encoded function call
        """
        token_address = STABLECOINS[token][self.network]
        amount_wei = self._convert_to_wei(token_address, amount)
        silo_address = self._get_silo_address(token)
        
        # Verify collateral type
        if collateral_type not in self.COLLATERAL_TYPE:
            raise ValueError(f"Invalid collateral type: {collateral_type}. Must be one of: {list(self.COLLATERAL_TYPE.keys())}")
        
        collateral_type_value = self.COLLATERAL_TYPE[collateral_type]
        
        with open(ABI_DIR / 'Silo.json') as f:
            silo_contract = self.w3.eth.contract(
                address=silo_address,
                abi=json.load(f)
            )
        
        # Create calldata for deposit function
        return silo_contract.encodeABI(
            fn_name="deposit",
            args=[amount_wei, self.account.address, collateral_type_value]
        )
    
    def build_withdraw_calldata(self, token: str, amount: float = None, collateral_type: str = 'standard') -> str:
        """
        Build calldata for withdraw function
        
        Args:
            token: Token symbol
            amount: Amount to withdraw, if None - withdraw all
            collateral_type: Type of collateral ('standard' or 'protected')
            
        Returns:
            Encoded function call
        """
        token_address = STABLECOINS[token][self.network]
        silo_address = self._get_silo_address(token)
        
        # Verify collateral type
        if collateral_type not in self.COLLATERAL_TYPE:
            raise ValueError(f"Invalid collateral type: {collateral_type}. Must be one of: {list(self.COLLATERAL_TYPE.keys())}")
        
        collateral_type_value = self.COLLATERAL_TYPE[collateral_type]
        
        with open(ABI_DIR / 'Silo.json') as f:
            silo_contract = self.w3.eth.contract(
                address=silo_address,
                abi=json.load(f)
            )
        
        if amount is None:
            # Get the user's max withdrawable amount
            max_withdraw = silo_contract.functions.maxWithdraw(
                self.account.address,
                collateral_type_value
            ).call()
            
            if max_withdraw == 0:
                raise ValueError(f"No withdrawable balance available for {token} in this vault with collateral type {collateral_type}")
            
            # Withdraw all available
            return silo_contract.encodeABI(
                fn_name="withdraw",
                args=[max_withdraw, self.account.address, self.account.address, collateral_type_value]
            )
        else:
            # Convert amount to wei
            amount_wei = self._convert_to_wei(token_address, amount)
            
            # Withdraw specific amount
            return silo_contract.encodeABI(
                fn_name="withdraw",
                args=[amount_wei, self.account.address, self.account.address, collateral_type_value]
            )
    
    def _convert_from_wei(self, token_address: str, amount_wei: int) -> float:
        """Convert amount from wei to float based on token decimals"""
        with open(ABI_DIR / 'ERC20.json') as f:
            token_contract = self.w3.eth.contract(
                address=token_address,
                abi=json.load(f)
            )
        
        decimals = token_contract.functions.decimals().call()
        return amount_wei / (10 ** decimals)

    def get_market_data(self, token: str) -> Dict[str, Any]:
        """
        Get market data for a specific Silo vault
        
        Args:
            token: Token symbol (e.g. 'USDC.E')
            
        Returns:
            Dictionary with market data including:
            - total_assets: Total assets in the vault
            - collateral_assets: Total collateral assets
            - debt_assets: Total debt assets
            - liquidity: Available liquidity
            - utilization: Current utilization ratio (%)
        """
        token_address = STABLECOINS[token][self.network]
        silo_address = self._get_silo_address(token)
        
        with open(ABI_DIR / 'Silo.json') as f:
            silo_contract = self.w3.eth.contract(
                address=silo_address,
                abi=json.load(f)
            )
        
        # Get various market metrics
        total_assets = silo_contract.functions.totalAssets().call()
        collateral_debt = silo_contract.functions.getCollateralAndDebtTotalsStorage().call()
        liquidity = silo_contract.functions.getLiquidity().call()
        
        collateral_assets = collateral_debt[0]
        debt_assets = collateral_debt[1]
        
        # Calculate utilization as debt / collateral (if collateral is 0, utilization is 0)
        utilization = (debt_assets / collateral_assets * 100) if collateral_assets > 0 else 0
        
        return {
            'total_assets': self._convert_from_wei(token_address, total_assets),
            'collateral_assets': self._convert_from_wei(token_address, collateral_assets),
            'debt_assets': self._convert_from_wei(token_address, debt_assets),
            'liquidity': self._convert_from_wei(token_address, liquidity),
            'utilization': utilization,
            'market_id': self.market_id
        }
        
    def check_borrowing_capacity(self, token: str) -> Dict[str, Any]:
        """
        Check how much can be borrowed by the account from this Silo market
        
        Args:
            token: Token symbol (e.g. 'USDC.E')
            
        Returns:
            Dictionary with borrowing capacity data including:
            - max_borrow_amount: Maximum amount that can be borrowed
            - is_solvent: Whether the account is solvent
            - has_collateral: Whether the account has collateral in this market
        """
        token_address = STABLECOINS[token][self.network]
        silo_address = self._get_silo_address(token)
        
        with open(ABI_DIR / 'Silo.json') as f:
            silo_contract = self.w3.eth.contract(
                address=silo_address,
                abi=json.load(f)
            )
        
        # Check if account is solvent (no outstanding debt)
        is_solvent = silo_contract.functions.isSolvent(self.account.address).call()
        
        # Check maximum borrowing capacity
        max_borrow_wei = silo_contract.functions.maxBorrow(self.account.address).call()
        
        # Check if user has any collateral
        balance_wei = silo_contract.functions.balanceOf(self.account.address).call()
        has_collateral = balance_wei > 0
        
        return {
            'max_borrow_amount': self._convert_from_wei(token_address, max_borrow_wei),
            'is_solvent': is_solvent,
            'has_collateral': has_collateral
        }
        
    def borrow(self, token: str, amount: float) -> str:
        """
        Borrow assets from Silo vault
        
        Args:
            token: Token symbol (e.g. 'USDC.E')
            amount: Amount to borrow
            
        Returns:
            Transaction hash
        """
        token_address = STABLECOINS[token][self.network]
        amount_wei = self._convert_to_wei(token_address, amount)
        silo_address = self._get_silo_address(token)
        
        # Create Silo contract
        with open(ABI_DIR / 'Silo.json') as f:
            silo_contract = self.w3.eth.contract(
                address=silo_address,
                abi=json.load(f)
            )
        
        # Check borrowing capacity
        max_borrow = silo_contract.functions.maxBorrow(self.account.address).call()
        if amount_wei > max_borrow:
            raise ValueError(f"Cannot borrow {amount} {token}, maximum allowed is {self._convert_from_wei(token_address, max_borrow)}")
        
        # Execute borrow transaction
        borrow_tx = self._send_transaction(
            silo_contract.functions.borrow(
                amount_wei,
                self.account.address,
                self.account.address
            )
        )
        
        logger.info(f"Borrowed {amount} {token} from Silo vault: {borrow_tx}")
        return borrow_tx
    
    def repay(self, token: str, amount: float = None) -> str:
        """
        Repay borrowed assets to Silo vault
        
        Args:
            token: Token symbol (e.g. 'USDC.E')
            amount: Amount to repay, if None - repay all outstanding debt
            
        Returns:
            Transaction hash
        """
        token_address = STABLECOINS[token][self.network]
        silo_address = self._get_silo_address(token)
        
        # Create Silo contract and token contract
        with open(ABI_DIR / 'Silo.json') as f:
            silo_contract = self.w3.eth.contract(
                address=silo_address,
                abi=json.load(f)
            )
            
        with open(ABI_DIR / 'ERC20.json') as f:
            token_contract = self.w3.eth.contract(
                address=token_address,
                abi=json.load(f)
            )
        
        # Get max repayable amount for this account
        max_repay = silo_contract.functions.maxRepay(self.account.address).call()
        
        if max_repay == 0:
            raise ValueError(f"No outstanding debt for {token} in this vault")
        
        if amount is None:
            # Repay all outstanding debt
            amount_wei = max_repay
        else:
            # Convert amount to wei
            amount_wei = self._convert_to_wei(token_address, amount)
            
            # Check if amount exceeds debt
            if amount_wei > max_repay:
                raise ValueError(f"Cannot repay {amount} {token}, outstanding debt is only {self._convert_from_wei(token_address, max_repay)}")
        
        # First, approve tokens for the silo contract
        approve_tx = self._send_transaction(
            token_contract.functions.approve(silo_address, amount_wei)
        )
        logger.info(f"Approved {amount_wei / (10**token_contract.functions.decimals().call())} {token} for repay: {approve_tx}")
        
        # Execute repay transaction
        repay_tx = self._send_transaction(
            silo_contract.functions.repay(
                amount_wei,
                self.account.address
            )
        )
        
        logger.info(f"Repaid {self._convert_from_wei(token_address, amount_wei)} {token} to Silo vault: {repay_tx}")
        return repay_tx
    
    def build_borrow_calldata(self, token: str, amount: float) -> str:
        """
        Build calldata for borrow function
        
        Args:
            token: Token symbol
            amount: Amount to borrow
            
        Returns:
            Encoded function call
        """
        token_address = STABLECOINS[token][self.network]
        amount_wei = self._convert_to_wei(token_address, amount)
        silo_address = self._get_silo_address(token)
        
        with open(ABI_DIR / 'Silo.json') as f:
            silo_contract = self.w3.eth.contract(
                address=silo_address,
                abi=json.load(f)
            )
        
        # Create calldata for borrow function
        return silo_contract.encodeABI(
            fn_name="borrow",
            args=[amount_wei, self.account.address, self.account.address]
        )
    
    def build_repay_calldata(self, token: str, amount: float = None) -> str:
        """
        Build calldata for repay function
        
        Args:
            token: Token symbol
            amount: Amount to repay, if None - repay maximum possible
            
        Returns:
            Encoded function call
        """
        token_address = STABLECOINS[token][self.network]
        silo_address = self._get_silo_address(token)
        
        with open(ABI_DIR / 'Silo.json') as f:
            silo_contract = self.w3.eth.contract(
                address=silo_address,
                abi=json.load(f)
            )
        
        if amount is None:
            # Get max repayable amount for this account
            max_repay = silo_contract.functions.maxRepay(self.account.address).call()
            
            if max_repay == 0:
                raise ValueError(f"No outstanding debt for {token} in this vault")
                
            # Repay all outstanding debt
            amount_wei = max_repay
        else:
            # Convert amount to wei
            amount_wei = self._convert_to_wei(token_address, amount)
        
        # Create calldata for repay function
        return silo_contract.encodeABI(
            fn_name="repay",
            args=[amount_wei, self.account.address]
        )

    def get_share_balance(self, token_address, owner_address):
        # Get balance of share tokens for accounting
        return self.silo_contract.functions.balanceOf(owner_address).call()

    def get_max_withdraw(self, token_address, owner_address, collateral_type=CollateralType.STANDARD):
        # Call maxWithdraw function to check available withdrawal amount
        return self.silo_contract.functions.maxWithdraw(
            owner_address, 
            collateral_type.value
        ).call()

    def get_silo_abi(self):
        """Получить ABI для Silo контракта"""
        with open(ABI_DIR / "Silo.json") as f:
            return json.load(f)

def get_protocol_operator(network: str, protocol: str, **kwargs):
    """Factory method to get protocol operator"""
    if protocol == 'aave-v3':
        return AaveOperator(network, protocol)
    elif protocol == 'lendle':
        return LendleOperator(network, protocol)
    elif protocol == 'uniswap-v3':
        return UniswapV3Operator(network, protocol)
    elif protocol == 'curve':
        if 'pool_name' not in kwargs:
            raise ValueError("pool_name is required for curve")
        return CurveOperator(network, kwargs['pool_name'])
    elif protocol == 'silo-v2':
        # Для Silo может быть передан дополнительный параметр market_id
        market_id = kwargs.get('market_id')
        return SiloOperator(network, market_id)
    else:
        raise ValueError(f"Unknown protocol: {protocol}")

def process_recommendations(recommendations: List[Dict]):
    operator = AgentOperator(network='Sonic')
    operator.load_agents_from_db()
    
    calls = []
    for rec in recommendations:
        protocol = rec.get('protocol', 'aave-v3')
        action = rec.get('action', 'deposit')  # Default action is deposit, but can be: deposit, withdraw, borrow, repay
        
        if protocol == 'silo-v2':
            # Извлекаем market_id из pool_id, если он передан
            # Формат pool_id: {asset}_{chain}_{protocol}_{market_id}
            # Например: USDC.E_Sonic_silo-v2_20
            pool_id = rec.get('pool_id', '')
            if '_' in pool_id:
                parts = pool_id.split('_')
                market_id = parts[-1] if len(parts) >= 4 else None
            else:
                market_id = None
            
            silo = SiloOperator(rec['chain'], market_id)
            
            # Determine action type and build appropriate calldata
            if action == 'deposit':
                # Определяем тип коллатерала, по умолчанию используем standard
                collateral_type = rec.get('collateral_type', 'standard')
                
                calls.append({
                    'target': silo._get_silo_address(rec['token']),
                    'data': silo.build_deposit_calldata(
                        token=rec['token'],
                        amount=rec['amount'],
                        collateral_type=collateral_type
                    )
                })
            elif action == 'withdraw':
                # Determine collateral type
                collateral_type = rec.get('collateral_type', 'standard')
                
                calls.append({
                    'target': silo._get_silo_address(rec['token']),
                    'data': silo.build_withdraw_calldata(
                        token=rec['token'],
                        amount=rec.get('amount'),  # None will withdraw all
                        collateral_type=collateral_type
                    )
                })
            elif action == 'borrow':
                calls.append({
                    'target': silo._get_silo_address(rec['token']),
                    'data': silo.build_borrow_calldata(
                        token=rec['token'],
                        amount=rec['amount']
                    )
                })
            elif action == 'repay':
                calls.append({
                    'target': silo._get_silo_address(rec['token']),
                    'data': silo.build_repay_calldata(
                        token=rec['token'],
                        amount=rec.get('amount')  # None will repay all
                    )
                })
            else:
                logger.warning(f"Unsupported action for Silo: {action}")
                
        elif protocol == 'aave-v3':
            aave = AaveOperator(rec['chain'], 'aave-v3')
            
            if action == 'deposit':
                calls.append({
                    'target': aave.contract_address,
                    'data': aave.build_deposit_calldata(
                        token=rec['token'],
                        amount=rec['amount']
                    )
                })
            elif action == 'withdraw':
                calls.append({
                    'target': aave.contract_address,
                    'data': aave.build_withdraw_calldata(
                        token=rec['token'],
                        amount=rec.get('amount')  # None will withdraw all
                    )
                })
            else:
                logger.warning(f"Unsupported action for Aave: {action}")
        # Add other protocols as needed
    
    operator.execute_on_agents(calls)

def read_silo_data(network: str, token: str, market_id: str, wallet_address: str = None):
    """
    Функция для чтения и вывода данных из Silo контракта.
    
    Args:
        network: Сеть (например, 'Sonic')
        token: Символ токена (например, 'USDC.E')
        market_id: ID рынка (например, '20')
        wallet_address: Опциональный адрес кошелька для проверки баланса
    
    Returns:
        Dict: Словарь с данными о рынке и балансах
    """
    try:
        logger.info(f"Чтение данных из Silo для {token} в сети {network}, market_id: {market_id}")
        
        # Создаем экземпляр SiloOperator
        silo = SiloOperator(network, market_id)
        
        # Получаем адрес Silo контракта для указанного токена и market_id
        silo_address = silo._get_silo_address(token)
        logger.info(f"Адрес Silo контракта: {silo_address}")
        
        # Получаем данные о рынке
        market_data = silo.get_market_data(token)
        
        # Данные для возврата
        result = {
            "silo_address": silo_address,
            "market_id": market_id,
            "token": token,
            "network": network,
            "market_data": market_data
        }
        
        # Если указан адрес кошелька, проверяем балансы и лимиты
        if wallet_address:
            # Создаем контракт Silo для чтения данных
            with open(ABI_DIR / 'Silo.json') as f:
                silo_contract = silo.w3.eth.contract(
                    address=silo_address,
                    abi=json.load(f)
                )
            
            # Получаем баланс обычного коллатерала
            standard_balance = silo_contract.functions.balanceOf(wallet_address).call()
            
            # Получаем информацию о максимально доступном для вывода количестве
            max_withdraw_standard = silo_contract.functions.maxWithdraw(
                wallet_address, 
                SiloOperator.COLLATERAL_TYPE['standard']
            ).call()
            
            max_withdraw_protected = silo_contract.functions.maxWithdraw(
                wallet_address, 
                SiloOperator.COLLATERAL_TYPE['protected']
            ).call()
            
            # Проверяем возможность заимствования
            borrow_capacity = silo.check_borrowing_capacity(token)
            
            # Проверяем solvent status для пользователя
            is_solvent = silo_contract.functions.isSolvent(wallet_address).call()
            
            # Добавляем данные пользователя в результат
            token_address = STABLECOINS[token][network]
            result["user_data"] = {
                "wallet_address": wallet_address,
                "standard_collateral_balance": silo._convert_from_wei(token_address, standard_balance),
                "max_withdraw_standard": silo._convert_from_wei(token_address, max_withdraw_standard),
                "max_withdraw_protected": silo._convert_from_wei(token_address, max_withdraw_protected),
                "borrowing_capacity": borrow_capacity,
                "is_solvent": is_solvent
            }
        
        # Выводим результаты в лог
        logger.info(f"Результаты для Silo {token}_{network}_silo-v2_{market_id}:")
        logger.info(f"Общие активы в хранилище: {market_data['total_assets']} {token}")
        logger.info(f"Коллатеральные активы: {market_data['collateral_assets']} {token}")
        logger.info(f"Долговые активы: {market_data['debt_assets']} {token}")
        logger.info(f"Доступная ликвидность: {market_data['liquidity']} {token}")
        logger.info(f"Уровень утилизации: {market_data['utilization']:.2f}%")
        
        if wallet_address and "user_data" in result:
            logger.info(f"Данные пользователя {wallet_address}:")
            logger.info(f"Баланс стандартного коллатерала: {result['user_data']['standard_collateral_balance']} {token}")
            logger.info(f"Максимально доступно для вывода (стандартный): {result['user_data']['max_withdraw_standard']} {token}")
            logger.info(f"Максимально доступно для вывода (защищенный): {result['user_data']['max_withdraw_protected']} {token}")
            logger.info(f"Максимально доступно для займа: {result['user_data']['borrowing_capacity']['max_borrow_amount']} {token}")
            logger.info(f"Платежеспособность: {'Да' if result['user_data']['is_solvent'] else 'Нет'}")
        
        return result
        
    except Exception as e:
        logger.error(f"Ошибка при чтении данных из Silo: {str(e)}", exc_info=True)
        raise

def find_silos_for_market(network: str, market_id: str) -> list:
    """
    Функция для поиска всех Silo контрактов для указанного маркета.
    
    Args:
        network: Сеть (например, 'Sonic')
        market_id: ID рынка (например, '8')
    
    Returns:
        List: Список со всеми найденными Silo контрактами и информацией о токенах
    """
    try:
        logger.info(f"Поиск Silo контрактов для маркета {market_id} в сети {network}")
        
        # Создаем экземпляр SiloOperator
        silo = SiloOperator(network, market_id)
        
        # Находим все Silo контракты для маркета
        silos = silo.find_silos_for_market(market_id)
        
        # Проверяем, что мы нашли Silo контракты
        if not silos:
            logger.warning(f"Не найдено Silo контрактов для маркета {market_id}")
            return []
            
        # Получаем полную информацию о каждом Silo
        for i, silo_info in enumerate(silos):
            silo_address = silo_info.get("silo_address")
            silo_type = silo_info.get("silo_type", "неизвестный")
            silo_type_name = "Standard" if silo_type == 0 else "Protected" if silo_type == 1 else "Неизвестный"
            
            # Если нет информации о токене, пытаемся получить ее
            if not silo_info.get("token_info"):
                token_info = silo.get_silo_info(silo_address)
                silos[i]["token_info"] = token_info
            
            # Выводим информацию о Silo
            token_info = silo_info.get("token_info", {})
            logger.info(f"Найден Silo {i+1}: {silo_address} (тип: {silo_type_name})")
            logger.info(f"  Токен: {token_info.get('symbol')} ({token_info.get('name')})")
            logger.info(f"  Адрес токена: {token_info.get('address')}")
            logger.info(f"  Decimals: {token_info.get('decimals')}")
            
            # Пытаемся получить дополнительную информацию о Silo
            try:
                with open(ABI_DIR / "Silo.json") as f:
                    silo_contract = silo.w3.eth.contract(
                        address=silo_address,
                        abi=json.load(f)
                    )
                
                # Получаем общие активы в хранилище
                total_assets = silo_contract.functions.totalAssets().call()
                silos[i]["total_assets"] = total_assets
                
                # Конвертируем в human-readable формат с учетом decimals
                decimals = token_info.get("decimals", 18)
                total_assets_human = total_assets / (10 ** decimals)
                
                # Выводим дополнительную информацию
                logger.info(f"  Общие активы: {total_assets_human} {token_info.get('symbol', '')}")
                
            except Exception as e:
                logger.warning(f"Не удалось получить дополнительную информацию о Silo {silo_address}: {str(e)}")
        
        return silos
        
    except Exception as e:
        logger.error(f"Ошибка при поиске Silo контрактов: {str(e)}", exc_info=True)
        raise

def get_all_silo_markets(network: str) -> list:
    """
    Получает список всех доступных маркетов Silo для указанной сети.
    
    Args:
        network: Сеть (например, 'Sonic')
        
    Returns:
        List[str]: Список ID маркетов
    """
    try:
        logger.info(f"Поиск всех доступных маркетов Silo в сети {network}")
        
        # Инициализация Web3 и контракта SiloFactory
        w3 = Web3(Web3.HTTPProvider(RPC_URLS[network]))
        factory_address = SUPPORTED_PROTOCOLS['silo-v2'][network]
        
        if not factory_address:
            raise ValueError(f"SiloFactory address not configured for network {network}")
        
        # Загружаем ABI для SiloFactory
        with open(ABI_DIR / "SiloFactory.json") as f:
            factory_abi = json.load(f)
        
        # Создаем контракт SiloFactory
        factory = w3.eth.contract(address=factory_address, abi=factory_abi)
        
        # Получаем максимальный ID маркета (через getNextSiloId)
        try:
            max_id = factory.functions.getNextSiloId().call()
            logger.info(f"Максимальный ID маркета: {max_id}")
        except Exception as e:
            logger.warning(f"Не удалось получить максимальный ID маркета: {str(e)}")
            # Если не удалось получить, используем фиксированное значение для тестирования
            max_id = 50
        
        # Получаем список всех доступных маркетов
        markets = []
        
        # Проверяем каждый ID от 1 до max_id
        for i in range(1, max_id + 1):
            try:
                # Получаем адрес SiloConfig для данного ID
                config_address = factory.functions.idToSiloConfig(i).call()
                
                # Если адрес не нулевой, значит маркет существует
                if config_address and config_address != "0x0000000000000000000000000000000000000000":
                    logger.info(f"Найден маркет с ID {i}: {config_address}")
                    markets.append(str(i))
                    
                    # Обновляем конфигурацию маркетов в кэше
                    if network not in SILO_MARKETS:
                        SILO_MARKETS[network] = {}
                    SILO_MARKETS[network][str(i)] = config_address
            except Exception as e:
                logger.debug(f"Ошибка при проверке маркета {i}: {str(e)}")
        
        return markets
        
    except Exception as e:
        logger.error(f"Ошибка при получении списка маркетов Silo: {str(e)}")
        return []

def inspect_silo_config(network: str, silo_config_address: str) -> dict:
    """
    Инспектирует контракт SiloConfig для определения его структуры и доступных методов
    
    Args:
        network: Сеть (например, 'Sonic')
        silo_config_address: Адрес SiloConfig
        
    Returns:
        dict: Информация о контракте
    """
    try:
        logger.info(f"Инспектирование контракта SiloConfig {silo_config_address} в сети {network}")
        
        # Инициализация Web3
        w3 = Web3(Web3.HTTPProvider(RPC_URLS[network]))
        
        # Собираем базовую ERC20 информацию
        result = {
            "address": silo_config_address,
            "contract_type": "Unknown",
            "methods": [],
            "properties": {}
        }
        
        # Проверяем базовую информацию
        for abi_file in ["SiloConfig.json", "ERC20.json", "Silo.json"]:
            try:
                with open(ABI_DIR / abi_file) as f:
                    contract_abi = json.load(f)
                
                contract = w3.eth.contract(address=silo_config_address, abi=contract_abi)
                
                # Пытаемся получить имя/символ/decimals (если это токен)
                try:
                    result["properties"]["name"] = contract.functions.name().call()
                    result["contract_type"] = "Token or Silo"
                except Exception:
                    pass
                
                try:
                    result["properties"]["symbol"] = contract.functions.symbol().call()
                except Exception:
                    pass
                
                try:
                    result["properties"]["decimals"] = contract.functions.decimals().call()
                except Exception:
                    pass
                
                # Пытаемся определить, это SiloConfig или нет
                try:
                    # Если это SiloConfig, то должен быть метод asset
                    asset_address = contract.functions.asset().call()
                    result["properties"]["asset"] = asset_address
                    result["contract_type"] = "SiloConfig or Silo"
                except Exception:
                    pass
                
                # Пытаемся проверить, это Silo или нет
                try:
                    total_assets = contract.functions.totalAssets().call()
                    result["properties"]["totalAssets"] = total_assets
                    result["contract_type"] = "Silo"
                except Exception:
                    pass
                
                # Пытаемся вызвать различные методы, чтобы определить, какие есть у контракта
                methods_to_check = [
                    "getSilo", "silos", "getSilos", "getStandardSilo", "getProtectedSilo",
                    "totalAssets", "totalSupply", "getAllMarkets", "getMarkets", "getNextSiloId",
                    "isSilo"
                ]
                
                for method_name in methods_to_check:
                    try:
                        method = contract.get_function_by_name(method_name)
                        result["methods"].append(method_name)
                    except Exception:
                        pass
                
                # Если нашли какие-то методы, останавливаемся на этом
                if result["methods"]:
                    break
                    
            except Exception as e:
                logger.debug(f"Ошибка при проверке контракта с ABI {abi_file}: {str(e)}")
        
        # Если не нашли никаких методов, пробуем использовать общие ERC20 вызовы
        if not result["methods"] and not result["properties"]:
            # Возможно, это простой EOA (обычный аккаунт, не контракт)
            try:
                balance = w3.eth.get_balance(silo_config_address)
                result["contract_type"] = "EOA (not a contract)"
                result["properties"]["balance"] = w3.from_wei(balance, 'ether')
            except Exception:
                pass
        
        return result
        
    except Exception as e:
        logger.error(f"Ошибка при инспектировании контракта: {str(e)}")
        return {"error": str(e)}

def main():
    try:
        print("Step 3.10: Testing SiloOperator for market 8")
        
        # Create operator for market 8
        silo_operator = SiloOperator(network="Sonic", market_id="8")
        
        # Get list of Silos for the market
        silos = silo_operator.find_silos_for_market("8")
        print(f"\nFound Silos for market 8:")
        print(json.dumps(silos, indent=2))
        
        # Get detailed information for each Silo
        for silo_info in silos:
            silo_address = silo_info["silo_address"]
            print(f"\nInformation about Silo {silo_address}:")
            silo_details = silo_operator.get_silo_info(silo_address)
            print(json.dumps(silo_details, indent=2))
            
    except Exception as e:
        logger.error(f"Error executing script: {str(e)}", exc_info=True)
        print(f"\nERROR: {str(e)}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
