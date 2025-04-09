"""
Data collector service for Yieldex protocol.
Collects yield data from DeFiLlama API and stores it in Supabase.
"""

from .collector import (
    fetch_pools,
    save_apy_data,
    run_data_collection
)

__version__ = "0.3.0" 