from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from typing import Optional, Dict, Any, List, Union
from pydantic import BaseModel, Field
from ..models.embeddings import EmbeddingManager  # Import from models
from pydantic import BaseModel
import os
import aiohttp
from datetime import datetime

router = APIRouter()
embedding_manager = EmbeddingManager()

embedding_manager.hyperbolic_api_url = os.environ.get("HYPERBOLIC_API_URL")
embedding_manager.hyperbolic_api_key = os.environ.get("HYPERBOLIC_API_KEY")

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
    user_id: str
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


@router.post("/search-similar-responses", response_model=SearchSimilarResponse)
async def search_similar_responses(request: SearchSimilarRequest):
    """
    Search for similar responses based on CLIP embeddings
    """
    try:
        print(f"Received search request for agent_id: {request.agent_id}")
        print(f"Query response: {request.response}")
        
        if not request.filters:
            request.filters = {"embedding_type": "text"}
        
        result = await embedding_manager.search_similar_responses(
            response=request.response,
            agent_id=request.agent_id,
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


@router.post("/embed/images")
async def create_image_embeddings(
    files: List[UploadFile] = File(...),
    user_id: str = Form(...),
    agent_id: str = Form(...),
    embedding_type: str = Form(...),
    data_type: Optional[str] = Form(None)
):
    print("Received request with:")
    print(f"user_id: {user_id}")
    print(f"agent_id: {agent_id}")
    print(f"embedding_type: {embedding_type}")
    print(f'data_type: {data_type}')
    print(f"Number of files: {len(files)}")

    if not user_id or not agent_id or not embedding_type:
        raise HTTPException(status_code=400, detail="user_id, agent_id, and embedding_type are required")
    
    try:
        image_data = []
        allowed_types = ['image/jpeg', 'image/png', 'image/gif']
        for file in files:
            print(f"Processing file: {file.filename}")
            print(f"Content type: {file.content_type}")
            
            if file.content_type not in allowed_types:
                raise HTTPException(
                    status_code=400, 
                    detail=f"Invalid file type: {file.content_type}. Allowed types are: {allowed_types}"
                )
            
            try:
                file_data = await file.read()
                print(f"Successfully read file data, size: {len(file_data)} bytes")
                image_data.append(file_data)
            except Exception as e:
                print(f"Error reading file: {str(e)}")
                raise HTTPException(status_code=500, detail=f"Error reading file: {str(e)}")
        
        try:
            print("Attempting to create embeddings...")
            result = await embedding_manager.create_embeddings(
                items=image_data,
                user_id=user_id,
                agent_id=agent_id,
                embedding_type=embedding_type,
                data_type=data_type
            )
            print("Successfully created embeddings")
            return result
        except Exception as e:
            print(f"Error in embedding_manager.create_embeddings: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Error creating embeddings: {str(e)}")
            
    except Exception as e:
        print(f"Unexpected error in create_image_embeddings: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    
@router.post("/embed/texts")
async def create_text_embeddings(request: TextEmbedRequest):
    """Create and store CLIP embeddings for multiple texts"""
    try:
        result = await embedding_manager.create_embeddings(
            items=request.texts,
            user_id=request.user_id,
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
        
        if request.store_result:
            try:
                await embedding_manager.store_similarity_result(
                    request.profile1_id,
                    request.profile2_id,
                    result
                )
            except Exception as e:
                print(f"Warning: Failed to store similarity result: {e}")
        
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