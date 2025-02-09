import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional, List
from web3 import Web3
from web3.contract import Contract
from .utils import get_token_address

from .config import PRIVATE_KEY, RPC_URLS, STABLECOINS, SUPPORTED_PROTOCOLS, YIELDEX_ORACLE_ADDRESS

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
            
            # Проверяем адрес контракта
            if not Web3.is_checksum_address(self.contract_address):
                self.contract_address = Web3.to_checksum_address(self.contract_address)
            
            # Создаем контракт
            contract = self.w3.eth.contract(
                address=self.contract_address,
                abi=abi
            )
            
            # Проверяем, что контракт доступен
            try:
                # Пробуем вызвать какой-нибудь view метод
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

        # Для L2 сетей используем gasPrice
        if self.network in ['Arbitrum', 'Optimism', 'Mantle']:
            base_params['gasPrice'] = self.w3.eth.gas_price
        else:
            # Для EVM-сетей используем EIP-1559 с базовыми параметрами
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
        """Simplified transaction sending from old version"""
        try:
            tx_params = self._get_gas_params()
            
            # Базовая оценка газа с фиксированным множителем
            estimated_gas = tx_function.estimate_gas(tx_params)
            tx_params['gas'] = int(estimated_gas * 1.2)  # 20% buffer
            
            signed_tx = self.account.sign_transaction(
                tx_function.build_transaction(tx_params)
            )
            
            tx_hash = self.w3.eth.send_raw_transaction(signed_tx.raw_transaction)
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
            
            if receipt.status != 1:
                logger.error(f"Transaction reverted: {receipt.transactionHash.hex()}")
                raise Exception("Transaction failed")
                
            return tx_hash.hex()
            
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
            
            # Специальная обработка для Arbitrum
            if self.network == 'Arbitrum':
                gas_price = self.w3.eth.gas_price
                params['gasPrice'] = int(gas_price * 1.2)  # +20% к базовой цене газа
                params['gas'] = 3000000  # Увеличенный лимит газа для Arbitrum
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
                # Используем _call_contract для decimals
                decimals = self._call_contract(erc20.functions.decimals())
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
            # Используем _call_contract вместо прямого call
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
            
            # Проверяем поддержку токена в пуле
            logger.info(f"Checking if token {token} ({token_address}) is supported in {self.network} pool")
            reserve_data = self.contract.functions.getReserveData(token_address).call()
            
            # Проверяем конфигурацию резерва
            configuration = reserve_data[0]
            is_active = (configuration >> 56) & 1
            is_frozen = (configuration >> 57) & 1
            atoken_address = reserve_data[7]
            
            if not is_active:
                raise ValueError(f"Token {token} is not active in the pool")
            if is_frozen:
                raise ValueError(f"Token {token} is frozen in the pool")
            if not Web3.is_address(atoken_address) or atoken_address in ['0x0000000000000000000000000000000000000000', '0x0000000000000000000000000000000000000005']:
                raise ValueError(f"Token {token} is not supported in {self.network} pool (invalid aToken address: {atoken_address})")
                
            logger.info(f"Token {token} is supported in {self.network} pool, aToken: {atoken_address}")
            
            amount_wei = self._convert_to_wei(token_address, amount)
            
            # Создаем контракт aToken и получаем баланс
            atoken_contract = self.w3.eth.contract(
                address=atoken_address,
                abi=json.load(open(ABI_DIR / 'ERC20.json'))
            )
            
            decimals = atoken_contract.functions.decimals().call()
            balance = atoken_contract.functions.balanceOf(self.account.address).call()
            logger.info(f"Current balance: {balance/10**decimals} {token}")
            
            if balance < amount_wei:
                raise ValueError(f"Insufficient balance: have {balance/10**decimals}, need {amount_wei/10**decimals}")
            
            # Выполняем вывод средств
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
            # Конвертация в формат контракта (2 знака после запятой)
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
            # Явное кодирование строки и распаковка значений
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
    
    def __init__(self, network: str):
        super().__init__(network, 'uniswap-v3')
        
    def _send_transaction(self, tx_params: Dict) -> str:
        """Send transaction with given parameters"""
        try:
            # Если передан готовый словарь с параметрами
            if isinstance(tx_params, dict):
                # Добавляем gas если его нет
                if 'gas' not in tx_params:
                    tx_params['gas'] = int(self.w3.eth.estimate_gas(tx_params) * 1.2)
                
                signed_tx = self.account.sign_transaction(tx_params)
            else:
                # Если передана функция контракта
                gas_params = self._get_gas_params()
                gas_params['gas'] = int(tx_params.estimate_gas(gas_params) * 1.2)
                signed_tx = self.account.sign_transaction(
                    tx_params.build_transaction(gas_params)
                )
            
            tx_hash = self.w3.eth.send_raw_transaction(signed_tx.raw_transaction)
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)
            
            if receipt.status != 1:
                raise Exception(f"Transaction reverted: {receipt.transactionHash.hex()}")
            
            return tx_hash.hex()
            
        except Exception as e:
            logger.error(f"Transaction failed: {str(e)}")
            raise

    def swap(self, token_in: str, token_out: str, amount_in: float, slippage: float = 0.5) -> str:
        """Execute swap using Uniswap V3 Router"""
        try:
            # Get token addresses
            token_in_addr = get_token_address(token_in, self.network)
            token_out_addr = get_token_address(token_out, self.network)
            
            # Get token contract
            with open(ABI_DIR / 'ERC20.json') as f:
                erc20_abi = json.load(f)
            
            token_contract = self.w3.eth.contract(
                address=token_in_addr,
                abi=erc20_abi
            )
            
            # Get decimals and calculate amount
            decimals = token_contract.functions.decimals().call()
            amount_wei = int(amount_in * 10 ** decimals)
            
            # Check and approve if needed
            allowance = token_contract.functions.allowance(
                self.account.address,
                self.contract_address
            ).call()
            
            if allowance < amount_wei:
                logger.info(f"Approving {token_in} for Uniswap V3")
                # Используем функцию контракта для approve
                approve_func = token_contract.functions.approve(
                    self.contract_address,
                    amount_wei
                )
                tx_hash = self._send_transaction(approve_func)
                logger.info(f"Approval transaction: {tx_hash}")
            
            # Build swap params
            path = bytes.fromhex(
                f"{token_in_addr[2:]}000bb8{token_out_addr[2:]}"
            )  # 0.3% fee tier
            
            deadline = self.w3.eth.get_block('latest')['timestamp'] + 600
            
            params = {
                'path': path,
                'recipient': self.account.address,
                'deadline': deadline,
                'amountIn': amount_wei,
                'amountOutMinimum': int(amount_wei * (1 - slippage/100))
            }
            
            # Execute swap using contract function
            swap_func = self.contract.functions.exactInput(params)
            return self._send_transaction(swap_func)
            
        except Exception as e:
            logger.error(f"Swap failed: {str(e)}")
            raise

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
