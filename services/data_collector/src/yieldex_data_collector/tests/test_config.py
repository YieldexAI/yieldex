import os
import pytest
from unittest.mock import patch
from yieldex_data_collector.config import validate_env_vars


def test_validate_env_vars_with_missing_vars():
    """Test validation fails when required vars are missing"""
    with patch.dict(os.environ, {}, clear=True):
        assert not validate_env_vars()


def test_validate_env_vars_with_required_vars():
    """Test validation passes with all required vars"""
    mock_env = {
        "SUPABASE_URL": "http://test.com",
        "SUPABASE_KEY": "test-key",
        "POLYGON_RPC_URL": "http://polygon",
        "ETHEREUM_RPC_URL": "http://eth",
    }
    with patch.dict(os.environ, mock_env, clear=True):
        assert validate_env_vars()
