# onchain.py
import json
import logging
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import requests
from web3 import Web3
from web3.contract import Contract
from web3.types import TxParams

from src.yieldex.analytics import get_recommendations
from src.yieldex.config import (AAVE_V3_ADDRESSES, LENDLE_POOL_ADDRESS,
                                MANTLE_RPC_URL, POLYGON_RPC_URL, PRIVATE_KEY,
                                RPC_URLS, STABLECOINS, SUPABASE_URL, SUPABASE_KEY)
# from src.yieldex.data_collector import save_my_pool_balance
from src.yieldex.protocol_fabric import AaveOperator, UniswapV3Operator
from src.yieldex.utils import get_token_address

logger = logging.getLogger(__name__)
ABI_DIR = Path(__file__).parent / "abi"

class ERC20Utils:
    """Utility class for working with ERC-20 tokens"""
    
    def __init__(self, network: str):
        self.network = network
        self.w3 = Web3(Web3.HTTPProvider(RPC_URLS.get(network)))
        
        if not self.w3.is_connected():
            raise ConnectionError(f"Failed to connect to {network} RPC")
            
        self.account = self.w3.eth.account.from_key(PRIVATE_KEY)
        
    def _get_token_contract(self, token_address: str) -> Contract:
        """Get ERC-20 token contract"""
        if not Web3.is_checksum_address(token_address):
            token_address = Web3.to_checksum_address(token_address)
        return self.w3.eth.contract(
            address=token_address,
            abi=json.load(open(ABI_DIR / 'ERC20.json'))
        )
    
    def _get_gas_params(self) -> Dict[str, Any]:
        """Get gas parameters for different networks"""
        base_params = {
            'from': self.account.address,
            'nonce': self.w3.eth.get_transaction_count(self.account.address),
            'chainId': self.w3.eth.chain_id
        }
        
        if self.network in ['Arbitrum', 'Optimism']:
            # Увеличиваем лимит газа для L2 сетей
            gas_price = self.w3.eth.gas_price
            base_params['gasPrice'] = int(gas_price * 1.2)  # +20% к текущей цене газа
        else:
            base_params['maxFeePerGas'] = self.w3.eth.gas_price
            base_params['maxPriorityFeePerGas'] = self.w3.to_wei(1, 'gwei')
            
        return base_params

    def _send_transaction(self, tx_function) -> str:
        """Universal method for sending transactions"""
        try:
            tx_params = self._get_gas_params()
            
            # Увеличиваем лимит газа и добавляем доп. запас
            try:
                estimated_gas = tx_function.estimate_gas(tx_params)
                tx_params['gas'] = int(estimated_gas * 1.5)  # +50% к оценке газа
            except Exception as e:
                logger.warning(f"Failed to estimate gas, using default: {str(e)}")
                tx_params['gas'] = 2000000  # Устанавливаем безопасное значение по умолчанию
            
            signed_tx = self.account.sign_transaction(
                tx_function.build_transaction(tx_params)
            )
            
            tx_hash = self.w3.eth.send_raw_transaction(signed_tx.raw_transaction)
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)
            
            if receipt.status != 1:
                raise Exception("Transaction reverted")
                
            return tx_hash.hex()
            
        except Exception as e:
            logger.error(f"Transaction failed: {str(e)}")
            raise

    def approve_token(self, token_address: str, spender_address: str, amount: float) -> str:
        """Approve token for specified protocol contract"""
        token_contract = self._get_token_contract(token_address)
        decimals = token_contract.functions.decimals().call()
        amount_wei = int(amount * 10 ** decimals)
        
        tx_func = token_contract.functions.approve(spender_address, amount_wei)
        return self._send_transaction(tx_func)
        
    def get_balance(self, token_address: str) -> float:
        """Get token balance for current account"""
        token_contract = self._get_token_contract(token_address)
        decimals = token_contract.functions.decimals().call()
        balance_wei = token_contract.functions.balanceOf(self.account.address).call()
        return balance_wei / 10 ** decimals
    
def execute_uniswap_flow(recommendation: dict):
    """Execute full swap flow using Uniswap V3"""
    try:
        chain = recommendation['from_chain']
        asset = recommendation['asset']
        amount = recommendation['position_size']
        
        logger.info(f"Starting Uniswap flow for {amount} {asset} on {chain}")
        
        # Инициализируем оператора и проверяем токен
        aave_operator = AaveOperator(chain, 'aave-v3')
        token_address = get_token_address(asset, chain)
        
        if not aave_operator._check_token_support(token_address):
            raise ValueError(f"Token {asset} not supported in {chain} pool")
            
        # Выполняем вывод
        withdraw_tx = aave_operator.withdraw(asset, amount)
        logger.info(f"Withdrawal successful: {withdraw_tx}")
        
        return {'withdraw_tx': withdraw_tx}
        
    except Exception as e:
        logger.error(f"Failed to execute Uniswap flow: {str(e)}")
        raise


if __name__ == "__main__":
    recommendations = get_recommendations()
    for recommendation in recommendations:
        print(recommendation)
        print(execute_uniswap_flow(recommendation))








