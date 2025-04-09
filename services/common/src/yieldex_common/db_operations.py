import logging
from typing import Optional, Dict, Any
from supabase import create_client
from supabase.client import Client
from common.config import SUPABASE_URL, SUPABASE_KEY

logger = logging.getLogger(__name__)

def get_supabase_client() -> Client:
    """Get Supabase client with connection parameters"""
    return create_client(SUPABASE_URL, SUPABASE_KEY)

def get_pool_balance_by_pool_id(pool_id: str) -> Optional[Dict[str, Any]]:
    """
    Get pool balance entry by pool_id
    
    Args:
        pool_id: Pool identifier string
        
    Returns:
        Dictionary with pool balance data or None if not found
    """
    supabase = get_supabase_client()
    
    try:
        result = supabase.table('pool_balances') \
            .select('*') \
            .eq('pool_id', pool_id) \
            .order('timestamp', desc=True) \
            .limit(1) \
            .execute()
            
        if result.data and len(result.data) > 0:
            return result.data[0]
        return None
    except Exception as e:
        logger.error(f"Error fetching pool balance for {pool_id}: {str(e)}")
        return None

def update_pool_balance(old_pool_id: str, new_pool_id: str, 
                       position_balance: float, tx_hash: str) -> bool:
    """
    Update pool balance record after moving funds between protocols
    
    Args:
        old_pool_id: Original pool identifier
        new_pool_id: New pool identifier after transfer
        position_balance: Amount of funds moved
        tx_hash: Transaction hash for verification
        
    Returns:
        True if update was successful, False otherwise
    """
    supabase = get_supabase_client()
    
    try:
        # Get the existing record for the old pool
        old_record = get_pool_balance_by_pool_id(old_pool_id)
        
        if not old_record:
            logger.error(f"Cannot update pool balance: No record found for {old_pool_id}")
            return False
            
        record_id = old_record['id']
        
        
        # Update the record with new pool_id
        result = supabase.table('pool_balances') \
            .update({
                'pool_id': new_pool_id,
                'position_balance': position_balance,
            }) \
            .eq('id', record_id) \
            .execute()
            
        if not result.data:
            logger.error(f"Failed to update pool balance for {old_pool_id} -> {new_pool_id}")
            return False
            
        logger.info(f"Successfully updated pool balance: {old_pool_id} -> {new_pool_id} " 
                  f"(Amount: {position_balance}, TX: {tx_hash})")
        return True
    except Exception as e:
        logger.error(f"Error updating pool balance {old_pool_id} -> {new_pool_id}: {str(e)}")
        return False

def insert_pool_balance(pool_id: str, position_balance: float) -> Optional[Dict[str, Any]]:
    """
    Insert a new pool balance record
    
    Args:
        pool_id: Pool identifier string
        position_balance: Amount in USD
        
    Returns:
        Dictionary with created record data or None if failed
    """
    supabase = get_supabase_client()
    
    try:
        
        result = supabase.table('pool_balances') \
            .insert({
                'pool_id': pool_id,
                'position_balance': position_balance,
            }) \
            .execute()
            
        if result.data and len(result.data) > 0:
            logger.info(f"Successfully inserted pool balance for {pool_id} with {position_balance} USD")
            return result.data[0]
        return None
    except Exception as e:
        logger.error(f"Error inserting pool balance for {pool_id}: {str(e)}")
        return None 