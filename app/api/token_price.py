from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
import httpx
import json
from ..config.settings import HELIUS_API_KEY
from datetime import datetime
from ..utils.helpers import generate_cache_key
import redis
from ..config.settings import REDIS_HOST, REDIS_PORT

router = APIRouter()

# Initialize Redis client
redis_client = redis.Redis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    decode_responses=True
)

# Cache TTLs
PRICE_CACHE_TTL = 60  # 1 minute for price
OHLCV_CACHE_TTL = 300  # 5 minutes for OHLCV

class TokenPriceResponse(BaseModel):
    success: bool
    message: str
    data: Optional[Dict[str, Any]] = None

class OHLCVData(BaseModel):
    timestamp: int
    open: float
    high: float
    low: float
    close: float
    volume: float

class OHLCVResponse(BaseModel):
    success: bool
    message: str
    data: Optional[List[OHLCVData]] = None

@router.get("/price/{token_mint}", response_model=TokenPriceResponse)
async def get_token_price(token_mint: str):
    """
    Get the price of a token using the Jupiter Price API.
    Includes 1-minute Redis caching.
    """
    try:
        # Try to get from cache first
        cache_key = generate_cache_key("token_price", token_mint)
        cached_data = redis_client.get(cache_key)
        
        if cached_data:
            return {
                "success": True,
                "message": "Token price fetched from cache",
                "data": json.loads(cached_data)
            }
        
        # If not in cache, fetch from API
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://price.jup.ag/v4/price?ids={token_mint}",
                timeout=10.0
            )
            
            if response.status_code != 200:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Token price API error: {response.text}"
                )
            
            data = response.json()
            token_data = data.get("data", {}).get(token_mint)
            
            # Cache the result
            if token_data:
                redis_client.setex(
                    cache_key,
                    PRICE_CACHE_TTL,
                    json.dumps(token_data)
                )
            
            return {
                "success": True,
                "message": "Token price fetched successfully",
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
            detail=f"Failed to fetch token price: {str(e)}"
        )

@router.get("/ohlcv/{token_mint}", response_model=OHLCVResponse)
async def get_token_ohlcv(
    token_mint: str,
    resolution: str = "1D",  # Default to 1 day
    start_time: Optional[int] = None,
    end_time: Optional[int] = None
):
    """
    Get OHLCV (Open, High, Low, Close, Volume) data for a token.
    Includes 5-minute Redis caching.
    
    Parameters:
    - token_mint: The token's mint address
    - resolution: Time resolution (1m, 3m, 5m, 15m, 30m, 1H, 2H, 4H, 1D, 1W, 1M)
    - start_time: Optional start time in Unix timestamp (seconds)
    - end_time: Optional end time in Unix timestamp (seconds)
    """
    try:
        # Generate cache key including all parameters
        cache_params = f"{token_mint}:{resolution}:{start_time}:{end_time}"
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
        params = {"resolution": resolution}
        if start_time:
            params["start_time"] = start_time
        if end_time:
            params["end_time"] = end_time

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://price.jup.ag/v4/ohlcv/{token_mint}",
                params=params,
                timeout=10.0
            )
            
            if response.status_code != 200:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"OHLCV API error: {response.text}"
                )
            
            data = response.json()
            
            # Transform the data into our response format
            ohlcv_data = []
            for candle in data.get("data", []):
                ohlcv_data.append(OHLCVData(
                    timestamp=candle[0],
                    open=candle[1],
                    high=candle[2],
                    low=candle[3],
                    close=candle[4],
                    volume=candle[5]
                ))
            
            # Cache the transformed data
            if ohlcv_data:
                redis_client.setex(
                    cache_key,
                    OHLCV_CACHE_TTL,
                    json.dumps([candle.dict() for candle in ohlcv_data])
                )
            
            return {
                "success": True,
                "message": "OHLCV data fetched successfully",
                "data": ohlcv_data
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