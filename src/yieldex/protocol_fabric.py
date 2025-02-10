import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional, List
from web3 import Web3
from web3.contract import Contract
from .utils import get_token_address

from .config import (PRIVATE_KEY, RPC_URLS, STABLECOINS, 
                    SUPPORTED_PROTOCOLS, BLOCK_EXPLORERS, YIELDEX_ORACLE_ADDRESS)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

ABI_DIR = Path(__file__).parent / "abi"

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
                'uniswap-v3': 'UniswapV3Router.json'
            }
            
            if self.protocol not in abi_map:
                raise ValueError(f"Unsupported protocol: {self.protocol}")
            
            abi_path = ABI_DIR / abi_map[self.protocol]
            
            if not abi_path.exists():
                raise FileNotFoundError(f"ABI file not found: {abi_path}")
            
            with open(abi_path) as f:
                abi = json.load(f)
            
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
                # Try calling a view method
                if self.protocol in ['aave-v3', 'aave-v2', 'lendle']:
                    contract.functions.getReserveData(
                        self.w3.to_checksum_address(
                            STABLECOINS['USDT'][self.network]
                        )
                    ).call()
            except Exception as e:
                logger.error(f"Contract verification failed: {str(e)}")
                raise ValueError(f"Contract not accessible on {self.network}")
            
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

def get_protocol_operator(network: str, protocol: str):
    """Factory for getting protocol operator"""
    protocol_map = {
        'aave-v3': AaveOperator,
        'aave-v2': AaveOperator,
        'lendle': LendleOperator,
        'curve': CurveOperator,
        'uniswap-v3': UniswapV3Operator
    }
    
    if protocol not in protocol_map:
        raise ValueError(f"Unsupported protocol: {protocol}")
        
    return protocol_map[protocol](network, protocol)
