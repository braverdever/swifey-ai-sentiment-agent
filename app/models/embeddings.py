import os
import numpy as np
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from sentence_transformers import SentenceTransformer
import faiss
from supabase import create_client, Client
import json
import asyncio
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache

class SemanticCache:
    def __init__(self, similarity_threshold=0.95):
        self.cache = {}
        self.similarity_threshold = similarity_threshold

    async def get(self, query: str, embedding_manager):
        query_embedding = await embedding_manager.get_embedding(query)
        
        # Clean expired entries
        now = datetime.now()
        self.cache = {
            k: v for k, v in self.cache.items() 
            if now - v['timestamp'] < timedelta(hours=24)
        }
        
        # Check for similar queries
        for cached_query, cache_entry in self.cache.items():
            similarity = np.dot(query_embedding, cache_entry['embedding'])
            if similarity > self.similarity_threshold:
                return cache_entry['results']
        return None

    def set(self, query: str, embedding: np.ndarray, results: Dict[str, Any]):
        self.cache[query] = {
            'embedding': embedding,
            'results': results,
            'timestamp': datetime.now()
        }

class OptimizedEmbeddingManager:
    def __init__(self):
        url = os.environ.get("SWIFEY_SUPABASE_URL")
        key = os.environ.get("SWIFEY_SUPABASE_KEY")
        if not url or not key:
            raise ValueError("Supabase credentials not found")
        
        self.supabase: Client = create_client(url, key)
        self.model = SentenceTransformer('all-MiniLM-L6-v2')
        self.embedding_dim = 384
        self.semantic_cache = SemanticCache()
        self.executor = ThreadPoolExecutor(max_workers=4)
        self.embedding_map = {}  
        self.init_index()

    def init_index(self):
        """Initialize HNSW index for approximate nearest neighbor search"""
        self.index = faiss.IndexHNSWFlat(self.embedding_dim, 32)  # 32 neighbors per node
        self.index.hnsw.efConstruction = 40  # Higher accuracy during construction
        self.index.hnsw.efSearch = 16  # Higher accuracy during search

    @lru_cache(maxsize=1000)
    def get_embedding_sync(self, text: str) -> np.ndarray:
        """Synchronous method to get embeddings with caching"""
        embedding = self.model.encode([text])
        return embedding[0]

    async def get_embedding(self, text: str) -> np.ndarray:
        """Async wrapper for getting embeddings"""
        return await asyncio.get_event_loop().run_in_executor(
            self.executor,
            self.get_embedding_sync,
            text
        )

    async def init_faiss_index(self):
        """Initialize FAISS index with existing embeddings"""
        try:
            print("Starting FAISS index initialization...")
            
            # Pre-filter verified profiles first
            verified_profiles = self.supabase.table('profiles') \
                .select('id') \
                .eq('verification_status', 'approved') \
                .execute()
            
            verified_user_ids = [p['id'] for p in verified_profiles.data] if verified_profiles.data else []
            
            if not verified_user_ids:
                print("No verified profiles found")
                return
                
            # Get embeddings only for verified users
            embeddings = self.supabase.table("embeddings") \
                .select('*') \
                .in_('user_id', verified_user_ids) \
                .execute()
                
            print(f"Retrieved {len(embeddings.data) if embeddings.data else 0} embeddings from database")
            
            if embeddings.data:
                all_embeddings = []
                embedding_map = {}
                
                for idx, record in enumerate(embeddings.data):
                    try:
                        embedding_str = record.get('embedding')
                        if embedding_str:
                            embedding_values = embedding_str.strip('[]').split(',')
                            embedding = np.array([float(x.strip()) for x in embedding_values], dtype=np.float32)
                            
                            if len(embedding) == self.embedding_dim:
                                all_embeddings.append(embedding)
                                embedding_map[len(all_embeddings) - 1] = record
                            else:
                                print(f"Wrong dimension for user {record['user_id']}")
                        else:
                            print(f"No embedding data for user {record['user_id']}")
                    except Exception as e:
                        print(f"Error processing embedding for user {record.get('user_id')}: {str(e)}")
                        continue
                
                if all_embeddings:
                    embeddings_array = np.vstack(all_embeddings)
                    norms = np.linalg.norm(embeddings_array, axis=1)
                    normalized = embeddings_array / norms[:, np.newaxis]
                    
                    self.init_index()  # Reinitialize HNSW index
                    self.index.add(normalized.astype('float32'))
                    self.embedding_map = embedding_map
                    print(f"Successfully initialized HNSW index with {len(all_embeddings)} embeddings")
                else:
                    print("No valid embeddings found for FAISS index")
            else:
                print("No embeddings found in database")
                
        except Exception as e:
            print(f"Error initializing FAISS index: {e}")
            import traceback
            print(traceback.format_exc())

    async def search_similar_responses(
        self,
        response: str,
        user_id: str,
        agent_id: Optional[str] = None,
        per_page: int = 20,
    ) -> Dict[str, Any]:
        """Search for similar responses using improved semantic similarity scoring"""
        try:
            # Check semantic cache first
            cached_result = await self.semantic_cache.get(response, self)
            if cached_result:
                print("Cache hit! Returning cached results")
                return cached_result
            
            # Get user preferences and filter eligible profiles
            user_preferences = self.supabase.table('profiles') \
                .select('gender_preference') \
                .eq('id', user_id) \
                .single() \
                .execute()
            
            preferred_genders = user_preferences.data.get('gender_preference', []) if user_preferences.data else []
            
            eligible_profiles = self.supabase.table('profiles') \
                .select('id, name, bio, gender, location, matching_prompt, photos, verification_status') \
                .in_('gender', preferred_genders) \
                .eq('verification_status', 'approved') \
                .execute()
            
            if not eligible_profiles.data:
                return {'results': [], 'meta': {'total_matches': 0}}
            
            eligible_user_ids = [p['id'] for p in eligible_profiles.data]
            profiles_lookup = {p['id']: p for p in eligible_profiles.data}
            
            # Generate embedding for query
            query_embedding = await self.get_embedding(response)
            
            # Normalize query embedding using L2 normalization
            query_norm = np.linalg.norm(query_embedding)
            if query_norm < 1e-8:
                return {'results': [], 'meta': {'total_matches': 0}}
            normalized_query = query_embedding / query_norm
            
            # Perform semantic search with cosine similarity
            k = min(self.index.ntotal, 100)  # Get top 100 candidates
            distances, indices = self.index.search(
                normalized_query.reshape(1, -1).astype('float32'),
                k
            )
            
            # Convert distances to similarities (cosine similarity is in [-1, 1])
            similarities = (distances[0] + 1) / 2  # Convert to [0, 1] range
            
            # Process results
            results = []
            seen_user_ids = set()
            
            for similarity, idx in zip(similarities, indices[0]):
                embedding_record = self.embedding_map.get(idx)
                if not embedding_record:
                    continue
                    
                user_id = embedding_record['user_id']
                if user_id in seen_user_ids or user_id not in eligible_user_ids:
                    continue
                    
                if user_id in profiles_lookup:
                    # Apply semantic relevance threshold
                    if similarity < 0.0:  
                        continue
                        
                    results.append({
                        'response_id': user_id,
                        'similarity_score': float(similarity),
                        'embedding_type': embedding_record.get('embedding_type', ''),
                        'data_type': embedding_record.get('data_type', ''),
                        'created_at': embedding_record['created_at'],
                        'profile': profiles_lookup[user_id]
                    })
                    seen_user_ids.add(user_id)
            
            # Sort by similarity score in descending order (higher is better)
            results.sort(key=lambda x: x['similarity_score'], reverse=True)
            results = results[:per_page]
            
            # Calculate metadata
            if results:
                all_scores = [r['similarity_score'] for r in results]
                meta = {
                    'total_matches': len(results),
                    'filtered_count': len(results),
                    'max_similarity': float(max(all_scores)),
                    'mean_similarity': float(np.mean(all_scores)),
                    'min_similarity': float(min(all_scores)),
                    'query_response': response
                }
            else:
                meta = {
                    'total_matches': 0,
                    'filtered_count': 0,
                    'max_similarity': 0.0,
                    'mean_similarity': 0.0,
                    'min_similarity': 0.0,
                    'query_response': response
                }
            
            response_data = {
                'results': results,
                'meta': meta
            }
            
            # Cache the results
            self.semantic_cache.set(response, normalized_query, response_data)
            
            return response_data
                
        except Exception as e:
            print(f"Error in search_similar_responses: {str(e)}")
            raise Exception(f"Failed to search similar responses: {str(e)}")   
     
    async def create_text_embeddings(
        self,
        items: List[str],
        user_id: str,
        agent_id: str,
        embedding_type: str,
        data_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Create embeddings with optimized batch processing"""
        try:
            # Delete existing embeddings
            delete_result = self.supabase.table("embeddings") \
                .delete() \
                .eq('user_id', user_id) \
                .eq('data_type', data_type) \
                .eq('embedding_type', embedding_type) \
                .execute()
            
            print(f"Deleted existing embeddings for user {user_id}")
            results = []
            batch_size = 32  # Process in batches for better performance
            
            for i in range(0, len(items), batch_size):
                batch = items[i:i + batch_size]
                batch_embeddings = []
                
                # Generate embeddings for the batch
                for item in batch:
                    embedding = await self.get_embedding(item)
                    embedding_list = embedding.tolist() if isinstance(embedding, np.ndarray) else list(embedding)
                    batch_embeddings.append(embedding_list)
                
                # Prepare batch records
                batch_records = [
                    {
                        "user_id": user_id,
                        "agent_id": agent_id,
                        "embedding": embedding,
                        "embedding_type": embedding_type,
                        "data_type": data_type,
                        "created_at": datetime.utcnow().isoformat()
                    }
                    for embedding in batch_embeddings
                ]
                
                # Batch insert
                result = self.supabase.table("embeddings") \
                    .insert(batch_records) \
                    .execute()
                
                if result.data:
                    # Convert back to numpy arrays for FAISS
                    normalized_embeddings = np.vstack([
                        np.array(embedding) / np.linalg.norm(np.array(embedding))
                        for embedding in batch_embeddings
                    ])
                    self.index.add(normalized_embeddings.astype('float32'))
                    results.extend(result.data)
                    print(f"Processed batch of {len(batch)} embeddings")
            
            return results
            
        except Exception as e:
            print(f"Error in create_text_embeddings: {str(e)}")
            raise Exception(f"Failed to create text embeddings: {str(e)}")