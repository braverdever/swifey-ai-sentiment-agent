import os
import torch
import clip
from PIL import Image
import numpy as np
from typing import Optional, List, Dict, Any
from datetime import datetime
from supabase import create_client, Client
from io import BytesIO

class EmbeddingManager:
    def __init__(self):
        url = os.environ.get("SUPABASE_URL")
        key = os.environ.get("SUPABASE_KEY")
        if not url or not key:
            raise ValueError("Supabase credentials not found in environment variables")
        
        self.supabase: Client = create_client(url, key)
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model, self.preprocess = clip.load("ViT-B/32", device=self.device)
    
    async def create_image_embedding(
        self,
        image_data: bytes,
        user_id: str,
        agent_id: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Create and store CLIP embedding for an image"""
        try:
            # Process image and generate embedding
            image = Image.open(BytesIO(image_data))
            image_input = self.preprocess(image).unsqueeze(0).to(self.device)
            
            with torch.no_grad():
                image_features = self.model.encode_image(image_input)
                embedding = image_features.cpu().numpy().flatten().tolist()
            
            # Store in Supabase
            embedding_data = {
                "user_id": user_id,
                "agent_id": agent_id,
                "embedding": embedding,
                "metadata": metadata or {},
                "created_at": datetime.utcnow().isoformat(),
                "embedding_type": "clip_image"
            }
            
            result = self.supabase.table("embeddings").insert(embedding_data).execute()
            return result.data[0]
            
        except Exception as e:
            raise Exception(f"Failed to create image embedding: {str(e)}")
    
    async def search_similar_images(
        self,
        query_embedding: List[float],
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        limit: int = 10,
        similarity_threshold: float = 0.7
    ) -> List[Dict[str, Any]]:
        """Search for similar images using cosine similarity"""
        query = self.supabase.table("embeddings").select("*")
        
        if user_id:
            query = query.eq("user_id", user_id)
        if agent_id:
            query = query.eq("agent_id", agent_id)
            
        # Add vector similarity search condition
        # Note: This assumes you've set up the appropriate vector similarity search function in Supabase
        query = query.execute()
        
        return query.data

    @staticmethod
    def calculate_similarity(embedding1: List[float], embedding2: List[float]) -> float:
        """Calculate cosine similarity between two embeddings"""
        vec1 = np.array(embedding1)
        vec2 = np.array(embedding2)
        return float(np.dot(vec1, vec2) / (np.linalg.norm(vec1) * np.linalg.norm(vec2))) 