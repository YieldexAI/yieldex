from unittest.mock import MagicMock


class PoolFactory:
    """Factory class for creating test pool data"""

    @staticmethod
    def create_minimal_pool(
        symbol="USDC", chain="Ethereum", project="aave-v3", apy=5.0, tvl=1000000
    ):
        """Create a minimal pool with only required fields"""
        return {
            "symbol": symbol,
            "chain": chain,
            "project": project,
            "apy": apy,
            "tvlUsd": tvl,
        }

    @staticmethod
    def create_full_pool(
        symbol="USDC",
        chain="Ethereum",
        project="aave-v3",
        apy=5.0,
        tvl=1000000,
        pool_meta=None,
    ):
        """Create a pool with all fields"""
        pool = PoolFactory.create_minimal_pool(symbol, chain, project, apy, tvl)
        pool.update(
            {
                "apyBase": 4.0,
                "apyReward": 1.0,
                "apyMean30d": 4.8,
                "apyPct1D": 0.2,
                "apyPct7D": -0.1,
                "apyPct30D": 0.5,
                "poolMeta": pool_meta,
            }
        )
        return pool


class RecordValidator:
    """Validator for checking record fields"""

    @staticmethod
    def validate_base_fields(record, pool_id, asset, chain, apy, tvl, timestamp):
        """Validate the base required fields of a record"""
        assert record["pool_id"] == pool_id
        assert record["asset"] == asset
        assert record["chain"] == chain
        assert record["apy"] == apy
        assert record["tvl"] == tvl
        assert record["timestamp"] == timestamp

    @staticmethod
    def validate_extended_fields(
        record,
        apy_base=0,
        apy_reward=0,
        apy_mean_30d=0,
        apy_change_1d=0,
        apy_change_7d=0,
        apy_change_30d=0,
    ):
        """Validate the extended APY fields of a record"""
        assert record["apy_base"] == apy_base
        assert record["apy_reward"] == apy_reward
        assert record["apy_mean_30d"] == apy_mean_30d
        assert record["apy_change_1d"] == apy_change_1d
        assert record["apy_change_7d"] == apy_change_7d
        assert record["apy_change_30d"] == apy_change_30d

    @staticmethod
    def validate_data_source(record, source="Defillama"):
        """Validate the data_source field of a record"""
        assert "data_source" in record
        assert record["data_source"] == source


class SupabaseMocker:
    """Helper for creating Supabase mocks"""

    @staticmethod
    def create_mock_client():
        """Create a mock Supabase client with table, upsert and execute methods"""
        mock_client = MagicMock()
        mock_table = MagicMock()
        mock_upsert = MagicMock()
        mock_execute = MagicMock()

        mock_client.table.return_value = mock_table
        mock_table.upsert.return_value = mock_execute

        return mock_client, mock_table, mock_upsert
