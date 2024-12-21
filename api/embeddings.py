from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from typing import Optional, Dict, Any
from models.embeddings import EmbeddingManager

router = APIRouter()
embedding_manager = EmbeddingManager()

@router.post("/embed/image")
async def create_image_embedding(
    file: UploadFile = File(...),
    user_id: str = None,
    agent_id: str = None,
    metadata: Optional[Dict[str, Any]] = None
):
    """Create and store CLIP embedding for an uploaded image"""
    if not file.content_type.startswith('image/'):
        raise HTTPException(status_code=400, detail="File must be an image")
    
    if not user_id or not agent_id:
        raise HTTPException(status_code=400, detail="user_id and agent_id are required")
    
    try:
        image_data = await file.read()
        result = await embedding_manager.create_image_embedding(
            image_data=image_data,
            user_id=user_id,
            agent_id=agent_id,
            metadata=metadata
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/similar/images")
async def search_similar_images(
    user_id: Optional[str] = None,
    agent_id: Optional[str] = None,
    limit: int = 10,
    similarity_threshold: float = 0.7
):
    """Search for similar images based on embedding similarity"""
    try:
        results = await embedding_manager.search_similar_images(
            user_id=user_id,
            agent_id=agent_id,
            limit=limit,
            similarity_threshold=similarity_threshold
        )
        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) 