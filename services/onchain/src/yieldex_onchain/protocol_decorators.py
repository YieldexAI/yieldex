import functools
import logging
from typing import Callable, Any, Optional
import inspect
from yieldex_common.db_operations import update_pool_balance, get_pool_balance_by_pool_id

logger = logging.getLogger(__name__)

def extract_protocol_from_instance(instance) -> Optional[str]:
    """Extract protocol name from operator instance"""
    class_name = instance.__class__.__name__
    if 'Operator' in class_name:
        protocol = class_name.replace('Operator', '').lower()
        return protocol
    return None

def create_pool_id(asset: str, chain: str, protocol: str) -> str:
    """Create standard pool_id string"""
    return f"{asset}_{chain}_{protocol}"

def track_withdraw(old_protocol: str = None, new_protocol: str = None):
    """
    Decorator for withdraw methods
    
    This decorator should be applied to withdraw methods in protocol operators.
    It stores information about the withdrawal for later use in the supply operation.
    
    Args:
        old_protocol: Protocol name being withdrawn from (if None, extracted from class name)
        new_protocol: Protocol name funds will be deposited to
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            # Extract asset and amount from function arguments
            sig = inspect.signature(func)
            bound_args = sig.bind(self, *args, **kwargs)
            bound_args.apply_defaults()
            
            asset = bound_args.arguments.get('token', bound_args.arguments.get('asset', None))
            amount = bound_args.arguments.get('amount', 0)
            
            if not asset:
                logger.warning("Cannot track withdraw: missing asset information")
                return func(self, *args, **kwargs)
                
            # Extract chain from operator instance
            chain = getattr(self, 'network', None)
            if not chain:
                logger.warning("Cannot track withdraw: missing chain information")
                return func(self, *args, **kwargs)
                
            # Extract protocol name if not provided
            protocol = old_protocol or extract_protocol_from_instance(self)
            if not protocol:
                logger.warning("Cannot track withdraw: unable to determine protocol")
                return func(self, *args, **kwargs)
            
            # Create pool_id
            pool_id = create_pool_id(asset, chain, protocol)
            
            # Store information in the instance for later use
            if not hasattr(self, '_tracking_info'):
                self._tracking_info = {}
                
            self._tracking_info['withdraw'] = {
                'pool_id': pool_id,
                'asset': asset,
                'amount': amount,
                'chain': chain,
                'protocol': protocol,
                'new_protocol': new_protocol
            }
            
            # Execute the withdraw function
            try:
                result = func(self, *args, **kwargs)
                
                # Store transaction hash if returned
                if isinstance(result, str) and result.startswith('0x'):
                    self._tracking_info['withdraw']['tx_hash'] = result
                    
                return result
            except Exception as e:
                # Clear tracking info on failure
                if hasattr(self, '_tracking_info'):
                    self._tracking_info.pop('withdraw', None)
                raise
                
        return wrapper
    return decorator
    
def track_supply(new_protocol: str = None):
    """
    Decorator for supply/deposit methods
    
    This decorator should be applied to supply/deposit methods in protocol operators.
    It performs DB update based on the previous withdraw operation.
    
    Args:
        new_protocol: Protocol name being deposited to (if None, extracted from class name)
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            # Execute the supply function first
            try:
                result = func(self, *args, **kwargs)
                tx_hash = result if isinstance(result, str) and result.startswith('0x') else None
                
                # Extract asset and amount from function arguments
                sig = inspect.signature(func)
                bound_args = sig.bind(self, *args, **kwargs)
                bound_args.apply_defaults()
                
                asset = bound_args.arguments.get('token', bound_args.arguments.get('asset', None))
                amount = bound_args.arguments.get('amount', 0)
                
                if not asset:
                    logger.warning("Cannot track supply: missing asset information")
                    return result
                    
                # Extract chain from operator instance
                chain = getattr(self, 'network', None)
                if not chain:
                    logger.warning("Cannot track supply: missing chain information")
                    return result
                    
                # Extract protocol name if not provided
                protocol = new_protocol or extract_protocol_from_instance(self)
                if not protocol:
                    logger.warning("Cannot track supply: unable to determine protocol")
                    return result
                
                # Create new pool_id
                new_pool_id = create_pool_id(asset, chain, protocol)
                
                # Check if we have withdraw tracking info
                if hasattr(self, '_tracking_info') and 'withdraw' in self._tracking_info:
                    withdraw_info = self._tracking_info['withdraw']
                    old_pool_id = withdraw_info['pool_id']
                    
                    # Update the pool balance in the database
                    success = update_pool_balance(
                        old_pool_id=old_pool_id,
                        new_pool_id=new_pool_id,
                        position_balance=amount,
                        tx_hash=tx_hash or 'unknown'
                    )
                    
                    if success:
                        logger.info(f"Pool balance updated: {old_pool_id} -> {new_pool_id}")
                    else:
                        logger.error(f"Failed to update pool balance: {old_pool_id} -> {new_pool_id}")
                        
                    # Clear tracking info after processing
                    self._tracking_info.pop('withdraw', None)
                else:
                    logger.warning(f"No withdraw tracking info found. Skipping pool balance update for {new_pool_id}")
                
                return result
            except Exception as e:
                logger.error(f"Error in supply tracking: {str(e)}")
                # Still raise the exception to caller
                raise
                
        return wrapper
    return decorator

def sync_transaction_pool_balances(func):
    """
    Combined decorator that tracks both withdraw and supply operations
    
    This decorator should be applied to methods that perform both withdraw and supply
    in a single operation, like cross-protocol transfers.
    """
    @functools.wraps(func)
    def wrapper(self, *args, **kwargs):
        # Execute the function
        result = func(self, *args, **kwargs)
        
        # Check if result contains expected keys
        if isinstance(result, dict) and 'status' in result and result['status'] == 'success':
            # Extract details from result
            if all(k in result for k in ['from_market_id', 'to_market_id', 'chain', 'asset']):
                # For Silo market transfers
                chain = result.get('chain')
                asset = result.get('asset')
                from_market = result.get('from_market_id')
                to_market = result.get('to_market_id')
                amount = result.get('amount_transferred', 0)
                tx_hash = result.get('deposit_tx', 'unknown')
                
                old_pool_id = f"{asset}_{chain}_silo-v2_{from_market}"
                new_pool_id = f"{asset}_{chain}_silo-v2_{to_market}"
                
                success = update_pool_balance(
                    old_pool_id=old_pool_id,
                    new_pool_id=new_pool_id,
                    position_balance=amount,
                    tx_hash=tx_hash
                )
                
                if success:
                    logger.info(f"Pool balance updated after market transfer: {old_pool_id} -> {new_pool_id}")
                else:
                    logger.error(f"Failed to update pool balance after market transfer: {old_pool_id} -> {new_pool_id}")
            
            # For standard protocol transfers
            elif all(k in result for k in ['withdraw_tx', 'deposit_tx']):
                withdraw_tx = result.get('withdraw_tx')
                deposit_tx = result.get('deposit_tx')
                
                # Would need additional context to determine pool_ids
                logger.warning("Transaction successful but insufficient context to update pool balances")
                
        return result
    return wrapper 