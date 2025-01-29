from fastapi import APIRouter, HTTPException, Query, Path
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
import httpx
import json
from ..config.settings import ASTRALANE_API_KEY
from datetime import datetime
from ..utils.helpers import generate_cache_key
import redis
from ..config.settings import REDIS_HOST, REDIS_PORT
from ..auth.middleware import verify_app_token
from fastapi import Depends
from ..db.supabase import get_supabase
from ...config.settings import  REDIS_URL, REDIS_CACHE_TTL

router = APIRouter()

# Initialize Redis client
redis_client = redis.from_url(
    url=REDIS_URL,
    decode_responses=True
)

# Cache TTLs
PRICE_CACHE_TTL = 60  # 1 minute for price
OHLCV_CACHE_TTL = 300  # 5 minutes for OHLCV

# API Headers
API_HEADERS = {
    "x-api-key": ASTRALANE_API_KEY,
    "Content-Type": "application/json"
}

# Supported intervals for OHLCV
SUPPORTED_INTERVALS = {
    "1s": "1 SECOND",
    "5s": "5 SECONDS",
    "15s": "15 SECONDS",
    "1m": "1 MINUTE",
    "3m": "3 MINUTES",
    "5m": "5 MINUTES",
    "15m": "15 MINUTES",
    "30m": "30 MINUTES",
    "1h": "1 HOUR",
    "4h": "4 HOURS",
    "6h": "6 HOURS",
    "8h": "8 HOURS",
    "12h": "12 HOURS",
    "1d": "1 DAY"
}

class TokenPriceResponse(BaseModel):
    success: bool
    message: str
    data: Optional[Dict[str, Any]] = None

class OHLCVData(BaseModel):
    time: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    volume_usd: float

class OHLCVResponse(BaseModel):
    success: bool
    message: str
    data: Optional[List[OHLCVData]] = None

# Add this class for the request body
class TokenVanityUseRequest(BaseModel):
    public_key: str

@router.get("/price", response_model=TokenPriceResponse)
async def get_token_prices(
    tokens: str,
    profile_id: str = Depends(verify_app_token)
):
    """
    Get prices for multiple tokens using the Astralane GraphQL API.
    Includes 1-minute Redis caching.
    """
    try:
        # Try to get from cache first
        cache_key = generate_cache_key("token_prices", tokens)
        cached_data = redis_client.get(cache_key)
        print('cached_data', cached_data)
        if cached_data is not None:
            return {
                "success": True,
                "message": "Token prices fetched from cache",
                "data": json.loads(cached_data)
            }

        # GraphQL query for token prices
        # query = """
        # query GetTokenPrices($tokens: [String!]!) {
        #     tokens(addresses: $tokens) {
        #         address
        #         price
        #         priceChange24h
        #         volume24h
        #     }
        # }
        # """
        
        # variables = {
        #     "tokens": tokens.split(",")
        # }

        # If not in cache, fetch from API
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://graphql.astralane.io/api/v1/price-by-token?tokens={tokens}",
                headers=API_HEADERS,
                timeout=10.0
            )
            print('response', response)
            if response.status_code != 200:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Token price API error: {response.text}"
                )
            
            data = response.json()
            print('data', data)
            token_data = data.get("data", {}).get("tokens", {})
            print('token_data', data)
            
            # Cache the result
            if token_data:
                redis_client.setex(
                    cache_key,
                    PRICE_CACHE_TTL,
                    json.dumps(token_data)
                )
            
            return {
                "success": True,
                "message": "Token prices fetched successfully",
                "data": token_data
            }
            
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=504,
            detail="Request to token price API timed out"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch token prices: {str(e)}"
        )

@router.get("/ohlcv", response_model=OHLCVResponse)
async def get_token_ohlcv(
    pool_address: str,
    interval: str = "1m",  # Default to 1 minute
    from_time: Optional[int] = None,
    to_time: Optional[int] = None,
    profile_id: str = Depends(verify_app_token)
):
    """
    Get OHLCV (Open, High, Low, Close, Volume) data for a token pool.
    Includes 5-minute Redis caching.
    
    Parameters:
    - pool_address: The pool address to fetch OHLCV data for
    - interval: Time interval (1s, 5s, 15s, 1m, 3m, 5m, 15m, 30m, 1h, 4h, 6h, 8h, 12h, 1d)
    - from_time: Optional start time in Unix timestamp (seconds)
    - to_time: Optional end time in Unix timestamp (seconds)
    """
    try:
        if interval not in SUPPORTED_INTERVALS:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported interval. Supported intervals are: {', '.join(SUPPORTED_INTERVALS.keys())}"
            )

        # Generate cache key including all parameters
        cache_params = f"{pool_address}:{interval}:{from_time}:{to_time}"
        cache_key = generate_cache_key("token_ohlcv", cache_params)
        
        # Try to get from cache first
        cached_data = redis_client.get(cache_key)
        if cached_data:
            return {
                "success": True,
                "message": "OHLCV data fetched from cache",
                "data": [OHLCVData(**candle) for candle in json.loads(cached_data)]
            }

        # Build query parameters
        params = {"interval": interval}
        if from_time:
            params["from"] = from_time
        if to_time:
            params["to"] = to_time

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://graphql.astralane.io/api/v1/dataset/trade/ohlcv/{pool_address}",
                headers=API_HEADERS,
                params=params,
                timeout=10.0
            )
            
            if response.status_code != 200:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"OHLCV API error: {response.text}"
                )
            
            data = response.json()
            
            # Cache the raw data
            if data:
                redis_client.setex(
                    cache_key,
                    OHLCV_CACHE_TTL,
                    json.dumps(data)
                )
            
            return {
                "success": True,
                "message": "OHLCV data fetched successfully",
                "data": data
            }
            
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=504,
            detail="Request to OHLCV API timed out"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch OHLCV data: {str(e)}"
        ) 
    
@router.get("/token_vanity")
async def get_token_vanity(
    profile_id: str = Depends(verify_app_token)
):
    """
    Get the first unused token contract's public key from the database
    """
    supabase = get_supabase()
    response = supabase.table('token_contracts') \
        .select('public_key,used') \
        .eq('used', False) \
        .limit(1) \
        .execute()
    
    return response.data[0] if response.data else None

@router.post("/token_vanity/use")
async def use_token_vanity(
    request: TokenVanityUseRequest,
    profile_id: str = Depends(verify_app_token)
):
    """
    Mark a token contract as used
    """
    supabase = get_supabase()
    response = supabase.table('token_contracts') \
        .update({'used': True}) \
        .eq('public_key', request.public_key) \
        .execute()
    return {"success": True, "message": "Token contract marked as used"}

