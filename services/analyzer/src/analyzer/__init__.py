"""
Analytics service for Yieldex protocol.
Analyzes yield data and generates recommendations.
"""

from .analyzer import (
    analyze_apy_differences,
    get_top_asset_overall,
    get_top_asset_by_chain
)

__version__ = "0.3.0" 