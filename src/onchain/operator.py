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
                                RPC_URLS, STABLECOINS, SUPABASE_KEY,
                                SUPABASE_URL)
# from src.yieldex.data_collector import save_my_pool_balance
from onchain.protocol_fabric import AaveOperator, UniswapV3Operator
from common.utils import get_token_address

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
            # Increase gas limit for L2 networks
            gas_price = self.w3.eth.gas_price
            base_params['gasPrice'] = int(gas_price * 1.3)  # +30% to current gas price
        else:
            base_params['maxFeePerGas'] = self.w3.eth.gas_price
            base_params['maxPriorityFeePerGas'] = self.w3.to_wei(1, 'gwei')
            
        return base_params

    def _send_transaction(self, tx_function) -> str:
        """Universal method for sending transactions"""
        try:
            tx_params = self._get_gas_params()
            
            # Increase gas limit and add buffer
            try:
                estimated_gas = tx_function.estimate_gas(tx_params)
                tx_params['gas'] = int(estimated_gas * 1.5)  # +50% to estimated gas
            except Exception as e:
                logger.warning(f"Failed to estimate gas, using default: {str(e)}")
                tx_params['gas'] = 2000000  # Set safe default value
            
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
        try:
            # Check connection
            if not self.w3.is_connected():
                raise ConnectionError(f"Not connected to {self.network}")
            
            # Check if address is valid
            if not Web3.is_checksum_address(token_address):
                token_address = Web3.to_checksum_address(token_address)
            
            # Check if contract code exists at address
            if self.w3.eth.get_code(token_address) == b'':
                raise ValueError(f"No contract at address {token_address}")
            
            token_contract = self._get_token_contract(token_address)
            
            # Check if we can call decimals()
            try:
                decimals = token_contract.functions.decimals().call()
            except Exception as e:
                logger.error(f"Failed to get decimals: {str(e)}")
                raise
            
            balance_wei = token_contract.functions.balanceOf(self.account.address).call()
            return balance_wei / 10 ** decimals
            
        except Exception as e:
            logger.error(f"Failed to get balance for {token_address}: {str(e)}")
            raise

def execute_uniswap_flow(recommendation: dict):
    """Execute full swap flow using Uniswap V3"""
    try:
        chain = recommendation['from_chain']
        asset = recommendation['asset']
        to_asset = recommendation['to_asset']
        amount = recommendation['position_size']
        
        logger.info(f"Starting Uniswap flow for {amount} {asset} on {chain}")
        
        # Initialize operator and check token support
        aave_operator = AaveOperator(chain, 'aave-v3')
        token_address = get_token_address(asset, chain)
        
        if not aave_operator._check_token_support(token_address):
            raise ValueError(f"Token {asset} not supported in {chain} pool")
            
        # Execute withdrawal
        withdraw_tx = aave_operator.withdraw(asset, amount)
        logger.info(f"Withdrawal successful: {withdraw_tx}")
        
        # Execute swap
        uniswap_operator = UniswapV3Operator(chain, 'uniswap-v3')
        swap_tx = uniswap_operator.swap(asset, to_asset, amount, 0.1)
        logger.info(f"Swap successful: {swap_tx}")

        # Execute deposit
        deposit_tx = aave_operator.supply(to_asset, amount)
        logger.info(f"Deposit successful: {deposit_tx}")

        return {'withdraw_tx': withdraw_tx, 'swap_tx': swap_tx, 'deposit_tx': deposit_tx}

    except Exception as e:
        logger.error(f"Failed to execute Uniswap flow: {str(e)}")
        raise


if __name__ == "__main__":

    recommendations = get_recommendations()
    for recomedation in recommendations:
        print(recomedation)
        execute_uniswap_flow(recomedation)







