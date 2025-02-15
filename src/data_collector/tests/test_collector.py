import pytest
from unittest.mock import patch, MagicMock
from data_collector.collector import fetch_pools, save_apy_data

@pytest.fixture
def mock_response():
    """Mock response from DeFiLlama API"""
    return {
        'data': [
            {
                'symbol': 'USDT',
                'chain': 'Polygon',
                'project': 'aave-v3',
                'apy': 5.5,
                'tvlUsd': 1000000
            },
            {
                'symbol': 'USDC',
                'chain': 'Ethereum',
                'project': 'aave-v2',
                'apy': 4.2,
                'tvlUsd': 2000000
            }
        ]
    }

@pytest.fixture
def mock_white_lists():
    """Mock whitelist configuration"""
    return {
        'protocols': ['aave-v3', 'aave-v2'],
        'tokens': ['USDT', 'USDC']
    }

def test_fetch_pools_success(mock_response, mock_white_lists):
    """Test successful pool fetching"""
    with patch('requests.get') as mock_get:
        mock_get.return_value.json.return_value = mock_response
        mock_get.return_value.raise_for_status = MagicMock()
        
        with patch('data_collector.collector.get_white_lists', return_value=mock_white_lists):
            pools = fetch_pools()
            
            assert len(pools) == 2
            assert pools[0]['symbol'] == 'USDT'
            assert pools[1]['symbol'] == 'USDC'

def test_fetch_pools_network_error():
    """Test handling of network errors"""
    with patch('requests.get') as mock_get:
        mock_get.side_effect = Exception("Network error")
        pools = fetch_pools()
        assert pools == []

def test_save_apy_data(mock_response):
    """Test saving APY data to Supabase"""
    pools = mock_response['data']
    
    with patch('data_collector.collector.create_client') as mock_client:
        mock_supabase = MagicMock()
        mock_client.return_value = mock_supabase
        
        save_apy_data(pools)
        
        # Verify Supabase calls
        mock_supabase.table.assert_called_once_with('apy_history')
        mock_supabase.table().upsert.assert_called_once() 