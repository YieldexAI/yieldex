import pytest
from unittest.mock import patch, MagicMock
from data_collector.collector import fetch_pools, save_apy_data, run_data_collection, load_config, save_config, get_white_lists
import os
import json
from pathlib import Path

@pytest.fixture
def mock_pools_response():
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
def mock_supabase():
    """Mock Supabase client"""
    mock = MagicMock()
    mock.table.return_value.upsert.return_value.execute.return_value = None
    return mock

def test_fetch_pools_success(mock_pools_response):
    """Test successful pool fetching"""
    with patch('requests.get') as mock_get:
        mock_get.return_value.json.return_value = mock_pools_response
        mock_get.return_value.raise_for_status = MagicMock()
        
        with patch('data_collector.collector.get_white_lists', return_value={
            'protocols': ['aave-v3', 'aave-v2'],
            'tokens': ['USDT', 'USDC']
        }):
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

def test_save_apy_data(mock_pools_response, mock_supabase):
    """Test saving APY data to Supabase"""
    with patch('data_collector.collector.create_client', return_value=mock_supabase):
        save_apy_data(mock_pools_response['data'])
        
        # Verify Supabase calls
        mock_supabase.table.assert_called_once_with('apy_history')
        mock_supabase.table().upsert.assert_called_once()

def test_save_apy_data_database_error(mock_pools_response, mock_supabase):
    """Test handling database errors in save_apy_data"""
    mock_supabase.table.return_value.upsert.side_effect = Exception("Database error")
    
    with patch('data_collector.collector.create_client', return_value=mock_supabase):
        with pytest.raises(Exception) as exc_info:
            save_apy_data(mock_pools_response['data'])
        assert "Database error" in str(exc_info.value)

def test_run_data_collection_success(mock_pools_response, mock_supabase):
    """Test successful data collection workflow"""
    with patch('requests.get') as mock_get, \
         patch('data_collector.collector.create_client', return_value=mock_supabase), \
         patch('data_collector.collector.validate_env_vars', return_value=True):
        
        mock_get.return_value.json.return_value = mock_pools_response
        mock_get.return_value.raise_for_status = MagicMock()
        
        result = run_data_collection()
        assert result is not None
        assert len(result) == 2

def test_run_data_collection_fetch_error():
    """Test handling fetch errors in run_data_collection"""
    with patch('data_collector.collector.validate_env_vars', return_value=True), \
         patch('data_collector.collector.fetch_pools', return_value=[]), \
         patch('data_collector.collector.get_white_lists', return_value={
             'protocols': ['test'],
             'tokens': ['TEST']
         }):
        result = run_data_collection()
        assert result == []

def test_run_data_collection_save_error(mock_pools_response, mock_supabase):
    """Test handling save errors in run_data_collection"""
    mock_supabase.table.return_value.upsert.side_effect = Exception("Save error")
    
    with patch('data_collector.collector.validate_env_vars', return_value=True), \
         patch('data_collector.collector.fetch_pools', return_value=mock_pools_response['data']), \
         patch('data_collector.collector.create_client', return_value=mock_supabase):
        result = run_data_collection()
        assert result is None

def test_run_data_collection_unexpected_error():
    """Test handling unexpected errors in run_data_collection"""
    with patch('data_collector.collector.validate_env_vars', side_effect=Exception("Unexpected error")):
        result = run_data_collection()
        assert result is None

def test_run_data_collection_invalid_config():
    """Test data collection with invalid configuration"""
    with patch('data_collector.collector.validate_env_vars', return_value=False):
        result = run_data_collection()
        assert result is None

def test_fetch_pools_filter_by_protocol(mock_pools_response):
    """Test filtering out unsupported protocols"""
    # Adding a pool with unsupported protocol
    mock_pools_response['data'].append({
        'symbol': 'USDT',
        'chain': 'BSC',
        'project': 'unsupported-protocol',
        'apy': 6.0,
        'tvlUsd': 3000000
    })
    
    with patch('requests.get') as mock_get:
        mock_get.return_value.json.return_value = mock_pools_response
        mock_get.return_value.raise_for_status = MagicMock()
        
        with patch('data_collector.collector.get_white_lists', return_value={
            'protocols': ['aave-v3', 'aave-v2'],  # unsupported-protocol not in list
            'tokens': ['USDT', 'USDC']
        }):
            pools = fetch_pools()
            
            assert len(pools) == 2  # Only aave pools
            projects = [pool['project'] for pool in pools]
            assert 'unsupported-protocol' not in projects
            assert all(p in ['aave-v3', 'aave-v2'] for p in projects)

def test_fetch_pools_filter_by_token(mock_pools_response):
    """Test filtering out unsupported tokens"""
    # Adding a pool with unsupported token
    mock_pools_response['data'].append({
        'symbol': 'UNSUPPORTED',
        'chain': 'Ethereum',
        'project': 'aave-v3',
        'apy': 7.0,
        'tvlUsd': 4000000
    })
    
    with patch('requests.get') as mock_get:
        mock_get.return_value.json.return_value = mock_pools_response
        mock_get.return_value.raise_for_status = MagicMock()
        
        with patch('data_collector.collector.get_white_lists', return_value={
            'protocols': ['aave-v3', 'aave-v2'],
            'tokens': ['USDT', 'USDC']  # UNSUPPORTED not in list
        }):
            pools = fetch_pools()
            
            assert len(pools) == 2  # Only USDT and USDC
            tokens = [pool['symbol'] for pool in pools]
            assert 'UNSUPPORTED' not in tokens
            assert all(t in ['USDT', 'USDC'] for t in tokens)

def test_fetch_pools_empty_after_filtering(mock_pools_response):
    """Test when all pools are filtered out"""
    with patch('requests.get') as mock_get:
        mock_get.return_value.json.return_value = mock_pools_response
        mock_get.return_value.raise_for_status = MagicMock()
        
        with patch('data_collector.collector.get_white_lists', return_value={
            'protocols': ['unsupported'],  # No supported protocols
            'tokens': ['OTHER']  # No supported tokens
        }):
            pools = fetch_pools()
            
            assert len(pools) == 0  # All pools are filtered out

def test_load_config_from_file(tmp_path):
    """Test loading config from file"""
    config_file = tmp_path / "config.json"
    test_config = {
        'protocols': ['test-protocol'],
        'tokens': ['TEST']
    }
    config_file.write_text(json.dumps(test_config))
    
    with patch('data_collector.collector.CONFIG_PATH', config_file):
        config = load_config()
        assert config == test_config

def test_load_config_from_env():
    """Test loading config from environment variables"""
    test_env = {
        'WHITE_LIST_PROTOCOLS': 'protocol1,protocol2',
        'WHITE_LIST_TOKENS': 'token1,token2'
    }
    
    with patch.dict(os.environ, test_env), \
         patch('data_collector.collector.CONFIG_PATH', Path('/nonexistent')):
        config = load_config()
        assert config['protocols'] == ['protocol1', 'protocol2']
        assert config['tokens'] == ['token1', 'token2']

def test_save_config(tmp_path):
    """Test saving config to file"""
    config_dir = tmp_path / "config"
    config_file = config_dir / "config.json"
    
    test_config = {
        'protocols': ['test-protocol'],
        'tokens': ['TEST']
    }
    
    with patch('data_collector.collector.CONFIG_PATH', config_file):
        save_config(test_config)
        assert config_file.exists()
        saved_config = json.loads(config_file.read_text())
        assert saved_config == test_config

def test_get_white_lists():
    """Test getting white lists"""
    test_config = {
        'protocols': ['test-protocol'],
        'tokens': ['TEST']
    }
    
    with patch('data_collector.collector.load_config', return_value=test_config):
        white_lists = get_white_lists()
        assert white_lists == test_config