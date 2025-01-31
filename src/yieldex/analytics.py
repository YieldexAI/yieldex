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

def get_top_apy_pools(apy_data: List[Dict], limit: int = 3) -> List[Dict]:
    """Get top APY pools with TVL filtering"""
    filtered = [
        p for p in apy_data 
        if p['tvl'] > 1_000_000 and p['apy'] > 0
    ]
    sorted_pools = sorted(
        filtered,
        key=lambda x: x['apy'],
        reverse=True
    )
    return sorted_pools[:limit] 

def get_top_asset_overall(latest_apy: List[Dict]) -> Dict:
    """Find top asset by total+base APY with TVL >1M (all chains)"""
    filtered = [p for p in latest_apy if p['tvl'] > 1_000_000]
    if not filtered:
        return None
    
    sorted_pools = sorted(
        filtered,
        key=lambda x: (x['apy'], x.get('apyBase', 0)), 
        reverse=True
    )
    return sorted_pools[0] if sorted_pools else None

def get_top_asset_by_chain(latest_apy: List[Dict], chain: str) -> Dict:
    """Find top asset in specific chain with TVL >1M"""
    filtered = [p for p in latest_apy if p['chain'] == chain and p['tvl'] > 1_000_000]
    if not filtered:
        return None
    
    sorted_pools = sorted(
        filtered,
        key=lambda x: (x.get('apyBase', 0), x['apy']), 
        reverse=True
    )
    return sorted_pools[0] if sorted_pools else None

def get_top3_base_apy(latest_apy: List[Dict]) -> List[Dict]:
    """Top 3 assets by base APY with TVL >1M"""
    filtered = [p for p in latest_apy if p['tvl'] > 1_000_000 and 'apyBase' in p]
    sorted_pools = sorted(
        filtered,
        key=lambda x: x['apyBase'],
        reverse=True
    )
    return sorted_pools[:3]

def get_top_growing_asset(hours: int = 24) -> Dict:
    """Find asset with largest base APY growth (>1M TVL)"""
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    
    # Get last 2 records for each pool
    response = supabase.rpc('get_apy_history_window', {'hours': hours}).execute()
    
    growth_map = {}
    for pool in response.data:
        key = pool['pool_id']
        if key not in growth_map:
            growth_map[key] = {'current': pool['apy'], 'previous': pool['apy']}
        else:
            growth_map[key]['previous'] = pool['apy']
    
    # Calculate growth
    results = []
    for pool_id, apys in growth_map.items():
        growth = apys['current'] - apys['previous']
        if growth > 0:
            pool_data = next(p for p in response.data if p['pool_id'] == pool_id)
            if pool_data['tvl'] > 1_000_000:
                results.append({
                    **pool_data,
                    'growth': growth
                })
    
    return sorted(results, key=lambda x: x['growth'], reverse=True)[0] if results else None

def get_top_growing_asset(hours: int = 24) -> Dict:
    """Find asset with largest base APY growth (>1M TVL)"""
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    
    # Get last 2 records for each pool
    response = supabase.rpc('get_apy_history_window', {'hours': hours}).execute()
    
    growth_map = {}
    for pool in response.data:
        key = pool['pool_id']
        if key not in growth_map:
            growth_map[key] = {'current': pool['apy'], 'previous': pool['apy']}
        else:
            growth_map[key]['previous'] = pool['apy']
    
    # Calculate growth
    results = []
    for pool_id, apys in growth_map.items():
        growth = apys['current'] - apys['previous']
        if growth > 0:
            pool_data = next(p for p in response.data if p['pool_id'] == pool_id)
            if pool_data['tvl'] > 1_000_000:
                results.append({
                    **pool_data,
                    'growth': growth
                })
    
    return sorted(results, key=lambda x: x['growth'], reverse=True)[0] if results else None 