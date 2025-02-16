import pytest
from unittest.mock import MagicMock

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
                'tvlUsd': 1000000,
                'poolMeta': None
            },
            {
                'symbol': 'USDC',
                'chain': 'Ethereum',
                'project': 'aave-v2',
                'apy': 4.2,
                'tvlUsd': 2000000,
                'poolMeta': 'v2'
            }
        ]
    }

@pytest.fixture
def mock_supabase():
    """Mock Supabase client"""
    mock = MagicMock()
    mock.table.return_value.upsert.return_value.execute.return_value = None
    return mock 