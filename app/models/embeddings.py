import os
import torch
import clip
from PIL import Image
import numpy as np
from typing import Optional, List, Dict, Any, Union
from datetime import datetime
from supabase import create_client, Client
from io import BytesIO
import json
import requests
import ast


class EmbeddingManager:
    def __init__(self):
        url = os.environ.get("SWIFEY_SUPABASE_URL")
        key = os.environ.get("SWIFEY_SUPABASE_KEY")
        if not url or not key:
            raise ValueError("Supabase credentials not found in environment variables (SWIFEY_SUPABASE_URL and SWIFEY_SUPABASE_KEY)")
        
        self.supabase: Client = create_client(url, key)
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model, self.preprocess = clip.load("ViT-B/32", device=self.device)

    async def fetch_profile_photos(self, user_id: str) -> List[str]:
        """Fetch photo paths from the profiles table."""
        try:
            response = self.supabase.table('profiles') \
                .select('photos') \
                .eq('id', user_id) \
                .single() \
                .execute()
            
            if response.data and 'photos' in response.data:
                return response.data['photos']
            return []
        except Exception as e:
            print(f"Error fetching profile photos: {str(e)}")
            return []

    async def fetch_image(self, image_path: str) -> Optional[bytes]:
        """Fetch image data from storage."""
        try:
            response = self.supabase.storage.from_('photos').download(image_path)
            return response
        except Exception as e:
            print(f"Error fetching image {image_path}: {str(e)}")
            return None

    async def sync_profile_embeddings(
        self,
        user_id: str,
    ) -> Dict[str, Any]:
        """Sync embeddings with current profile photos, creating new ones and deleting old ones."""
        try:
            print(f"Starting embedding sync for user {user_id}...")
            
            current_photo_paths = await self.fetch_profile_photos(user_id)
            if not current_photo_paths:
                print("No photos found in profile")
                return {
                    "photos_total": 0,
                    "embeddings_deleted": 0,
                    "embeddings_created": 0,
                    "status": "success"
                }
                
            print(f"Found {len(current_photo_paths)} photos in profile")

            existing_embeddings = self.supabase.table("embeddings") \
                .select('*') \
                .eq('user_id', user_id) \
                .like('embedding_type', 'photo_%') \
                .execute()
            
            existing_paths = {
                embed['photo_path']: embed
                for embed in existing_embeddings.data
                if embed.get('photo_path')
            }

            print(f"Found {len(existing_paths)} existing embeddings")

            paths_to_delete = set(existing_paths.keys()) - set(current_photo_paths)
            if paths_to_delete:
                print(f"Deleting embeddings for {len(paths_to_delete)} removed photos...")
                embedding_types_to_delete = [
                    existing_paths[path]['embedding_type'] for path in paths_to_delete
                ]
                
                try:
                    delete_result = await self.delete_embeddings(
                        user_id=user_id,
                        embedding_types=embedding_types_to_delete
                    )
                    print(f"Deleted {len(delete_result) if delete_result else 0} embeddings")
                except Exception as delete_error:
                    print(f"Error deleting embeddings: {str(delete_error)}")

            successful_creations = 0
            
            print(f"Processing {len(current_photo_paths)} photos...")
            for idx, photo_path in enumerate(current_photo_paths):
                try:
                    print(f"Processing photo {idx + 1}/{len(current_photo_paths)}: {photo_path}")
                    
                    image_data = await self.fetch_image(photo_path)
                    if not image_data:
                        print(f"Skipping photo {photo_path} - failed to fetch data")
                        continue
                    
                    image = Image.open(BytesIO(image_data))
                    image_input = self.preprocess(image).unsqueeze(0).to(self.device)
                    
                    with torch.no_grad():
                        features = self.model.encode_image(image_input)
                        embedding = features.cpu().numpy().flatten().tolist()
                    
                    embedding_type = f"photo_{idx}"  # Use unique embedding type for each photo
                    
                    await self.delete_embeddings(
                        user_id=user_id,
                        embedding_types=[embedding_type]
                    )
                    
                    embedding_record = {
                        "user_id": user_id,
                        "embedding": embedding,
                        "embedding_type": embedding_type,
                        "data_type": "image",
                        "created_at": datetime.utcnow().isoformat(),
                        "photo_path": photo_path
                    }
                    
                    print(f"Storing/updating embedding for {embedding_type}")
                    result = self.supabase.table("embeddings").upsert(
                        embedding_record
                    ).execute()
                    
                    if result.data:
                        successful_creations += 1
                        print(f"Successfully created embedding {embedding_type}")
                    
                except Exception as e:
                    print(f"Error processing photo {idx}: {str(e)}")
                    continue
            
            return {
                "photos_total": len(current_photo_paths),
                "embeddings_deleted": len(paths_to_delete),
                "embeddings_created": successful_creations,
                "status": "success"
            }
            
        except Exception as e:
            print(f"Error in sync_profile_embeddings: {str(e)}")
            raise Exception(f"Failed to sync profile embeddings: {str(e)}")
    
    async def delete_embeddings(
        self,
        user_id: str,
        embedding_types: List[str]
    ) -> List[Dict[str, Any]]:
        """Delete specific embeddings for a user."""
        try:
            result = self.supabase.table("embeddings") \
                .delete() \
                .eq('user_id', user_id) \
                .in_('embedding_type', embedding_types) \
                .execute()
            
            return result.data
        except Exception as e:
            print(f"Error deleting embeddings: {str(e)}")
            return []
    
    async def create_text_embeddings(
        self,
        items: List[str],  
        user_id: str,
        agent_id: str,
        embedding_type: str,
        data_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Create or update CLIP embeddings for multiple text items"""
        try:
            print("Starting text embedding creation/update...")
            embeddings_data = []
            
            await self.delete_embeddings(
                user_id=user_id,
                embedding_types=[embedding_type]
            )
            
            for idx, item in enumerate(items):
                print(f"Processing item {idx + 1}/{len(items)}")
                
                text_input = clip.tokenize([item]).to(self.device)
                    
                with torch.no_grad():
                    features = self.model.encode_text(text_input)
                    embedding = features.cpu().numpy().flatten().tolist()
                
                embedding_record = {
                    "user_id": user_id,
                    "agent_id": agent_id,
                    "embedding": embedding,
                    "embedding_type": embedding_type,
                    "data_type": data_type,
                    "created_at": datetime.utcnow().isoformat()
                }
                embeddings_data.append(embedding_record)
            
            if not embeddings_data:
                raise Exception("No valid embeddings were generated")
            
            print(f"Storing/updating {len(embeddings_data)} text embeddings in Supabase...")
            result = self.supabase.table("embeddings").upsert(
                embeddings_data  # Fixed: Use the full list instead of single record
            ).execute()
            print("Text embeddings stored/updated successfully")
            return result.data
            
        except Exception as e:
            print(f"Error in create_text_embeddings: {str(e)}")
            raise Exception(f"Failed to create/update text embeddings: {str(e)}")

    async def get_profile_data(self, profile_id: str) -> Optional[Dict]:
        """Fetch profile data from Supabase."""
        try:
            response = self.supabase.table('profiles') \
                .select('id, name, bio, gender, location, matching_prompt, photos') \
                .eq('id', profile_id) \
                .single() \
                .execute()
            
            return response.data if response.data else None
        except Exception as e:
            print(f"Error fetching profile data: {e}")
            return None
        
        
        
    def find_common_interests(self, profile1: Dict, profile2: Dict) -> List[str]:
        """Extract and compare interests from profiles' bios and matching prompts."""
        interests = []
        
        def extract_keywords(text: str) -> List[str]:
            if not text:
                return []
            keywords = text.lower().replace(',', ' ').split()
            return [word.strip('.,!?') for word in keywords]

        profile1_keywords = set(extract_keywords(profile1.get('bio', '')) + 
                              extract_keywords(profile1.get('matching_prompt', '')))
        profile2_keywords = set(extract_keywords(profile2.get('bio', '')) + 
                              extract_keywords(profile2.get('matching_prompt', '')))

        common_keywords = profile1_keywords.intersection(profile2_keywords)
        
        stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for'}
        interests = [word for word in common_keywords if word not in stop_words]

        return interests

    async def calculate_visual_similarity(self, profile1_id: str, profile2_id: str) -> float:
        """Calculate visual similarity between two profiles using CLIP embeddings."""
        try:
            result = await self.supabase.rpc(
                'compare_users',
                {
                    'user_id_1': profile1_id,
                    'user_id_2': profile2_id,
                    'embedding_type_filter': 'selfie'  
                }
            ).execute()
            
            if result.data and len(result.data) > 0:
                return float(result.data[0].get('similarity', 0))
            return 0.0
            
        except Exception as e:
            print(f"Error calculating visual similarity: {e}")
            return 0.0
        
    
    async def search_similar_responses(
        self,
        response: str,
        user_id: str,
        agent_id: str,
        per_page: int = 20,
        filters: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """Search for similar responses based on CLIP embeddings"""
        try:
            print(f"Starting similarity search for agent_id: {agent_id}")
            print(f"Query text: {response}")
            print(f"Filters: {filters}")
            
            text_input = clip.tokenize([response]).to(self.device)
            with torch.no_grad():
                text_features = self.model.encode_text(text_input)
                query_embedding = text_features[0].cpu().numpy().flatten().tolist()
            
            print(f"Generated query embedding shape: {len(query_embedding)}")

            try:
                query = self.supabase.table('embeddings').select('*')
                responses = query.execute()
                
                user_ids = list(set(resp['user_id'] for resp in responses.data if 'user_id' in resp))                
                profiles = self.supabase.table('profiles').select('*').in_('id', user_ids).execute()
                
                total_records = len(responses.data) if responses.data else 0
                print(f"Found {total_records} records after filtering")
                
                if responses.data and total_records > 0:
                    sample_record = responses.data[0]
                    print(f"Sample record keys: {sample_record.keys()}")
                    if 'embedding' in sample_record:
                        print(f"Embedding type: {type(sample_record['embedding'])}")

            except Exception as db_error:
                print(f"Database query error: {str(db_error)}")
                raise Exception(f"Database query failed: {str(db_error)}")

            similarities = []
            for resp in responses.data:
                try:
                    if resp['user_id'] == user_id:
                        continue

                    embedding = resp.get('embedding')
                    if isinstance(embedding, str):
                        try:
                            embedding = json.loads(embedding)
                        except json.JSONDecodeError:
                            # Try parsing as string representation of list
                            embedding = ast.literal_eval(embedding)
                    
                    if not embedding or not isinstance(embedding, (list, np.ndarray)):
                        print(f"Skipping record {resp.get('user_id')} - invalid embedding format: {type(embedding)}")
                        continue

                    resp_array = np.array(embedding, dtype=np.float32)
                    query_array = np.array(query_embedding, dtype=np.float32)

                    # Verify embedding dimensions
                    if query_array.shape != resp_array.shape:
                        print(f"Skipping record {resp.get('user_id')} - shape mismatch: {query_array.shape} vs {resp_array.shape}")
                        continue

                    # Calculate cosine similarity
                    similarity = float(np.dot(query_array, resp_array) / 
                                    (np.linalg.norm(query_array) * np.linalg.norm(resp_array)))

                    if similarity > 0.1:
                        similarities.append({
                            'response_id': resp['user_id'],
                            'similarity_score': similarity,
                            'metadata': {
                                'userId': resp['user_id'],
                                'embedding_type': resp.get('embedding_type', ''),
                                'data_type': resp.get('data_type', ''),
                                'timestamp': resp['created_at'],
                                'text': resp.get('text', '')
                            },
                            'relative_score': 0.0
                        })
                        print(f"Added similarity score {similarity:.4f} for user {resp['user_id']}")
                except Exception as e:
                    print(f"Error processing record {resp.get('user_id')}: {str(e)}")
                    continue

            if similarities:
                user_ids = list(set(s['response_id'] for s in similarities))
                
                profiles_response = self.supabase.table('profiles') \
                    .select('id, name, bio, gender, location, matching_prompt, photos') \
                    .in_('id', user_ids) \
                    .execute()
                
                profiles_lookup = {
                    profile['id']: profile 
                    for profile in profiles_response.data
                } if profiles_response.data else {}

                max_score = max(s['similarity_score'] for s in similarities)
                mean_score = sum(s['similarity_score'] for s in similarities) / len(similarities)
                print(f"Max similarity: {max_score:.4f}, Mean similarity: {mean_score:.4f}")
                
                results = []
                for s in similarities:
                    s['relative_score'] = float(s['similarity_score'] / max_score if max_score > 0 else 0.0)
                    # Add profile data to each result
                    s['profile'] = profiles_lookup.get(s['response_id'], {})
                    results.append(s)

                # Sort and limit results
                results.sort(key=lambda x: x['similarity_score'], reverse=True)
                results = results[:per_page]
                print(f"Returning {len(results)} results with profiles")
            else:
                results = []
                max_score = mean_score = 0.0

            return {
                'results': results,
                'meta': {
                    'agent_id': agent_id,
                    'total_matches': len(similarities),
                    'filtered_count': len(results),
                    'max_similarity': float(max_score),
                    'mean_similarity': float(mean_score),
                    'query_response': response,
                    'debug_info': {
                        'total_records': total_records,
                        'final_filtered': len(similarities)
                    }
                }
            }

        except Exception as e:
            print(f"Error in search_similar_responses: {str(e)}")
            raise Exception(f"Failed to search similar responses: {str(e)}")
                    
    async def generate_enhanced_similarity_message(
        self, 
        profile1_id: str, 
        profile2_id: str,
        include_visual: bool = True
    ) -> Dict[str, Any]:
        """Generate an enhanced similarity message incorporating both text and visual similarity."""
        try:
            profile1 = await self.get_profile_data(profile1_id)
            profile2 = await self.get_profile_data(profile2_id)

            if not profile1 or not profile2:
                raise ValueError("Could not fetch profile data")

            common_interests = self.find_common_interests(profile1, profile2)
            visual_similarity = 0.0
            if include_visual:
                visual_similarity = await self.calculate_visual_similarity(profile1_id, profile2_id)

            shared_interest_part = ''
            if common_interests:
                if len(common_interests) == 1:
                    shared_interest_part = f"{profile1['name']} and {profile2['name']} both love {common_interests[0]}. "
                else:
                    interests_text = f"{', '.join(common_interests[:-1])} and {common_interests[-1]}"
                    shared_interest_part = f"{profile1['name']} and {profile2['name']} share common interests in {interests_text}. "

            visual_comment = ""
            if include_visual and visual_similarity > 0.3:
                visual_comment = "You two even have similar vibes in your photos! "
            elif include_visual and visual_similarity > 0.2:
                visual_comment = "Your photos suggest you'd make a great match! "

            prompt = f"""
            Let's craft a message for {profile2['name']} and me that's not just cheesy, but also heartfelt and detailed. Here's what you need to know about them:
            - {profile1['name']}: {json.dumps(profile1)}
            - {profile2['name']}: {json.dumps(profile2)}
            They've just found out they {
                f"share a passion for {'several things' if len(common_interests) > 1 else common_interests[0]}" 
                if common_interests 
                else 'have something incredible in common'
            }. {visual_comment}We want a message that's rich in puns, playful jokes, and celebrates their shared interest in a way that's both funny and touching. 
            Include: "{shared_interest_part}Think of the wonderful adventures that lie ahead!"
            Aim for a message that's under 300 characters, packed with humor and warmth, making it impossible for them not to smile.
            """

            hyperbolic_api_url = os.environ.get("HYPERBOLIC_API_URL")
            hyperbolic_api_key = os.environ.get("HYPERBOLIC_API_KEY")

            response = requests.post(
                hyperbolic_api_url,
                json={
                    "messages": [
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ],
                    "model": "meta-llama/Llama-3.3-70B-Instruct",
                    "max_tokens": 1024,
                    "temperature": 0.7,
                    "top_p": 0.9
                },
                headers={
                    'Content-Type': 'application/json',
                    'Authorization': f'Bearer {hyperbolic_api_key}'
                }
            )

            response.raise_for_status()
            message = response.json()['choices'][0]['message']['content']
            
            return {
                "message": message,
                "similarity_metrics": {
                    "common_interests": common_interests,
                    "common_interests_count": len(common_interests),
                    "visual_similarity": visual_similarity if include_visual else None
                }
            }

        except Exception as e:
            print(f"Error generating message: {e}")
            return {
                "message": f"{profile2['name'] if profile2 else 'You two'} seem to have a lot in common. You're off to a great start!",
                "similarity_metrics": {
                    "common_interests": [],
                    "common_interests_count": 0,
                    "visual_similarity": None
                }
            }

    
    async def search_similar(
        self,
        query_embedding: List[float],
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        embedding_type: Optional[str] = None,
        data_type: Optional[str] = None,
        limit: int = 10,
        similarity_threshold: float = 0.7
    ) -> List[Dict[str, Any]]:
        """Search for similar items using cosine similarity"""
        try:
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
            if data_type:
                query = query.eq('data_type', data_type)
            
            result = query.execute()
            return result.data
        
        except Exception as e:
            raise Exception(f"Failed to search similar items: {str(e)}")

    async def find_similar_users(
        self,
        user_id: str,
        embedding_type: Optional[str] = None,
        data_type: Optional[str] = None,
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
                    'data_type_filter': data_type,
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
        embedding_type: Optional[str] = None,
        data_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Compare two users based on their embeddings"""
        try:
            result = self.supabase.rpc(
                'compare_users',
                {
                    'user_id_1': user_id_1,
                    'user_id_2': user_id_2,
                    'embedding_type_filter': embedding_type,
                    'data_type_filter': data_type
                }
            ).execute()
            
            return result.data
        
        except Exception as e:
            raise Exception(f"Failed to compare users: {str(e)}")
        
__all__ = ['EmbeddingManager']