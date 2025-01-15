from fastapi import APIRouter, Depends, HTTPException
from ..db.supabase import get_supabase
from ..auth.middleware import verify_app_token
from upstash_redis import Redis
from pydantic import BaseModel
from typing import Optional, List
import json

router = APIRouter()

class AiCoach(BaseModel):
    id: str
    created_at: str
    name: str
    symbol: str
    profile_image: str
    prompt: str
    truth_index: int
    interaction_freq: int
    who_sees_you_prompt: Optional[str]
    who_you_see_prompt: Optional[str]
    wallet_addr: str
    price: Optional[float]
    token_mint: str
    category: str

class AiCoachesData(BaseModel):
    coaches: List[AiCoach]

def get_category_from_truth_index(truth_index: int) -> str:
    if truth_index >= 81 and truth_index <= 100:
        return 'Unfiltered truth teller'
    elif truth_index >= 61 and truth_index <= 80:
        return 'Serious challenger'
    elif truth_index >= 41 and truth_index <= 60:
        return 'Curious investigator'
    elif truth_index >= 21 and truth_index <= 40:
        return 'Mild chaos agent'
    else:
        return 'Lighthearted ally'

def add_category_to_agent(agent: dict) -> dict:
    return {
        **agent,
        'category': get_category_from_truth_index(agent['truth_index']) if agent.get('truth_index') else ''
    }

@router.get("/")
async def get_ai_coach(
    cursor: str | None = None,
    limit: int = 10,
    profile_id: str = Depends(verify_app_token)
):
    supabase = get_supabase()
    query = supabase.table('ai_agents')\
        .select('*')\
        .order('created_at', desc=True)\
        .limit(limit + 1)
    
    if cursor:
        query = query.lt('created_at', cursor)
    
    try:
        response = query.execute()
        data = response.data
        
        has_more = False
        next_cursor = None
        
        if len(data) > limit:
            has_more = True
            data.pop()
            next_cursor = data[-1]['created_at']
        
        enriched_data = [add_category_to_agent(agent) for agent in data]
        
        return {
            "data": enriched_data,
            "pagination": {
                "hasMore": has_more,
                "nextCursor": next_cursor
            }
        }
    
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail="Failed to fetch AI coaches"
        )

@router.get("/cached")
async def get_ai_coach_cached():
    redis = Redis.from_env()
    try:
        value = redis.get('ai_coaches')
        if value: 
            data = json.loads(value)
            return {
                'cached': True,
                'data': data
            }
        else:
            return {
                'cached': False
            }
    except Exception as e:
        print(e)
        raise HTTPException(status_code=500, detail="Failed to fetch cached AI coach")

@router.get("/{coach_id}")
async def get_ai_coach_by_id(
    coach_id: str,
    profile_id: str = Depends(verify_app_token)
):
    supabase = get_supabase()
    try:
        response = supabase.table('ai_agents')\
            .select('*')\
            .eq('id', coach_id)\
            .execute()
        
        data = response.data[0] if response.data else None
        
        if not data:
            raise HTTPException(
                status_code=404,
                detail="AI coach not found"
            )
        
        enriched_data = add_category_to_agent(data)
        return enriched_data
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail="Failed to fetch AI coach"
        )
    
@router.post("/cached")
async def set_ai_coach_cached(data: List[AiCoach]):
    redis = Redis.from_env()
    try:
        json_data = json.dumps([coach.dict() for coach in data])
        
        result = redis.set('ai_coaches', json_data)
        if not result:
            raise HTTPException(status_code=500, detail="Failed to cache AI coaches list.")
        
        return {
            "status": "success",
            "message": "AI coach data cached successfully"
        }
    except Exception as e:
        print(e)
        raise HTTPException(status_code=500, detail="Failed to set cached AI coach")
