import logging
from typing import Optional, Dict, List
from common.config import SUPABASE_URL, SUPABASE_KEY
from supabase import create_client
import re

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

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

def get_current_positions(chain=None):
    """
    Get current positions from pool_balances
    
    Args:
        chain: Optional filter for specific blockchain network
        
    Returns:
        List of dictionaries with pool_id and position_balance
    """
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    
    # We only need pool_id and position_balance
    query = supabase.table('pool_balances')\
        .select('pool_id, position_balance')\
        .order('timestamp', desc=True)
    
    # Apply chain filter if specified
    if chain:
        # Sonic format is special, may have different structures
        if chain.lower() == 'sonic':
            query = query.or_(f'pool_id.ilike.%_Sonic_%,pool_id.ilike.%_SONIC_%')
        else:
            # More standard format
            query = query.or_(f'pool_id.ilike.%_{chain}_%,pool_id.ilike.%_{chain.upper()}_%')
    
    return query.execute().data

def extract_chain_from_pool_id(pool_id):
    """
    Safely extract chain information from pool_id with different formats
    
    Args:
        pool_id: The pool identifier string
        
    Returns:
        Chain name or None if can't be determined
    """
    # Special case for Sonic IDs which may have numeric postfixes
    if '_sonic_' in pool_id.lower() or '_sonic' in pool_id.lower():
        return 'Sonic'
    
    # Standard format attempts
    parts = pool_id.split('_')
    
    # Try to identify chain in a flexible way
    if len(parts) >= 2:
        # Common format: asset_chain_protocol_id
        chain_candidates = [parts[1]]
        
        # Also check if chain might be in another position
        if len(parts) >= 3:
            chain_candidates.append(parts[2])
        
        # Check against known chains
        known_chains = ['Ethereum', 'Polygon', 'Arbitrum', 'Optimism', 'Avalanche', 'Base', 'Sonic', 'Scroll']
        for candidate in chain_candidates:
            for chain in known_chains:
                if candidate.lower() == chain.lower():
                    return chain
    
    # If all else fails, try to extract from the full string
    for chain in ['Ethereum', 'Polygon', 'Arbitrum', 'Optimism', 'Avalanche', 'Base', 'Sonic', 'Scroll']:
        if chain.lower() in pool_id.lower():
            return chain
    
    return None

def extract_protocol_from_pool_id(pool_id):
    """
    Extract protocol information from pool_id
    
    Args:
        pool_id: The pool identifier string (e.g., 'USDC_Scroll_aave-v3')
        
    Returns:
        Protocol name or None if can't be determined
    """
    parts = pool_id.split('_')
    
    # Typical format: asset_chain_protocol_extra
    if len(parts) >= 3:
        protocol = parts[2]
        # Clean up any extra parts if needed
        protocol = protocol.split('-')[0] if '-' in protocol else protocol
        return protocol
    
    # Try to identify known protocols in the string
    known_protocols = ['aave', 'compound', 'curve', 'uniswap', 'sushiswap', 'balancer', 'yearn', 'silo']
    for protocol in known_protocols:
        if protocol in pool_id.lower():
            return protocol
    
    return None

def get_latest_apy_data(chain=None):
    """
    Get latest APY data from Supabase with proper handling of Silo markets
    
    Args:
        chain: Optional filter for specific blockchain network
        
    Returns:
        Dictionary mapping asset_chain keys to APY data with special handling for Silo markets
    """
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    
    # Direct query to apy_history table instead of RPC function
    query = supabase.table('apy_history')\
        .select('*')\
        .order('timestamp', desc=True)
    
    if chain:
        query = query.eq('chain', chain)
    
    result = query.execute().data
    logger.info(f"Fetched {len(result)} APY data entries from Supabase")
    
    # Process results to handle Silo markets properly
    apy_map = {}
    unique_pools = set()  # To track unique pool IDs
    
    for entry in result:
        pool_id = entry.get('pool_id', '')
        
        # Skip if we already processed this pool ID (taking only the latest)
        if pool_id in unique_pools:
            continue
        
        unique_pools.add(pool_id)
        
        # Special handling for Silo markets
        if 'silo-v2' in pool_id.lower():
            market_id = extract_market_id_from_pool_id(pool_id)
            if market_id:
                # Create market-specific key for Silo
                key = f"{entry['asset']}_{entry['chain']}_market_{market_id}"
                entry['market_id'] = market_id
                apy_map[key] = entry
                logger.info(f"Processed Silo market {market_id} for {entry['asset']} with APY: {entry['apy']}%")
        
        # Standard handling for other protocols
        standard_key = f"{entry['asset']}_{entry['chain']}"
        if standard_key not in apy_map:
            apy_map[standard_key] = entry
        
        # Also add lowercase version for easier matching
        apy_map[standard_key.lower()] = entry
    
    logger.info(f"Created APY map with {len(apy_map)} entries (including Silo markets)")
    return apy_map

def extract_market_id_from_pool_id(pool_id):
    """
    Extract market ID from pool_id with comprehensive pattern matching
    
    Format examples:
    - USDC.E_Sonic_silo-v2_8
    - USDC.E_sonic_silo_8
    - USDC_sonic_silov2_20
    - USDC.E_Sonic_silo-v2_34
    
    Returns:
        Market ID or None if not found
    """
    # Handle common format patterns
    silo_market_pattern = re.compile(r'.*?_(?:sonic|Sonic)_(?:silo|silo-v2|silov2)_?(\d+)', re.IGNORECASE)
    match = silo_market_pattern.match(pool_id)
    if match:
        return match.group(1)
    
    # Fallback approaches if regex didn't match
    parts = pool_id.split('_')
    
    # Last part might be the market ID if numeric
    if parts and parts[-1].isdigit():
        return parts[-1]
    
    # Look for a numeric part after silo/silo-v2
    for i, part in enumerate(parts):
        if part.lower() in ['silo', 'silo-v2', 'silov2'] and i+1 < len(parts) and parts[i+1].isdigit():
            return parts[i+1]
    
    # Try to find any numeric part
    for part in parts:
        if part.isdigit():
            return part
    
    return None

def get_recommendations(min_profit: float = 0.3, chain=None, show_all_comparisons: bool = False) -> List[Dict]:
    """
    Analyze APY differences between different assets/chains/markets and generate recommendations
    
    Args:
        min_profit: Minimum profit percentage to consider for a recommendation
        chain: Optional filter to only include positions from a specific chain
        show_all_comparisons: Show all comparisons, even unprofitable ones
        
    Returns:
        List of recommendation dictionaries
    """
    logger.info("Starting get_recommendations")
    
    # Get current positions
    current_positions = get_current_positions(chain)
    logger.info(f"Got {len(current_positions)} current positions: {current_positions}")
    
    # Get latest APY data with enhanced Silo market handling
    apy_map = get_latest_apy_data(chain)
    
    if not current_positions:
        logger.warning("No current positions found")
        return []
    
    recommendations = []
    all_comparisons = []  # Store all comparisons for debugging
    
    # Special handling for Sonic
    is_sonic = chain and chain.lower() == 'sonic'
    
    # For each position, find the best swap target
    for position in current_positions:
        pool_id = position['pool_id']
        position_balance = position['position_balance']
        
        logger.info(f"Processing position with pool_id: {pool_id}")
        
        try:
            # Extract basic information from pool_id
            position_chain = extract_chain_from_pool_id(pool_id)
            parts = pool_id.split('_')
            asset = parts[0] if parts else None
            
            # Get protocol information
            from_protocol = extract_protocol_from_pool_id(pool_id)
            
            # Special handling for Silo markets
            is_silo = 'silo' in pool_id.lower()
            market_id = None
            
            if is_silo:
                market_id = extract_market_id_from_pool_id(pool_id)
                logger.info(f"Detected Silo market: {market_id} for {asset} on {position_chain}")
            
            # Skip if chain filter is specified and doesn't match
            if chain and position_chain.lower() != chain.lower():
                logger.info(f"Skipping position with chain {position_chain} because filter is for {chain}")
                continue
            
            # Find current APY
            current_apy = None
            matched_key = None
            
            # For Silo markets, try market-specific key first
            if is_silo and market_id:
                silo_key = f"{asset}_{position_chain}_market_{market_id}"
                if silo_key in apy_map:
                    current_apy = apy_map[silo_key]['apy']
                    matched_key = silo_key
                    logger.info(f"Found current APY for Silo market {market_id}: {current_apy}%")
            
            # If not found, try standard keys
            if current_apy is None:
                apy_keys_to_try = [
                    f"{asset}_{position_chain}",
                    f"{asset}_{position_chain}".lower(),
                    f"{asset.lower()}_{position_chain.lower()}" if asset else None
                ]
                
                for key in [k for k in apy_keys_to_try if k]:
                    if key in apy_map:
                        current_apy = apy_map[key]['apy']
                        matched_key = key
                        logger.info(f"Found current APY with standard key: {current_apy}%")
                        break
            
            # If still not found, skip this position
            if current_apy is None:
                logger.warning(f"No APY data found for position with pool_id: {pool_id}")
                continue
            
            # Find better opportunities
            comparisons = []
            best_option = None
            best_profit = 0
            
            # For Silo markets, prioritize comparison with other markets of same asset
            if is_silo and is_sonic and market_id:
                # Find other Silo markets for same asset
                for key, data in apy_map.items():
                    if f"{asset}_{position_chain}_market_" in key and key != matched_key:
                        target_market_id = data.get('market_id')
                        if not target_market_id:
                            continue
                        
                        target_apy = data['apy']
                        
                        # Minimal gas cost for same-chain, same-asset transfer
                        gas_cost = 0.05
                        
                        # Calculate profit
                        profit = target_apy - current_apy - gas_cost
                        
                        comparison = {
                            'from_asset': asset,
                            'from_chain': position_chain,
                            'from_market': market_id,
                            'to_asset': asset,
                            'to_chain': position_chain,
                            'to_market': target_market_id,
                            'from_apy': current_apy,
                            'to_apy': target_apy,
                            'gas_cost': gas_cost,
                            'profit': profit,
                            'min_profit_required': min_profit
                        }
                        comparisons.append(comparison)
                        
                        logger.info(f"Comparing Silo markets: {market_id} ({current_apy}%) → "
                                   f"{target_market_id} ({target_apy}%): Profit = {profit}%")
                        
                        if profit > min_profit and profit > best_profit:
                            best_profit = profit
                            best_option = {
                                'type': 'silo_market_transfer',
                                'asset': asset,
                                'from_market_id': market_id,
                                'to_market_id': target_market_id,
                                'chain': position_chain,
                                'current_apy': current_apy,
                                'target_apy': target_apy,
                                'profit': profit,
                                'pool_id': pool_id,
                                'data': data
                            }
            
            # Standard comparison with other assets/chains
            if best_profit < min_profit:  # Only if we haven't found good Silo market transfer
                for key, data in apy_map.items():
                    # Skip Silo market-specific entries for standard comparison
                    if 'market_' in key:
                        continue
                        
                    target_asset = data.get('asset')
                    target_chain = data.get('chain')
                    
                    # Skip if missing data
                    if not target_asset or not target_chain:
                        continue
                    
                    # Skip if same asset and chain
                    if target_asset == asset and target_chain == position_chain:
                        continue
                    
                    # Skip if chain filter applied and doesn't match
                    if chain and target_chain.lower() != chain.lower():
                        continue
                    
                    target_apy = data['apy']
                    
                    # Gas cost depends on whether cross-chain
                    gas_cost = 0.15 if target_chain != position_chain else 0.05
                    
                    # Calculate profit
                    profit = target_apy - current_apy - gas_cost
                    
                    comparison = {
                        'from_asset': asset,
                        'from_chain': position_chain,
                        'to_asset': target_asset,
                        'to_chain': target_chain,
                        'from_apy': current_apy,
                        'to_apy': target_apy,
                        'gas_cost': gas_cost,
                        'profit': profit,
                        'min_profit_required': min_profit
                    }
                    comparisons.append(comparison)
                    
                    logger.info(f"Comparing {asset} on {position_chain} ({current_apy}%) → "
                               f"{target_asset} on {target_chain} ({target_apy}%): Profit = {profit}%")
                    
                    if profit > min_profit and profit > best_profit:
                        best_profit = profit
                        best_option = {
                            'type': 'standard_transfer',
                            'asset': asset,
                            'to_asset': target_asset,
                            'from_chain': position_chain,
                            'to_chain': target_chain,
                            'current_apy': current_apy,
                            'target_apy': target_apy,
                            'profit': profit,
                            'pool_id': pool_id,
                            'data': data
                        }
            
            # Create final recommendation based on best option
            if best_option:
                if best_option['type'] == 'silo_market_transfer':
                    recommendation = {
                        'asset': asset,
                        'to_asset': asset,  # Same asset for Silo market transfers
                        'from_chain': position_chain,
                        'to_chain': position_chain,
                        'from_protocol': from_protocol,
                        'to_protocol': 'silo',  # Silo market transfers are always within Silo protocol
                        'from_market_id': best_option['from_market_id'],
                        'to_market_id': best_option['to_market_id'],
                        'current_apy': round(current_apy, 2),
                        'target_apy': round(best_option['target_apy'], 2),
                        'gas_cost': 0.05,  # Fixed for same-chain transfers
                        'estimated_profit': round(best_option['profit'], 2),
                        'position_size': position_balance,
                        'pool_id': pool_id,
                        'recommendation_type': 'silo_market_transfer',
                        'swap_details': {
                            'from_token': asset,
                            'to_token': asset,
                            'from_market': best_option['from_market_id'],
                            'to_market': best_option['to_market_id'],
                            'swap_protocol': 'silo-v2'
                        }
                    }
                else:
                    # Extract protocol from target pool if available
                    to_protocol = None
                    if 'pool_id' in best_option['data']:
                        to_protocol = extract_protocol_from_pool_id(best_option['data']['pool_id'])
                    
                    # Standard asset/chain transfer
                    recommendation = {
                        'asset': asset,
                        'to_asset': best_option['to_asset'],
                        'from_chain': position_chain,
                        'to_chain': best_option['to_chain'],
                        'from_protocol': from_protocol,
                        'to_protocol': to_protocol,
                        'current_apy': round(current_apy, 2),
                        'target_apy': round(best_option['target_apy'], 2),
                        'gas_cost': 0.15 if best_option['to_chain'] != position_chain else 0.05,
                        'estimated_profit': round(best_option['profit'], 2),
                        'position_size': position_balance,
                        'pool_id': pool_id,
                        'recommendation_type': 'standard_transfer',
                        'swap_details': {
                            'from_token': asset,
                            'to_token': best_option['to_asset'],
                            'swap_protocol': 'uniswap-v3' if best_option['to_chain'] != position_chain else 'curve'
                        }
                    }
                
                logger.info(f"Adding recommendation: {recommendation}")
                recommendations.append(recommendation)
            else:
                logger.info(f"No profitable recommendations found for {asset} on {position_chain}")
            
            # Store comparison data for debugging
            all_comparisons.append({
                'pool_id': pool_id,
                'asset': asset,
                'chain': position_chain,
                'market_id': market_id if is_silo else None,
                'current_apy': current_apy,
                'comparisons': comparisons
            })
            
        except Exception as e:
            logger.error(f"Error analyzing position {pool_id}: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            continue
    
    logger.info(f"Generated {len(recommendations)} recommendations")
    
    # Return all comparisons if requested
    if show_all_comparisons:
        return recommendations, all_comparisons
    
    return recommendations

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

def get_chain_data(chain_name: str, limit: int = 100):
    """Get data for specific chain"""
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    
    return supabase.table('apy_history') \
        .select('asset, chain, apy, tvl, timestamp') \
        .eq('chain', chain_name) \
        .order('timestamp', desc=True) \
        .order('apy', desc=True) \
        .limit(limit) \
        .execute().data


if __name__ == "__main__":
    # Parse command line arguments
    import argparse
    parser = argparse.ArgumentParser(description='Generate yield optimization recommendations')
    parser.add_argument('--chain', type=str, help='Filter recommendations to specific chain')
    parser.add_argument('--min-profit', type=float, default=0.3, help='Minimum profit percentage threshold')
    parser.add_argument('--debug', action='store_true', help='Enable debug output')
    parser.add_argument('--show-all-comparisons', action='store_true', help='Show all comparisons including unprofitable ones')
    parser.add_argument('--zero-threshold', action='store_true', help='Set profit threshold to 0 to see all potential swaps')
    
    args = parser.parse_args()
    
    # Set debug logging if requested
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
        logging.getLogger('httpx').setLevel(logging.INFO)
    
    # Apply zero threshold if requested
    if args.zero_threshold:
        args.min_profit = 0
    
    # Get recommendations
    if args.show_all_comparisons:
        recommendations, all_comparisons = get_recommendations(
            min_profit=args.min_profit, 
            chain=args.chain,
            show_all_comparisons=True
        )
    else:
        recommendations = get_recommendations(
            min_profit=args.min_profit, 
            chain=args.chain
        )
    
    print(f"\nFound {len(recommendations)} recommendations:")
    for i, rec in enumerate(recommendations, 1):
        if rec.get('recommendation_type') == 'silo_market_transfer':
            print(f"\n{i}. Move {rec['asset']} from Market {rec['from_market_id']} to Market {rec['to_market_id']} on {rec['to_chain']}")
            print(f"   Recommendation Type: Silo Market Transfer")
            print(f"   Protocol: {rec['from_protocol'].capitalize() if rec['from_protocol'] else 'Unknown'}")
        else:
            from_protocol = rec['from_protocol'].capitalize() if rec['from_protocol'] else 'Unknown'
            to_protocol = rec['to_protocol'].capitalize() if rec['to_protocol'] else 'Unknown'
            print(f"\n{i}. Move {rec['asset']} from {rec['from_chain']} to {rec['to_asset']} on {rec['to_chain']}")
            print(f"   Recommendation Type: Cross-Asset/Chain Transfer")
            print(f"   From Protocol: {from_protocol} → To Protocol: {to_protocol}")
            
        print(f"   Current APY: {rec['current_apy']}% → Target APY: {rec['target_apy']}%")
        print(f"   Estimated profit: {rec['estimated_profit']}% (after gas costs of {rec['gas_cost']}%)")
        print(f"   Position size: ${rec['position_size']}")
        print(f"   Original pool ID: {rec['pool_id']}")
        
        # Display target pool ID if available
        if rec.get('recommendation_type') == 'standard_transfer' and 'data' in rec and 'pool_id' in rec['data']:
            print(f"   Target pool ID: {rec['data']['pool_id']}")
    
    if args.show_all_comparisons:
        print("\n\n======= ALL COMPARISONS (FOR DEBUGGING) =======")
        for position in all_comparisons:
            if position.get('market_id'):
                print(f"\nPosition: {position['asset']} on {position['chain']} in Market {position['market_id']} (Current APY: {position['current_apy']}%)")
            else:
                print(f"\nPosition: {position['asset']} on {position['chain']} (Current APY: {position['current_apy']}%)")
                
            print(f"Pool ID: {position['pool_id']}")
            
            if not position['comparisons']:
                print("  No comparisons made")
                continue
                
            print("  Comparisons:")
            for i, comp in enumerate(sorted(position['comparisons'], key=lambda x: x['profit'], reverse=True), 1):
                profit_status = "PROFITABLE" if comp['profit'] > comp['min_profit_required'] else "not profitable"
                
                # Handle different comparison types
                if 'from_market' in comp and 'to_market' in comp:
                    print(f"  {i}. Market {comp['from_market']} → Market {comp['to_market']} (same asset: {comp['from_asset']})")
                else:
                    print(f"  {i}. {comp['from_asset']} ({comp['from_chain']}) → {comp['to_asset']} ({comp['to_chain']})")
                
                print(f"     From APY: {comp['from_apy']}% → To APY: {comp['to_apy']}%")
                print(f"     Gas cost: {comp['gas_cost']}%")
                print(f"     Profit: {comp['profit']:.2f}%")
                print(f"     Status: {profit_status} (min required: {comp['min_profit_required']}%)")
                print()
