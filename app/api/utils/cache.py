import redis
import json
import os
from typing import Optional, Dict, Any
from ...db.supabase import get_supabase
from ...config.settings import  REDIS_HOST, REDIS_PORT,  REDIS_CACHE_TTL

# Initialize Redis client
redis_client = redis.Redis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    db=0,
    decode_responses=True
)

CACHE_TTL = REDIS_CACHE_TTL  # Use the TTL from settings

async def get_user_by_id(user_id: str) -> Optional[Dict[str, Any]]:
    """
    Get user profile by ID with Redis caching
    First checks Redis cache, if not found fetches from database and caches the result
    """
    # Try to get from cache first
    cache_key = f"user_profile:{user_id}"
    cached_profile = redis_client.get(cache_key)
    
    if cached_profile:
        return json.loads(cached_profile)
    
    # If not in cache, get from database
    try:
        supabase = get_supabase()
        user_profile = supabase.from_("profiles") \
            .select("*") \
            .eq("id", user_id) \
            .single() \
            .execute()
        
        if user_profile.data:
            await update_user_cache(user_id, user_profile.data)
            return user_profile.data
        
        return None
    
    except Exception as e:
        print(f"Error fetching user profile: {str(e)}")
        return None

async def update_user_cache(user_id: str, profile_data: Dict[str, Any]) -> None:
    """
    Update the cache with new profile data
    """
    cache_key = f"user_profile:{user_id}"
    redis_client.setex(
        cache_key,
        CACHE_TTL,
        json.dumps(profile_data)
    )

def invalidate_user_cache(user_id: str) -> None:
    """
    Invalidate the cache for a specific user
    Call this when user profile is updated
    """
    cache_key = f"user_profile:{user_id}"
    redis_client.delete(cache_key) 