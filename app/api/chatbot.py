import logging
from fastapi import APIRouter, HTTPException
from app.models.chat import (
    ChatMessage, ChatResponse, MessageType, AgentDetails,
    AgentCreationState
)
from app.models.chat import generate_text_response, generate_image
from typing import Optional

router = APIRouter()
logger = logging.getLogger(__name__)

async def analyze_user_prompt(prompt: str, is_regeneration: bool = False) -> AgentDetails:
    """Analyze user prompt to extract agent details"""
    context = "Generate a DIFFERENT agent profile than before. Be more creative and unique." if is_regeneration else ""
    
    analysis_prompt = f"""{context}
Create a memecoin-style AI matching agent based on: "{prompt}"

Return ONLY a JSON object with these fields:
{{
    "name": "memecoin-style name (like DOGE, PEPE)",
    "symbol": "4-5 letter ticker symbol",
    "description": "engaging description under 20 words",
    "category": "VIBE/LOOK/LIFESTYLE",
    "theme": "animal/character theme for the logo"
}}

Requirements:
1. name: Create a catchy memecoin-style name (playful, not explicit)
2. symbol: Create a matching ticker symbol (like DOGE, PEPE, SHIB)
3. description: Short, engaging description
4. category: ONE of VIBE/LOOK/LIFESTYLE
5. theme: Specify an animal/character for the logo (e.g., "shiba inu dog", "pepe frog")

Example for "I want to meet gym enthusiasts":
{{
    "name": "GymApe",
    "symbol": "GAPE",
    "description": "Connecting fitness fanatics who lift together and grow together",
    "category": "LIFESTYLE",
    "theme": "strong gorilla in gym attire"
}}"""
    
    try:
        logger.info(f"Analyzing prompt: {prompt}")
        response = await generate_text_response(analysis_prompt)
        cleaned_response = clean_json_response(response)
        
        try:
            import json
            details = json.loads(cleaned_response)
            validate_agent_details(details)
            
            agent_details = AgentDetails(
                name=details["name"],
                symbol=details["symbol"],
                description=details["description"],
                category=details["category"],
                user_prompt=prompt,
                creation_state=AgentCreationState.AWAITING_CONFIRMATION
            )
            
            # Generate memecoin-style logo
            image_url = await generate_agent_image(agent_details, details["theme"])
            if image_url:
                agent_details.image_url = image_url
            
            return agent_details
            
        except Exception as e:
            logger.error(f"Error parsing agent details: {str(e)}")
            raise ValueError("Could not create agent from response")
            
    except Exception as e:
        logger.error(f"Error in agent creation: {str(e)}")
        raise HTTPException(status_code=500, detail="Could not create agent. Please try again.")

async def generate_agent_image(agent_details: AgentDetails, theme: str) -> Optional[str]:
    """Generate a memecoin-style logo for the agent"""
    try:
        base_prompt = f"""Create a memecoin-style logo featuring a {theme}.
        Style: Modern crypto/memecoin logo design
        Must include:
        - Cute/fun {theme} as main element
        - Clean, minimal design
        - Vibrant colors
        - Circular coin/token style
        - NO text or symbols
        Make it: Professional but playful, like popular memecoins
        Colors: Rich, eye-catching palette
        Mood: Fun, engaging, memorable
        Context: {agent_details.description}"""
        
        logger.info(f"Generating image with prompt: {base_prompt}")
        image_response = await generate_image(base_prompt)
        
        if not image_response or "images" not in image_response:
            logger.error("Invalid image response")
            return None
            
        image_url = image_response.get("images", [{}])[0].get("image")
        return image_url
        
    except Exception as e:
        logger.error(f"Error generating image: {str(e)}")
        return None

async def handle_confirmation(message: ChatMessage) -> ChatResponse:
    """Generate dynamic confirmation messages based on context"""
    confirmation_prompt = f"""Generate a confirmation message for this AI agent:
    Name: {message.agent_details.name}
    Symbol: {message.agent_details.symbol}
    Description: {message.agent_details.description}
    
    Requirements:
    1. Keep it brief and clear
    2. Ask for simple yes/no confirmation
    3. No small talk or unnecessary text"""
    
    confirmation_text = await generate_text_response(confirmation_prompt)
    return ChatResponse(
        text=confirmation_text,
        image_encoding=message.agent_details.image_url,
        message_type=MessageType.AGENT_CONFIRMATION,
        agent_details=message.agent_details
    )

async def handle_creation_flow(message: ChatMessage) -> ChatResponse:
    """Handle the agent creation flow based on state"""
    try:
        state = message.agent_details.creation_state if message.agent_details else AgentCreationState.AWAITING_PROMPT
        content_lower = message.content.lower()

        # Handle initial prompt
        if state == AgentCreationState.AWAITING_PROMPT:
            agent_details = await analyze_user_prompt(message.content)
            return await handle_confirmation(ChatMessage(
                content=message.content,
                message_type=MessageType.AGENT_CONFIRMATION,
                agent_details=agent_details
            ))

        # Handle truth index setting
        if state == AgentCreationState.SETTING_TRUTH_INDEX:
            try:
                truth_index = int(content_lower)
                if 1 <= truth_index <= 100:
                    message.agent_details.truth_index = truth_index
                    message.agent_details.creation_state = AgentCreationState.SETTING_FREQUENCY
                    
                    frequency_prompt = """Generate a brief message asking for interaction frequency:
                    - Options: rarely, sometimes, often
                    - Keep it simple and clear
                    - One line question"""
                    
                    response_text = await generate_text_response(frequency_prompt)
                    return ChatResponse(
                        text=response_text,
                        message_type=MessageType.AGENT_FREQUENCY_UPDATE,
                        agent_details=message.agent_details
                    )
            except ValueError:
                error_prompt = "Generate a message asking for a valid number between 1-100"
                error_text = await generate_text_response(error_prompt)
                return ChatResponse(
                    text=error_text,
                    message_type=MessageType.AGENT_TRUTH_INDEX_UPDATE,
                    agent_details=message.agent_details
                )

        # Handle frequency setting
        if state == AgentCreationState.SETTING_FREQUENCY:
            valid_responses = {
                "1": "rarely", "rarely": "rarely",
                "2": "sometimes", "sometimes": "sometimes",
                "3": "often", "often": "often"
            }
            
            if content_lower in valid_responses:
                message.agent_details.interaction_frequency = valid_responses[content_lower]
                message.agent_details.creation_state = AgentCreationState.COMPLETED
                
                completion_prompt = f"""Generate a completion message for the AI agent:
                Name: {message.agent_details.name}
                Symbol: {message.agent_details.symbol}
                Description: {message.agent_details.description}
                
                Requirements:
                1. Confirm successful creation
                2. Keep it brief and professional
                3. No additional questions or options"""
                
                completion_text = await generate_text_response(completion_prompt)
                return ChatResponse(
                    text=completion_text,
                    message_type=MessageType.AGENT_COMPLETE,
                    agent_details=message.agent_details
                )

        # Handle confirmation responses
        if state == AgentCreationState.AWAITING_CONFIRMATION:
            if content_lower in ['yes', 'y', 'sure', 'ok', 'okay']:
                message.agent_details.creation_state = AgentCreationState.SETTING_TRUTH_INDEX
                truth_prompt = "Generate a message asking for Truth Index (1-100)"
                truth_text = await generate_text_response(truth_prompt)
                return ChatResponse(
                    text=truth_text,
                    message_type=MessageType.AGENT_TRUTH_INDEX_UPDATE,
                    agent_details=message.agent_details
                )
            elif content_lower in ['no', 'n', 'nope']:
                return ChatResponse(
                    text="Let me create a different agent. Please describe what you're looking for again.",
                    message_type=MessageType.TEXT,
                    agent_details=AgentDetails(creation_state=AgentCreationState.AWAITING_PROMPT)
                )

        # Generate contextual response for other states
        context_prompt = f"""Generate a focused response for AI agent creation.
        Current state: {state}
        User message: {message.content}
        
        Requirements:
        1. Stay strictly within agent creation context
        2. Clear, actionable response
        3. Move conversation forward
        4. No small talk or chitchat"""
        
        response_text = await generate_text_response(context_prompt)
        return ChatResponse(
            text=response_text,
            message_type=MessageType.TEXT,
            agent_details=message.agent_details
        )

    except Exception as e:
        logger.error(f"Error in creation flow: {str(e)}")
        return ChatResponse(
            text="Something went wrong. Please describe what kind of agent you'd like to create.",
            message_type=MessageType.TEXT,
            agent_details=AgentDetails(creation_state=AgentCreationState.AWAITING_PROMPT)
        )

@router.post("/chat", response_model=ChatResponse)
async def chat(message: ChatMessage) -> ChatResponse:
    """Process chat messages and return responses"""
    try:
        content_lower = message.content.lower()
        logger.debug(f"Received message: {message.dict()}")

        # Check if starting new conversation
        if content_lower in ["hi", "hello", "start", "hey", "new", "begin"]:
            start_prompt = """Generate a welcoming message asking user to describe their ideal match.
            Requirements:
            1. Brief and focused on agent creation
            2. Ask for match preferences
            3. No examples or additional options"""
            
            welcome_text = await generate_text_response(start_prompt)
            return ChatResponse(
                text=welcome_text,
                message_type=MessageType.TEXT,
                agent_details=AgentDetails(creation_state=AgentCreationState.AWAITING_PROMPT)
            )

        # Handle existing conversation flow
        return await handle_creation_flow(message)

    except Exception as e:
        logger.error(f"Error in chat endpoint: {str(e)}")
        error_prompt = "Generate an error message asking user to try again"
        error_text = await generate_text_response(error_prompt)
        return ChatResponse(
            text=error_text,
            message_type=MessageType.TEXT,
            agent_details=AgentDetails(creation_state=AgentCreationState.AWAITING_PROMPT)
        )

def clean_json_response(response: str) -> str:
    """Clean and extract JSON from response"""
    cleaned = response.strip()
    if "```" in cleaned:
        parts = cleaned.split("```")
        for part in parts:
            if "{" in part and "}" in part:
                cleaned = part.strip()
                break
    if cleaned.startswith(("json", "JSON")):
        cleaned = cleaned[4:].strip()
    return cleaned

def validate_agent_details(details: dict) -> None:
    """Validate required fields and formats"""
    required_fields = ['name', 'symbol', 'description', 'category', 'theme']
    if not all(field in details for field in required_fields):
        missing = [f for f in required_fields if f not in details]
        raise ValueError(f"Missing required fields: {', '.join(missing)}")
    
    if details["category"] not in ["VIBE", "LOOK", "LIFESTYLE"]:
        raise ValueError("Invalid category")
    
    if len(details["description"]) > 200:
        raise ValueError("Description too long")