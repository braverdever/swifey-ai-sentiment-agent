from fastapi import APIRouter, HTTPException, Depends
from app.models.embeddings import OptimizedEmbeddingManager
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field

router = APIRouter()
embedding_manager = OptimizedEmbeddingManager()

@router.on_event("startup")
async def startup_event():
    await embedding_manager.init_faiss_index()

class SearchSimilarRequest(BaseModel):
    response: str = Field(..., description="Response text to search for similarities")
    agent_id: Optional[str] = Field(None, description="ID of the agent")
    user_id: str = Field(..., description="ID of the user")
    per_page: int = Field(default=10, ge=1, le=100, description="Number of results per page")

class TextEmbedRequest(BaseModel):
    texts: List[str]
    user_id: str
    agent_id: str
    embedding_type: str
    data_type: Optional[str] = None

@router.post("/search-similar-responses")
async def search_similar_responses(request: SearchSimilarRequest):
    """Search for similar responses using optimized embedding search"""
    try:
        result = await embedding_manager.search_similar_responses(
            response=request.response,
            user_id=request.user_id,
            agent_id=request.agent_id,
            per_page=request.per_page,
        )
        return result
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )

@router.post("/embed/texts")
async def create_text_embeddings(
    request: TextEmbedRequest
):
    """Create and store text embeddings one at a time"""
    try:
        result = await embedding_manager.create_text_embeddings(
            items=request.texts,
            user_id=request.user_id,
            agent_id=request.agent_id,
            embedding_type=request.embedding_type,
            data_type=request.data_type
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
