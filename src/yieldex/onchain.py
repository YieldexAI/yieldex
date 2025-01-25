# onchain.py
from web3 import Web3
from typing import Optional, Dict, Any
from src.yieldex.config import POLYGON_RPC_URL, PRIVATE_KEY, AAVE_V3_ADDRESSES, get_token_address, LENDLE_POOL_ADDRESS, MANTLE_RPC_URL
import logging
import json
from web3.contract import Contract
from typing import Tuple
from web3.types import TxParams
from decimal import Decimal
from src.yieldex.data_collector import save_my_pool_balance
import requests
from pathlib import Path
logger = logging.getLogger(__name__)
ABI_DIR = Path(__file__).parent / "abi"

class AaveV3Operator:
    """Optimized class for interacting with AAVE V3 Protocol"""
    
    def __init__(self, network: str = 'Polygon'):
        if not POLYGON_RPC_URL:
            raise ValueError("POLYGON_RPC_URL not configured")
        if not PRIVATE_KEY:
            raise ValueError("PRIVATE_KEY not configured")
            
        self.w3 = Web3(Web3.HTTPProvider(POLYGON_RPC_URL))
        self.network = network
        self.account = self.w3.eth.account.from_key(PRIVATE_KEY)
        
        if not self.w3.is_connected():
            raise ConnectionError(f"Failed to connect to {network} RPC")
            
        self.pool_address = AAVE_V3_ADDRESSES[network]
        self.pool_contract = self._load_contract(
            'AaveV3Pool.json', 
            self.pool_address
        )
        
        logger.info(f"Initialized AaveOperator for {network}. Account: {self.account.address}")
        

    def _load_contract(self, abi_file: str, address: str) -> Contract:
        """Loads contract from ABI file"""
        abi_path = ABI_DIR / abi_file
        with open(abi_path) as f:
            abi = json.load(f)
        return self.w3.eth.contract(address=address, abi=abi)

    def _get_gas_prices(self) -> Tuple:
        """Gets recommended gas prices via API"""
        try:
            response = requests.get("https://gasstation.polygon.technology/v2")
            data = response.json()
            return (
                self.w3.to_wei(data['safeLow']['maxPriorityFee'], 'gwei'),
                self.w3.to_wei(data['safeLow']['maxFee'], 'gwei')
            )
        except Exception as e:
            logger.warning(f"Gas API error: {e}. Using fallback values")
            return (self.w3.to_wei(30, 'gwei'), 
                    self.w3.to_wei(50, 'gwei'))

    def _build_tx_params(self) -> TxParams:
        """Generates transaction parameters with EIP-1559"""
        priority_fee, max_fee = self._get_gas_prices()
        
        return {
            'from': self.account.address,
            'nonce': self.w3.eth.get_transaction_count(self.account.address),
            'maxFeePerGas': max_fee,
            'maxPriorityFeePerGas': priority_fee,
            'chainId': self.w3.eth.chain_id
        }

    def _send_transaction(self, contract_function) -> str:
        """Universal method for sending transactions"""
        try:
            # Gas estimation
            tx_params = self._build_tx_params()
            estimated_gas = contract_function.estimate_gas(tx_params)
            tx_params['gas'] = int(estimated_gas * 1.2)  # 20% buffer
            
            # Sign transaction
            tx = contract_function.build_transaction(tx_params)
            signed_tx = self.w3.eth.account.sign_transaction(tx, PRIVATE_KEY)
            
            # web3.py version compatibility
            raw_tx = signed_tx.raw_transaction if hasattr(signed_tx, 'raw_transaction') \
                else signed_tx.rawTransaction
            
            # Send and wait for confirmation
            tx_hash = self.w3.eth.send_raw_transaction(raw_tx)
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
            
            if receipt.status != 1:
                raise Exception("Transaction reverted")
                
            logger.info(f"Transaction successful: {tx_hash.hex()}")
            return tx_hash.hex()
            
        except Exception as e:
            logger.error(f"Transaction failed: {str(e)}")
            raise

    def _convert_amount(self, token_address: str, amount: float) -> int:
        """Converts amount to token's minimal units"""
        erc20 = self._load_contract('ERC20.json', token_address)
        decimals = erc20.functions.decimals().call()
        return int(amount * 10 ** decimals)

    def approve_token(self, token_address: str, amount: float) -> str:
        """Approves token usage"""
        amount_wei = self._convert_amount(token_address, amount)
        erc20 = self._load_contract('ERC20.json', token_address)
        
        logger.info(f"Approving {amount} tokens for AAVE")
        return self._send_transaction(
            erc20.functions.approve(self.pool_address, amount_wei)
        )
    
    def supply(self, token_address: str, amount: float) -> str:
        """Optimized deposit method"""
        amount_wei = self._convert_amount(token_address, amount)
        
        logger.info(f"Supplying {amount} tokens")
        return self._send_transaction(
            self.pool_contract.functions.supply(
                token_address,
                amount_wei,
                self.account.address,
                0
            )
        )

    def withdraw(self, token_address: str, amount: float) -> str:
        """Optimized withdrawal method"""
        amount_wei = self._convert_amount(token_address, amount)
        
        logger.info(f"Withdrawing {amount} tokens")
        return self._send_transaction(
            self.pool_contract.functions.withdraw(
                token_address,
                amount_wei,
                self.account.address
            )
        )

    def get_token_balance(self, token_address: str) -> float:
        """Gets token balance"""
        erc20 = self._load_contract('ERC20.json', token_address)
        decimals = erc20.functions.decimals().call()
        balance_wei = erc20.functions.balanceOf(self.account.address).call()
        return balance_wei / (10 ** decimals)

class LendleOperator:
    """Class for interacting with Lendle Protocol (Mantle)"""
    
    def __init__(self, network: str = 'Mantle'):
        if not MANTLE_RPC_URL:
            raise ValueError("RPC_URL not configured")
        if not PRIVATE_KEY:
            raise ValueError("PRIVATE_KEY not configured")
            
        self.w3 = Web3(Web3.HTTPProvider(MANTLE_RPC_URL))
        self.network = network
        self.account = self.w3.eth.account.from_key(PRIVATE_KEY)
        
        if not self.w3.is_connected():
            raise ConnectionError(f"Failed to connect to {network} RPC")
            
        self.pool_address = LENDLE_POOL_ADDRESS[network]
        self.pool_contract = self._load_contract(
            'LendleLendingPool.json', 
            self.pool_address
        )
        
        logger.info(f"Initialized LendleOperator for {network}. Account: {self.account.address}")

    def _load_contract(self, abi_file: str, address: str) -> Contract:
        """Loads contract from ABI file"""
        abi_path = ABI_DIR / abi_file
        with open(abi_path) as f:
            abi = json.load(f)
        return self.w3.eth.contract(address=address, abi=abi)

    def _get_gas_prices(self) -> Tuple:
        """Using standard values for Mantle"""
        try:
            # Mantle gas API endpoint if available
            return (self.w3.to_wei(0.1, 'gwei'), 
                    self.w3.to_wei(0.2, 'gwei'))
        except Exception as e:
            logger.warning(f"Gas API error: {e}. Using Mantle defaults")
            return (self.w3.to_wei(0.1, 'gwei'), 
                    self.w3.to_wei(0.2, 'gwei'))

    def _build_tx_params(self) -> TxParams:
        """Generates transaction parameters with EIP-1559"""
        priority_fee, max_fee = self._get_gas_prices()
        
        return {
            'from': self.account.address,
            'nonce': self.w3.eth.get_transaction_count(self.account.address),
            'maxFeePerGas': max_fee,
            'maxPriorityFeePerGas': priority_fee,
            'chainId': self.w3.eth.chain_id
        }

    def _send_transaction(self, contract_function) -> str:
        """Universal method for sending transactions"""
        try:
            # Gas estimation
            tx_params = self._build_tx_params()
            estimated_gas = contract_function.estimate_gas(tx_params)
            tx_params['gas'] = int(estimated_gas * 1.2)  # 20% buffer
            
            # Sign transaction
            tx = contract_function.build_transaction(tx_params)
            signed_tx = self.w3.eth.account.sign_transaction(tx, PRIVATE_KEY)
            
            # web3.py version compatibility
            raw_tx = signed_tx.raw_transaction if hasattr(signed_tx, 'raw_transaction') \
                else signed_tx.rawTransaction
            
            # Send and wait for confirmation
            tx_hash = self.w3.eth.send_raw_transaction(raw_tx)
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
            
            if receipt.status != 1:
                raise Exception("Transaction reverted")
                
            logger.info(f"Transaction successful: {tx_hash.hex()}")
            return tx_hash.hex()
            
        except Exception as e:
            logger.error(f"Transaction failed: {str(e)}")
            raise

    def _convert_amount(self, token_address: str, amount: float) -> int:
        """Converts amount to token's minimal units"""
        erc20 = self._load_contract('ERC20.json', token_address)
        decimals = erc20.functions.decimals().call()
        return int(amount * 10 ** decimals)

    def approve_token(self, token_address: str, amount: float) -> str:
        """Approves token usage in Lendle"""
        amount_wei = self._convert_amount(token_address, amount)
        erc20 = self._load_contract('ERC20.json', token_address)
        
        logger.info(f"Approving {amount} tokens for Lendle")
        return self._send_transaction(
            erc20.functions.approve(self.pool_address, amount_wei)
        )
    
    def supply(self, token_address: str, amount: float) -> str:
        """Deposits funds to Lendle"""
        amount_wei = self._convert_amount(token_address, amount)
        
        logger.info(f"Supplying {amount} tokens to Lendle")
        return self._send_transaction(
            self.pool_contract.functions.deposit(
                token_address,
                amount_wei,
                self.account.address,
                0  # referralCode
            )
        )

    def withdraw(self, token_address: str, amount: float) -> str:
        """Withdraws funds from Lendle"""
        amount_wei = self._convert_amount(token_address, amount)
        
        logger.info(f"Withdrawing {amount} tokens from Lendle")
        return self._send_transaction(
            self.pool_contract.functions.withdraw(
                token_address,
                amount_wei,
                self.account.address
            )
        )

    def get_token_balance(self, token_address: str) -> float:
        """Gets token balance"""
        erc20 = self._load_contract('ERC20.json', token_address)
        decimals = erc20.functions.decimals().call()
        balance_wei = erc20.functions.balanceOf(self.account.address).call()
        return balance_wei / (10 ** decimals)

if __name__ == "__main__":
    # Initialize operator for Polygon
    operator = AaveV3Operator(network='Polygon')
    operator_mantle = LendleOperator(network='Mantle')
    
    # USDT address in Polygon
    usdt_address = get_token_address('USDT', 'Polygon')
    usdt_address_mantle = get_token_address('USDT', 'Mantle')
    try:
        # 1. Check current balance
        balance = operator.get_token_balance(usdt_address)
        print(f"Current USDT balance: {balance}")

        balance_mantle = operator_mantle.get_token_balance(usdt_address_mantle)
        print(f"Current USDT balance: {balance_mantle}")
        
        # # 2. Approve 0.5 USDT
        # print("\nApproving 0.5 USDT...")
        # approve_tx = operator.approve_erc20(usdt_address, 0.5)
        
        # # 3. Deposit funds to AAVE
        # print("\nDepositing 0.5 USDT to AAVE...")
        # supply_tx = operator.supply(usdt_address, 0.5)
        
        # # 4. Check updated balance
        # new_balance = operator.get_token_balance(usdt_address)
        # print(f"\nNew USDT balance: {new_balance}")
        
        # # 5. Save balance info to DB
        # save_my_pool_balance(
        #     pool_id=f"aave_v3_usdt_{operator.network.lower()}",
        #     balance=new_balance
        # )

        # # 6. Withdraw funds
        # print("\nWithdrawing 0.5 USDT from AAVE...")
        # withdraw_tx = operator.withdraw(usdt_address, 0.5)  
        
        # # 7. Check updated balance
        # new_balance = operator.get_token_balance(usdt_address)
        # print(f"\nNew USDT balance: {new_balance}")
        
    except Exception as e:
        print(f"Operation failed: {str(e)}")

