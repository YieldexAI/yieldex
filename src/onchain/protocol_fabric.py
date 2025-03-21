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
                     SILO_MARKETS, SILO_VAULTS, COMPOUND_ADDRESSES, RHO_ADDRESSES)

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
            
        try:
            self.contract_address = SUPPORTED_PROTOCOLS[protocol][network]
        except KeyError:
            available_networks = list(SUPPORTED_PROTOCOLS[protocol].keys())
            raise ValueError(f"{protocol} contracts not found on {network}. Available on: {', '.join(available_networks)}")
        
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
                'silo-v2': 'SiloFactory.json',
                'compound-v3': 'CompoundComet.json',
                'rho': 'ERC20-rhoMarket.json'
            }
            
            
            if self.protocol not in abi_map:
                raise ValueError(f"Unsupported protocol: {self.protocol}")
            
            abi_path = ABI_DIR / abi_map[self.protocol]
            
            # Check possible alternative paths
            if not os.path.exists(abi_path):
                alt_path = os.path.join(os.path.dirname(__file__), f"../common/abi/{self.protocol}.json")
                if os.path.exists(alt_path):
                    abi_path = alt_path
                else:
                    raise FileNotFoundError(f"ABI file not found: {abi_path}")
            
            with open(abi_path) as f:
                abi = json.load(f)
                logger.info(f"ABI loaded: {abi_path}")

            if self.protocol == 'rho':
                self.contract_address = RHO_ADDRESSES[self.network]['usdc']
            
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
        if self.network in ['Arbitrum', 'Optimism', 'Mantle', 'Sonic', 'Scroll']:
            gas_price = self.w3.eth.gas_price
            
            # For Sonic, increase gas price by 50%
            if self.network == 'Sonic':
                gas_price = int(gas_price * 1.5)  # +50% to current gas price
                logger.info(f"Using increased gas price for Sonic: {gas_price}")
            
            base_params['gasPrice'] = gas_price
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
            
            # Try to send transaction, with up to 3 attempts with increased gas price
            max_attempts = 3
            attempt = 1
            
            while attempt <= max_attempts:
                try:
                    signed_tx = self.account.sign_transaction(
                        tx_function.build_transaction(tx_params)
                    )
                    
                    tx_hash = self.w3.eth.send_raw_transaction(signed_tx.raw_transaction)
                    receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)
                    
                    if receipt.status != 1:
                        raise Exception("Transaction reverted")
                        
                    tx_hash_hex = tx_hash.hex()
                    logger.info(f'Transaction successful: {self.explorer_url}/tx/0x{tx_hash_hex}')
                    
                    return f'{self.explorer_url}/tx/0x{tx_hash_hex}'
                    
                except Exception as e:
                    error_msg = str(e)
                    
                    # Check if error is "transaction underpriced"
                    if "underpriced" in error_msg.lower() and attempt < max_attempts:
                        # Increase gas price by 30% for each retry
                        if 'gasPrice' in tx_params:
                            tx_params['gasPrice'] = int(tx_params['gasPrice'] * 1.3)
                            logger.warning(f"Transaction underpriced. Increasing gas price to {tx_params['gasPrice']} (attempt {attempt}/{max_attempts})")
                        else:
                            # If using EIP-1559, increase both maxFeePerGas and maxPriorityFeePerGas
                            if 'maxFeePerGas' in tx_params:
                                tx_params['maxFeePerGas'] = int(tx_params['maxFeePerGas'] * 1.3)
                                tx_params['maxPriorityFeePerGas'] = int(tx_params['maxPriorityFeePerGas'] * 1.3)
                                logger.warning(f"Transaction underpriced. Increasing maxFeePerGas to {tx_params['maxFeePerGas']} (attempt {attempt}/{max_attempts})")
                            else:
                                # Fallback to standard gasPrice if neither is set
                                tx_params['gasPrice'] = int(self.w3.eth.gas_price * (1.3 ** attempt))
                                logger.warning(f"Transaction underpriced. Setting gasPrice to {tx_params['gasPrice']} (attempt {attempt}/{max_attempts})")
                                
                        # Update nonce in case it's changed
                        tx_params['nonce'] = self.w3.eth.get_transaction_count(self.account.address)
                        attempt += 1
                        continue
                    else:
                        # For other errors or if max attempts reached, raise the exception
                        logger.error(f"Transaction error: {error_msg}")
                        raise
            
            # If we've reached here, all attempts failed
            raise Exception(f"Failed to send transaction after {max_attempts} attempts")
            
        except Exception as e:
            logger.error(f"Transaction failed: {str(e)}")
            return None

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
        
        logger.info(f"Current wallet balance: {balance_human} {token}")
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
            logger.info(f"Current wallet balance: {balance/10**decimals} {token}")

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


class CollateralType(Enum):
    STANDARD = 0
    PROTECTED = 1

class SiloOperator(BaseProtocolOperator):
    """Class for working with Silo-v2 protocol across networks
    
    Silo-v2 is a lending protocol that uses ERC4626 vault standard.
    Each market is identified by a unique market_id.
    Collateral can be of two types: standard collateral (0) or protected collateral (1).
    """
    
    # Add an enum for collateral types

    
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

    def supply(self, token: str, amount: float, collateral_type: CollateralType = CollateralType.PROTECTED) -> Optional[str]:
        """
        Deposit funds into Silo vault
        
        Args:
            token: Token symbol (e.g. 'USDC.E')
            amount: Amount to deposit
            collateral_type: Type of collateral, PROTECTED (1) by default for stablecoins
            
        Returns:
            Transaction hash if successful, None otherwise
        """
        try:
            # Get token address
            if token in STABLECOINS and self.network in STABLECOINS[token]:
                token_address = STABLECOINS[token][self.network]
            else:
                token_address = get_token_address(token, self.network)
                
            logger.info(f"Supplying {amount} {token} to Silo market {self.market_id} on {self.network}")
            
            # Find Silo for this token and market
            silos = self.find_silos_for_market(self.market_id)
            
            # Filter silos to find the one matching our token and collateral type
            matching_silo = None
            for silo in silos:
                silo_type = silo.get("silo_type")
                token_info = silo.get("token_info", {})
                
                # Check if token symbol or name contains our token
                symbol = token_info.get("symbol", "").upper()
                name = token_info.get("name", "").upper()
                silo_symbol = token_info.get("silo_symbol", "").upper()
                silo_name = token_info.get("silo_name", "").upper()
                
                # Use different checks depending on token type
                if token in ["USDC", "USDC.E", "USDT", "USDT.E", "DAI"]:
                    # For stablecoins, prefer matching by symbol and type
                    if (
                        (token in symbol or token in name or token in silo_symbol or token in silo_name) and
                        silo_type == collateral_type.value
                    ):
                        matching_silo = silo
                        break
                else:
                    # For other tokens, match by symbol
                    if token in symbol or token in name or token in silo_symbol or token in silo_name:
                        matching_silo = silo
                        break
            
            # If no match by token name, use collateral type as fallback
            if not matching_silo:
                for silo in silos:
                    if silo.get("silo_type") == collateral_type.value:
                        matching_silo = silo
                        logger.warning(f"No exact match for {token}, using silo with correct collateral type")
                        break
            
            # If still no match, use the first silo as a last resort
            if not matching_silo and silos:
                matching_silo = silos[0]
                logger.warning(f"No matching silo for {token} and collateral type {collateral_type.name}, using first available silo")
            
            if not matching_silo:
                raise ValueError(f"No suitable silo found for token {token} in market {self.market_id}")
                
            silo_address = matching_silo["silo_address"]
            logger.info(f"Found matching silo for {token}: {silo_address}")
            
            # Create ERC20 token contract
            with open(ABI_DIR / 'ERC20.json') as f:
                token_contract = self.w3.eth.contract(
                    address=token_address,
                    abi=json.load(f)
                )
            
            # Get and log balance
            decimals = token_contract.functions.decimals().call()
            balance = token_contract.functions.balanceOf(self.account.address).call()
            balance_human = balance / 10**decimals
            
            logger.info(f"Current wallet balance: {balance_human} {token}")
            logger.info(f"Attempting to supply: {amount} {token}")
            
            amount_wei = int(amount * 10**decimals)
            if balance < amount_wei:
                raise ValueError(f"Insufficient balance: have {balance_human}, need {amount} {token}")
            
            # Check allowance and approve if needed
            allowance = token_contract.functions.allowance(
                self.account.address,
                silo_address
            ).call()
            
            if allowance < amount_wei:
                logger.info(f"Approving {token} for Silo at {silo_address}")
                approve_tx = token_contract.functions.approve(
                    silo_address,
                    amount_wei
                )
                self._send_transaction(approve_tx)
            
            # Now deposit into Silo
            return self.deposit(silo_address, amount)
            
        except Exception as e:
            logger.error(f"Error in supply operation for {token} on {self.network}: {str(e)}")
            return None
    
    def withdraw_token(self, token: str, amount: float, collateral_type: CollateralType = CollateralType.PROTECTED) -> Optional[str]:
        """
        Withdraw specific token from Silo market
        
        Args:
            token: Token symbol or address
            amount: Amount to withdraw (in asset tokens)
            collateral_type: Type of collateral (STANDARD or PROTECTED)
            
        Returns:
            Transaction hash or None if operation failed
        """
        try:
            # Find appropriate Silo for the token
            silo_address = None
            silos = self.find_silos_for_market(self.market_id)
            
            # Try to find exact match by token symbol and collateral type
            for silo in silos:
                silo_info = self.get_silo_info(silo)
                if silo_info and 'symbol' in silo_info:
                    symbol = silo_info['symbol']
                    if token.upper() in symbol.upper():
                        silo_type = "STANDARD" if collateral_type == CollateralType.STANDARD else "PROTECTED"
                        if silo_type in symbol.upper():
                            silo_address = silo
                            logger.info(f"Found exact matching silo for {token}: {silo_address}")
                            break
            
            # If no exact match, try to find by collateral type
            if not silo_address:
                for silo in silos:
                    silo_info = self.get_silo_info(silo)
                    if silo_info:
                        # Check if this is the right type of silo (Protected/Standard)
                        if collateral_type == CollateralType.PROTECTED and "PROTECTED" in str(silo_info).upper():
                            silo_address = silo
                            logger.info(f"Found protected silo: {silo_address}")
                            break
                        elif collateral_type == CollateralType.STANDARD and "STANDARD" in str(silo_info).upper():
                            silo_address = silo
                            logger.info(f"Found standard silo: {silo_address}")
                            break
            
            # If still no match, use the first available silo
            if not silo_address and silos:
                silo_address = silos[0]
                logger.warning(f"No matching silo found for {token}, using first available: {silo_address}")
            
            if not silo_address:
                raise ValueError(f"No silos found for market {self.market_id}")
            
            # Check maximum withdrawable amount
            max_withdraw = self.get_max_withdraw(silo_address, collateral_type)
            if max_withdraw is None:
                raise ValueError(f"Failed to get maximum withdrawable amount from silo {silo_address}")
                
            logger.info(f"Maximum withdrawable amount: {max_withdraw}")
            
            # Adjust amount if necessary
            if amount > max_withdraw:
                logger.warning(f"Withdrawal amount ({amount}) exceeds maximum withdrawable amount ({max_withdraw}). Using maximum.")
                amount = max_withdraw
                
            if amount <= 0:
                logger.warning("Nothing to withdraw")
                return None
            
            # Execute withdrawal using the redeem function
            return self.withdraw(silo_address, amount, collateral_type)
            
        except Exception as e:
            logger.error(f"Error withdrawing {token}: {e}")
            return None
    
    def get_token_balance(self, token: str, collateral_type: CollateralType = CollateralType.PROTECTED) -> Optional[float]:
        """
        Get token balance in Silo
        
        Args:
            token: Token symbol (e.g. 'USDC.E')
            collateral_type: Type of collateral, PROTECTED (1) by default for stablecoins
            
        Returns:
            Balance as float, or None if an error occurred
        """
        try:
            logger.info(f"Getting balance for {token} in Silo market {self.market_id} on {self.network}")
            
            # Find Silo for this token and market
            silos = self.find_silos_for_market(self.market_id)
            
            # Filter silos to find the one matching our token and collateral type
            matching_silo = None
            for silo in silos:
                silo_type = silo.get("silo_type")
                token_info = silo.get("token_info", {})
                
                # Check if token symbol or name contains our token
                symbol = token_info.get("symbol", "").upper()
                name = token_info.get("name", "").upper()
                silo_symbol = token_info.get("silo_symbol", "").upper()
                silo_name = token_info.get("silo_name", "").upper()
                
                # Use different checks depending on token type
                if token in ["USDC", "USDC.E", "USDT", "USDT.E", "DAI"]:
                    # For stablecoins, prefer matching by symbol and type
                    if (
                        (token in symbol or token in name or token in silo_symbol or token in silo_name) and
                        silo_type == collateral_type.value
                    ):
                        matching_silo = silo
                        break
                else:
                    # For other tokens, match by symbol
                    if token in symbol or token in name or token in silo_symbol or token in silo_name:
                        matching_silo = silo
                        break
            
            # If no match by token name, use collateral type as fallback
            if not matching_silo:
                for silo in silos:
                    if silo.get("silo_type") == collateral_type.value:
                        matching_silo = silo
                        logger.warning(f"No exact match for {token}, using silo with correct collateral type")
                        break
            
            # If still no match, use the first silo as a last resort
            if not matching_silo and silos:
                matching_silo = silos[0]
                logger.warning(f"No matching silo for {token} and collateral type {collateral_type.name}, using first available silo")
            
            if not matching_silo:
                raise ValueError(f"No suitable silo found for token {token} in market {self.market_id}")
                
            silo_address = matching_silo["silo_address"]
            logger.info(f"Found matching silo for {token}: {silo_address}")
            
            # Get balance
            return self.get_silo_balance(silo_address)
            
        except Exception as e:
            logger.error(f"Error getting balance for {token} on {self.network}: {str(e)}")
            return None

    def deposit(self, silo_address: str, amount: float) -> Optional[str]:
        """
        Deposit funds into Silo
        
        Args:
            silo_address: Silo contract address
            amount: Amount to deposit
            
        Returns:
            Transaction hash or None in case of error
        """
        try:
            if not Web3.is_checksum_address(silo_address):
                silo_address = Web3.to_checksum_address(silo_address)
            
            # Load ABI for Silo
            with open(ABI_DIR / "Silo.json") as f:
                silo_abi = json.load(f)
            
            # Create contract
            silo = self.w3.eth.contract(
                address=silo_address,
                abi=silo_abi
            )
            
            # Get token address and log it
            token_address = silo.functions.asset().call()
            logger.info(f"Underlying token address: {token_address}")
            
            # Get silo decimals for reference
            silo_decimals = silo.functions.decimals().call()
            logger.info(f"Silo decimals: {silo_decimals}")
            
            # Get token contract and decimals
            token_contract = self.w3.eth.contract(
                address=token_address,
                abi=json.load(open(ABI_DIR / "ERC20.json"))
            )
            
            token_decimals = token_contract.functions.decimals().call()
            logger.info(f"Token decimals: {token_decimals}")
            
            # Always use token decimals for amount conversion
            amount_wei = int(amount * 10**token_decimals)
            logger.info(f"Amount in wei (using token decimals): {amount_wei}")
            
            # Check balance
            balance = token_contract.functions.balanceOf(self.account.address).call()
            balance_human = balance / 10**token_decimals
            logger.info(f"Current token balance: {balance_human}")
            
            # Check if enough balance
            if balance < amount_wei:
                error_msg = f"Insufficient funds: have {balance_human}, need {amount}"
                logger.error(error_msg)
                raise ValueError(error_msg)
            
            # Check allowance
            allowance = token_contract.functions.allowance(
                self.account.address,
                silo_address
            ).call()
            logger.info(f"Current allowance: {allowance}")
            
            # Approve if needed
            if allowance < amount_wei:
                logger.info(f"Approving token for Silo, amount: {amount_wei}")
                approve_tx = token_contract.functions.approve(
                    silo_address,
                    amount_wei
                )
                self._send_transaction(approve_tx)
            
            # Execute deposit
            logger.info(f"Depositing {amount} into Silo {silo_address}")
            
            # Use deposit function
            deposit_tx = silo.functions.deposit(
                amount_wei,
                self.account.address
            )
            
            return self._send_transaction(deposit_tx)
        except Exception as e:
            logger.error(f"Error depositing into Silo {silo_address}: {e}")
            return None
    
    def withdraw(self, silo_address: str, amount: float, collateral_type: CollateralType = CollateralType.PROTECTED, force_withdrawal: bool = False) -> Optional[str]:
        """
        Withdraw funds from Silo using the redeem function
        
        Args:
            silo_address: Silo contract address
            amount: Amount to withdraw (in asset tokens)
            collateral_type: Type of collateral (STANDARD or PROTECTED)
            force_withdrawal: If True, attempts to withdraw the full requested amount even if not all 
                              is immediately available. The protocol may fulfill this partially.
        
        Returns:
            Transaction hash or None in case of error
        """
        try:
            if not Web3.is_checksum_address(silo_address):
                silo_address = Web3.to_checksum_address(silo_address)
            
            # Load ABI for Silo
            with open(ABI_DIR / "Silo.json") as f:
                silo_abi = json.load(f)
            
            # Create contract
            silo = self.w3.eth.contract(
                address=silo_address,
                abi=silo_abi
            )
            
            # Get withdrawal info
            withdrawal_info = self.get_withdrawal_info(silo_address, collateral_type)
            total_balance = withdrawal_info['total_balance']
            max_withdraw = withdrawal_info['available_balance']
            
            if not force_withdrawal:
                # Check if requested amount exceeds available amount
                if amount > max_withdraw:
                    logger.warning(f"Withdrawal amount ({amount}) exceeds maximum withdrawable amount ({max_withdraw}). Using maximum.")
                    amount = max_withdraw
                    
                if amount <= 0:
                    logger.warning(f"Nothing to withdraw (amount: {amount})")
                    return None
            else:
                # For force withdrawal, we'll try with the full amount but inform the user
                if amount > max_withdraw:
                    logger.warning(f"Forced withdrawal of {amount} requested, but only {max_withdraw} is immediately available.")
                    logger.warning(f"Protocol will likely fulfill only {max_withdraw / amount * 100:.2f}% of the request.")
                    
                # Cap at total balance
                if amount > total_balance:
                    logger.warning(f"Requested amount {amount} exceeds total balance {total_balance}. Using total balance.")
                    amount = total_balance
                
                if amount <= 0:
                    logger.warning(f"Nothing to withdraw (amount: {amount})")
                    return None
            
            # Get token address for decimals
            token_address = silo.functions.asset().call()
            logger.info(f"Underlying token address: {token_address}")
            
            # Get token contract and decimals
            token_contract = self.w3.eth.contract(
                address=token_address,
                abi=json.load(open(ABI_DIR / "ERC20.json"))
            )
            
            token_decimals = token_contract.functions.decimals().call()
            logger.info(f"Token decimals: {token_decimals}")
            
            # Convert amount to shares
            amount_wei = int(amount * 10**token_decimals)
            logger.info(f"Amount in wei (using token decimals): {amount_wei}")
            
            # Try to convert assets to shares
            try:
                shares = silo.functions.convertToShares(amount_wei).call()
                logger.info(f"Converting {amount} assets to {shares/(10**token_decimals)} shares")
            except Exception as e:
                logger.warning(f"Failed to convert assets to shares: {e}")
                # Fallback to using amount_wei directly
                shares = amount_wei
                logger.info(f"Using direct conversion for shares: {shares}")
            
            # Use redeem function
            logger.info(f"Redeeming {shares/(10**token_decimals)} shares from Silo {silo_address}")
            logger.info(f"Collateral type: {collateral_type.name}")
            
            # Build and execute transaction
            tx_func = silo.functions.redeem(
                shares,  # shares amount
                self.account.address,  # receiver
                self.account.address,  # owner
                int(collateral_type.value)  # collateral type as uint8
            )
            
            return self._send_transaction(tx_func)
        except Exception as e:
            logger.error(f"Error withdrawing from Silo {silo_address}: {e}")
            return None
    
    def get_max_withdraw(self, silo_address: str, collateral_type: CollateralType = CollateralType.PROTECTED) -> Optional[float]:
        """
        Get maximum withdrawable amount from a Silo
        
        Args:
            silo_address: Silo contract address
            collateral_type: Type of collateral (STANDARD or PROTECTED)
            
        Returns:
            Maximum withdrawable amount in human-readable format or None if error
        """
        try:
            if not Web3.is_checksum_address(silo_address):
                silo_address = Web3.to_checksum_address(silo_address)
            
            # Load ABI for Silo
            with open(ABI_DIR / "Silo.json") as f:
                silo_abi = json.load(f)
            
            # Create contract
            silo = self.w3.eth.contract(
                address=silo_address,
                abi=silo_abi
            )
            
            # Try to use maxWithdraw first (ERC4626 standard)
            try:
                # Call maxWithdraw function
                max_withdraw_wei = silo.functions.maxWithdraw(
                    self.account.address,
                    int(collateral_type.value)
                ).call()
                
                # Convert to human-readable format
                decimals = silo.functions.decimals().call()
                max_withdraw = max_withdraw_wei / 10**decimals
                
                logger.info(f"Maximum withdrawable amount: {max_withdraw}")
                return max_withdraw
            except Exception as e:
                logger.warning(f"Error calling maxWithdraw: {e}")
                
                # Fallback: try to get balance as maxWithdraw alternative
                try:
                    balance_wei = silo.functions.balanceOf(self.account.address).call()
                    decimals = silo.functions.decimals().call()
                    balance = balance_wei / 10**decimals
                    
                    logger.info(f"Using balance as max withdrawable amount: {balance}")
                    return balance
                except Exception as e2:
                    logger.error(f"Error getting balance: {e2}")
                    return None
        except Exception as e:
            logger.error(f"Error determining maximum withdrawable amount: {e}")
            return None
    
    def get_silo_balance(self, silo_address: str, account: Optional[str] = None) -> Optional[float]:
        """
        Get balance in Silo for the given account
        
        Args:
            silo_address: Silo contract address
            account: Account address (optional, defaults to current account)
            
        Returns:
            Balance in human-readable format or None if error
        """
        try:
            if not Web3.is_checksum_address(silo_address):
                silo_address = Web3.to_checksum_address(silo_address)
            
            # Load ABI for Silo
            with open(ABI_DIR / "Silo.json") as f:
                silo_abi = json.load(f)
            
            # Create contract
            silo = self.w3.eth.contract(
                address=silo_address,
                abi=silo_abi
            )
            
            # Use the provided account or default to current account
            account_address = account if account else self.account.address
            
            # Call balanceOf function
            balance_wei = silo.functions.balanceOf(account_address).call()
            
            # Get decimals
            decimals = silo.functions.decimals().call()
            
            # Convert to human-readable format
            balance = balance_wei / 10**decimals
            
            return balance
        except Exception as e:
            logger.error(f"Error getting balance from Silo {silo_address}: {e}")
            return None

    def get_withdrawal_info(self, silo_address: str, collateral_type: CollateralType = CollateralType.PROTECTED) -> Dict[str, Any]:
        """
        Get comprehensive information about withdrawal options from a Silo
        
        Args:
            silo_address: Silo contract address
            collateral_type: Type of collateral (STANDARD or PROTECTED)
            
        Returns:
            Dictionary containing total balance, available balance, and liquidity percentage
        """
        try:
            if not Web3.is_checksum_address(silo_address):
                silo_address = Web3.to_checksum_address(silo_address)
            
            # Load ABI for Silo
            with open(ABI_DIR / "Silo.json") as f:
                silo_abi = json.load(f)
            
            # Create contract
            silo = self.w3.eth.contract(
                address=silo_address,
                abi=silo_abi
            )
            
            # Get total balance (in share tokens)
            share_balance_wei = silo.functions.balanceOf(self.account.address).call()
            decimals = silo.functions.decimals().call()
            share_balance = share_balance_wei / 10**decimals
            
            # Get total assets this represents
            try:
                # Try to use previewRedeem function if available (ERC4626 standard)
                total_assets_wei = silo.functions.previewRedeem(share_balance_wei).call()
            except Exception:
                try:
                    # Fallback to convertToAssets
                    total_assets_wei = silo.functions.convertToAssets(share_balance_wei).call()
                except Exception:
                    # Final fallback - use balanceOf as share balance
                    total_assets_wei = share_balance_wei
            
            # Get token decimals to convert to human-readable format
            token_address = silo.functions.asset().call()
            token_contract = self.w3.eth.contract(
                address=token_address,
                abi=json.load(open(ABI_DIR / "ERC20.json"))
            )
            token_decimals = token_contract.functions.decimals().call()
            
            total_assets = total_assets_wei / 10**token_decimals
            
            # Get maximum withdrawable amount
            max_withdraw_wei = silo.functions.maxWithdraw(
                self.account.address,
                int(collateral_type.value)
            ).call()
            max_withdraw = max_withdraw_wei / 10**token_decimals
            
            # Calculate liquidity percentage
            liquidity_percentage = (max_withdraw / total_assets * 100) if total_assets > 0 else 0
            
            result = {
                "total_balance": total_assets,
                "available_balance": max_withdraw,
                "liquidity_percentage": liquidity_percentage,
                "token_decimals": token_decimals,
                "silo_decimals": decimals,
                "shares": share_balance
            }
            
            logger.info(f"Withdrawal info for Silo {silo_address}: {result}")
            return result
            
        except Exception as e:
            logger.error(f"Error getting withdrawal info: {e}")
            return {
                "total_balance": 0,
                "available_balance": 0,
                "liquidity_percentage": 0,
                "error": str(e)
            }


class RhoOperator(BaseProtocolOperator):
    """Class for working with Rho protocol"""
    
    def supply(self, token: str, amount: float) -> str:
        """Supply tokens to Rho protocol"""
        token_address = get_token_address(token, self.network)
        amount_wei = self._convert_to_wei(token_address, amount)
        
        # Проверяем баланс
        # Create token contract
        with open(ABI_DIR / 'ERC20.json') as f:
            token_contract = self.w3.eth.contract(
                address=token_address,
                abi=json.load(f)
            )
        
        decimals = token_contract.functions.decimals().call()
        balance = token_contract.functions.balanceOf(self.account.address).call()
        balance_human = balance / 10**decimals
        
        logger.info(f"Current balance of {token}: {balance_human}")
        
        if balance < amount_wei:
            logger.error(f"Insufficient {token} balance: {balance_human}, needed: {amount}")
            raise ValueError(f"Insufficient {token} balance")
        
        rho_market_address = RHO_ADDRESSES[self.network][token.lower()]
        
        # Проверяем разрешение на использование токенов
        allowance = token_contract.functions.allowance(
            self.account.address, rho_market_address
        ).call()


        rho_market_contract = self.w3.eth.contract(
            address=rho_market_address,
            abi=json.load(open(ABI_DIR / 'ERC20-rhoMarket.json'))
        )
        
        if allowance < amount_wei:
            approve_tx = token_contract.functions.approve(
                rho_market_address, amount_wei * 2  # С запасом
            )
            
            approve_hash = self._send_transaction(approve_tx)
            logger.info(f"Approved {token} for Rho: {approve_hash}")
        
        # Выполняем поставку токенов
        supply_tx = rho_market_contract.functions.mint(amount_wei)
        return self._send_transaction(supply_tx)
    
    def withdraw(self, token: str, amount: float) -> str:
        """Withdraw funds from protocol"""
        try:
            token_address = get_token_address(token, self.network)
            
            # Check token support in pool
            logger.info(f"Checking if token {token} ({token_address}) is supported in {self.network} pool")
    
            rho_market_address = RHO_ADDRESSES[self.network][token.lower()]
            rho_market_contract = self.w3.eth.contract(
                address=rho_market_address,
                abi=json.load(open(ABI_DIR / 'ERC20-rhoMarket.json'))
            )
            
            # Use direct call() as in get_balance
            decimals = rho_market_contract.functions.decimals().call()
            balance = rho_market_contract.functions.balanceOf(self.account.address).call()
            logger.info(f"Current wallet balance: {balance/10**decimals} {token} in {self.protocol} {token} makret")

            amount_wei = self._convert_to_wei(token_address, amount)
            
            if balance < amount_wei:
                raise ValueError(f"Insufficient balance: have {balance / 10 ** decimals}, need {amount_wei / 10 ** decimals}")
            
            # Execute withdrawal
            tx_func = rho_market_contract.functions.redeem(
                amount_wei,
            )
            
            return self._send_transaction(tx_func)
            
        except Exception as e:
            logger.error(f"Withdrawal failed for {token} on {self.network}: {str(e)}")
            raise

class CompoundOperator(BaseProtocolOperator):
    """Class for working with Compound III protocol"""
    

    def get_protocol_balance(self, token: str) -> float:
        """
        Get user balance for a specific token in Compound protocol
        
        Args:
            token: Token symbol (e.g., 'USDC')
            
        Returns:
            Balance as float
        """
        try:
            # Получаем адрес токена из словаря STABLECOINS
            if token in STABLECOINS and self.network in STABLECOINS[token]:
                token_address = STABLECOINS[token][self.network]
            else:
                token_address = get_token_address(token, self.network)
                
            logger.info(f"Checking balance for token {token} ({token_address}) in Compound")
            
            
            # Create token contract
            with open(ABI_DIR / 'ERC20.json') as f:
                token_contract = self.w3.eth.contract(
                    address=token_address,
                    abi=json.load(f)
                )
            
            # Get and log balance
            balance = token_contract.functions.balanceOf(self.account.address).call()
            decimals = token_contract.functions.decimals().call()
            
            # Для базового токена (обычно USDC) вызываем balanceOf
            balance_wei = self.contract.functions.balanceOf(self.account.address).call()
            balance_human = balance_wei / 10**decimals
 
            logger.info(f"User balance for {token}: {balance_human} in protocol {self.protocol}")
            
            return balance
        except Exception as e:
            logger.error(f"Error getting protocol balance for {token}: {e}")
            return 0.0

    def supply(self, token: str, amount: float) -> str:
        """Supply tokens to Compound protocol"""
        token_address = get_token_address(token, self.network)
        amount_wei = self._convert_to_wei(token_address, amount)
        
        # Проверяем баланс
        # Create token contract
        with open(ABI_DIR / 'ERC20.json') as f:
            token_contract = self.w3.eth.contract(
                address=token_address,
                abi=json.load(f)
            )
        
        decimals = token_contract.functions.decimals().call()
        balance = token_contract.functions.balanceOf(self.account.address).call()
        balance_human = balance / 10**decimals
        
        logger.info(f"Current balance of {token}: {balance_human}")
        
        if balance < amount_wei:
            logger.error(f"Insufficient {token} balance: {balance_human}, needed: {amount}")
            raise ValueError(f"Insufficient {token} balance")
        
        # Проверяем разрешение на использование токенов
        allowance = token_contract.functions.allowance(
            self.account.address, self.contract_address
        ).call()
        
        if allowance < amount_wei:
            approve_tx = token_contract.functions.approve(
                self.contract_address, amount_wei * 2  # С запасом
            )
            
            approve_hash = self._send_transaction(approve_tx)
            logger.info(f"Approved {token} for Compound: {approve_hash}")
        
        # Выполняем поставку токенов
        supply_tx = self.contract.functions.supply(token_address, amount_wei)
        return self._send_transaction(supply_tx)
    
    def withdraw(self, token: str, amount: float) -> str:
        """Withdraw tokens from Compound protocol"""

        token_address = get_token_address(token, self.network)
        amount_wei = self._convert_to_wei(token_address, amount)
        
        # Проверяем баланс
        # Create token contract
        with open(ABI_DIR / 'ERC20.json') as f:
            token_contract = self.w3.eth.contract(
                address=token_address,
                abi=json.load(f)
            )
        
        decimals = token_contract.functions.decimals().call()
        balance = token_contract.functions.balanceOf(self.account.address).call()
        balance_human = balance / 10**decimals
        
        logger.info(f"Current {token} balance in Compound: {balance_human}")
        
        # Если запрошено 0 или больше баланса, используем весь доступный баланс
        if amount <= 0 or amount > balance_human:
            amount = balance_human
            logger.info(f"Adjusting withdrawal to available balance: {amount}")
        
        
        # Выполняем вывод
        withdraw_tx = self.contract.functions.withdraw(token_address, amount_wei)
        return self._send_transaction(withdraw_tx)
    

def get_protocol_operator(network: str, protocol: str, **kwargs):
    """
    Factory function to get the appropriate protocol operator
    """
    try:
        if protocol == 'aave-v3':
            return AaveOperator(network, protocol)
        elif protocol == 'lendle':
            return LendleOperator(network, protocol)
        elif protocol == 'compound-v3':
            return CompoundOperator(network, protocol)
        elif protocol == 'silo-v2':
            market_id = kwargs.get('market_id')
            return SiloOperator(network, market_id)
        elif protocol == 'curve':
            pool_name = kwargs.get('pool_name')
            return CurveOperator(network, pool_name)
        elif protocol == 'uniswap-v3':
            return UniswapV3Operator(network, protocol)
        elif protocol == 'rho':
            return RhoOperator(network, protocol)
        else:
            available_protocols = list(SUPPORTED_PROTOCOLS.keys())
            raise ValueError(f"Unknown protocol: {protocol}. Available: {', '.join(available_protocols)}")
    except ValueError as e:
        raise e  # Пробрасываем ошибку из BaseProtocolOperator без изменений
    except Exception as e:
        raise ValueError(f"Error initializing {protocol} on {network}: {str(e)}")




def main():
    # compoud_operator = get_protocol_operator('Scroll', 'compound-v3')
    # print(compoud_operator.get_protocol_balance('USDC'))

    # compoud_operator.supply('USDC', 5)
    # compoud_operator.withdraw('USDC', 5)

    # aave_operator = get_protocol_operator('Scroll', 'aave-v3')
    # print(aave_operator.supply('USDC', 5))
    # rho_operator = get_protocol_operator('Scroll', 'rho')
    # print(rho_operator.supply('USDC', 5))

    # rho_operator.withdraw('USDC', 4.520983)
    # aave_operator.withdraw('USDC', 5)

    uniswap_operator = get_protocol_operator('Scroll', 'uniswap-v3')
    print(uniswap_operator)
    uniswap_operator.withdraw('USDC', 0.3)



if __name__ == "__main__":
    sys.exit(main())
