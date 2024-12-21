from typing import Dict, Any, List, Optional
from datetime import datetime
from supabase import create_client, Client
import os

class AttributeManager:
    def __init__(self):
        url = os.environ.get("SUPABASE_URL")
        key = os.environ.get("SUPABASE_KEY")
        if not url or not key:
            raise ValueError("Supabase credentials not found in environment variables")
        
        self.supabase: Client = create_client(url, key)
    
    async def set_attribute(
        self,
        user_id: str,
        agent_id: str,
        key: str,
        value: Any
    ) -> Dict[str, Any]:
        """Set a key-value attribute for a user"""
        try:
            attribute_data = {
                "user_id": user_id,
                "agent_id": agent_id,
                "key": key,
                "value": value,
                "updated_at": datetime.utcnow().isoformat()
            }
            
            # Upsert the attribute (insert or update if exists)
            result = self.supabase.table("user_attributes").upsert(
                attribute_data,
                on_conflict="user_id,agent_id,key"
            ).execute()
            
            return result.data[0]
        
        except Exception as e:
            raise Exception(f"Failed to set attribute: {str(e)}")
    
    async def get_attribute(
        self,
        user_id: str,
        agent_id: str,
        key: str
    ) -> Optional[Dict[str, Any]]:
        """Get a specific attribute for a user"""
        try:
            result = self.supabase.table("user_attributes").select("*").filter(
                "user_id", "eq", user_id
            ).filter(
                "agent_id", "eq", agent_id
            ).filter(
                "key", "eq", key
            ).execute()
            
            return result.data[0] if result.data else None
        
        except Exception as e:
            raise Exception(f"Failed to get attribute: {str(e)}")
    
    async def get_all_attributes(
        self,
        user_id: str,
        agent_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get all attributes for a user, optionally filtered by agent_id"""
        try:
            query = self.supabase.table("user_attributes").select("*").filter(
                "user_id", "eq", user_id
            )
            
            if agent_id:
                query = query.filter("agent_id", "eq", agent_id)
            
            result = query.execute()
            return result.data
        
        except Exception as e:
            raise Exception(f"Failed to get attributes: {str(e)}")
    
    async def delete_attribute(
        self,
        user_id: str,
        agent_id: str,
        key: str
    ) -> bool:
        """Delete a specific attribute"""
        try:
            result = self.supabase.table("user_attributes").delete().filter(
                "user_id", "eq", user_id
            ).filter(
                "agent_id", "eq", agent_id
            ).filter(
                "key", "eq", key
            ).execute()
            
            return bool(result.data)
        
        except Exception as e:
            raise Exception(f"Failed to delete attribute: {str(e)}") 