from enum import Enum
from pydantic import BaseModel, Field
from typing import Optional, List, Union, Dict
import httpx
from typing import Optional
from app.config.settings import TEXT_LLM_CONFIG, IMAGE_LLM_CONFIG
from fastapi import HTTPException
import logging
import asyncio

logger = logging.getLogger(__name__)

class MessageType(str, Enum):
    TEXT = "text"
    IMAGE = "image"
    AGENT_CREATION = "agent_creation"
    AGENT_DETAILS = "agent_details"
    AGENT_CONFIRMATION = "agent_confirmation"
    AGENT_MODIFY = "agent_modify"
    AGENT_NAME_UPDATE = "agent_name_update"
    AGENT_SYMBOL_UPDATE = "agent_symbol_update"
    AGENT_DESCRIPTION_UPDATE = "agent_description_update"
    AGENT_IMAGE_UPDATE = "agent_image_update"
    AGENT_TRUTH_INDEX_UPDATE = "agent_truth_index_update"
    AGENT_FREQUENCY_UPDATE = "agent_frequency_update"
    AGENT_COMPLETE = "agent_complete"

class AgentCreationState(str, Enum):
    INITIAL = "initial"
    AWAITING_PROMPT = "awaiting_prompt"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    MODIFYING_DETAILS = "modifying_details"
    MODIFYING_NAME = "modifying_name"
    MODIFYING_SYMBOL = "modifying_symbol"
    MODIFYING_DESCRIPTION = "modifying_description"
    MODIFYING_IMAGE = "modifying_image"
    SETTING_TRUTH_INDEX = "setting_truth_index"
    SETTING_FREQUENCY = "setting_frequency"
    CONFIRMING_NAME = "confirming_name"
    CONFIRMING_SYMBOL = "confirming_symbol"
    CONFIRMING_DESCRIPTION = "confirming_description"
    CONFIRMING_IMAGE = "confirming_image"
    COMPLETED = "completed"

class AgentDetails(BaseModel):
    name: Optional[str] = Field(None, description="Name of the AI agent")
    symbol: Optional[str] = Field(None, description="Symbol/ticker for the agent (like SOLMATE)")
    description: Optional[str] = Field(None, description="Catchy description under 20 words")
    image_url: Optional[str] = Field(None, description="Generated image URL for the agent")
    user_prompt: Optional[str] = Field(None, description="Original user prompt that created this agent")
    category: Optional[str] = Field(None, description="Main category of the agent (Vibe/Look/Lifestyle)")
    truth_index: Optional[int] = Field(None, description="Truth index for truth bomb generation (1-100)")
    interaction_frequency: Optional[str] = Field(None, description="How often truth bombs should appear")
    creation_state: AgentCreationState = Field(default=AgentCreationState.INITIAL, description="Current state of agent creation")
    previous_state: Optional[AgentCreationState] = Field(None, description="Previous state for handling back operations")

class ChatMessage(BaseModel):
    content: str = Field(..., description="The message content")
    message_type: MessageType = Field(default=MessageType.TEXT, description="Type of message to generate")
    image_prompt: Optional[str] = Field(None, description="Specific prompt for image generation when type is image")
    agent_details: Optional[AgentDetails] = Field(None, description="Agent details when creating a new agent")

class ChatResponse(BaseModel):
    text: Optional[str] = Field(None, description="Text response from the model")
    image_encoding: Optional[str] = Field(None, description="Generated image URL if image was requested")
    message_type: MessageType = Field(default=MessageType.TEXT, description="Type of message to generate")
    agent_details: Optional[AgentDetails] = Field(None, description="Agent details in the response")

async def generate_text_response(content: str) -> str:
    """Generate text response with shorter timeout and retries"""
    max_retries = 2
    for attempt in range(max_retries):
        try:
            timeout = httpx.Timeout(15.0, connect=5.0)  # Shorter timeout
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    TEXT_LLM_CONFIG["api_url"],
                    headers={
                        "Authorization": f"Bearer {TEXT_LLM_CONFIG['api_key']}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "messages": [{"role": "user", "content": content}],
                        "model": "meta-llama/Llama-3.3-70B-Instruct",
                        "max_tokens": 512,
                        "temperature": 0.7,
                        "top_p": 0.9
                    }
                )
                
                response.raise_for_status()
                result = response.json()
                return result["choices"][0]["message"]["content"]
                
        except (httpx.TimeoutException, httpx.ConnectError) as e:
            if attempt == max_retries - 1:
                raise HTTPException(status_code=504, detail="Service temporarily unavailable. Please try again.")
            await asyncio.sleep(1)
            
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

async def generate_image(prompt: str, max_retries: int = 3, retry_delay: float = 1.0) -> Optional[Dict]:
    """Generate an image using the Hyperbolic API with retry logic"""
    for attempt in range(max_retries):
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                enhanced_prompt = f"""Create a professional profile picture.
                Theme: {prompt}
                Style requirements:
                - Professional and appropriate appearance
                - Modern digital art style
                - Suitable for social networking
                - Clean and minimal design
                - Do not include any text in the image
                - Appropriate for all audiences
                """

                request_payload = {
                    "model_name": "FLUX.1-dev",                
                    "prompt": enhanced_prompt,
                    "steps": 30,
                    "cfg_scale": 7.0,
                    "enable_refiner": False,
                    "height": 1024,
                    "width": 1024,
                    "backend": "auto"
                }
                
                response = await client.post(
                    IMAGE_LLM_CONFIG["api_url"],
                    headers={
                        "Authorization": f"Bearer {IMAGE_LLM_CONFIG['api_key']}",
                        "Content-Type": "application/json"
                    },
                    json=request_payload,
                )
                
                if response.status_code == 429:  # Too Many Requests
                    logger.warning(f"Rate limit hit, attempt {attempt + 1}/{max_retries}")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(retry_delay * (attempt + 1))  # Exponential backoff
                        continue
                    else:
                        logger.error("Rate limit persisted, proceeding without image")
                        return None
                
                response.raise_for_status()
                result = response.json()
                
                if result and "images" in result:
                    image_data = result["images"][0].get("image")
                    if image_data:
                        return {"images": [{"image": f"data:image/png;base64,{image_data}"}]}
                
                return None
                
        except Exception as e:
            logger.error(f"Image generation error on attempt {attempt + 1}: {str(e)}")
            if attempt < max_retries - 1:
                await asyncio.sleep(retry_delay * (attempt + 1))
            else:
                logger.error("All retry attempts failed")
                return None
    
    return None