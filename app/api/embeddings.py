from fastapi import APIRouter, HTTPException
from typing import Optional, Dict, Any, List, Union
from pydantic import BaseModel, Field
from ..models.embeddings import EmbeddingManager  
import os
from datetime import datetime
from ..db.supabase import get_supabase
from fastapi import Depends
from ..auth.middleware import verify_app_token

router = APIRouter()
embedding_manager = EmbeddingManager()

class SearchSimilarRequest(BaseModel):
    agent_id: str = Field(..., description="ID of the agent")
    response: str = Field(..., description="Response text to search for similarities")
    per_page: int = Field(default=10, ge=1, le=100, description="Number of results per page")
    filters: Optional[Dict] = Field(default=None, description="Additional filters to apply")

class SearchSimilarResponse(BaseModel):
    results: List[Dict[str, Any]]
    meta: Dict[str, Any]

class TextEmbedRequest(BaseModel):
    texts: List[str]
    agent_id: str
    embedding_type: str
    data_type: Optional[str] = None

class SimilarityResponse(BaseModel):
    message: str
    similarity_metrics: Dict[str, Any]

class SimilarityRequest(BaseModel):
    profile1_id: str
    profile2_id: str
    include_visual: bool = True
    store_result: bool = True

class ProfilePhotoRequest(BaseModel):
    user_id: str

class UserAIRequest(BaseModel):
    agent_id: str
    compatibilty_prompt: str

@router.post("/sync-profile-photos")
async def sync_profile_photos(request: ProfilePhotoRequest):
    """Sync profile photos with embeddings"""
    try:
        result = await embedding_manager.sync_profile_embeddings(
            user_id=request.user_id,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/search-similar-responses", response_model=SearchSimilarResponse)
async def search_similar_responses(request: SearchSimilarRequest, user_id: str = Depends(verify_app_token)):
    """Search for similar responses based on CLIP embeddings"""
    try:
        print(f"Received search request for agent_id: {request.agent_id}")
        print(f"Query response: {request.response}")
                
        result = await embedding_manager.search_similar_responses(
            response=request.response,
            agent_id=request.agent_id,
            user_id=user_id,
            per_page=request.per_page,
            filters=request.filters
        )
        
        print(f"Search results - Total matches: {result['meta']['total_matches']}")
        return result
    except Exception as e:
        print(f"Error in search endpoint: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": str(e),
                "meta": {
                    "agent_id": request.agent_id,
                    "timestamp": datetime.utcnow().isoformat()
                }
            }
        )

# @router.post("/embed/profile-photos")
# async def create_profile_photo_embeddings(request: ProfilePhotoRequest):
#     """Create embeddings for all photos in a user's profile"""
#     try:
#         result = await embedding_manager.create_profile_embeddings(
#             user_id=request.user_id,
#         )
#         return result
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))

@router.post("/embed/texts")
async def create_text_embeddings(request: TextEmbedRequest, user_id: str = Depends(verify_app_token)):
    """Create and store CLIP embeddings for multiple texts"""
    try:
        result = await embedding_manager.create_text_embeddings(
            items=request.texts,
            user_id=user_id,
            agent_id=request.agent_id,
            embedding_type=request.embedding_type,
            data_type=request.data_type
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
@router.post("/similarity/generate", response_model=SimilarityResponse)
async def generate_similarity_message(request: SimilarityRequest):
    """Generate a similarity message for two profiles with enhanced metrics."""
    try:
        result = await embedding_manager.generate_enhanced_similarity_message(
            profile1_id=request.profile1_id,
            profile2_id=request.profile2_id,
            include_visual=request.include_visual
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/similar/{user_id}")
async def search_similar(
    user_id: str,
    agent_id: Optional[str] = None,
    embedding_type: Optional[str] = None,
    limit: int = 10,
    similarity_threshold: float = 0.7
):
    """Search for similar items based on embedding similarity"""
    try:
        results = await embedding_manager.search_similar(
            user_id=user_id,
            agent_id=agent_id,
            embedding_type=embedding_type,
            limit=limit,
            similarity_threshold=similarity_threshold
        )
        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/similar-users/{user_id}")
async def find_similar_users(
    user_id: str,
    embedding_type: Optional[str] = None,
    similarity_threshold: float = 0.7,
    max_users: int = 10
):
    """Find similar users based on their embeddings"""
    try:
        results = await embedding_manager.find_similar_users(
            user_id=user_id,
            embedding_type=embedding_type,
            similarity_threshold=similarity_threshold,
            max_users=max_users
        )
        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/compare/{user_id_1}/{user_id_2}")
async def compare_users(
    user_id_1: str,
    user_id_2: str,
    embedding_type: Optional[str] = None
):
    """Compare two users based on their embeddings"""
    try:
        results = await embedding_manager.compare_users(
            user_id_1=user_id_1,
            user_id_2=user_id_2,
            embedding_type=embedding_type
        )
        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
@router.post('/create_user_ai_data')
async def create_user_ai_data(request: UserAIRequest, profile_id: str = Depends(verify_app_token)):
    try: 
        supabase = get_supabase()
        response = supabase.table('user_ai_data').insert({
            'profile_id': profile_id,
            'agent_id': request.agent_id,
            'compatibilty_prompt': request.compatibilty_prompt
        }).execute()

        return {
            "success": True,
            "message": "User AI data created successfully"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))