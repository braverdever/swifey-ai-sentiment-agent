from fastapi import APIRouter, UploadFile, File, HTTPException
from typing import Optional, Dict, Any, List, Union
from models.embeddings import EmbeddingManager
from pydantic import BaseModel
import aiohttp

router = APIRouter()
embedding_manager = EmbeddingManager()

class TextEmbedRequest(BaseModel):
    texts: List[str]
    user_id: str
    agent_id: str
    embedding_type: str

@router.post("/embed/images")
async def create_image_embeddings(
    files: List[Union[UploadFile, str]] = File(...),
    user_id: str = None,
    agent_id: str = None,
    embedding_type: str = None
):
    """Create and store CLIP embeddings for multiple images, either uploaded or provided as URLs"""
    if not user_id or not agent_id or not embedding_type:
        raise HTTPException(status_code=400, detail="user_id, agent_id, and embedding_type are required")
    
    try:
        # Process all images, either uploaded or downloaded from URLs
        image_data = []
        for file in files:
            if isinstance(file, UploadFile):
                if not file.content_type.startswith('image/'):
                    raise HTTPException(status_code=400, detail=f"File {file.filename} must be an image")
                image_data.append(await file.read())
            elif isinstance(file, str):
                # Assuming file is a URL, download the image
                async with aiohttp.ClientSession() as session:
                    async with session.get(file) as response:
                        if response.status == 200:
                            image_data.append(await response.read())
                        else:
                            raise HTTPException(status_code=400, detail=f"Failed to download image from URL {file}")
            else:
                raise HTTPException(status_code=400, detail="Invalid file type")
        
        result = await embedding_manager.create_embeddings(
            items=image_data,
            user_id=user_id,
            agent_id=agent_id,
            embedding_type=embedding_type
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/embed/texts")
async def create_text_embeddings(request: TextEmbedRequest):
    """Create and store CLIP embeddings for multiple texts"""
    try:
        result = await embedding_manager.create_embeddings(
            items=request.texts,
            user_id=request.user_id,
            agent_id=request.agent_id,
            embedding_type=request.embedding_type
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