import json
import logging
import sys
import os
from pathlib import Path
from typing import Any, Dict, Optional, List
from enum import Enum
from web3 import Web3
from web3.contract import Contract
import time

from yieldex_common.utils import get_token_address
from yieldex_common.config import (
    PRIVATE_KEY,
    RPC_URLS,
    STABLECOINS,
    SUPPORTED_PROTOCOLS,
    BLOCK_EXPLORERS,
    YIELDEX_ORACLE_ADDRESS,
    SILO_MARKETS,
    SILO_VAULTS,
    COMPOUND_ADDRESSES,
    RHO_ADDRESSES,
    FLUID_ADDRESSES,
)

from analyzer.analyzer import get_recommendations, format_recommendations

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Обновляем путь к ABI файлам - берем из пакета yieldex_common
from yieldex_common import config
# Используем ABI из модуля yieldex_common
ABI_DIR = Path(os.path.dirname(config.__file__)) / "abi"
if not os.path.exists(ABI_DIR):
    logger.error(f"ABI директория не найдена: {ABI_DIR}")
    raise FileNotFoundError(f"ABI директория не найдена: {ABI_DIR}")
else:
    logger.info(f"Найдена ABI директория: {ABI_DIR}")

# Добавляем переменную для протоколов без getReserveData
no_reserve_data_protocols = ['silo-v2', 'yieldex-oracle', 'uniswap-v3', 'rho-markets', 'compound-v3', 'fluid']



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
            raise ValueError(
                f"{protocol} contracts not found on {network}. Available on: {', '.join(available_networks)}"
            )

        self.contract = self._load_contract()
        self.account = self.w3.eth.account.from_key(PRIVATE_KEY)
        self.explorer_url = BLOCK_EXPLORERS.get(self.network)

    def _load_contract(self) -> Contract:
        """Load ABI based on protocol"""
        try:
            abi_map = {
                "aave-v3": "AaveV3Pool.json",
                "aave-v2": "AaveV2LendingPool.json",
                "lendle": "LendleLendingPool.json",
                "yieldex-oracle": "YieldexOracle.json",
                "uniswap-v3": "UniswapV3Router.json",
                "silo-v2": "SiloFactory.json",
                "compound-v3": "CompoundComet.json",
                "rho-markets": "ERC20-rhoMarket.json",
                "fluid": "FluidLendingPool.json",  # Add Fluid ABI mapping
            }

            if self.protocol not in abi_map:
                raise ValueError(f"Unsupported protocol: {self.protocol}")

            abi_path = ABI_DIR / abi_map[self.protocol]

            # Check possible alternative paths
            if not os.path.exists(abi_path):
                alt_path = os.path.join(
                    os.path.dirname(__file__), f"../common/abi/{self.protocol}.json"
                )
                if os.path.exists(alt_path):
                    abi_path = alt_path
                else:
                    raise FileNotFoundError(f"ABI file not found: {abi_path}")

            with open(abi_path) as f:
                abi = json.load(f)
                logger.info(f"ABI loaded: {abi_path}")

            if self.protocol == "rho-markets":
                self.contract_address = RHO_ADDRESSES[self.network]["usdc"]

            if self.protocol == "fluid":
                self.contract_address = FLUID_ADDRESSES[self.network][
                    "USDT"
                ]  ## Just for initial contract loading

            # Check if contract address is valid
            if not Web3.is_checksum_address(self.contract_address):
                self.contract_address = Web3.to_checksum_address(self.contract_address)

            # Create contract
            contract = self.w3.eth.contract(address=self.contract_address, abi=abi)

            # Check if contract is accessible
            try:
                # Try calling a view method, but only for protocols that support it
                if self.protocol not in no_reserve_data_protocols:
                    contract.functions.getReserveData(
                        self.w3.to_checksum_address(STABLECOINS["USDT"][self.network])
                    ).call()
                elif self.protocol == "silo-v2":
                    # Для Silo проверяем другим методом
                    contract.functions.getNextSiloId().call()
                elif self.protocol == "yieldex-oracle":
                    # Для oracle проверяем getApy
                    contract.functions.getApy("test").call()
                elif self.protocol == "uniswap-v3":
                    # Для Uniswap мы можем просто проверить, что байткод контракта не пустой
                    if self.w3.eth.get_code(self.contract_address) == b"":
                        raise ValueError(
                            f"No contract at address {self.contract_address}"
                        )
            except Exception as e:
                logger.warning(f"Contract verification warning: {str(e)}")
                # Не выбрасываем исключение, так как контракт всё равно может быть рабочим

            return contract

        except Exception as e:
            logger.error(
                f"Error loading contract for {self.protocol} on {self.network}: {str(e)}"
            )
            raise

    def _get_gas_params(self) -> Dict[str, Any]:
        """
        Get appropriate gas parameters for the current network.

        Returns:
            Dictionary with gas parameters appropriate for the current network
        """
        # For Arbitrum, we need to be very careful with gas parameters
        if self.network == "Arbitrum":
            # Get current base fee from latest block
            latest_block = self.w3.eth.get_block("latest")
            base_fee = latest_block.get("baseFeePerGas", self.w3.eth.gas_price)

            # Add 50% buffer to ensure the transaction goes through
            safe_gas_price = int(base_fee * 1.5)

            logger.info(
                f"Using gas price for Arbitrum: {safe_gas_price} (base fee {base_fee})"
            )

            return {
                "gasPrice": safe_gas_price,
                "gas": 1000000,  # Higher gas limit for Arbitrum
            }

        # For other networks, use standard gas pricing
        gas_price = self.w3.eth.gas_price
        return {"gasPrice": gas_price}

    def _send_transaction(self, tx_function) -> str:
        """
        Send a transaction to the blockchain and return the transaction hash.

        Args:
            tx_function: Web3.py contract function to call

        Returns:
            Transaction hash as hex string if successful, None otherwise
        """
        logger.info("Preparing to send transaction...")
        try:
            # Estimate gas first to check if transaction would succeed
            try:
                gas_estimate = tx_function.estimate_gas(
                    {"from": self.account.address, **self._get_gas_params()}
                )
                logger.info(f"Gas estimate: {gas_estimate}")
            except Exception as gas_error:
                error_str = str(gas_error)
                logger.error(f"Gas estimation failed: {error_str}")

                # Try to extract revert reason
                if "execution reverted" in error_str:
                    # Extract any specific error message
                    if "message" in error_str:
                        revert_msg = error_str.split('message":"')[1].split('"')[0]
                        logger.error(
                            f"Transaction would revert with reason: {revert_msg}"
                        )
                    else:
                        logger.error("Transaction would revert but no reason provided")
                return None

            # Build and sign transaction
            tx = tx_function.build_transaction(
                {
                    "from": self.account.address,
                    "nonce": self.w3.eth.get_transaction_count(self.account.address),
                    **self._get_gas_params(),
                }
            )

            signed_tx = self.w3.eth.account.sign_transaction(
                tx, private_key=self.account.key
            )
            tx_hash = self.w3.eth.send_raw_transaction(signed_tx.raw_transaction)
            tx_hash_hex = tx_hash.hex()

            # Add explorer URL if available
            if self.explorer_url:
                tx_url = f"{self.explorer_url}/tx/{tx_hash_hex}"
                logger.info(f"Transaction sent: {tx_url}")
            else:
                logger.info(f"Transaction sent, hash: {tx_hash_hex}")
                
            # Wait for transaction receipt
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=180)

            if receipt["status"] == 1:
                logger.info(f"Transaction successful: {tx_hash_hex}")
                if self.explorer_url:
                    logger.info(f"Transaction URL: {self.explorer_url}/tx/0x{tx_hash_hex}")
                return tx_hash_hex
            else:
                logger.error(f"Transaction failed: {tx_hash_hex}")
                logger.error(f"Receipt: {receipt}")
                return None

        except Exception as e:
            error_str = str(e)
            logger.error(f"Failed to send transaction: {error_str}")

            # Try to extract more information about the error
            if "execution reverted" in error_str:
                if "message" in error_str:
                    try:
                        revert_msg = error_str.split('message":"')[1].split('"')[0]
                        logger.error(f"Revert reason: {revert_msg}")
                    except:
                        pass

                if "data" in error_str:
                    try:
                        error_data = error_str.split('data":"')[1].split('"')[0]
                        logger.error(f"Error data: {error_data}")
                    except:
                        pass

            # Fluid specific errors
            if "Contract does not have fallback nor receive functions" in error_str:
                logger.error(
                    "This error typically occurs when trying to send native tokens (ETH) to a contract that doesn't accept them."
                )
                logger.error(
                    "Make sure you're not sending ETH value with your transaction to the ERC4626 vault."
                )

            return None

    def _send_transaction_eip1559(self, tx_function) -> str:
        """
        Enhanced implementation for sending transactions with EIP-1559 support
        
        Args:
            tx_function: Web3.py contract function to call
            
        Returns:
            Transaction hash if successful, None otherwise
        """
        try:
            logger.info("Preparing transaction with EIP-1559 format...")
            
            # Получаем текущий nonce (включая pending транзакции)
            nonce = self.w3.eth.get_transaction_count(self.account.address, "pending")
            
            # Получаем информацию о последнем блоке для расчета газа
            latest_block = self.w3.eth.get_block('latest')
            base_fee = latest_block.get('baseFeePerGas', 0)
            
            # Устанавливаем priority fee (чаевые майнерам)
            priority_fee = self.w3.eth.max_priority_fee
            
            # Максимальная комиссия = базовая комиссия * 2 + приоритетная комиссия
            # Умножаем базовую комиссию на 2 для запаса
            max_fee = base_fee * 2 + priority_fee
            
            logger.info(f"Gas parameters: baseFee={base_fee}, priorityFee={priority_fee}, maxFee={max_fee}")
            
            # Пытаемся оценить газ для транзакции
            try:
                # Add more detailed transaction parameters for gas estimation to reduce failures
                estimated_gas = tx_function.estimate_gas({
                    'from': self.account.address,
                    'nonce': nonce,
                    'maxFeePerGas': max_fee,
                    'maxPriorityFeePerGas': priority_fee
                })
                # Добавляем 10% к оценке газа для запаса
                gas_limit = int(estimated_gas * 1.1)
                logger.info(f"Estimated gas: {estimated_gas}, using limit: {gas_limit}")
            except Exception as e:
                logger.warning(f"Gas estimation failed: {e}")
                
                # Check if this is an approve function (common cause of gas estimation failures)
                function_signature = tx_function.function_identifier if hasattr(tx_function, 'function_identifier') else str(tx_function)
                if 'approve' in function_signature.lower():
                    logger.info("This is an approve transaction, using a higher gas limit for safety")
                    gas_limit = 100000  # Higher limit specifically for approvals, which are typically around 50,000
                else:
                    # Если оценка газа не удалась, используем фиксированное значение
                    gas_limit = 300000
                
                logger.info(f"Using default gas limit: {gas_limit}")
            
            # Строим транзакцию
            transaction = tx_function.build_transaction({
                'from': self.account.address,
                'nonce': nonce,
                'gas': gas_limit,
                # Используем EIP-1559 параметры газа
                'maxFeePerGas': max_fee,
                'maxPriorityFeePerGas': priority_fee,
                'chainId': int(self.w3.eth.chain_id)
            })
            
            # Подписываем транзакцию
            signed_tx = self.account.sign_transaction(transaction)
            
            # Отправляем транзакцию
            tx_hash = self.w3.eth.send_raw_transaction(signed_tx.raw_transaction)
            tx_hash_hex = tx_hash.hex()
            
            # Добавляем ссылку на Explorer
            if self.explorer_url:
                tx_url = f"{self.explorer_url}/tx/{tx_hash_hex}"
                logger.info(f"Transaction sent: {tx_url}")
            else:
                logger.info(f"Transaction sent, hash: {tx_hash_hex}")
            
            # More robust transaction confirmation
            try:
                # Ожидаем завершения транзакции с таймаутом
                logger.info(f"Waiting for transaction confirmation...")
                receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=180)  # Increased timeout
                
                if receipt.status == 1:
                    logger.info(f"Transaction successful, used gas: {receipt.gasUsed}")
                    
                    # For Arbitrum, which has frequent reorgs, double-check transaction success
                    if self.network == "Arbitrum":
                        time.sleep(5)  # Additional wait for Arbitrum
                        confirm_receipt = self.w3.eth.get_transaction_receipt(tx_hash)
                        if confirm_receipt.status != 1:
                            logger.error("Transaction was reorged or failed on second check")
                            return None
                    
                    return tx_hash_hex
                else:
                    logger.error(f"Transaction failed, receipt status: {receipt.status}")
                    return None
            except Exception as wait_error:
                logger.error(f"Error waiting for transaction confirmation: {wait_error}")
                
                # Try to check transaction status one more time
                try:
                    time.sleep(30)  # Wait a bit longer
                    final_receipt = self.w3.eth.get_transaction_receipt(tx_hash)
                    if final_receipt and final_receipt.status == 1:
                        logger.info("Transaction succeeded after timeout")
                        return tx_hash_hex
                    else:
                        logger.error("Transaction failed or status unknown after timeout")
                        return None
                except Exception:
                    logger.error("Could not determine final transaction status")
                    return None
            
        except Exception as e:
            logger.error(f"Error sending transaction: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None

    def _call_contract(self, function) -> Any:
        """Execute contract call with proper gas estimation"""
        try:
            params = {
                "from": self.account.address,
                "chainId": self.w3.eth.chain_id,
            }

            # Special handling for Arbitrum
            if self.network == "Arbitrum":
                gas_price = self.w3.eth.gas_price
                params["gasPrice"] = int(gas_price * 1.2)  # +20% to base gas price
                params["gas"] = 3000000  # Increased gas limit for Arbitrum
            else:
                gas_estimate = function.estimate_gas(params)
                params["gas"] = int(gas_estimate * 1.5)

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

            if self.w3.eth.get_code(token_address) == b"":
                raise ValueError(f"No contract at address {token_address}")

            with open(ABI_DIR / "ERC20.json") as f:
                abi = json.load(f)

            erc20 = self.w3.eth.contract(address=token_address, abi=abi)

            try:
                # Use _call_contract for decimals
                decimals = erc20.functions.decimals().call()
                logger.info(f"Got decimals for {token_address}: {decimals}")
            except Exception as e:
                logger.warning(f"Failed to get decimals, using default (18): {str(e)}")
                decimals = 18

            return int(amount * 10**decimals)

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
        with open(ABI_DIR / "ERC20.json") as f:
            token_contract = self.w3.eth.contract(
                address=token_address, abi=json.load(f)
            )

        # Get and log balance
        decimals = token_contract.functions.decimals().call()
        balance = token_contract.functions.balanceOf(self.account.address).call()
        balance_human = balance / 10**decimals

        logger.info(f"Current wallet balance: {balance_human} {token}")
        logger.info(f"Attempting to supply: {amount} {token}")

        if balance < amount_wei:
            raise ValueError(
                f"Insufficient balance: have {balance_human}, need {amount} {token}"
            )

        # Rest of the supply logic...
        allowance = token_contract.functions.allowance(
            self.account.address, self.contract_address
        ).call()

        if allowance < amount_wei:
            approve_tx = token_contract.functions.approve(
                self.contract_address, amount_wei
            )
            logger.info(f"Approving {token} for Aave V3")
            self._send_transaction(approve_tx)

        if self.protocol == "aave-v3":
            tx_func = self.contract.functions.supply(
                token_address, amount_wei, self.account.address, 0
            )
        elif self.protocol == "aave-v2":
            tx_func = self.contract.functions.deposit(
                token_address, amount_wei, self.account.address, 0
            )

        return self._send_transaction(tx_func)

    def withdraw(self, token: str, amount: float) -> str:
        """Withdraw funds from protocol"""
        try:
            token_address = get_token_address(token, self.network)

            # Check token support in pool
            logger.info(
                f"Checking if token {token} ({token_address}) is supported in {self.network} pool"
            )
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
            if (
                not Web3.is_address(atoken_address)
                or atoken_address == "0x0000000000000000000000000000000000000000"
            ):
                raise ValueError(
                    f"Invalid aToken address for {token}: {atoken_address}"
                )

            logger.info(f"Token is supported, aToken address: {atoken_address}")

            # Create aToken contract and get balance
            atoken_contract = self.w3.eth.contract(
                address=atoken_address, abi=json.load(open(ABI_DIR / "ERC20.json"))
            )

            # Use direct call() as in get_balance
            decimals = atoken_contract.functions.decimals().call()
            balance = atoken_contract.functions.balanceOf(self.account.address).call()
            logger.info(f"Current wallet balance: {balance / 10**decimals} {token}")

            amount_wei = self._convert_to_wei(token_address, amount)

            if balance < amount_wei:
                raise ValueError(
                    f"Insufficient balance: have {balance / 10**decimals}, need {amount_wei / 10**decimals}"
                )

            # Execute withdrawal
            tx_func = self.contract.functions.withdraw(
                token_address, amount_wei, self.account.address
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
            token_address, amount_wei, self.account.address, 0
        )
        return self._send_transaction(tx_func)

    def withdraw(self, token: str, amount: float) -> str:
        token_address = STABLECOINS[token][self.network]
        amount_wei = self._convert_to_wei(token_address, amount)

        tx_func = self.contract.functions.withdraw(
            token_address, amount_wei, self.account.address
        )
        return self._send_transaction(tx_func)


class YieldexOracleOperator(BaseProtocolOperator):
    def __init__(self, network: str):
        if network != "Mantle":
            raise ValueError("Oracle only available on Mantle")
        super().__init__(network, "yieldex-oracle")
        self.contract_address = Web3.to_checksum_address(
            YIELDEX_ORACLE_ADDRESS[network]
        )

    def update_apy(self, pool_id: str, apy: float) -> Optional[str]:
        """Update APY in the oracle contract"""
        try:
            # Conversion to contract format (2 decimal places)
            apy_scaled = int(apy * 100)

            tx_func = self.contract.functions.updateApy(pool_id, apy_scaled)

            return self._send_transaction(tx_func)

        except Exception as e:
            logger.error(f"Failed to update APY for {pool_id}: {str(e)}")
            return None

    def update_multiple_apys(
        self, pool_ids: List[str], apys: List[float]
    ) -> Optional[str]:
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
            apy_scaled, timestamp = self.contract.functions.getApy(pool_id).call()
            return apy_scaled / 100
        except Exception as e:
            logger.error(f"Ошибка при получении APY: {str(e)}")
            return None


class CrossChainManager:
    """Management of cross-chain operations"""

    def __init__(self):
        self.bridge_contracts = {
            "Polygon": "0x...",
            "Arbitrum": "0x...",
            "Mantle": "0x...",
        }

    def bridge_assets(self, token: str, amount: float, from_chain: str, to_chain: str):
        """Transfer tokens between chains via official bridge"""
        operator = AaveOperator(from_chain, "aave-v3")
        operator.withdraw(token, amount)

        # Bridging logic
        bridge_contract = self.w3.eth.contract(
            address=self.bridge_contracts[from_chain],
            abi=json.load(open(ABI_DIR / "Bridge.json")),
        )

        tx_hash = bridge_contract.functions.deposit(
            STABLECOINS[token][from_chain], amount, to_chain
        ).transact()

        return tx_hash.hex()


class CurveOperator(BaseProtocolOperator):
    """Class for working with Curve.fi pools"""

    def __init__(self, network: str, pool_name: str):
        self.pool_name = pool_name
        super().__init__(network, "curve")

    def swap(self, from_token: str, to_token: str, amount: float) -> str:
        """Execute swap between two stablecoins in Curve pool"""
        from_address = STABLECOINS[from_token][self.network]
        to_address = STABLECOINS[to_token][self.network]

        # Get pool contract with Curve-specific ABI
        pool_contract = self.w3.eth.contract(
            address=self.contract_address,
            abi=json.load(open(ABI_DIR / "CurvePool.json")),
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
            0,  # min_received_amount (will calculate properly in real scenario)
        )

        return self._send_transaction(tx_func)


class UniswapV3Operator(BaseProtocolOperator):
    """Class for working with Uniswap V3 swaps"""

    # Add dictionary with Quoter contract addresses
    QUOTER_ADDRESSES = {
        "Arbitrum": "0xb27308f9F90D607463bb33eA1BeBb41C27CE5AB6",
        "Optimism": "0x7637DcE4704b41Bf52BF338C650Dc46A586f7cF38",
    }

    # Available fee tiers in Uniswap V3
    FEE_TIERS = {
        100: "0064",  # 0.01%
        500: "01f4",  # 0.05%
        3000: "0bb8",  # 0.3%
        10000: "2710",  # 1%
    }

    def _get_token_decimals(self, token_address: str) -> int:
        """Get token decimals using existing ERC20 contract"""
        with open(ABI_DIR / "ERC20.json") as f:
            erc20 = self.w3.eth.contract(address=token_address, abi=json.load(f))
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

    def _get_quote(
        self,
        token_in_addr: str,
        token_out_addr: str,
        amount_wei: int,
        fee_tier: Optional[str] = None,
    ) -> int:
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
                raise ValueError(
                    f"Quoter address not configured for network {self.network}"
                )

            quoter_abi = json.load(open(ABI_DIR / "UniswapV3Quoter.json"))
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
            quote_amount = quoter.functions.quoteExactInput(path, amount_wei).call()

            logger.info(f"Quote successful: {quote_amount / 10**decimals_out} tokens")
            return quote_amount

        except Exception as e:
            logger.error(f"Failed to get quote: {str(e)}")
            raise

    def swap(
        self, token_in: str, token_out: str, amount_in: float, slippage: float = 0.5
    ) -> str:
        """Execute swap using Uniswap V3 Router"""
        try:
            # Validate addresses
            token_in_addr = self._validate_token_address(
                get_token_address(token_in, self.network)
            )
            token_out_addr = self._validate_token_address(
                get_token_address(token_out, self.network)
            )

            logger.info(
                f"Tokens: {token_in} -> {token_out} ({token_in_addr} -> {token_out_addr})"
            )

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
                quote_amount = self._get_quote(
                    token_in_addr, token_out_addr, amount_wei, fee_tier
                )
                min_amount_out = int(quote_amount * (1 - slippage / 100))
            except Exception as e:
                logger.warning(f"Using fallback slippage calculation: {str(e)}")
                min_amount_out = int(amount_wei * 0.95)  # 5% slippage as fallback

            # Build path and execute swap
            path = self._build_path(token_in_addr, token_out_addr, fee_tier)

            # Execute swap
            deadline = self.w3.eth.get_block("latest")["timestamp"] + 600
            params = {
                "path": path,
                "recipient": self.account.address,
                "deadline": deadline,
                "amountIn": amount_wei,
                "amountOutMinimum": min_amount_out,
            }

            swap_func = self.contract.functions.exactInput(params)
            return self._send_transaction(swap_func)

        except Exception as e:
            logger.error(f"Swap failed: {str(e)}")
            raise

    def _handle_token_approval(self, token_address: str, amount: int) -> None:
        """Handle token approval for Uniswap"""
        with open(ABI_DIR / "ERC20.json") as f:
            token_contract = self.w3.eth.contract(
                address=token_address, abi=json.load(f)
            )

        allowance = token_contract.functions.allowance(
            self.account.address, self.contract_address
        ).call()

        if allowance < amount:
            logger.info(f"Approving token {token_address}")
            approve_func = token_contract.functions.approve(
                self.contract_address, amount
            )
            tx_hash = self._send_transaction(approve_func)
            logger.info(f"Approval transaction: {tx_hash}")

    def _build_path(self, token_in: str, token_out: str, fee_tier: str) -> bytes:
        """Build path for Uniswap swap"""
        # Remove '0x' prefix if present and ensure addresses are 20 bytes (40 hex chars)
        token_in_clean = (
            token_in[2:].zfill(40) if token_in.startswith("0x") else token_in.zfill(40)
        )
        token_out_clean = (
            token_out[2:].zfill(40)
            if token_out.startswith("0x")
            else token_out.zfill(40)
        )

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
        super().__init__(network, "silo-v2")
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
            logger.debug(
                f"Getting Silo address for token {token} ({token_address}) on market {self.market_id}"
            )

            # Если нет market_id, невозможно найти Silo
            if not self.market_id:
                raise ValueError("Market ID is required to get Silo address")

            # Проверяем наличие маркета в SILO_MARKETS
            if (
                self.network not in SILO_MARKETS
                or self.market_id not in SILO_MARKETS[self.network]
            ):
                logger.warning(
                    f"Маркет {self.market_id} не найден в SILO_MARKETS для сети {self.network}"
                )
                # Обновляем список маркетов
                markets = get_all_silo_markets(self.network)
                if self.market_id not in markets:
                    raise ValueError(
                        f"Маркет {self.market_id} не существует в сети {self.network}"
                    )

            # Проверяем кэш SILO_VAULTS для известных Silo
            silo_address = None

            # По умолчанию используем Standard Silo (тип 0)
            silo_type = 0

            if (
                self.network in SILO_VAULTS
                and self.market_id in SILO_VAULTS[self.network]
                and silo_type in SILO_VAULTS[self.network][self.market_id]
            ):
                silo_address = SILO_VAULTS[self.network][self.market_id][silo_type]
                logger.info(
                    f"Найден адрес Silo для маркета {self.market_id} в кэше: {silo_address}"
                )
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
                    logger.warning(
                        f"Не найден Silo типа {silo_type}, используем первый доступный: {silo_address}"
                    )
                else:
                    raise ValueError(
                        f"No Silo found for market {self.market_id} on {self.network}"
                    )

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
            logger.info(
                f"Finding Silo vaults for market {market_id} on network {self.network}"
            )

            # Check if market exists in SILO_MARKETS
            if (
                self.network not in SILO_MARKETS
                or market_id not in SILO_MARKETS[self.network]
            ):
                logger.warning(
                    f"Market {market_id} not found in SILO_MARKETS for network {self.network}"
                )

                # If market not in SILO_MARKETS, get new list of markets
                markets = get_all_silo_markets(self.network)
                if market_id not in markets:
                    raise ValueError(
                        f"Market {market_id} does not exist in network {self.network}"
                    )

            # Get SiloConfig address from SILO_MARKETS
            silo_config_address = SILO_MARKETS[self.network][market_id]
            if (
                not silo_config_address
                or silo_config_address == "0x0000000000000000000000000000000000000000"
            ):
                raise ValueError(f"Invalid SiloConfig address for market {market_id}")

            logger.info(
                f"Using SiloConfig address for market {market_id}: {silo_config_address}"
            )

            # Check if there are known Silos in SILO_VAULTS cache
            silos_result = []
            if (
                self.network in SILO_VAULTS
                and market_id in SILO_VAULTS[self.network]
                and SILO_VAULTS[self.network][market_id]
            ):
                logger.info(f"Found cached Silos for market {market_id}")
                silo_types = SILO_VAULTS[self.network][market_id]

                for silo_type, silo_address in silo_types.items():
                    if (
                        silo_address
                        and silo_address != "0x0000000000000000000000000000000000000000"
                    ):
                        token_info = self.get_silo_info(silo_address)
                        if token_info:
                            silos_result.append(
                                {
                                    "silo_address": silo_address,
                                    "token_info": token_info,
                                    "silo_type": silo_type,
                                }
                            )

            # If not in cache, get Silos from SiloConfig
            if not silos_result:
                try:
                    # Load ABI for SiloConfig
                    with open(ABI_DIR / "SiloConfig.json") as f:
                        config_abi = json.load(f)

                    # Create SiloConfig contract
                    silo_config = self.w3.eth.contract(
                        address=silo_config_address, abi=config_abi
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

                        if (
                            silo0_address
                            != "0x0000000000000000000000000000000000000000"
                        ):
                            # Save to cache
                            SILO_VAULTS[self.network][market_id][0] = silo0_address

                            silo0_info = self.get_silo_info(silo0_address)
                            if silo0_info:
                                silos_result.append(
                                    {
                                        "silo_address": silo0_address,
                                        "token_info": silo0_info,
                                        "silo_type": 0,
                                    }
                                )
                    except Exception as e:
                        logger.warning(f"Error getting Silo0 address: {str(e)}")

                    # Try to get Silo1 address (protected Silo)
                    try:
                        silo1_address = silo_config.functions.getSilo(1).call()
                        logger.info(f"Found Silo1 address: {silo1_address}")

                        if (
                            silo1_address
                            != "0x0000000000000000000000000000000000000000"
                        ):
                            # Save to cache
                            SILO_VAULTS[self.network][market_id][1] = silo1_address

                            silo1_info = self.get_silo_info(silo1_address)
                            if silo1_info:
                                silos_result.append(
                                    {
                                        "silo_address": silo1_address,
                                        "token_info": silo1_info,
                                        "silo_type": 1,
                                    }
                                )
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
                                    if (
                                        silo_address
                                        and silo_address
                                        != "0x0000000000000000000000000000000000000000"
                                    ):
                                        logger.info(
                                            f"Found Silo through silos({i}): {silo_address}"
                                        )

                                        # Determine Silo type (assume even - standard, odd - protected)
                                        silo_type = 0 if i % 2 == 0 else 1
                                        SILO_VAULTS[self.network][market_id][
                                            silo_type
                                        ] = silo_address

                                        silo_info = self.get_silo_info(silo_address)
                                        if silo_info:
                                            silos_result.append(
                                                {
                                                    "silo_address": silo_address,
                                                    "token_info": silo_info,
                                                    "silo_type": silo_type,
                                                }
                                            )
                                except Exception:
                                    pass
                        except Exception as e:
                            logger.debug(f"silos method not found: {str(e)}")

                        # 2. Try getSilos() method
                        if not silos_result:
                            try:
                                silo_addresses = silo_config.functions.getSilos().call()
                                if silo_addresses and len(silo_addresses) > 0:
                                    logger.info(
                                        f"Found Silos through getSilos(): {silo_addresses}"
                                    )

                                    for i, silo_address in enumerate(silo_addresses):
                                        if (
                                            silo_address
                                            and silo_address
                                            != "0x0000000000000000000000000000000000000000"
                                        ):
                                            # Determine Silo type
                                            silo_type = 0 if i % 2 == 0 else 1
                                            SILO_VAULTS[self.network][market_id][
                                                silo_type
                                            ] = silo_address

                                            silo_info = self.get_silo_info(silo_address)
                                            if silo_info:
                                                silos_result.append(
                                                    {
                                                        "silo_address": silo_address,
                                                        "token_info": silo_info,
                                                        "silo_type": silo_type,
                                                    }
                                                )
                            except Exception as e:
                                logger.debug(f"getSilos method not found: {str(e)}")

                            # 3. Try direct getStandardSilo() and getProtectedSilo() methods
                            if not silos_result:
                                try:
                                    # Standard Silo
                                    try:
                                        silo0_address = silo_config.functions.getStandardSilo().call()
                                        if (
                                            silo0_address
                                            and silo0_address
                                            != "0x0000000000000000000000000000000000000000"
                                        ):
                                            logger.info(
                                                f"Found Standard Silo: {silo0_address}"
                                            )
                                            SILO_VAULTS[self.network][market_id][0] = (
                                                silo0_address
                                            )

                                            silo0_info = self.get_silo_info(
                                                silo0_address
                                            )
                                            if silo0_info:
                                                silos_result.append(
                                                    {
                                                        "silo_address": silo0_address,
                                                        "token_info": silo0_info,
                                                        "silo_type": 0,
                                                    }
                                                )
                                    except Exception as e:
                                        logger.debug(
                                            f"getStandardSilo method not found: {str(e)}"
                                        )

                                    # Protected Silo
                                    try:
                                        silo1_address = silo_config.functions.getProtectedSilo().call()
                                        if (
                                            silo1_address
                                            and silo1_address
                                            != "0x0000000000000000000000000000000000000000"
                                        ):
                                            logger.info(
                                                f"Found Protected Silo: {silo1_address}"
                                            )
                                            SILO_VAULTS[self.network][market_id][1] = (
                                                silo1_address
                                            )

                                            silo1_info = self.get_silo_info(
                                                silo1_address
                                            )
                                            if silo1_info:
                                                silos_result.append(
                                                    {
                                                        "silo_address": silo1_address,
                                                        "token_info": silo1_info,
                                                        "silo_type": 1,
                                                    }
                                                )
                                    except Exception as e:
                                        logger.debug(
                                            f"getProtectedSilo method not found: {str(e)}"
                                        )
                                except Exception as e:
                                    logger.debug(
                                        f"Error trying to use getStandardSilo/getProtectedSilo methods: {str(e)}"
                                    )
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
                logger.warning(
                    f"Error getting asset token from Silo {silo_address}: {str(e)}"
                )
                return None

            # Get token information
            token_info = self.get_token_info(token_address)

            # Add Silo-specific information
            try:
                token_info["silo_name"] = silo.functions.name().call()
                token_info["silo_symbol"] = silo.functions.symbol().call()
            except Exception as e:
                logger.warning(
                    f"Error getting Silo name/symbol from {silo_address}: {str(e)}"
                )

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
                "decimals": decimals,
            }

        except Exception as e:
            logger.error(f"Error getting token info for {token_address}: {str(e)}")
            return None

    def deposit(
        self, token: str, amount: float, collateral_type: str = "standard"
    ) -> str:
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
            raise ValueError(
                f"Invalid collateral type: {collateral_type}. Must be one of: {list(self.COLLATERAL_TYPE.keys())}"
            )

        collateral_type_value = self.COLLATERAL_TYPE[collateral_type]

        # Create ERC20 token contract
        with open(ABI_DIR / "ERC20.json") as f:
            token_contract = self.w3.eth.contract(
                address=token_address, abi=json.load(f)
            )

        # Create Silo contract
        with open(ABI_DIR / "Silo.json") as f:
            silo_contract = self.w3.eth.contract(address=silo_address, abi=json.load(f))

        # First, approve tokens for the silo contract
        approve_tx = self._send_transaction(
            token_contract.functions.approve(silo_address, amount_wei)
        )
        logger.info(f"Approved {amount} {token} for Silo vault: {approve_tx}")

        # Deposit into the silo contract with specified collateral type
        deposit_tx = self._send_transaction(
            silo_contract.functions.deposit(
                amount_wei, self.account.address, collateral_type_value
            )
        )

        logger.info(
            f"Deposited {amount} {token} into Silo vault with collateral type {collateral_type}: {deposit_tx}"
        )

        return deposit_tx

    def withdraw(
        self, token: str, amount: float = None, collateral_type: str = "standard"
    ) -> str:
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
            raise ValueError(
                f"Invalid collateral type: {collateral_type}. Must be one of: {list(self.COLLATERAL_TYPE.keys())}"
            )

        collateral_type_value = self.COLLATERAL_TYPE[collateral_type]

        # Create Silo contract
        with open(ABI_DIR / "Silo.json") as f:
            silo_contract = self.w3.eth.contract(address=silo_address, abi=json.load(f))

        if amount is None:
            # Get the user's max withdrawable amount
            max_withdraw = silo_contract.functions.maxWithdraw(
                self.account.address, collateral_type_value
            ).call()

            if max_withdraw == 0:
                raise ValueError(
                    f"No withdrawable balance available for {token} in this vault with collateral type {collateral_type}"
                )

            # Withdraw all available
            tx = self._send_transaction(
                silo_contract.functions.withdraw(
                    max_withdraw,
                    self.account.address,
                    self.account.address,
                    collateral_type_value,
                )
            )
            logger.info(
                f"Withdrew all available {token} from Silo vault with collateral type {collateral_type}: {tx}"
            )
        else:
            # Convert amount to wei
            amount_wei = self._convert_to_wei(token_address, amount)

            # Withdraw specific amount
            tx = self._send_transaction(
                silo_contract.functions.withdraw(
                    amount_wei,
                    self.account.address,
                    self.account.address,
                    collateral_type_value,
                )
            )
            logger.info(
                f"Withdrew {amount} {token} from Silo vault with collateral type {collateral_type}: {tx}"
            )

        return tx

    def get_balance(self, token: str) -> float:
        """Get the current balance of token in the Silo vault"""
        token_address = STABLECOINS[token][self.network]
        silo_address = self._get_silo_address(token)

        with open(ABI_DIR / "Silo.json") as f:
            silo_contract = self.w3.eth.contract(address=silo_address, abi=json.load(f))

        # Get user's balance in shares
        balance_wei = silo_contract.functions.balanceOf(self.account.address).call()

        # Convert shares to assets
        assets_wei = silo_contract.functions.convertToAssets(balance_wei).call()

        # Convert wei to float
        return self._convert_from_wei(token_address, assets_wei)

    def build_deposit_calldata(
        self, token: str, amount: float, collateral_type: str = "standard"
    ) -> str:
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
            raise ValueError(
                f"Invalid collateral type: {collateral_type}. Must be one of: {list(self.COLLATERAL_TYPE.keys())}"
            )

        collateral_type_value = self.COLLATERAL_TYPE[collateral_type]

        with open(ABI_DIR / "Silo.json") as f:
            silo_contract = self.w3.eth.contract(address=silo_address, abi=json.load(f))

        # Create calldata for deposit function
        return silo_contract.encodeABI(
            fn_name="deposit",
            args=[amount_wei, self.account.address, collateral_type_value],
        )

    def build_withdraw_calldata(
        self, token: str, amount: float = None, collateral_type: str = "standard"
    ) -> str:
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
            raise ValueError(
                f"Invalid collateral type: {collateral_type}. Must be one of: {list(self.COLLATERAL_TYPE.keys())}"
            )

        collateral_type_value = self.COLLATERAL_TYPE[collateral_type]

        with open(ABI_DIR / "Silo.json") as f:
            silo_contract = self.w3.eth.contract(address=silo_address, abi=json.load(f))

        if amount is None:
            # Get the user's max withdrawable amount
            max_withdraw = silo_contract.functions.maxWithdraw(
                self.account.address, collateral_type_value
            ).call()

            if max_withdraw == 0:
                raise ValueError(
                    f"No withdrawable balance available for {token} in this vault with collateral type {collateral_type}"
                )

            # Withdraw all available
            return silo_contract.encodeABI(
                fn_name="withdraw",
                args=[
                    max_withdraw,
                    self.account.address,
                    self.account.address,
                    collateral_type_value,
                ],
            )
        else:
            # Convert amount to wei
            amount_wei = self._convert_to_wei(token_address, amount)

            # Withdraw specific amount
            return silo_contract.encodeABI(
                fn_name="withdraw",
                args=[
                    amount_wei,
                    self.account.address,
                    self.account.address,
                    collateral_type_value,
                ],
            )

    def _convert_from_wei(self, token_address: str, amount_wei: int) -> float:
        """Convert amount from wei to float based on token decimals"""
        with open(ABI_DIR / "ERC20.json") as f:
            token_contract = self.w3.eth.contract(
                address=token_address, abi=json.load(f)
            )

        decimals = token_contract.functions.decimals().call()
        return amount_wei / (10**decimals)

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

        with open(ABI_DIR / "Silo.json") as f:
            silo_contract = self.w3.eth.contract(address=silo_address, abi=json.load(f))

        # Get various market metrics
        total_assets = silo_contract.functions.totalAssets().call()
        collateral_debt = (
            silo_contract.functions.getCollateralAndDebtTotalsStorage().call()
        )
        liquidity = silo_contract.functions.getLiquidity().call()

        collateral_assets = collateral_debt[0]
        debt_assets = collateral_debt[1]

        # Calculate utilization as debt / collateral (if collateral is 0, utilization is 0)
        utilization = (
            (debt_assets / collateral_assets * 100) if collateral_assets > 0 else 0
        )

        return {
            "total_assets": self._convert_from_wei(token_address, total_assets),
            "collateral_assets": self._convert_from_wei(
                token_address, collateral_assets
            ),
            "debt_assets": self._convert_from_wei(token_address, debt_assets),
            "liquidity": self._convert_from_wei(token_address, liquidity),
            "utilization": utilization,
            "market_id": self.market_id,
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

        with open(ABI_DIR / "Silo.json") as f:
            silo_contract = self.w3.eth.contract(address=silo_address, abi=json.load(f))

        # Check if account is solvent (no outstanding debt)
        is_solvent = silo_contract.functions.isSolvent(self.account.address).call()

        # Check maximum borrowing capacity
        max_borrow_wei = silo_contract.functions.maxBorrow(self.account.address).call()

        # Check if user has any collateral
        balance_wei = silo_contract.functions.balanceOf(self.account.address).call()
        has_collateral = balance_wei > 0

        return {
            "max_borrow_amount": self._convert_from_wei(token_address, max_borrow_wei),
            "is_solvent": is_solvent,
            "has_collateral": has_collateral,
        }

    def get_share_balance(self, token_address, owner_address):
        # Get balance of share tokens for accounting
        return self.silo_contract.functions.balanceOf(owner_address).call()

    def get_max_withdraw(
        self, token_address, owner_address, collateral_type=CollateralType.STANDARD
    ):
        # Call maxWithdraw function to check available withdrawal amount
        return self.silo_contract.functions.maxWithdraw(
            owner_address, collateral_type.value
        ).call()

    def get_silo_abi(self):
        """Получить ABI для Silo контракта"""
        with open(ABI_DIR / "Silo.json") as f:
            return json.load(f)

    def supply(
        self,
        token: str,
        amount: float,
        collateral_type: CollateralType = CollateralType.PROTECTED,
    ) -> Optional[str]:
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

            logger.info(
                f"Supplying {amount} {token} to Silo market {self.market_id} on {self.network}"
            )

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
                        token in symbol
                        or token in name
                        or token in silo_symbol
                        or token in silo_name
                    ) and silo_type == collateral_type.value:
                        matching_silo = silo
                        break
                else:
                    # For other tokens, match by symbol
                    if (
                        token in symbol
                        or token in name
                        or token in silo_symbol
                        or token in silo_name
                    ):
                        matching_silo = silo
                        break

            # If no match by token name, use collateral type as fallback
            if not matching_silo:
                for silo in silos:
                    if silo.get("silo_type") == collateral_type.value:
                        matching_silo = silo
                        logger.warning(
                            f"No exact match for {token}, using silo with correct collateral type"
                        )
                        break

            # If still no match, use the first silo as a last resort
            if not matching_silo and silos:
                matching_silo = silos[0]
                logger.warning(
                    f"No matching silo for {token} and collateral type {collateral_type.name}, using first available silo"
                )

            if not matching_silo:
                raise ValueError(
                    f"No suitable silo found for token {token} in market {self.market_id}"
                )

            silo_address = matching_silo["silo_address"]
            logger.info(f"Found matching silo for {token}: {silo_address}")

            # Create ERC20 token contract
            with open(ABI_DIR / "ERC20.json") as f:
                token_contract = self.w3.eth.contract(
                    address=token_address, abi=json.load(f)
                )

            # Get and log balance
            decimals = token_contract.functions.decimals().call()
            balance = token_contract.functions.balanceOf(self.account.address).call()
            balance_human = balance / 10**decimals

            logger.info(f"Current wallet balance: {balance_human} {token}")
            logger.info(f"Attempting to supply: {amount} {token}")

            amount_wei = int(amount * 10**decimals)
            if balance < amount_wei:
                raise ValueError(
                    f"Insufficient balance: have {balance_human}, need {amount} {token}"
                )

            # Check allowance and approve if needed
            allowance = token_contract.functions.allowance(
                self.account.address, silo_address
            ).call()

            if allowance < amount_wei:
                logger.info(f"Approving {token} for Silo at {silo_address}")
                approve_tx = token_contract.functions.approve(silo_address, amount_wei)
                self._send_transaction(approve_tx)

            # Now deposit into Silo
            return self.deposit(silo_address, amount)

        except Exception as e:
            logger.error(
                f"Error in supply operation for {token} on {self.network}: {str(e)}"
            )
            return None

    def withdraw_token(
        self,
        token: str,
        amount: float,
        collateral_type: CollateralType = CollateralType.PROTECTED,
    ) -> Optional[str]:
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
                if silo_info and "symbol" in silo_info:
                    symbol = silo_info["symbol"]
                    if token.upper() in symbol.upper():
                        silo_type = (
                            "STANDARD"
                            if collateral_type == CollateralType.STANDARD
                            else "PROTECTED"
                        )
                        if silo_type in symbol.upper():
                            silo_address = silo
                            logger.info(
                                f"Found exact matching silo for {token}: {silo_address}"
                            )
                            break

            # If no exact match, try to find by collateral type
            if not silo_address:
                for silo in silos:
                    silo_info = self.get_silo_info(silo)
                    if silo_info:
                        # Check if this is the right type of silo (Protected/Standard)
                        if (
                            collateral_type == CollateralType.PROTECTED
                            and "PROTECTED" in str(silo_info).upper()
                        ):
                            silo_address = silo
                            logger.info(f"Found protected silo: {silo_address}")
                            break
                        elif (
                            collateral_type == CollateralType.STANDARD
                            and "STANDARD" in str(silo_info).upper()
                        ):
                            silo_address = silo
                            logger.info(f"Found standard silo: {silo_address}")
                            break

            # If still no match, use the first available silo
            if not silo_address and silos:
                silo_address = silos[0]
                logger.warning(
                    f"No matching silo found for {token}, using first available: {silo_address}"
                )

            if not silo_address:
                raise ValueError(f"No silos found for market {self.market_id}")

            # Check maximum withdrawable amount
            max_withdraw = self.get_max_withdraw(silo_address, collateral_type)
            if max_withdraw is None:
                raise ValueError(
                    f"Failed to get maximum withdrawable amount from silo {silo_address}"
                )

            logger.info(f"Maximum withdrawable amount: {max_withdraw}")

            # Adjust amount if necessary
            if amount > max_withdraw:
                logger.warning(
                    f"Withdrawal amount ({amount}) exceeds maximum withdrawable amount ({max_withdraw}). Using maximum."
                )
                amount = max_withdraw

            if amount <= 0:
                logger.warning("Nothing to withdraw")
                return None

            # Execute withdrawal using the redeem function
            return self.withdraw(silo_address, amount, collateral_type)

        except Exception as e:
            logger.error(f"Error withdrawing {token}: {e}")
            return None

    def get_token_balance(
        self, token: str, collateral_type: CollateralType = CollateralType.PROTECTED
    ) -> Optional[float]:
        """
        Get token balance in Silo

        Args:
            token: Token symbol (e.g. 'USDC.E')
            collateral_type: Type of collateral, PROTECTED (1) by default for stablecoins

        Returns:
            Balance as float, or None if an error occurred
        """
        try:
            logger.info(
                f"Getting balance for {token} in Silo market {self.market_id} on {self.network}"
            )

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
                        token in symbol
                        or token in name
                        or token in silo_symbol
                        or token in silo_name
                    ) and silo_type == collateral_type.value:
                        matching_silo = silo
                        break
                else:
                    # For other tokens, match by symbol
                    if (
                        token in symbol
                        or token in name
                        or token in silo_symbol
                        or token in silo_name
                    ):
                        matching_silo = silo
                        break

            # If no match by token name, use collateral type as fallback
            if not matching_silo:
                for silo in silos:
                    if silo.get("silo_type") == collateral_type.value:
                        matching_silo = silo
                        logger.warning(
                            f"No exact match for {token}, using silo with correct collateral type"
                        )
                        break

            # If still no match, use the first silo as a last resort
            if not matching_silo and silos:
                matching_silo = silos[0]
                logger.warning(
                    f"No matching silo for {token} and collateral type {collateral_type.name}, using first available silo"
                )

            if not matching_silo:
                raise ValueError(
                    f"No suitable silo found for token {token} in market {self.market_id}"
                )

            silo_address = matching_silo["silo_address"]
            logger.info(f"Found matching silo for {token}: {silo_address}")

            # Get balance
            return self.get_silo_balance(silo_address)

        except Exception as e:
            logger.error(
                f"Error getting balance for {token} on {self.network}: {str(e)}"
            )
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
            silo = self.w3.eth.contract(address=silo_address, abi=silo_abi)

            # Get token address and log it
            token_address = silo.functions.asset().call()
            logger.info(f"Underlying token address: {token_address}")

            # Get silo decimals for reference
            silo_decimals = silo.functions.decimals().call()
            logger.info(f"Silo decimals: {silo_decimals}")

            # Get token contract and decimals
            token_contract = self.w3.eth.contract(
                address=token_address, abi=json.load(open(ABI_DIR / "ERC20.json"))
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
                self.account.address, silo_address
            ).call()
            logger.info(f"Current allowance: {allowance}")

            # Approve if needed
            if allowance < amount_wei:
                logger.info(f"Approving token for Silo, amount: {amount_wei}")
                approve_tx = token_contract.functions.approve(silo_address, amount_wei)
                self._send_transaction(approve_tx)

            # Execute deposit
            logger.info(f"Depositing {amount} into Silo {silo_address}")

            # Use deposit function
            deposit_tx = silo.functions.deposit(amount_wei, self.account.address)

            return self._send_transaction(deposit_tx)
        except Exception as e:
            logger.error(f"Error depositing into Silo {silo_address}: {e}")
            return None

    def withdraw(
        self,
        silo_address: str,
        amount: float,
        collateral_type: CollateralType = CollateralType.PROTECTED,
        force_withdrawal: bool = False,
    ) -> Optional[str]:
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
            silo = self.w3.eth.contract(address=silo_address, abi=silo_abi)

            # Get withdrawal info
            withdrawal_info = self.get_withdrawal_info(silo_address, collateral_type)
            total_balance = withdrawal_info["total_balance"]
            max_withdraw = withdrawal_info["available_balance"]

            if not force_withdrawal:
                # Check if requested amount exceeds available amount
                if amount > max_withdraw:
                    logger.warning(
                        f"Withdrawal amount ({amount}) exceeds maximum withdrawable amount ({max_withdraw}). Using maximum."
                    )
                    amount = max_withdraw

                if amount <= 0:
                    logger.warning(f"Nothing to withdraw (amount: {amount})")
                    return None
            else:
                # For force withdrawal, we'll try with the full amount but inform the user
                if amount > max_withdraw:
                    logger.warning(
                        f"Forced withdrawal of {amount} requested, but only {max_withdraw} is immediately available."
                    )
                    logger.warning(
                        f"Protocol will likely fulfill only {max_withdraw / amount * 100:.2f}% of the request."
                    )

                # Cap at total balance
                if amount > total_balance:
                    logger.warning(
                        f"Requested amount {amount} exceeds total balance {total_balance}. Using total balance."
                    )
                    amount = total_balance

                if amount <= 0:
                    logger.warning(f"Nothing to withdraw (amount: {amount})")
                    return None

            # Get token address for decimals
            token_address = silo.functions.asset().call()
            logger.info(f"Underlying token address: {token_address}")

            # Get token contract and decimals
            token_contract = self.w3.eth.contract(
                address=token_address, abi=json.load(open(ABI_DIR / "ERC20.json"))
            )

            token_decimals = token_contract.functions.decimals().call()
            logger.info(f"Token decimals: {token_decimals}")

            # Convert amount to shares
            amount_wei = int(amount * 10**token_decimals)
            logger.info(f"Amount in wei (using token decimals): {amount_wei}")

            # Try to convert assets to shares
            try:
                shares = silo.functions.convertToShares(amount_wei).call()
                logger.info(
                    f"Converting {amount} assets to {shares / (10**token_decimals)} shares"
                )
            except Exception as e:
                logger.warning(f"Failed to convert assets to shares: {e}")
                # Fallback to using amount_wei directly
                shares = amount_wei
                logger.info(f"Using direct conversion for shares: {shares}")

            # Use redeem function
            logger.info(
                f"Redeeming {shares / (10**token_decimals)} shares from Silo {silo_address}"
            )
            logger.info(f"Collateral type: {collateral_type.name}")

            # Build and execute transaction
            tx_func = silo.functions.redeem(
                shares,  # shares amount
                self.account.address,  # receiver
                self.account.address,  # owner
                int(collateral_type.value),  # collateral type as uint8
            )

            return self._send_transaction(tx_func)
        except Exception as e:
            logger.error(f"Error withdrawing from Silo {silo_address}: {e}")
            return None

    def get_max_withdraw(
        self,
        silo_address: str,
        collateral_type: CollateralType = CollateralType.PROTECTED,
    ) -> Optional[float]:
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
            silo = self.w3.eth.contract(address=silo_address, abi=silo_abi)

            # Try to use maxWithdraw first (ERC4626 standard)
            try:
                # Call maxWithdraw function
                max_withdraw_wei = silo.functions.maxWithdraw(
                    self.account.address, int(collateral_type.value)
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

    def get_silo_balance(
        self, silo_address: str, account: Optional[str] = None
    ) -> Optional[float]:
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
            silo = self.w3.eth.contract(address=silo_address, abi=silo_abi)

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

    def get_withdrawal_info(
        self,
        silo_address: str,
        collateral_type: CollateralType = CollateralType.PROTECTED,
    ) -> Dict[str, Any]:
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
            silo = self.w3.eth.contract(address=silo_address, abi=silo_abi)

            # Get total balance (in share tokens)
            share_balance_wei = silo.functions.balanceOf(self.account.address).call()
            decimals = silo.functions.decimals().call()
            share_balance = share_balance_wei / 10**decimals

            # Get total assets this represents
            try:
                # Try to use previewRedeem function if available (ERC4626 standard)
                total_assets_wei = silo.functions.previewRedeem(
                    share_balance_wei
                ).call()
            except Exception:
                try:
                    # Fallback to convertToAssets
                    total_assets_wei = silo.functions.convertToAssets(
                        share_balance_wei
                    ).call()
                except Exception:
                    # Final fallback - use balanceOf as share balance
                    total_assets_wei = share_balance_wei

            # Get token decimals to convert to human-readable format
            token_address = silo.functions.asset().call()
            token_contract = self.w3.eth.contract(
                address=token_address, abi=json.load(open(ABI_DIR / "ERC20.json"))
            )
            token_decimals = token_contract.functions.decimals().call()

            total_assets = total_assets_wei / 10**token_decimals

            # Get maximum withdrawable amount
            max_withdraw_wei = silo.functions.maxWithdraw(
                self.account.address, int(collateral_type.value)
            ).call()
            max_withdraw = max_withdraw_wei / 10**token_decimals

            # Calculate liquidity percentage
            liquidity_percentage = (
                (max_withdraw / total_assets * 100) if total_assets > 0 else 0
            )

            result = {
                "total_balance": total_assets,
                "available_balance": max_withdraw,
                "liquidity_percentage": liquidity_percentage,
                "token_decimals": token_decimals,
                "silo_decimals": decimals,
                "shares": share_balance,
            }

            logger.info(f"Withdrawal info for Silo {silo_address}: {result}")
            return result

        except Exception as e:
            logger.error(f"Error getting withdrawal info: {e}")
            return {
                "total_balance": 0,
                "available_balance": 0,
                "liquidity_percentage": 0,
                "error": str(e),
            }


class RhoOperator(BaseProtocolOperator):
    """Class for working with Rho protocol"""

    def supply(self, token: str, amount: float) -> str:
        """Supply tokens to Rho protocol"""
        token_address = get_token_address(token, self.network)
        amount_wei = self._convert_to_wei(token_address, amount)

        # Проверяем баланс
        # Create token contract
        with open(ABI_DIR / "ERC20.json") as f:
            token_contract = self.w3.eth.contract(
                address=token_address, abi=json.load(f)
            )

        decimals = token_contract.functions.decimals().call()
        balance = token_contract.functions.balanceOf(self.account.address).call()
        balance_human = balance / 10**decimals

        logger.info(f"Current balance of {token}: {balance_human}")

        if balance < amount_wei:
            logger.error(
                f"Insufficient {token} balance: {balance_human}, needed: {amount}"
            )
            raise ValueError(f"Insufficient {token} balance")

        rho_market_address = RHO_ADDRESSES[self.network][token.lower()]

        # Проверяем разрешение на использование токенов
        allowance = token_contract.functions.allowance(
            self.account.address, rho_market_address
        ).call()

        rho_market_contract = self.w3.eth.contract(
            address=rho_market_address,
            abi=json.load(open(ABI_DIR / "ERC20-rhoMarket.json")),
        )

        if allowance < amount_wei:
            approve_tx = token_contract.functions.approve(
                rho_market_address,
                amount_wei * 2,  # С запасом
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
            logger.info(
                f"Checking if token {token} ({token_address}) is supported in {self.network} pool"
            )

            rho_market_address = RHO_ADDRESSES[self.network][token.lower()]
            rho_market_contract = self.w3.eth.contract(
                address=rho_market_address,
                abi=json.load(open(ABI_DIR / "ERC20-rhoMarket.json")),
            )

            # Use direct call() as in get_balance
            decimals = rho_market_contract.functions.decimals().call()
            balance = rho_market_contract.functions.balanceOf(
                self.account.address
            ).call()
            logger.info(
                f"Current wallet balance: {balance / 10**decimals} {token} in {self.protocol} {token} makret"
            )

            amount_wei = self._convert_to_wei(token_address, amount)

            # if balance < amount_wei:
            #     raise ValueError(f"Insufficient balance: have {balance / 10 ** decimals}, need {amount_wei / 10 ** decimals}")

            # Execute withdrawal
            tx_func = rho_market_contract.functions.redeem(
                balance,  ## for DEMO PURPOSES withdraw all balance
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

            logger.info(
                f"Checking balance for token {token} ({token_address}) in Compound"
            )

            # Create token contract
            with open(ABI_DIR / "ERC20.json") as f:
                token_contract = self.w3.eth.contract(
                    address=token_address, abi=json.load(f)
                )

            # Get and log balance
            balance = token_contract.functions.balanceOf(self.account.address).call()
            decimals = token_contract.functions.decimals().call()

            # Для базового токена (обычно USDC) вызываем balanceOf
            balance_wei = self.contract.functions.balanceOf(self.account.address).call()
            balance_human = balance_wei / 10**decimals

            logger.info(
                f"User balance for {token}: {balance_human} in protocol {self.protocol}"
            )

            return balance
        except Exception as e:
            logger.error(f"Error getting protocol balance for {token}: {e}")
            return 0.0

    def supply(self, token: str, amount: float) -> str:
        """Supply tokens to Compound protocol"""
        token_address = get_token_address(token, self.network)
        amount_wei = self._convert_to_wei(token_address, amount)

        # Create token contract
        with open(ABI_DIR / "ERC20.json") as f:
            token_contract = self.w3.eth.contract(
                address=token_address, abi=json.load(f)
            )

        decimals = token_contract.functions.decimals().call()
        balance = token_contract.functions.balanceOf(self.account.address).call()
        balance_human = balance / 10**decimals

        logger.info(f"Current balance of {token}: {balance_human}")

        if balance < amount_wei:
            logger.error(
                f"Insufficient {token} balance: {balance_human}, needed: {amount}"
            )
            raise ValueError(f"Insufficient {token} balance")

        # Проверяем разрешение на использование токенов
        allowance = token_contract.functions.allowance(
            self.account.address, self.contract_address
        ).call()

        if allowance < amount_wei:
            # Увеличим апрув до amount_wei * 10 для будущих операций
            approve_tx = token_contract.functions.approve(
                self.contract_address,
                amount_wei * 10,  # Увеличил запас
            )

            approve_hash = self._send_transaction(approve_tx)
            logger.info(f"Approved {token} for Compound: {approve_hash}")

            # Добавим небольшую задержку после апрува
            time.sleep(2)

        # Выполняем поставку токенов
        try:
            supply_tx = self.contract.functions.supply(token_address, amount_wei)
            tx_hash = self._send_transaction(supply_tx)
            logger.info(f"Supply transaction successful: {tx_hash}")
            return tx_hash
        except Exception as e:
            logger.error(f"Supply transaction failed: {str(e)}")
            # Проверим allowance после ошибки
            current_allowance = token_contract.functions.allowance(
                self.account.address, self.contract_address
            ).call()
            logger.error(f"Current allowance after error: {current_allowance}")
            raise

    def withdraw(self, token: str, amount: float) -> str:
        """Withdraw tokens from Compound protocol"""

        token_address = get_token_address(token, self.network)
        amount_wei = self._convert_to_wei(token_address, amount)

        # Проверяем баланс
        # Create token contract
        with open(ABI_DIR / "ERC20.json") as f:
            token_contract = self.w3.eth.contract(
                address=token_address, abi=json.load(f)
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


class FluidOperator(BaseProtocolOperator):
    """Class for working with Fluid Finance lending protocol using direct contract interaction"""

    def _custom_send_transaction(self, tx_function):
        """
        Custom implementation to send transaction to avoid issues with raw transactions
        
        Args:
            tx_function: Transaction function to execute
            
        Returns:
            Transaction hash if successful, None otherwise
        """
        try:
            # Используем новый метод для отправки EIP-1559 транзакций
            logger.info("Using EIP-1559 transaction format for Fluid")
            return self._send_transaction_eip1559(tx_function)
            
        except Exception as e:
            logger.error(f"Error sending custom transaction: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None
            
    def _print_contract_info(self, contract):
        """
        Print detailed information about a contract for debugging purposes
        
        Args:
            contract: Web3 contract instance
        """
        logger.info(f"Contract address: {contract.address}")
        
        # Get a list of all available functions
        functions = []
        for attr in dir(contract.functions):
            if not attr.startswith('_'):
                functions.append(attr)
        
        logger.info(f"Available functions ({len(functions)}):")
        for func in functions:
            logger.info(f"  - {func}")
            
        # Try to identify if this is an ERC4626 vault
        erc4626_functions = [
            'asset', 'totalAssets', 'convertToShares', 'convertToAssets', 
            'maxDeposit', 'previewDeposit', 'deposit', 'maxMint', 
            'previewMint', 'mint', 'maxWithdraw', 'previewWithdraw', 
            'withdraw', 'maxRedeem', 'previewRedeem', 'redeem'
        ]
        
        erc4626_count = 0
        for func in erc4626_functions:
            if func in functions:
                erc4626_count += 1
                
        erc4626_match = erc4626_count / len(erc4626_functions)
        logger.info(f"ERC4626 compatibility: {erc4626_count}/{len(erc4626_functions)} functions ({erc4626_match:.0%})")
        
        # Try to find the correct deposit function signature
        deposit_functions = [f for f in functions if 'deposit' in f.lower()]
        logger.info(f"Deposit-related functions: {deposit_functions}")
        
        # Check ABI for deposit function details
        deposit_abis = []
        for item in contract.abi:
            if item.get('type') == 'function' and item.get('name') == 'deposit':
                deposit_abis.append(item)
                
        if deposit_abis:
            logger.info("Deposit function ABI details:")
            for i, abi in enumerate(deposit_abis):
                logger.info(f"  Deposit variant {i+1}:")
                logger.info(f"    Inputs: {json.dumps(abi.get('inputs', []))}")
                logger.info(f"    Outputs: {json.dumps(abi.get('outputs', []))}")
        else:
            logger.info("No deposit function found in ABI")

    def get_balance(self, token: str) -> float:
        """
        Get current balance of fToken (e.g. fUSDC)

        Args:
            token: Token symbol (e.g. 'USDC')

        Returns:
            Balance as float
        """
        try:
            # Получаем контракт vault токена (fToken)
            vault_token_contract = self.contract if token.upper() == "USDC" else self._load_contract()

            # Получаем баланс пользователя (количество fToken)
            balance_wei = vault_token_contract.functions.balanceOf(self.account.address).call()

            # Получаем количество десятичных знаков для fToken
            decimals = vault_token_contract.functions.decimals().call()

            # Конвертируем в человеко-читаемый формат
            balance = balance_wei / 10**decimals

            logger.info(f"Balance of f{token} tokens: {balance}")
            return balance

        except Exception as e:
            logger.error(f"Error getting Fluid balance for {token}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return 0.0

    def test_approval(self, token: str, amount: float) -> bool:
        """
        Test token approval for Fluid vault separately
        
        Args:
            token: Token symbol (e.g. 'USDC')
            amount: Amount to approve
            
        Returns:
            True if approval successful, False otherwise
        """
        try:
            # Get token address and contract
            token_address = get_token_address(token, self.network)
            token_contract = self.w3.eth.contract(address=token_address, abi=json.load(open(ABI_DIR / "ERC20.json")))
            
            # Get vault contract
            vault_contract = self.contract if token.upper() == "USDC" else self._load_contract()
            
            # Log addresses
            logger.info("=== APPROVAL TEST ===")
            logger.info(f"Token address: {token_address}")
            logger.info(f"Vault address: {vault_contract.address}")
            logger.info(f"User address: {self.account.address}")
            
            # Check decimals and convert amount
            decimals = token_contract.functions.decimals().call()
            amount_wei = int(amount * 10**decimals)
            logger.info(f"Amount to approve: {amount} {token} ({amount_wei} wei)")
            
            # Check current allowance
            current_allowance = token_contract.functions.allowance(
                self.account.address, vault_contract.address
            ).call()
            logger.info(f"Current allowance: {current_allowance / 10**decimals} {token}")
            
            # Check if approval is needed
            if current_allowance >= amount_wei:
                logger.info("Current allowance is already sufficient")
                return True
                
            # Create approval transaction
            approve_amount = amount_wei * 2  # Approve double the amount
            logger.info(f"Creating approval for {approve_amount} wei ({approve_amount / 10**decimals} {token})")
            
            # Create the approval function
            approve_function = token_contract.functions.approve(vault_contract.address, approve_amount)
            
            # Execute transaction with lower gas limit specifically for approval
            try:
                # Estimate gas
                gas_estimate = approve_function.estimate_gas({'from': self.account.address})
                logger.info(f"Estimated gas for approval: {gas_estimate}")
                gas_limit = int(gas_estimate * 1.5)  # 50% buffer
            except Exception as e:
                logger.warning(f"Gas estimation failed for approval: {e}")
                gas_limit = 70000  # Standard ERC20 approve is around 45k-60k gas
                
            logger.info(f"Using gas limit of {gas_limit} for approval")
            
            # Get nonce
            nonce = self.w3.eth.get_transaction_count(self.account.address, "pending")
            
            # Get gas parameters
            latest_block = self.w3.eth.get_block('latest')
            base_fee = latest_block.get('baseFeePerGas', 0)
            priority_fee = self.w3.eth.max_priority_fee
            max_fee = base_fee * 2 + priority_fee
            
            # Build transaction
            tx_data = approve_function.build_transaction({
                'from': self.account.address,
                'nonce': nonce,
                'gas': gas_limit,
                'maxFeePerGas': max_fee,
                'maxPriorityFeePerGas': priority_fee,
                'chainId': int(self.w3.eth.chain_id)
            })
            
            # Sign and send
            signed_tx = self.account.sign_transaction(tx_data)
            tx_hash = self.w3.eth.send_raw_transaction(signed_tx.raw_transaction)
            tx_hash_hex = tx_hash.hex()
            
            logger.info(f"Approval transaction sent: {tx_hash_hex}")
            
            # Wait for confirmation
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=180)
            
            if receipt.status == 1:
                logger.info(f"Approval transaction succeeded, gas used: {receipt.gasUsed}")
                
                # Verify new allowance
                time.sleep(10)  # Wait for blockchain state to update
                new_allowance = token_contract.functions.allowance(
                    self.account.address, vault_contract.address
                ).call()
                
                logger.info(f"New allowance: {new_allowance / 10**decimals} {token}")
                
                if new_allowance >= amount_wei:
                    logger.info("Approval successful!")
                    return True
                else:
                    logger.error("Approval transaction succeeded but allowance did not increase")
                    return False
            else:
                logger.error(f"Approval transaction failed, status: {receipt.status}")
                return False
                
        except Exception as e:
            logger.error(f"Error during approval test: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False

    def supply(self, token: str, amount: float) -> str:
        """
        Supply tokens to Fluid protocol using deposit method

        Args:
            token: Token symbol (e.g. 'USDC')
            amount: Amount to supply

        Returns:
            Transaction hash if successful, None otherwise
        """
        try:
            # Получаем адрес токена
            token_address = get_token_address(token, self.network)
            
            # Получаем контракт токена
            token_contract = self.w3.eth.contract(address=token_address, abi=json.load(open(ABI_DIR / "ERC20.json")))
            
            # Получаем контракт vault
            token_vault_contract = self.contract if token.upper() == "USDC" else self._load_contract()
            
            # Print detailed contract information for debugging
            logger.info(f"Analyzing ERC4626 vault contract for {token}...")
            self._print_contract_info(token_vault_contract)
            
            # Log contract addresses for debugging
            logger.info(f"Token address: {token_address}")
            logger.info(f"Vault contract address: {token_vault_contract.address}")
            
            # Получаем количество десятичных знаков для токена
            decimals = token_contract.functions.decimals().call()
            
            # Конвертируем сумму в wei
            amount_wei = int(amount * 10**decimals)
            logger.info(f"Amount in Wei: {amount_wei} (Decimals: {decimals})")
            
            # Проверяем баланс пользователя
            user_balance = token_contract.functions.balanceOf(self.account.address).call()
            logger.info(f"User balance: {user_balance / 10**decimals} {token} ({user_balance} wei)")
            
            if user_balance < amount_wei:
                logger.error(f"Insufficient {token} balance: {user_balance / 10**decimals}, needed: {amount}")
                return None

            # Проверяем, есть ли уже достаточный allowance для основного контракта
            allowance = token_contract.functions.allowance(
                self.account.address, token_vault_contract.address
            ).call()
            logger.info(f"Current allowance: {allowance / 10**decimals} {token} ({allowance} wei)")
            
            # Если allowance недостаточно, выполняем approve SEPARATELY
            if allowance < amount_wei:
                try:
                    logger.info(f"Insufficient allowance. Approving {amount_wei} of {token} for Fluid contract")
                    
                    # Create the approve transaction with a more reliable implementation
                    approve_amount = amount_wei * 2  # Double the amount needed
                    approve_function = token_contract.functions.approve(token_vault_contract.address, approve_amount)
                    
                    # Try to estimate gas for approval
                    try:
                        gas_estimate = approve_function.estimate_gas({'from': self.account.address})
                        logger.info(f"Estimated gas for approval: {gas_estimate}")
                        gas_limit = int(gas_estimate * 1.5)  # 50% buffer
                    except Exception as e:
                        logger.warning(f"Gas estimation failed for approval: {e}")
                        gas_limit = 70000  # Standard ERC20 approve uses ~45k-60k gas
                    
                    logger.info(f"Using gas limit of {gas_limit} for approval")
                    
                    # Get current nonce
                    nonce = self.w3.eth.get_transaction_count(self.account.address, "pending")
                    
                    # Get gas parameters
                    latest_block = self.w3.eth.get_block('latest')
                    base_fee = latest_block.get('baseFeePerGas', 0)
                    priority_fee = self.w3.eth.max_priority_fee
                    max_fee = base_fee * 2 + priority_fee
                    
                    # Build transaction
                    approval_tx = approve_function.build_transaction({
                        'from': self.account.address,
                        'nonce': nonce,
                        'gas': gas_limit,
                        'maxFeePerGas': max_fee,
                        'maxPriorityFeePerGas': priority_fee,
                        'chainId': int(self.w3.eth.chain_id)
                    })
                    
                    # Sign and send
                    signed_tx = self.account.sign_transaction(approval_tx)
                    tx_hash = self.w3.eth.send_raw_transaction(signed_tx.raw_transaction)
                    approve_hash = tx_hash.hex()
                    
                    logger.info(f"Approval transaction sent: {approve_hash}")
                    logger.info("Waiting for approval transaction confirmation...")
                    
                    # Wait for confirmation
                    receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=180)
                    
                    if receipt.status == 1:
                        logger.info(f"Approval transaction successful, used gas: {receipt.gasUsed}")
                    else:
                        logger.error(f"Approval transaction failed, receipt status: {receipt.status}")
                        return None
                        
                    # Add a wait to ensure the approval is confirmed
                    logger.info("Waiting for approval to be confirmed...")
                    time.sleep(15)
                    
                    # Verify new allowance
                    new_allowance = token_contract.functions.allowance(
                        self.account.address, token_vault_contract.address
                    ).call()
                    
                    logger.info(f"New allowance after approval: {new_allowance / 10**decimals} {token} ({new_allowance} wei)")
                    
                    if new_allowance < amount_wei:
                        logger.error("Approval transaction did not increase allowance sufficiently")
                        return None
                except Exception as e:
                    logger.error(f"Error during approval process: {e}")
                    import traceback
                    logger.error(traceback.format_exc())
                    return None
            
            # Once approval is confirmed, proceed with deposit
            logger.info(f"Depositing {amount} {token} to Fluid")
            
            try:
                # Get contract interface directly
                logger.info(f"Using verified deposit function: deposit(uint256 assets, address receiver)")
                
                # Try to call the function first to check for errors
                try:
                    deposit_func = token_vault_contract.functions.deposit(amount_wei, self.account.address)
                    # Test if this would work using call() first
                    logger.info("Checking if deposit would succeed...")
                    result = deposit_func.call({'from': self.account.address})
                    logger.info(f"Deposit call successful, would return: {result}")
                except Exception as e:
                    error_str = str(e)
                    logger.error(f"Deposit call check failed: {error_str}")
                    
                    # Try to extract more useful error information
                    if "execution reverted" in error_str:
                        try:
                            revert_reason = error_str.split('message":"')[1].split('"')[0]
                            logger.error(f"Revert reason: {revert_reason}")
                        except:
                            logger.error("Could not extract revert reason")
                            
                    logger.info("Checking vault requirements...")
                    
                    # Check deposit limits
                    try:
                        # Check max deposit
                        if hasattr(token_vault_contract.functions, 'maxDeposit'):
                            max_deposit = token_vault_contract.functions.maxDeposit(self.account.address).call()
                            logger.info(f"Maximum deposit allowed: {max_deposit} (attempting {amount_wei})")
                            if amount_wei > max_deposit:
                                logger.error(f"Deposit amount exceeds maximum allowed ({amount_wei} > {max_deposit})")
                                return None
                    except Exception as limit_error:
                        logger.warning(f"Could not check max deposit: {limit_error}")
                        
                    # Try a smaller amount as a fallback
                    try:
                        test_amount = amount_wei // 10  # 10% of original amount
                        logger.info(f"Trying with a smaller test amount: {test_amount} wei")
                        result = token_vault_contract.functions.deposit(test_amount, self.account.address).call({'from': self.account.address})
                        logger.info(f"Smaller deposit call succeeded with result: {result}")
                        logger.info("Will proceed with original amount in actual transaction")
                    except Exception as test_error:
                        logger.error(f"Even smaller deposit test failed: {test_error}")
                        logger.error("Deposit operation likely to fail - protocol may have restrictions")
                        # We'll still try but with high chance of failure
                
                # Proceed with transaction regardless of call check (it might still work)
                deposit_tx = token_vault_contract.functions.deposit(amount_wei, self.account.address)
                
                # Get a new nonce
                nonce = self.w3.eth.get_transaction_count(self.account.address, "pending")
                
                # Calculate gas parameters
                latest_block = self.w3.eth.get_block('latest')
                base_fee = latest_block.get('baseFeePerGas', 0)
                priority_fee = self.w3.eth.max_priority_fee
                max_fee = base_fee * 2 + priority_fee
                
                # Set higher gas limit for safety
                gas_limit = 500000  # Higher limit as we've had issues
                
                # Build transaction
                deposit_tx_data = deposit_tx.build_transaction({
                    'from': self.account.address,
                    'nonce': nonce,
                    'gas': gas_limit,
                    'maxFeePerGas': max_fee,
                    'maxPriorityFeePerGas': priority_fee,
                    'chainId': int(self.w3.eth.chain_id)
                })
                
                # Sign and send transaction
                signed_tx = self.account.sign_transaction(deposit_tx_data)
                tx_hash = self.w3.eth.send_raw_transaction(signed_tx.raw_transaction)
                deposit_hash = tx_hash.hex()
                
                logger.info(f"Deposit transaction sent: {deposit_hash}")
                logger.info("Waiting for deposit transaction confirmation...")
                
                # Wait for confirmation
                receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=300)
                
                if receipt.status == 1:
                    logger.info(f"Deposit transaction successful, used gas: {receipt.gasUsed}")
                    return deposit_hash
                else:
                    logger.error(f"Deposit transaction failed, receipt status: {receipt.status}")
                    return None
                
            except Exception as e:
                logger.error(f"Error during deposit process: {e}")
                import traceback
                logger.error(traceback.format_exc())
                return None

        except Exception as e:
            logger.error(f"Error supplying {token} to Fluid: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None

    def withdraw(self, token: str, amount: float) -> str:
        """
        Withdraw tokens from Fluid protocol using redeem method

        Args:
            token: Token symbol (e.g. 'USDC')
            amount: Amount to withdraw (in base tokens, not shares)

        Returns:
            Transaction hash if successful, None otherwise
        """
        try:
            token_address = get_token_address(token, self.network)

            # Получаем контракты
            vault_token_contract = self.contract if token.upper() == "USDC" else self._load_contract()
            token_contract = self.w3.eth.contract(address=token_address, abi=json.load(open(ABI_DIR / "ERC20.json")))
            
            # Получаем десятичные знаки
            decimals = token_contract.functions.decimals().call()
            vault_decimals = vault_token_contract.functions.decimals().call()
            
            # Конвертируем сумму в wei
            amount_wei = int(amount * 10**decimals)
            
            # Получаем текущий баланс в vault
            current_balance = self.get_balance(token)
            if current_balance < amount:
                logger.error(f"Insufficient {token} balance in Fluid: {current_balance}, needed: {amount}")
                return None
            
            # Проверяем общий баланс vault токенов (fTokens)
            vault_balance_wei = vault_token_contract.functions.balanceOf(self.account.address).call()
            
            # Расчитываем примерное количество shares для вывода заданной суммы
            try:
                # Используем convertToShares, если такая функция есть
                shares_to_redeem = vault_token_contract.functions.convertToShares(amount_wei).call()
                logger.info(f"Using convertToShares: {shares_to_redeem} shares for {amount_wei} tokens")
            except Exception:
                # Если функции нет, используем соотношение
                try:
                    price_per_share = vault_token_contract.functions.convertToAssets(10**vault_decimals).call() / 10**decimals
                    shares_to_redeem = int(amount_wei / price_per_share)
                    logger.info(f"Calculated shares: {shares_to_redeem} for {amount_wei} tokens")
                except Exception:
                    # Если и это не работает, просто используем имеющиеся shares
                    shares_to_redeem = vault_balance_wei
                    logger.info(f"Using all available shares: {shares_to_redeem}")
            
            # Убедимся, что не выводим больше, чем есть
            if shares_to_redeem > vault_balance_wei:
                shares_to_redeem = vault_balance_wei
                logger.info(f"Adjusted shares to redeem to maximum available: {shares_to_redeem}")
            
            logger.info(f"Withdrawing {amount} {token} (approx. {shares_to_redeem/(10**vault_decimals)} shares)")
            
            # Выполняем redeem для вывода средств
            try:
                # Пробуем стандартный метод redeem
                redeem_tx = vault_token_contract.functions.redeem(
                    shares_to_redeem, 
                    self.account.address,  # receiver
                    self.account.address   # owner
                )
                tx_hash = self._send_transaction_eip1559(redeem_tx)
            except Exception as e:
                logger.error(f"Error calling redeem: {e}")
                # Пробуем метод withdraw
                try:
                    withdraw_tx = vault_token_contract.functions.withdraw(
                        amount_wei,
                        self.account.address,  # receiver
                        self.account.address   # owner
                    )
                    tx_hash = self._send_transaction_eip1559(withdraw_tx)
                except Exception as alt_e:
                    logger.error(f"Error with withdraw method: {alt_e}")
                    return None
            
            if tx_hash:
                logger.info(f"Successfully withdrew approx. {amount} {token} from Fluid: {tx_hash}")
                return tx_hash
            else:
                logger.error("Failed to withdraw tokens from Fluid")
                return None
                
        except Exception as e:
            logger.error(f"Error withdrawing {token} from Fluid: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None


def get_protocol_operator(network: str, protocol: str, **kwargs):
    """Get protocol operator instance for a given network and protocol"""
    # Normalize protocol name
    protocol_lower = protocol.lower()

    if network not in RPC_URLS:
        raise ValueError(f"Unsupported network: {network}")

    # Match protocol to operator class
    if protocol_lower == "aave-v3" or protocol_lower == "aave-v2":
        return AaveOperator(network, protocol_lower)
    elif protocol_lower == "lendle":
        return LendleOperator(network, protocol_lower)
    elif protocol_lower == "yieldex-oracle":
        return YieldexOracleOperator(network)
    elif protocol_lower == "curve":
        pool_name = kwargs.get("pool_name", "USDT_FRAX")
        return CurveOperator(network, pool_name)
    elif protocol_lower == "uniswap-v3":
        return UniswapV3Operator(network, protocol_lower)
    elif protocol_lower == "silo-v2":
        market_id = kwargs.get("market_id", None)
        return SiloOperator(network, market_id)
    elif protocol_lower == "compound-v3":
        return CompoundOperator(network, protocol_lower)
    elif protocol_lower == "rho-markets":
        return RhoOperator(network, protocol_lower)
    elif protocol_lower == "fluid":
        return FluidOperator(network, protocol_lower)
    else:
        supported = [
            "aave-v3",
            "aave-v2",
            "lendle",
            "yieldex-oracle",
            "curve",
            "uniswap-v3",
            "silo-v2",
            "compound-v3",
            "rho-markets",
            "fluid",
        ]
        raise ValueError(
            f"Unsupported protocol: {protocol}. Supported protocols: {supported}"
        )


def main():
    # Инициализация оператора
    # aave = get_protocol_operator("Arbitrum", "aave-v3")

    recommendations = get_recommendations(chain="Scroll", same_asset_only=True)

    print(format_recommendations(recommendations))

    executor = RecommendationExecutor(recommendations[0])

    # # Вывод USDC
    # tx_hash = fluid.withdraw("USDC", 0.5)
    # if tx_hash:
    #     print(f"USDC Withdrawal transaction hash: {tx_hash}")
    # else:
    #     print(f"USDC Withdrawal failed. Check logs for details.")


if __name__ == "__main__":
    main()
