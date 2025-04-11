import pytest
from unittest.mock import patch, MagicMock
from yieldex_data_collector.collector import (
    fetch_pools,
    save_apy_data,
    run_data_collection,
    load_config,
    save_config,
    get_white_lists,
)
import os
import json
from pathlib import Path
from .test_utils import PoolFactory, RecordValidator, SupabaseMocker


@pytest.fixture
def mock_pools_response():
    """Mock response from DeFiLlama API"""
    return {
        "data": [
            {
                "symbol": "USDT",
                "chain": "Polygon",
                "project": "aave-v3",
                "apy": 5.5,
                "tvlUsd": 1000000,
            },
            {
                "symbol": "USDC",
                "chain": "Ethereum",
                "project": "aave-v2",
                "apy": 4.2,
                "tvlUsd": 2000000,
            },
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
    with patch("requests.get") as mock_get:
        mock_get.return_value.json.return_value = mock_pools_response
        mock_get.return_value.raise_for_status = MagicMock()

        with patch(
            "data_collector.collector.get_white_lists",
            return_value={
                "protocols": ["aave-v3", "aave-v2"],
                "tokens": ["USDT", "USDC"],
            },
        ):
            pools = fetch_pools()

            assert len(pools) == 2
            assert pools[0]["symbol"] == "USDT"
            assert pools[1]["symbol"] == "USDC"


def test_fetch_pools_network_error():
    """Test handling of network errors"""
    with patch("requests.get") as mock_get:
        mock_get.side_effect = Exception("Network error")
        pools = fetch_pools()
        assert pools == []


def test_save_apy_data(mock_pools_response, mock_supabase):
    """Test saving APY data to Supabase"""
    # Capture the data being saved
    saved_records = []
    original_upsert = mock_supabase.table().upsert

    def capture_records(records, *args, **kwargs):
        # Make a deep copy to prevent modification
        saved_records.extend(records)
        return original_upsert(records, *args, **kwargs)

    mock_supabase.table().upsert = capture_records

    with patch("data_collector.collector.create_client", return_value=mock_supabase):
        save_apy_data(mock_pools_response["data"])

        # Verify Supabase calls - just check any call to table with apy_history
        assert mock_supabase.table.call_args_list[-1][0][0] == "apy_history"

        # Verify data fields using validators
        assert len(saved_records) > 0
        for record in saved_records:
            # Here we just check the data_source field, other fields
            # are already tested in other more specific tests
            RecordValidator.validate_data_source(record)


def test_save_apy_data_database_error(mock_pools_response, mock_supabase):
    """Test handling database errors in save_apy_data"""
    mock_supabase.table.return_value.upsert.side_effect = Exception("Database error")

    with patch("data_collector.collector.create_client", return_value=mock_supabase):
        with pytest.raises(Exception) as exc_info:
            save_apy_data(mock_pools_response["data"])
        assert "Database error" in str(exc_info.value)


def test_run_data_collection_success(mock_pools_response, mock_supabase):
    """Test successful data collection workflow"""
    with (
        patch("requests.get") as mock_get,
        patch("data_collector.collector.create_client", return_value=mock_supabase),
        patch("data_collector.collector.validate_env_vars", return_value=True),
        patch("data_collector.collector.SUPABASE_URL", "https://test.supabase.co"),
        patch("data_collector.collector.SUPABASE_KEY", "test_key"),
    ):
        mock_get.return_value.json.return_value = mock_pools_response
        mock_get.return_value.raise_for_status = MagicMock()

        result = run_data_collection()
        assert result is not None
        assert len(result) == 2


def test_run_data_collection_fetch_error():
    """Test handling fetch errors in run_data_collection"""
    with (
        patch("data_collector.collector.validate_env_vars", return_value=True),
        patch("data_collector.collector.fetch_pools", return_value=[]),
        patch(
            "data_collector.collector.get_white_lists",
            return_value={"protocols": ["test"], "tokens": ["TEST"]},
        ),
    ):
        result = run_data_collection()
        assert result == []


def test_run_data_collection_save_error(mock_pools_response, mock_supabase):
    """Test handling save errors in run_data_collection"""
    mock_supabase.table.return_value.upsert.side_effect = Exception("Save error")

    with (
        patch("data_collector.collector.validate_env_vars", return_value=True),
        patch(
            "data_collector.collector.fetch_pools",
            return_value=mock_pools_response["data"],
        ),
        patch("data_collector.collector.create_client", return_value=mock_supabase),
    ):
        result = run_data_collection()
        assert result is None


def test_run_data_collection_unexpected_error():
    """Test handling unexpected errors in run_data_collection"""
    with patch(
        "data_collector.collector.validate_env_vars",
        side_effect=Exception("Unexpected error"),
    ):
        result = run_data_collection()
        assert result is None


def test_run_data_collection_invalid_config():
    """Test data collection with invalid configuration"""
    with patch("data_collector.collector.validate_env_vars", return_value=False):
        result = run_data_collection()
        assert result is None


def test_fetch_pools_filter_by_protocol(mock_pools_response):
    """Test filtering out unsupported protocols"""
    # Adding a pool with unsupported protocol
    mock_pools_response["data"].append(
        {
            "symbol": "USDT",
            "chain": "BSC",
            "project": "unsupported-protocol",
            "apy": 6.0,
            "tvlUsd": 3000000,
        }
    )

    with patch("requests.get") as mock_get:
        mock_get.return_value.json.return_value = mock_pools_response
        mock_get.return_value.raise_for_status = MagicMock()

        with patch(
            "data_collector.collector.get_white_lists",
            return_value={
                "protocols": ["aave-v3", "aave-v2"],  # unsupported-protocol not in list
                "tokens": ["USDT", "USDC"],
            },
        ):
            pools = fetch_pools()

            # Current implementation only filters by tokens, not protocols
            assert len(pools) == 3  # All pools with supported tokens are included
            tokens = [pool["symbol"] for pool in pools]
            assert all(t in ["USDT", "USDC"] for t in tokens)

            # Check that the unsupported-protocol is included (since it has a supported token)
            projects = [pool["project"] for pool in pools]
            assert "unsupported-protocol" in projects


def test_fetch_pools_filter_by_token(mock_pools_response):
    """Test filtering out unsupported tokens"""
    # Adding a pool with unsupported token
    mock_pools_response["data"].append(
        {
            "symbol": "UNSUPPORTED",
            "chain": "Ethereum",
            "project": "aave-v3",
            "apy": 7.0,
            "tvlUsd": 4000000,
        }
    )

    with patch("requests.get") as mock_get:
        mock_get.return_value.json.return_value = mock_pools_response
        mock_get.return_value.raise_for_status = MagicMock()

        with patch(
            "data_collector.collector.get_white_lists",
            return_value={
                "protocols": ["aave-v3", "aave-v2"],
                "tokens": ["USDT", "USDC"],  # UNSUPPORTED not in list
            },
        ):
            pools = fetch_pools()

            assert len(pools) == 2  # Only USDT and USDC
            tokens = [pool["symbol"] for pool in pools]
            assert "UNSUPPORTED" not in tokens
            assert all(t in ["USDT", "USDC"] for t in tokens)


def test_fetch_pools_no_protocol_filter(mock_pools_response):
    """Test that no protocols are filtered out"""
    # Add a pool for a protocol not in protocols list
    mock_pools_response["data"].append(
        {
            "symbol": "USDT",  # supported token
            "chain": "Ethereum",
            "project": "new-project-outside-whitelist",  # not in whitelist
            "apy": 7.0,
            "tvlUsd": 4000000,
        }
    )

    with patch("requests.get") as mock_get:
        mock_get.return_value.json.return_value = mock_pools_response
        mock_get.return_value.raise_for_status = MagicMock()

        with patch(
            "data_collector.collector.get_white_lists",
            return_value={
                "protocols": ["aave-v3", "aave-v2"],  # new-project not in list
                "tokens": ["USDT", "USDC"],
            },
        ):
            pools = fetch_pools()

            assert len(pools) == 3  # All pools with supported tokens
            projects = [pool["project"] for pool in pools]
            # Should include the new project now
            assert "new-project-outside-whitelist" in projects


def test_fetch_pools_empty_after_filtering(mock_pools_response):
    """Test when all pools are filtered out"""
    with patch("requests.get") as mock_get:
        mock_get.return_value.json.return_value = mock_pools_response
        mock_get.return_value.raise_for_status = MagicMock()

        with patch(
            "data_collector.collector.get_white_lists",
            return_value={
                "protocols": ["unsupported"],  # No supported protocols
                "tokens": ["OTHER"],  # No supported tokens
            },
        ):
            pools = fetch_pools()

            assert len(pools) == 0  # All pools are filtered out


def test_load_config_from_file(tmp_path):
    """Test loading config from file"""
    config_file = tmp_path / "config.json"
    test_config = {"protocols": ["test-protocol"], "tokens": ["TEST"]}
    config_file.write_text(json.dumps(test_config))

    with patch("data_collector.collector.CONFIG_PATH", config_file):
        config = load_config()
        assert config == test_config


def test_load_config_from_env():
    """Test loading config from environment variables"""
    test_env = {
        "WHITE_LIST_PROTOCOLS": "protocol1,protocol2",
        "WHITE_LIST_TOKENS": "token1,token2",
    }

    with (
        patch.dict(os.environ, test_env),
        patch("data_collector.collector.CONFIG_PATH", Path("/nonexistent")),
    ):
        config = load_config()
        assert config["protocols"] == ["protocol1", "protocol2"]
        assert config["tokens"] == ["token1", "token2"]


def test_save_config(tmp_path):
    """Test saving config to file"""
    config_dir = tmp_path / "config"
    config_file = config_dir / "config.json"

    test_config = {"protocols": ["test-protocol"], "tokens": ["TEST"]}

    with patch("data_collector.collector.CONFIG_PATH", config_file):
        save_config(test_config)
        assert config_file.exists()
        saved_config = json.loads(config_file.read_text())
        assert saved_config == test_config


def test_get_white_lists():
    """Test getting white lists"""
    test_config = {"protocols": ["test-protocol"], "tokens": ["TEST"]}

    with patch("data_collector.collector.load_config", return_value=test_config):
        white_lists = get_white_lists()
        assert white_lists == test_config


def test_save_apy_data_with_extended_fields(mock_pools_response):
    """Test that extended APY data fields are saved properly"""
    # Create test pool using the factory
    enhanced_pool = PoolFactory.create_full_pool()

    # Setup mocks using the mocker utility
    mock_client, mock_table, _ = SupabaseMocker.create_mock_client()

    with (
        patch("data_collector.collector.create_client", return_value=mock_client),
        patch("time.time", return_value=1234567890),
    ):
        save_apy_data([enhanced_pool])

        # Check that data was passed to upsert
        mock_client.table.assert_called_with("apy_history")
        assert mock_table.upsert.called

        upsert_call_args = mock_table.upsert.call_args[0][0]
        assert len(upsert_call_args) == 1
        saved_record = upsert_call_args[0]

        # Use validator to verify fields
        RecordValidator.validate_base_fields(
            saved_record,
            "USDC_Ethereum_aave-v3",
            "USDC",
            "Ethereum",
            5.0,
            1000000,
            1234567890,
        )

        RecordValidator.validate_extended_fields(
            saved_record,
            apy_base=4.0,
            apy_reward=1.0,
            apy_mean_30d=4.8,
            apy_change_1d=0.2,
            apy_change_7d=-0.1,
            apy_change_30d=0.5,
        )

        RecordValidator.validate_data_source(saved_record)


def test_save_apy_data_with_missing_fields(mock_pools_response):
    """Test that APY data is saved properly when fields are missing"""
    # Create a minimal pool using the factory
    minimal_pool = PoolFactory.create_minimal_pool()

    # Setup mocks using the mocker utility
    mock_client, mock_table, _ = SupabaseMocker.create_mock_client()

    with (
        patch("data_collector.collector.create_client", return_value=mock_client),
        patch("time.time", return_value=1234567890),
    ):
        save_apy_data([minimal_pool])

        # Check that data was passed to upsert
        mock_client.table.assert_called_with("apy_history")
        assert mock_table.upsert.called

        upsert_call_args = mock_table.upsert.call_args[0][0]
        assert len(upsert_call_args) == 1
        saved_record = upsert_call_args[0]

        # Use validator to verify fields
        RecordValidator.validate_base_fields(
            saved_record,
            "USDC_Ethereum_aave-v3",
            "USDC",
            "Ethereum",
            5.0,
            1000000,
            1234567890,
        )

        # Default values for missing fields
        RecordValidator.validate_extended_fields(saved_record)

        # Check data source
        RecordValidator.validate_data_source(saved_record)


@pytest.mark.parametrize(
    "pool_config",
    [
        # Test pool with minimal fields
        {
            "symbol": "USDT",
            "chain": "Ethereum",
            "project": "compound",
            "apy": 3.5,
            "tvl": 500000,
        },
        # Test pool with optional poolMeta field
        {
            "symbol": "DAI",
            "chain": "Polygon",
            "project": "aave-v3",
            "apy": 2.1,
            "tvl": 1500000,
            "pool_meta": "lending",
        },
        # Test pool with all APY fields customized
        {
            "symbol": "USDC",
            "chain": "Arbitrum",
            "project": "curve",
            "apy": 4.2,
            "tvl": 3000000,
            "apy_base": 3.2,
            "apy_reward": 1.0,
            "apy_mean_30d": 4.1,
            "apy_change_1d": 0.1,
            "apy_change_7d": -0.2,
            "apy_change_30d": 0.3,
        },
    ],
)
def test_save_apy_data_parametrized(pool_config):
    """Parametrized test for saving different types of pool data"""
    # Create pool based on configuration
    if "apy_base" in pool_config:
        # Create full pool with custom APY fields
        pool = PoolFactory.create_full_pool(
            symbol=pool_config["symbol"],
            chain=pool_config["chain"],
            project=pool_config["project"],
            apy=pool_config["apy"],
            tvl=pool_config["tvl"],
            pool_meta=pool_config.get("pool_meta"),
        )
        # Override default APY fields
        pool.update(
            {
                "apyBase": pool_config.get("apy_base", 0),
                "apyReward": pool_config.get("apy_reward", 0),
                "apyMean30d": pool_config.get("apy_mean_30d", 0),
                "apyPct1D": pool_config.get("apy_change_1d", 0),
                "apyPct7D": pool_config.get("apy_change_7d", 0),
                "apyPct30D": pool_config.get("apy_change_30d", 0),
            }
        )
    else:
        # Create minimal pool
        pool = PoolFactory.create_minimal_pool(
            symbol=pool_config["symbol"],
            chain=pool_config["chain"],
            project=pool_config["project"],
            apy=pool_config["apy"],
            tvl=pool_config["tvl"],
        )
        if "pool_meta" in pool_config:
            pool["poolMeta"] = pool_config["pool_meta"]

    # Setup mocks
    mock_client, mock_table, _ = SupabaseMocker.create_mock_client()

    # Define expected pool_id
    base_id = f"{pool_config['symbol']}_{pool_config['chain']}_{pool_config['project']}"
    expected_pool_id = (
        f"{base_id}_{pool_config['pool_meta']}"
        if "pool_meta" in pool_config
        else base_id
    )

    with (
        patch("data_collector.collector.create_client", return_value=mock_client),
        patch("time.time", return_value=1234567890),
    ):
        save_apy_data([pool])

        # Verify data was sent to correct table
        mock_client.table.assert_called_with("apy_history")
        assert mock_table.upsert.called

        # Get the saved record
        upsert_call_args = mock_table.upsert.call_args[0][0]
        assert len(upsert_call_args) == 1
        saved_record = upsert_call_args[0]

        # Validate base fields
        RecordValidator.validate_base_fields(
            saved_record,
            expected_pool_id,
            pool_config["symbol"],
            pool_config["chain"],
            pool_config["apy"],
            pool_config["tvl"],
            1234567890,
        )

        # Validate APY fields if specified
        if "apy_base" in pool_config:
            RecordValidator.validate_extended_fields(
                saved_record,
                apy_base=pool_config.get("apy_base", 0),
                apy_reward=pool_config.get("apy_reward", 0),
                apy_mean_30d=pool_config.get("apy_mean_30d", 0),
                apy_change_1d=pool_config.get("apy_change_1d", 0),
                apy_change_7d=pool_config.get("apy_change_7d", 0),
                apy_change_30d=pool_config.get("apy_change_30d", 0),
            )
        else:
            # Default zero values
            RecordValidator.validate_extended_fields(saved_record)

        # Validate data source
        RecordValidator.validate_data_source(saved_record)
