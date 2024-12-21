from fastapi import APIRouter, HTTPException
from typing import Optional, Dict, Any, List
from models.attributes import AttributeManager
from pydantic import BaseModel

router = APIRouter()
attribute_manager = AttributeManager()

class AttributeValue(BaseModel):
    value: Any

@router.put("/attributes/{user_id}/{agent_id}/{key}")
async def set_attribute(
    user_id: str,
    agent_id: str,
    key: str,
    attribute: AttributeValue
):
    """Set a key-value attribute for a user"""
    try:
        result = await attribute_manager.set_attribute(
            user_id=user_id,
            agent_id=agent_id,
            key=key,
            value=attribute.value
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/attributes/{user_id}/{agent_id}/{key}")
async def get_attribute(
    user_id: str,
    agent_id: str,
    key: str
):
    """Get a specific attribute for a user"""
    try:
        result = await attribute_manager.get_attribute(
            user_id=user_id,
            agent_id=agent_id,
            key=key
        )
        if not result:
            raise HTTPException(status_code=404, detail="Attribute not found")
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/attributes/{user_id}")
async def get_all_attributes(
    user_id: str,
    agent_id: Optional[str] = None
):
    """Get all attributes for a user, optionally filtered by agent_id"""
    try:
        result = await attribute_manager.get_all_attributes(
            user_id=user_id,
            agent_id=agent_id
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/attributes/{user_id}/{agent_id}/{key}")
async def delete_attribute(
    user_id: str,
    agent_id: str,
    key: str
):
    """Delete a specific attribute"""
    try:
        result = await attribute_manager.delete_attribute(
            user_id=user_id,
            agent_id=agent_id,
            key=key
        )
        if not result:
            raise HTTPException(status_code=404, detail="Attribute not found")
        return {"message": "Attribute deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) 