from .data_collector import fetch_pools, save_apy_data, run_data_collection
from .analytics import (
    analyze_apy_differences,
    get_top_asset_overall,
    get_top_asset_by_chain,
    get_top_growing_asset,
    get_top3_base_apy,
    get_latest_apy_data,
    get_top_apy_pools
)
# from .onchain import AaveV3Operator
from .notifications import TelegramNotifier, send_telegram_alert

__version__ = "0.3.0" 