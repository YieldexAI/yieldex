"""
Module to apply DB tracking decorators to protocol operator methods
"""

import logging
from inspect import isfunction
from typing import Type

from yieldex_onchain.protocol_fabric import (
    AaveOperator,
    CompoundOperator,
    LendleOperator,
    SiloOperator,
    CurveOperator,
    UniswapV3Operator,
)
from yieldex_onchain.protocol_decorators import (
    track_withdraw,
    track_supply,
    sync_transaction_pool_balances,
)

logger = logging.getLogger(__name__)


def apply_decorators():
    """Apply tracking decorators to protocol operator methods"""
    logger.info("Applying decorators to protocol operators")

    # Apply to AaveOperator
    original_aave_withdraw = AaveOperator.withdraw
    original_aave_supply = AaveOperator.supply

    AaveOperator.withdraw = track_withdraw("aave-v3")(original_aave_withdraw)
    AaveOperator.supply = track_supply("aave-v3")(original_aave_supply)

    # Apply to CompoundOperator
    original_compound_withdraw = CompoundOperator.withdraw
    original_compound_supply = CompoundOperator.supply

    CompoundOperator.withdraw = track_withdraw("compound-v3")(
        original_compound_withdraw
    )
    CompoundOperator.supply = track_supply("compound-v3")(original_compound_supply)

    # Apply to LendleOperator
    original_lendle_withdraw = LendleOperator.withdraw
    original_lendle_deposit = LendleOperator.deposit

    LendleOperator.withdraw = track_withdraw("lendle")(original_lendle_withdraw)
    LendleOperator.deposit = track_supply("lendle")(original_lendle_deposit)

    # Apply to SiloOperator (more complex case)
    original_silo_withdraw = SiloOperator.withdraw
    original_silo_deposit = SiloOperator.deposit

    SiloOperator.withdraw = track_withdraw("silo-v2")(original_silo_withdraw)
    SiloOperator.deposit = track_supply("silo-v2")(original_silo_deposit)

    # Apply to transaction methods
    from yieldex_onchain.onchain_operator import (
        execute_silo_market_transfer,
        execute_uniswap_flow,
    )

    # Apply sync decorator to complex flow methods
    execute_silo_market_transfer = sync_transaction_pool_balances(
        execute_silo_market_transfer
    )
    execute_uniswap_flow = sync_transaction_pool_balances(execute_uniswap_flow)

    logger.info("Successfully applied decorators to protocol operators")


if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    apply_decorators()
