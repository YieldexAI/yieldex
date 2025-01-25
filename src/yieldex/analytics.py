from typing import Optional, Dict, List
from .config import SUPABASE_URL, SUPABASE_KEY
from supabase import create_client

GAS_COSTS = {
    'Polygon': 0.05,
    'Arbitrum': 0.15,
    'Optimism': 0.10,
    'Base': 0.08,
    'Avalanche': 0.07,
    'Ethereum': 0.20
}

def analyze_apy_differences() -> Optional[Dict]:
    """Analyze APY differences between chains"""
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    
    try:
        response = supabase.table('apy_history') \
            .select('asset, chain, apy') \
            .order('timestamp', desc=True) \
            .limit(100) \
            .execute()
    except Exception as e:
        print(f"Database error: {e}")
        return None

    current_rates = {}
    for item in response.data:
        key = (item['asset'], item['chain'])
        if key not in current_rates:
            current_rates[key] = item['apy']

    recommendations = []
    for (asset, chain), apy in current_rates.items():
        for (comp_asset, comp_chain), comp_apy in current_rates.items():
            if asset == comp_asset and chain != comp_chain:
                gas_cost = GAS_COSTS.get(chain, 0) + GAS_COSTS.get(comp_chain, 0)
                profit = (comp_apy - apy) - gas_cost
                
                if profit > 0.5:  # Minimum profit filter
                    recommendations.append({
                        'asset': asset,
                        'from_chain': chain,
                        'to_chain': comp_chain,
                        'estimated_profit': round(profit, 2)
                    })

    return sorted(recommendations, key=lambda x: x['estimated_profit'], reverse=True)[:3] if recommendations else None 

def get_current_positions():
    """Get current positions from pool_balances"""
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    return supabase.table('pool_balances')\
        .select('pool_id, position_balance')\
        .order('timestamp', desc=True)\
        .execute().data

def get_latest_apy_data():
    """Get latest APY for all pools"""
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    return supabase.rpc('get_latest_apy').execute().data

def get_recommendations(min_profit: float = 0.5) -> List[Dict]:
    """Generate recommendations for moving funds considering gas costs"""
    current_positions = get_current_positions()
    latest_apy = get_latest_apy_data()
    
    # Collect latest APY for each pool
    apy_map = {p['pool_id']: p for p in latest_apy}
    
    recommendations = []
    
    for position in current_positions:
        current_pool = apy_map.get(position['pool_id'])
        if not current_pool:
            logger.warning(f"No APY data for position {position['pool_id']}")
            continue
            
        # Find best option for this asset considering gas
        best_option = None
        max_profit = 0
        
        for pool in latest_apy:
            if pool['asset'] == current_pool['asset'] and pool['pool_id'] != position['pool_id']:
                # Use static gas values from config
                gas_cost = GAS_COSTS.get(current_pool['chain'], 0) + GAS_COSTS.get(pool['chain'], 0)
                
                profit = (pool['apy'] - current_pool['apy']) - gas_cost
                
                if profit > max_profit and profit > min_profit:
                    max_profit = profit
                    best_option = pool
        
        if best_option:
            recommendations.append({
                'asset': current_pool['asset'],
                'from_chain': current_pool['chain'],
                'to_chain': best_option['chain'],
                'current_apy': round(current_pool['apy'], 2),
                'target_apy': round(best_option['apy'], 2),
                'gas_cost': round(gas_cost, 2),
                'estimated_profit': round(max_profit, 2),
                'position_size': position['position_balance']
            })
    
    # Sort by potential profit
    return sorted(recommendations, key=lambda x: x['estimated_profit'] * x['position_size'], reverse=True)

def analyze_opportunities():
    # Get current positions
    current_positions = get_current_positions() 
    
    # Get latest APY for all pools
    latest_apy = get_latest_apy_data()
    
    recommendations = []
    for position in current_positions:
        current_apy = next(
            (p['apy'] for p in latest_apy 
             if p['pool_id'] == position['pool_id']), 0
        )
        
        # Find best option for this asset
        best_option = max(
            [p for p in latest_apy if p['asset'] == position['asset']],
            key=lambda x: x['apy']
        )
        
        if best_option['apy'] - current_apy > MIN_PROFIT_THRESHOLD:
            recommendations.append({
                'move_from': position['pool_id'],
                'move_to': best_option['pool_id'],
                'estimated_profit': best_option['apy'] - current_apy
            })
    
    return recommendations 