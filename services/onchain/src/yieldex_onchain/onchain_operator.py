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

from yieldex_common.utils import get_token_address
from yieldex_onchain.protocol_fabric import get_protocol_operator
from analyzer.analyzer import (
    format_recommendation,
    format_recommendations,
    get_recommendations,
)
from yieldex_onchain.protocol_fabric import CollateralType, SiloOperator

logger = logging.getLogger(__name__)


class RecommendationExecutor:
    """Class for executing different types of recommendation flows"""

    def __init__(self, recommendation: dict):
        self.recommendation = recommendation
        self.type = recommendation.get("recommendation_type")
        self.from_chain = recommendation.get("from_chain")
        self.to_chain = recommendation.get("to_chain")
        self.asset = recommendation.get("asset")
        self.to_asset = recommendation.get("to_asset")
        self.amount = recommendation.get("position_size")
        self.from_protocol = recommendation.get("from_protocol")
        self.to_protocol = recommendation.get("to_protocol")

    def execute(self) -> Dict[str, str]:
        """
        Execute recommendation flow based on type

        Returns:
            Dictionary with transaction hashes for each step
        """
        if self.type == "standard_transfer":
            if self.from_chain == self.to_chain and self.asset == self.to_asset:
                return self._execute_same_chain_same_asset()
            elif self.from_chain == self.to_chain:
                return self._execute_same_chain_swap()
            else:
                return self._execute_cross_chain()
        elif self.type == "silo_market_transfer":
            return self._execute_silo_market_transfer()
        else:
            raise ValueError(f"Unknown recommendation type: {self.type}")

    def _execute_same_chain_same_asset(self) -> Dict[str, str]:
        """Execute transfer between protocols on same chain with same asset"""
        try:
            logger.info(
                f"Executing same chain transfer: {self.asset} from {self.from_protocol} to {self.to_protocol}"
            )

            # Get source protocol operator
            from_operator = get_protocol_operator(self.from_chain, self.from_protocol)

            # Withdraw from source protocol
            withdraw_tx = from_operator.withdraw(self.asset, self.amount)
            logger.info(f"Withdrawal successful: {withdraw_tx}")

            # Get target protocol operator
            to_operator = get_protocol_operator(self.to_chain, self.to_protocol)

            # Deposit to target protocol
            deposit_tx = to_operator.supply(self.asset, self.amount)
            logger.info(f"Deposit successful: {deposit_tx}")

            return {
                "withdraw_tx": withdraw_tx,
                "deposit_tx": deposit_tx,
                "status": "success",
            }

        except Exception as e:
            logger.error(f"Failed to execute same chain transfer: {str(e)}")
            return {"status": "failed", "error": str(e)}

    def _execute_same_chain_swap(self) -> Dict[str, str]:
        """Execute swap and transfer on same chain"""
        try:
            # Use existing implementation
            return execute_uniswap_flow(
                {
                    "from_chain": self.from_chain,
                    "asset": self.asset,
                    "to_asset": self.to_asset,
                    "position_size": self.amount,
                }
            )

        except Exception as e:
            logger.error(f"Failed to execute same chain swap: {str(e)}")
            return {"status": "failed", "error": str(e)}

    def _execute_cross_chain(self) -> Dict[str, str]:
        """Execute cross-chain transfer"""
        raise NotImplementedError("Cross-chain transfers are not yet implemented")

    def _execute_silo_market_transfer(self) -> Dict[str, str]:
        """Execute transfer between Silo markets"""
        try:
            # Extract additional Silo-specific fields from recommendation
            from_market = self.recommendation.get("from_market_id")
            to_market = self.recommendation.get("to_market_id")

            if not all([from_market, to_market]):
                raise ValueError("Missing required Silo market IDs in recommendation")

            # Use existing implementation but with our class fields
            return execute_silo_market_transfer(
                {
                    "asset": self.asset,
                    "from_chain": self.from_chain,
                    "from_market_id": from_market,
                    "to_market_id": to_market,
                    "position_size": self.amount,
                }
            )

        except Exception as e:
            logger.error(f"Failed to execute Silo market transfer: {str(e)}")
            return {"status": "failed", "error": str(e)}


def execute_uniswap_flow(recommendation: dict):
    """Execute full swap flow using Uniswap V3"""
    try:
        chain = recommendation["from_chain"]
        asset = recommendation["asset"]
        to_asset = recommendation["to_asset"]
        amount = recommendation["position_size"]

        logger.info(f"Starting Uniswap flow for {amount} {asset} on {chain}")

        # Initialize operator and check token support
        aave_operator = get_protocol_operator(chain, "aave-v3")
        token_address = get_token_address(asset, chain)

        if not aave_operator._check_token_support(token_address):
            raise ValueError(f"Token {asset} not supported in {chain} pool")

        # Execute withdrawal
        withdraw_tx = aave_operator.withdraw(asset, amount)
        logger.info(f"Withdrawal successful: {withdraw_tx}")

        # Execute swap
        uniswap_operator = get_protocol_operator(chain, "uniswap-v3")
        swap_tx = uniswap_operator.swap(asset, to_asset, amount, 0.1)
        logger.info(f"Swap successful: {swap_tx}")

        # Execute deposit
        deposit_tx = aave_operator.supply(to_asset, amount)
        logger.info(f"Deposit successful: {deposit_tx}")

        return {
            "withdraw_tx": withdraw_tx,
            "swap_tx": swap_tx,
            "deposit_tx": deposit_tx,
        }

    except Exception as e:
        logger.error(f"Failed to execute Uniswap flow: {str(e)}")
        raise


def execute_silo_market_transfer(recommendation: dict):
    """
    Execute the transfer of assets between Silo markets based on recommendation

    Args:
        recommendation: Dictionary with market transfer details

    Returns:
        Dictionary with transaction hashes
    """
    try:
        # Extract recommendation details
        asset = recommendation.get("asset")
        chain = recommendation.get("from_chain")
        from_market = recommendation.get("from_market_id")
        to_market = recommendation.get("to_market_id")
        position_size = recommendation.get("position_size")

        logger.info(
            f"Executing Silo market transfer: {asset} from market {from_market} to market {to_market} on {chain}"
        )

        # Import modules from our project
        from yieldex_onchain.protocol_fabric import CollateralType, SiloOperator
        from yieldex_onchain.silo_demo import (
            display_market_info,
            run_deposit_flow,
            run_withdraw_flow,
        )

        # Display information about both markets before transfer
        logger.info(f"Source market {from_market} information before transfer:")
        source_operator = SiloOperator(chain, from_market)
        display_market_info(source_operator, from_market)

        logger.info(f"Target market {to_market} information before transfer:")
        target_operator = SiloOperator(chain, to_market)
        display_market_info(target_operator, to_market)

        # Get the silos for each market
        source_silos = source_operator.find_silos_for_market(from_market)
        target_silos = target_operator.find_silos_for_market(to_market)

        logger.info(f"Found {len(source_silos)} silos for source market {from_market}")
        logger.info(f"Found {len(target_silos)} silos for target market {to_market}")

        # Debug: Log the structure of the silos list
        for i, silo in enumerate(source_silos):
            logger.info(f"Source silo {i + 1} structure: {silo}")

        # Find the Protected Silo in source market
        source_protected_silo = None
        for silo in source_silos:
            # Check if this is the Protected silo for USDC.E
            if (
                "type" in silo
                and silo["type"] == "Protected"
                and asset in silo.get("name", "")
            ):
                source_protected_silo = silo.get("address")
                logger.info(
                    f"Found Protected Silo for source market using type field: {source_protected_silo}"
                )
                break
            elif "Protected" in str(silo) and asset in str(silo):
                # Extract address from the silo info
                if "address" in silo:
                    source_protected_silo = silo["address"]
                    logger.info(
                        f"Found Protected Silo for source market using address field: {source_protected_silo}"
                    )
                    break

        # Direct assignment if we know the structure from logs
        if not source_protected_silo and len(source_silos) >= 2:
            # Try the second silo which is often the Protected one based on logs
            if isinstance(source_silos[1], dict) and "address" in source_silos[1]:
                source_protected_silo = source_silos[1]["address"]
                logger.info(
                    f"Using second silo as Protected Silo for source market: {source_protected_silo}"
                )

        # If still not found, try a more direct approach based on the log output
        if not source_protected_silo:
            # Extract the address from the log output string that contains 'Protected' and asset
            import re

            for line in str(source_silos).split("\n"):
                if "Protected" in line and asset in line:
                    # Look for the next line with 'Address:'
                    address_match = re.search(r"Address: (0x[a-fA-F0-9]+)", line)
                    if address_match:
                        source_protected_silo = address_match.group(1)
                        logger.info(
                            f"Extracted Protected Silo address from log: {source_protected_silo}"
                        )
                        break

            # If still not found, use a hardcoded address from the logs
            if not source_protected_silo and from_market == "34":
                source_protected_silo = "0x6030aD53d90ec2fB67F3805794dBB3Fa5FD6Eb64"  # From logs for market 34
                logger.info(
                    f"Using hardcoded Protected Silo address for market 34: {source_protected_silo}"
                )

        # Find the Protected Silo in target market with same approach
        target_protected_silo = None
        for silo in target_silos:
            if (
                "type" in silo
                and silo["type"] == "Protected"
                and asset in silo.get("name", "")
            ):
                target_protected_silo = silo.get("address")
                logger.info(
                    f"Found Protected Silo for target market using type field: {target_protected_silo}"
                )
                break
            elif "Protected" in str(silo) and asset in str(silo):
                if "address" in silo:
                    target_protected_silo = silo["address"]
                    logger.info(
                        f"Found Protected Silo for target market using address field: {target_protected_silo}"
                    )
                    break

        # Direct assignment if we know the structure
        if not target_protected_silo and len(target_silos) >= 2:
            if isinstance(target_silos[1], dict) and "address" in target_silos[1]:
                target_protected_silo = target_silos[1]["address"]
                logger.info(
                    f"Using second silo as Protected Silo for target market: {target_protected_silo}"
                )

        # If still not found, try the same direct approach
        if not target_protected_silo:
            for line in str(target_silos).split("\n"):
                if "Protected" in line and asset in line:
                    address_match = re.search(r"Address: (0x[a-fA-F0-9]+)", line)
                    if address_match:
                        target_protected_silo = address_match.group(1)
                        logger.info(
                            f"Extracted Protected Silo address from log: {target_protected_silo}"
                        )
                        break

            # If still not found, use hardcoded address from the logs
            if not target_protected_silo and to_market == "27":
                target_protected_silo = "0x7e88AE5E50474A48deA4c42a634aA7485e7CaA62"  # From logs for market 27
                logger.info(
                    f"Using hardcoded Protected Silo address for market 27: {target_protected_silo}"
                )

        # Final check for Protected Silo addresses
        if not source_protected_silo:
            logger.error(
                f"Could not find Protected Silo for source market {from_market}"
            )
            return {"status": "failed", "reason": "source_silo_not_found"}

        if not target_protected_silo:
            logger.error(f"Could not find Protected Silo for target market {to_market}")
            return {"status": "failed", "reason": "target_silo_not_found"}

        # Check our balance in the source Silo
        balance = source_operator.get_silo_balance(source_protected_silo)
        logger.info(f"Our balance in source market {from_market}: {balance} {asset}")

        if not balance or balance < 0.001:  # Minimal amount to consider
            logger.warning(f"Insufficient balance in market {from_market}: {balance}")
            return {"status": "failed", "reason": "insufficient_balance"}

        # Check available balance and max withdraw using the correct Silo address
        max_withdraw = source_operator.get_max_withdraw(
            source_protected_silo, collateral_type=CollateralType.PROTECTED
        )
        logger.info(
            f"Maximum withdrawable amount from market {from_market}: {max_withdraw}"
        )

        if (
            not max_withdraw or max_withdraw < position_size * 0.01
        ):  # At least 1% available
            logger.warning(f"Insufficient withdrawable funds in market {from_market}")
            return {"status": "failed", "reason": "insufficient_withdrawable_funds"}

        # Amount to transfer - either the whole position or max withdrawable if lower
        amount_to_transfer = min(position_size, max_withdraw)
        logger.info(f"Amount to transfer: {amount_to_transfer} {asset}")

        # Prepare withdrawal parameters for source market
        withdrawal_params = {
            "silo_address": source_protected_silo,
            "amount": amount_to_transfer,
            "collateral_type": CollateralType.PROTECTED,
        }

        # Execute withdrawal directly instead of using run_withdraw_flow to have more control
        logger.info(f"Executing withdrawal from market {from_market}")
        try:
            withdraw_tx = source_operator.withdraw(**withdrawal_params)
            logger.info(f"Withdrawal transaction initiated: {withdraw_tx}")
        except Exception as e:
            logger.error(f"Error during withdrawal: {str(e)}")
            return {"status": "failed", "reason": "withdrawal_error", "details": str(e)}

        # Wait a moment to ensure transaction is processed
        import time

        logger.info("Waiting for withdrawal transaction confirmation...")
        time.sleep(5)

        # Check wallet balance to ensure funds were withdrawn
        from yieldex_common.utils import get_token_address
        from yieldex_onchain.silo_demo import check_wallet_balance

        token_address = get_token_address(asset, chain)
        wallet_balance = check_wallet_balance(source_operator)
        logger.info(f"Wallet balance after withdrawal: {wallet_balance}")

        # Prepare deposit parameters for target market
        deposit_params = {
            "silo_address": target_protected_silo,
            "amount": amount_to_transfer,
        }

        # Execute deposit
        logger.info(f"Executing deposit to market {to_market}")
        try:
            deposit_tx = target_operator.deposit(**deposit_params)
            logger.info(f"Deposit transaction initiated: {deposit_tx}")
        except Exception as e:
            logger.error(f"Error during deposit: {str(e)}")
            return {
                "status": "partial",
                "reason": "deposit_error",
                "withdraw_tx": withdraw_tx,
                "details": str(e),
            }

        # Wait for deposit confirmation
        logger.info("Waiting for deposit transaction confirmation...")
        time.sleep(5)

        # Display final market information
        logger.info(f"Source market {from_market} information after transfer:")
        display_market_info(source_operator, from_market)

        logger.info(f"Target market {to_market} information after transfer:")
        display_market_info(target_operator, to_market)

        return {
            "status": "success",
            "withdraw_tx": withdraw_tx,
            "deposit_tx": deposit_tx,
            "amount_transferred": amount_to_transfer,
            "source_market": from_market,
            "target_market": to_market,
        }

    except Exception as e:
        logger.error(f"Failed to execute Silo market transfer: {str(e)}")
        import traceback

        logger.error(traceback.format_exc())
        return {"status": "failed", "reason": str(e)}


if __name__ == "__main__":
    # Geting recommendations
    recommendations = get_recommendations(chain="Arbitrum")

    # Selecting recommendation for execution
    # recommendation = recommendations[0]

    print(format_recommendations(recommendations))

    # # Executing recommendation
    # executor = RecommendationExecutor(recommendation)
    # result = executor.execute()

    # if result['status'] == 'success':
    #     print(f"Successfully executed: {result}")
    # else:
    #     print(f"Execution failed: {result['error']}")
