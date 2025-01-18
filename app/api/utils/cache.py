import redis
import json
import os
from typing import Optional, Dict, Any
from ...db.supabase import get_supabase
from ...config.settings import  REDIS_URL, REDIS_CACHE_TTL

# Initialize Redis client
redis_client = redis.from_url(
    url=REDIS_URL,
    decode_responses=True
)

CACHE_TTL = REDIS_CACHE_TTL  # Use the TTL from settings

async def get_user_by_id(user_id: str) -> Optional[Dict[str, Any]]:
    """
    Get user profile by ID with Redis caching
    First checks Redis cache, if not found fetches from database and caches the result
    """
    # Try to get from cache first
    print(f"Getting user profile for {user_id}")
    cache_key = f"user_profile:{user_id}"
    print(f"Cache key: {cache_key}")
    cached_profile = redis_client.get(cache_key)
    print(f"Cached profile: {cached_profile}")
    
    if cached_profile:
        print(f"Returning cached profile for {user_id}")
        return json.loads(cached_profile)
    
    # If not in cache, get from database
    try:
        print(f"Fetching user profile from database for {user_id}")
        supabase = get_supabase()
        user_profile = supabase.from_("profiles") \
            .select("*") \
            .eq("id", user_id) \
            .single() \
            .execute()
        
        if user_profile.data:
            print(f"Updating cache for {user_id}")
            await update_user_cache(user_id, user_profile.data)
            print(f"Returning user profile from database for {user_id}")
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