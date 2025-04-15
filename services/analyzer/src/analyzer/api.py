from fastapi import FastAPI, HTTPException, Depends, Query, Security, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security.api_key import APIKeyHeader, APIKey
import uvicorn
from typing import List, Dict, Optional, Any, Union
from pydantic import BaseModel, Field
import logging
import os
from supabase import create_client

from analyzer.analyzer import (
    get_recommendations,
    analyze_wallet_positions_alchemy,
    get_top_pools_for_entry,
)

# Logging setup
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Supabase setup
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
API_TOKEN = os.environ.get("API_TOKEN", "")
ALCHEMY_API_KEY = os.environ.get("ALCHEMY_API_KEY", "")

API_KEY_NAME = "X-API-Token"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

# Create FastAPI application
app = FastAPI(
    title="Yieldex Analyzer API",
    description="API for getting recommendations on yield optimization in DeFi protocols",
    version="1.0.0"
)

# CORS setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, limit the list of allowed sources
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API data models
class RecommendationResponse(BaseModel):
    recommendations: List[Dict[str, Any]] = Field([], description="List of recommendations")
    comparisons: Optional[List[Dict[str, Any]]] = Field(None, description="All comparisons (if requested)")

async def get_api_key(api_key_header: str = Security(api_key_header)):
    """
    Validates API token
    
    Args:
        api_key_header: API token from request header
        
    Returns:
        API token if valid
        
    Raises:
        HTTPException: if token is invalid or missing
    """
    if not API_TOKEN:
        # If API_TOKEN is not set, skip validation
        return api_key_header
    
    if api_key_header == API_TOKEN:
        return api_key_header
    
    raise HTTPException(
        status_code=403, 
        detail="Invalid API token. Access denied.",
        headers={"WWW-Authenticate": "Bearer"},
    )

def get_pool_urls(pool_ids: List[str]) -> Dict[str, str]:
    """
    Get URLs for pools from pool_sites table
    
    Args:
        pool_ids: List of pool identifiers
        
    Returns:
        Dictionary of {pool_id: site_url}
    """
    try:
        if not pool_ids or not SUPABASE_URL or not SUPABASE_KEY:
            return {}
        
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        
        # Use in filter for single query instead of multiple queries
        response = supabase.table("pool_sites").select("pool_id, site_url").in_("pool_id", pool_ids).execute()
        
        # Convert result to dictionary
        pool_urls = {}
        for item in response.data:
            pool_urls[item["pool_id"]] = item["site_url"]
            
        return pool_urls
    except Exception as e:
        logger.error(f"Error fetching pool URLs: {str(e)}")
        return {}

def enrich_recommendations_with_urls(recommendations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Enrich recommendations with pool URLs
    
    Args:
        recommendations: List of recommendations
        
    Returns:
        List of recommendations with added URLs
    """
    # If no recommendations, nothing to enrich
    if not recommendations:
        return recommendations
    
    # Collect all pool_ids from recommendations
    pool_ids = []
    for rec in recommendations:
        # Target pool_id
        if "pool_id" in rec:
            pool_ids.append(rec["pool_id"])
        
        # For standard transfers, also include source pool_id
        if rec.get("recommendation_type") == "standard_transfer" and "original_pool_id" in rec:
            pool_ids.append(rec["original_pool_id"])
    
    # Get pool URLs
    pool_urls = get_pool_urls(pool_ids)
    
    # Enrich recommendations with URLs
    for rec in recommendations:
        if "pool_id" in rec and rec["pool_id"] in pool_urls:
            rec["url"] = pool_urls[rec["pool_id"]]
        else:
            rec["url"] = ""
            
        # Add source URL for transfers
        if rec.get("recommendation_type") == "standard_transfer" and "original_pool_id" in rec:
            if rec["original_pool_id"] in pool_urls:
                rec["source_url"] = pool_urls[rec["original_pool_id"]]
            else:
                rec["source_url"] = ""
    
    return recommendations

# API endpoints
@app.get("/", tags=["Info"])
async def root():
    """API health check"""
    return {"status": "ok", "service": "Yieldex Analyzer API"}

@app.get("/recommendations", tags=["Recommendations"], response_model=RecommendationResponse)
async def get_recommendations_api(
    chain: Optional[str] = Query(None, description="Blockchain network filter, all chains if not specified"),
    min_profit: float = Query(0.3, description="Minimum profit percentage for recommendation"),
    same_asset_only: bool = Query(False, description="Recommend only within same asset"),
    debug: bool = Query(False, description="Debug mode"),
    suggest_entry: bool = Query(False, description="Suggest new pools if no positions"),
    show_all_comparisons: bool = Query(False, description="Show all comparisons, including unprofitable ones"),
    api_key: APIKey = Depends(get_api_key)
):
    """
    Get yield optimization recommendations based on Supabase data
    """
    try:
        # Check for all required parameters
        if show_all_comparisons:
            recs, comparisons = get_recommendations(
                min_profit=min_profit,
                chain=chain,
                show_all_comparisons=True,
                same_asset_only=same_asset_only,
                debug=debug,
                suggest_entry=suggest_entry
            )
        else:
            recs = get_recommendations(
                min_profit=min_profit,
                chain=chain,
                same_asset_only=same_asset_only,
                debug=debug,
                suggest_entry=suggest_entry
            )
            comparisons = None

        # Enrich recommendations with pool URLs
        recs = enrich_recommendations_with_urls(recs)

        return RecommendationResponse(
            recommendations=recs,
            comparisons=comparisons
        )
    except Exception as e:
        logger.error(f"Error getting recommendations: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error getting recommendations: {str(e)}")

@app.get("/wallet/recommendations", tags=["Wallet"], response_model=RecommendationResponse)
async def get_wallet_recommendations(
    address: str = Query(..., description="Wallet address for analysis"),
    chain: Optional[str] = Query(None, description="Blockchain network filter"),
    min_profit: float = Query(0.3, description="Minimum profit percentage for recommendation"),
    same_asset_only: bool = Query(False, description="Recommend only within same asset"),
    debug: bool = Query(False, description="Debug mode"),
    api_key: APIKey = Depends(get_api_key)
):
    """
    Get yield optimization recommendations for specific wallet via Alchemy API
    """
    try:
        recs = analyze_wallet_positions_alchemy(
            address=address,
            chain=chain,
            min_profit=min_profit,
            same_asset_only=same_asset_only,
            debug=debug
        )
        
        # Enrich recommendations with pool URLs
        recs = enrich_recommendations_with_urls(recs)
        
        return RecommendationResponse(
            recommendations=recs
        )
    except Exception as e:
        logger.error(f"Error analyzing wallet: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error analyzing wallet: {str(e)}")

@app.get("/entry/recommendations", tags=["Entry"], response_model=RecommendationResponse)
async def get_entry_recommendations(
    chain: Optional[str] = Query(None, description="Blockchain network filter"),
    limit: int = Query(3, description="Number of pools to suggest"),
    min_tvl: float = Query(1_000_000, description="Minimum TVL for recommendation"),
    api_key: APIKey = Depends(get_api_key)
):
    """
    Get recommendations for entry when user has no positions
    """
    try:
        recs = get_top_pools_for_entry(
            chain=chain,
            limit=limit,
            min_tvl=min_tvl
        )
        
        # Enrich recommendations with pool URLs
        recs = enrich_recommendations_with_urls(recs)
        
        return RecommendationResponse(
            recommendations=recs
        )
    except Exception as e:
        logger.error(f"Error getting entry recommendations: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error getting entry recommendations: {str(e)}")

def start_api_server():
    """Function to start API server from command line"""
    uvicorn.run("analyzer.api:app", host="0.0.0.0", port=8000, reload=True)

if __name__ == "__main__":
    start_api_server()