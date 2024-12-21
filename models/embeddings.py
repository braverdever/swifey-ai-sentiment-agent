import os
import torch
import clip
from PIL import Image
import numpy as np
from typing import Optional, List, Dict, Any, Union
from datetime import datetime
from supabase import create_client, Client
from io import BytesIO

class EmbeddingManager:
    def __init__(self):
        url = os.environ.get("SWIFEY_SUPABASE_URL")
        key = os.environ.get("SWIFEY_SUPABASE_KEY")
        if not url or not key:
            raise ValueError("Supabase credentials not found in environment variables (SWIFEY_SUPABASE_URL and SWIFEY_SUPABASE_KEY)")
        
        self.supabase: Client = create_client(url, key)
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model, self.preprocess = clip.load("ViT-B/32", device=self.device)
    
    async def create_embeddings(
        self,
        items: List[Union[bytes, str]],  # List of image bytes or text strings
        user_id: str,
        agent_id: str,
        embedding_type: str
    ) -> List[Dict[str, Any]]:
        """Create and store CLIP embeddings for multiple items"""
        try:
            embeddings_data = []
            
            for item in items:
                if isinstance(item, bytes):  # Image
                    # Process image and generate embedding
                    image = Image.open(BytesIO(item))
                    image_input = self.preprocess(image).unsqueeze(0).to(self.device)
                    
                    with torch.no_grad():
                        features = self.model.encode_image(image_input)
                        embedding = features.cpu().numpy().flatten().tolist()
                
                else:  # Text
                    # Process text and generate embedding
                    text_input = clip.tokenize([item]).to(self.device)
                    
                    with torch.no_grad():
                        features = self.model.encode_text(text_input)
                        embedding = features.cpu().numpy().flatten().tolist()
                
                embeddings_data.append({
                    "user_id": user_id,
                    "agent_id": agent_id,
                    "embedding": embedding,
                    "embedding_type": embedding_type,
                    "created_at": datetime.utcnow().isoformat()
                })
            
            # Store all embeddings in Supabase
            result = self.supabase.table("embeddings").insert(embeddings_data).execute()
            return result.data
            
        except Exception as e:
            raise Exception(f"Failed to create embeddings: {str(e)}")
    
    async def search_similar(
        self,
        query_embedding: List[float],
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        embedding_type: Optional[str] = None,
        limit: int = 10,
        similarity_threshold: float = 0.7
    ) -> List[Dict[str, Any]]:
        """Search for similar items using cosine similarity"""
        try:
            # Build the query with similarity search
            query = self.supabase.rpc(
                'match_embeddings',
                {
                    'query_embedding': query_embedding,
                    'match_threshold': similarity_threshold,
                    'match_count': limit
                }
            )
            
            if user_id:
                query = query.eq('user_id', user_id)
            if agent_id:
                query = query.eq('agent_id', agent_id)
            if embedding_type:
                query = query.eq('embedding_type', embedding_type)
            
            result = query.execute()
            return result.data
        
        except Exception as e:
            raise Exception(f"Failed to search similar items: {str(e)}")

    async def find_similar_users(
        self,
        user_id: str,
        embedding_type: Optional[str] = None,
        similarity_threshold: float = 0.7,
        max_users: int = 10
    ) -> List[Dict[str, Any]]:
        """Find similar users based on their embeddings"""
        try:
            result = self.supabase.rpc(
                'find_similar_users',
                {
                    'target_user_id': user_id,
                    'embedding_type_filter': embedding_type,
                    'similarity_threshold': similarity_threshold,
                    'max_users': max_users
                }
            ).execute()
            
            return result.data
        
        except Exception as e:
            raise Exception(f"Failed to find similar users: {str(e)}")

    async def compare_users(
        self,
        user_id_1: str,
        user_id_2: str,
        embedding_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Compare two users based on their embeddings"""
        try:
            result = self.supabase.rpc(
                'compare_users',
                {
                    'user_id_1': user_id_1,
                    'user_id_2': user_id_2,
                    'embedding_type_filter': embedding_type
                }
            ).execute()
            
            return result.data
        
        except Exception as e:
            raise Exception(f"Failed to compare users: {str(e)}")