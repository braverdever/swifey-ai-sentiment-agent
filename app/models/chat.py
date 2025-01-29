import logging
from enum import Enum
from pydantic import BaseModel, Field
from typing import Optional, Dict
import httpx
from app.config.settings import TEXT_LLM_CONFIG, IMAGE_LLM_CONFIG
from fastapi import HTTPException
import asyncio

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a professional AI matchmaking assistant that creates personalized agents with memecoin aesthetics.
Your responses should be natural, contextual, and engaging. Always maintain the conversation flow and context.

Core Abilities:
1. Create unique memecoin-style matching agents (like DOGE, PEPE)
2. Generate natural, contextual responses
3. Remember and reference previous interactions
4. Guide users through the creation process
5. Handle modifications and changes gracefully

When users want to:
- Modify: Help them change specific aspects while maintaining other details
- Start over: Acknowledge their request and begin fresh
- Change details: Show flexibility and understanding

Always maintain context and provide helpful, natural responses."""

class MessageType(str, Enum):
    TEXT = "text"
    AGENT_CREATION = "agent_creation"
    AGENT_CONFIRMATION = "agent_confirmation"
    AGENT_MODIFY = "agent_modify"
    AGENT_COMPLETE = "agent_complete"

class AgentCreationState(str, Enum):
    INITIAL = "initial"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    SETTING_TRUTH_INDEX = "setting_truth_index"
    SETTING_FREQUENCY = "setting_frequency"
    MODIFYING = "modifying"
    COMPLETED = "completed"

class AgentDetails(BaseModel):
    name: str
    symbol: str
    description: str
    question: str
    category: str
    image_url: Optional[str] = None
    truth_index: int
    interaction_frequency: int
    creation_state: AgentCreationState = AgentCreationState.INITIAL
    context: Dict = Field(default_factory=dict)

    class Config:
        json_encoders = {
            'AgentCreationState': lambda v: v.value
        }
        
    def dict(self, *args, **kwargs):
        d = super().dict(*args, **kwargs)
        d['creation_state'] = self.creation_state.value
        return d

class ChatMessage(BaseModel):
    content: str
    message_type: MessageType = MessageType.TEXT
    agent_details: Optional[AgentDetails] = None

class ChatResponse(BaseModel):
    text: Optional[str] = None
    name: Optional[str] = None
    symbol: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    question: Optional[str] = None
    truth_index: Optional[int] = None
    interaction_frequency: Optional[int] = None
    image_encoding: Optional[str] = None
    message_type: MessageType

async def generate_text_response(content: str, context: Optional[Dict] = None) -> str:
    """Generate contextual response using AI"""
    try:
        messages = [{"role": "user", "content": content}]
        
        if context:
            messages.insert(0, {"role": "assistant", "content": f"Previous context: {str(context)}"})
        
        url = "https://api.hyperbolic.xyz/v1/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": "Bearer " + TEXT_LLM_CONFIG["api_key"]
        }
        data = {
            "messages": messages,
            "model": "meta-llama/Llama-3.3-70B-Instruct",
            "max_tokens": 512,
            "temperature": 0.1,
            "top_p": 0.9
        }
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, headers=headers, json=data)
            
            if response.status_code != 200:
                logger.error(f"API Error: {response.status_code} - {response.text}")
                return ""
                
            data = response.json()
            if not data or "choices" not in data or not data["choices"]:
                logger.error(f"Invalid API response format: {data}")
                return ""
                
            return data["choices"][0]["message"]["content"]
            
    except Exception as e:
        logger.error(f"Error generating response: {str(e)}")
        return ""  # Return empty string instead of raising exception

async def generate_image(prompt: str) -> dict:
    """Generate themed agent image"""
    try:
        prompt = f"""Create a professional profile picture for a matching agent.
        Theme: {prompt}
        Style: Modern memecoin logo design
        Requirements: Professional, clean, minimal design, no text"""
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                IMAGE_LLM_CONFIG["api_url"],
                headers={
                    "Authorization": f"Bearer {IMAGE_LLM_CONFIG['api_key']}",
                    "Content-Type": "application/json"
                },
                json={
                    "model_name": "FLUX.1-dev",
                    "prompt": prompt,
                    "steps": 30,
                    "cfg_scale": 5,
                    "enable_refiner": False,
                    "height": 1024,
                    "width": 1024,
                    "backend": "auto"
                }
            )
            
            response.raise_for_status()
            return response.json()
                
    except Exception as e:
        logger.error(f"Error generating image: {str(e)}")
        return {"data": [{"url": None}]}
