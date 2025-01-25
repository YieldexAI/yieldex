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

from src.yieldex.config import (AAVE_V3_ADDRESSES, LENDLE_POOL_ADDRESS,
                                MANTLE_RPC_URL, POLYGON_RPC_URL, PRIVATE_KEY,
                                STABLECOINS, RPC_URLS, get_token_address)
from src.yieldex.data_collector import save_my_pool_balance

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
            base_params['gasPrice'] = self.w3.eth.gas_price
        else:
            base_params['maxFeePerGas'] = self.w3.eth.gas_price
            base_params['maxPriorityFeePerGas'] = self.w3.to_wei(1, 'gwei')
            
        return base_params

    def _send_transaction(self, tx_function) -> str:
        """Universal method for sending transactions"""
        try:
            tx_params = self._get_gas_params()
            tx_params['gas'] = int(tx_function.estimate_gas(tx_params) * 1.2)
            
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


if __name__ == "__main__":
    # Iterate over all networks and stablecoins to check balances
    try:
        for network in RPC_URLS.keys():
            print(f"--- Checking balances on {network} ---")
            try:
                operator = ERC20Utils(network)
            except ConnectionError as ce:
                print(f"Connection error for network {network}: {ce}")
                continue
            
            for token, networks in STABLECOINS.items():
                try:
                    token_address = get_token_address(token, network)
                except ValueError as e:
                    print(f"{token} is not available on {network}: {e}")
                    continue
                
                try:
                    # Ensure address has correct checksum before fetching balance
                    if not Web3.is_checksum_address(token_address):
                        token_address = Web3.to_checksum_address(token_address)
                    
                    balance = operator.get_balance(token_address)
                    print(f"{token} balance on {network}: {balance}")
                except Exception as e:
                    print(f"Failed to get balance for {token} on {network}: {e}")
    except Exception as e:
        print(f"Operation failed: {str(e)}")


