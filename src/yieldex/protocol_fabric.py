import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional, List

from web3 import Web3
from web3.contract import Contract

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
        abi_map = {
            'aave-v3': 'AaveV3Pool.json',
            'aave-v2': 'AaveV2LendingPool.json',
            'lendle': 'LendleLendingPool.json',
            'yieldex-oracle': 'YieldexOracle.json'
        }
        abi_path = ABI_DIR / abi_map[self.protocol]
        
        with open(abi_path) as f:
            abi = json.load(f)
            
        return self.w3.eth.contract(
            address=self.contract_address,
            abi=abi
        )
        
    def _get_gas_params(self) -> Dict[str, Any]:
        """Get gas parameters for different networks"""
        base_params = {
            'from': self.account.address,
            'nonce': self.w3.eth.get_transaction_count(self.account.address),
            'chainId': self.w3.eth.chain_id
        }

        # Use a simple gasPrice for Arbitrum, Optimism, and Mantle
        if self.network in ['Arbitrum', 'Optimism', 'Mantle']:
            base_params['gasPrice'] = self.w3.eth.gas_price
        else:
            # Use EIP-1559 parameters for networks that support it
            base_params['maxFeePerGas'] = self.w3.eth.gas_price
            # Make sure the priority fee is not more than the base gas price
            base_params['maxPriorityFeePerGas'] = min(
                self.w3.to_wei(1, 'gwei'),
                base_params['maxFeePerGas']
            )
        
        return base_params

    def _send_transaction(self, tx_function) -> str:
        try:
            tx_params = self._get_gas_params()
            tx_params['gas'] = int(tx_function.estimate_gas(tx_params) * 1.2)
            
            signed_tx = self.w3.eth.account.sign_transaction(
                tx_function.build_transaction(tx_params),
                private_key=self.account.key
            )
            
            tx_hash = self.w3.eth.send_raw_transaction(signed_tx.raw_transaction)
            
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)
            if receipt.status != 1:
                raise Exception(f"Transaction reverted: {receipt.transactionHash.hex()}")
                
            return tx_hash.hex()
            
        except Exception as e:
            logger.error(f"Transaction failed: {str(e)}")
            raise

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
        token_address = STABLECOINS[token][self.network]
        amount_wei = self._convert_to_wei(token_address, amount)
        
        tx_func = self.contract.functions.withdraw(
            token_address,
            amount_wei,
            self.account.address
        )
        
        return self._send_transaction(tx_func)
        
    def _convert_to_wei(self, token_address: str, amount: float) -> int:
        """Convert amount to wei considering token decimals"""
        erc20 = self.w3.eth.contract(
            address=token_address,
            abi=json.load(open(ABI_DIR / 'ERC20.json'))
        )
        decimals = erc20.functions.decimals().call()
        return int(amount * 10 ** decimals)

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

def get_protocol_operator(network: str, protocol: str):
    """Factory for getting protocol operator"""
    protocol_map = {
        'aave-v3': AaveOperator,
        'aave-v2': AaveOperator,
        'lendle': LendleOperator
    }
    
    if protocol not in protocol_map:
        raise ValueError(f"Unsupported protocol: {protocol}")
        
    return protocol_map[protocol](network, protocol)


if __name__ == "__main__":
    oracle = YieldexOracleOperator('Mantle')
    print(oracle.w3.is_connected())
