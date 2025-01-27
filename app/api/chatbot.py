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
                theme=details["theme"],
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

async def modify_name(message: ChatMessage) -> ChatResponse:
    """Handle name modification"""
    new_name = message.content.strip()
    
    if len(new_name) < 3 or len(new_name) > 50:
        error_prompt = "Generate message asking for valid name length (3-50 chars)"
        error_text = await generate_text_response(error_prompt)
        return ChatResponse(
            text=error_text,
            message_type=MessageType.AGENT_NAME_UPDATE,
            agent_details=message.agent_details
        )
    
    message.agent_details.name = new_name
    return await show_updated_agent(message.agent_details)

async def modify_description(message: ChatMessage) -> ChatResponse:
    """Handle description modification"""
    new_description = message.content.strip()
    
    if len(new_description) > 200:
        error_prompt = "Generate message asking for shorter description"
        error_text = await generate_text_response(error_prompt)
        return ChatResponse(
            text=error_text,
            message_type=MessageType.AGENT_DESCRIPTION_UPDATE,
            agent_details=message.agent_details
        )
    
    message.agent_details.description = new_description
    return await show_updated_agent(message.agent_details)

async def modify_theme(message: ChatMessage) -> ChatResponse:
    """Handle theme/image modification"""
    new_theme = message.content.strip()
    
    # Generate new image with updated theme
    image_url = await generate_agent_image(message.agent_details, new_theme)
    if image_url:
        message.agent_details.image_url = image_url
        message.agent_details.theme = new_theme
        
        confirm_prompt = """Generate message showing new image and asking for confirmation.
        Keep it brief, yes/no question."""
        
        confirm_text = await generate_text_response(confirm_prompt)
        return ChatResponse(
            text=confirm_text,
            image_encoding=image_url,
            message_type=MessageType.AGENT_IMAGE_UPDATE,
            agent_details=message.agent_details
        )
    
    error_prompt = "Generate message about image generation failure, ask to try again"
    error_text = await generate_text_response(error_prompt)
    return ChatResponse(
        text=error_text,
        message_type=MessageType.AGENT_MODIFY,
        agent_details=message.agent_details
    )

async def modify_symbol(message: ChatMessage) -> ChatResponse:
    """Handle symbol modification"""
    new_symbol = message.content.strip().upper()
    
    if len(new_symbol) < 4 or len(new_symbol) > 5:
        error_prompt = "Generate message asking for valid symbol length (4-5 chars)"
        error_text = await generate_text_response(error_prompt)
        return ChatResponse(
            text=error_text,
            message_type=MessageType.AGENT_SYMBOL_UPDATE,
            agent_details=message.agent_details
        )
    
    message.agent_details.symbol = new_symbol
    return await show_updated_agent(message.agent_details)

async def show_updated_agent(agent_details: AgentDetails) -> ChatResponse:
    """Show updated agent details and ask for further modifications"""
    update_prompt = f"""Generate message showing updated agent details:
    Name: {agent_details.name}
    Symbol: {agent_details.symbol}
    Description: {agent_details.description}
    
    Ask if they want to:
    1. Make more changes
    2. Finish updating
    
    Keep it brief and clear."""
    
    update_text = await generate_text_response(update_prompt)
    return ChatResponse(
        text=update_text,
        image_encoding=agent_details.image_url,
        message_type=MessageType.AGENT_CONFIRMATION,
        agent_details=agent_details
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

        # Handle modifications
        if state in [AgentCreationState.MODIFYING_DETAILS, 
                    AgentCreationState.MODIFYING_NAME,
                    AgentCreationState.MODIFYING_DESCRIPTION,
                    AgentCreationState.MODIFYING_THEME,
                    AgentCreationState.MODIFYING_SYMBOL]:
            return await handle_modification(message)

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

async def handle_modification(message: ChatMessage) -> ChatResponse:
    """Handle modifications to agent details"""
    content_lower = message.content.lower()
    
    # If first time entering modification mode, show options
    if message.agent_details.creation_state == AgentCreationState.COMPLETED:
        edit_prompt = f"""Generate modification options for the AI agent:
        Current Details:
        - Name: {message.agent_details.name}
        - Symbol: {message.agent_details.symbol}
        - Description: {message.agent_details.description}
        - Theme: {message.agent_details.theme}
        - Truth Index: {message.agent_details.truth_index}
        - Frequency: {message.agent_details.interaction_frequency}

        List available modifications and ask what they'd like to change.
        Format as numbered list (1-6).
        Keep it brief and clear."""
        
        options_text = await generate_text_response(edit_prompt)
        message.agent_details.creation_state = AgentCreationState.MODIFYING_DETAILS
        return ChatResponse(
            text=options_text,
            message_type=MessageType.AGENT_MODIFY,
            agent_details=message.agent_details
        )

    # Handle specific modification requests
    modification_map = {
        "1": AgentCreationState.MODIFYING_NAME,
        "name": AgentCreationState.MODIFYING_NAME,
        "2": AgentCreationState.MODIFYING_DESCRIPTION,
        "description": AgentCreationState.MODIFYING_DESCRIPTION,
        "3": AgentCreationState.MODIFYING_THEME,
        "image": AgentCreationState.MODIFYING_THEME,
        "theme": AgentCreationState.MODIFYING_THEME,
        "4": AgentCreationState.SETTING_TRUTH_INDEX,
        "truth": AgentCreationState.SETTING_TRUTH_INDEX,
        "5": AgentCreationState.SETTING_FREQUENCY,
        "frequency": AgentCreationState.SETTING_FREQUENCY,
        "6": AgentCreationState.MODIFYING_SYMBOL,
        "symbol": AgentCreationState.MODIFYING_SYMBOL,
        "done": AgentCreationState.COMPLETED,
        "finish": AgentCreationState.COMPLETED,
        "complete": AgentCreationState.COMPLETED
    }

    if content_lower in modification_map:
        new_state = modification_map[content_lower]
        
        if new_state == AgentCreationState.COMPLETED:
            completion_prompt = f"""Generate a completion message showing final agent details:
            Name: {message.agent_details.name}
            Symbol: {message.agent_details.symbol}
            Description: {message.agent_details.description}
            Theme: {message.agent_details.theme}
            Truth Index: {message.agent_details.truth_index}
            Frequency: {message.agent_details.interaction_frequency}
            
            Keep it brief and professional."""
            
            completion_text = await generate_text_response(completion_prompt)
            message.agent_details.creation_state = AgentCreationState.COMPLETED
            return ChatResponse(
                text=completion_text,
                image_encoding=message.agent_details.image_url,
                message_type=MessageType.AGENT_COMPLETE,
                agent_details=message.agent_details
            )
        
        message.agent_details.creation_state = new_state
        return await generate_modification_prompt(message.agent_details, new_state)

    # Handle actual modifications based on state
    if message.agent_details.creation_state == AgentCreationState.MODIFYING_NAME:
        return await modify_name(message)
    elif message.agent_details.creation_state == AgentCreationState.MODIFYING_DESCRIPTION:
        return await modify_description(message)
    elif message.agent_details.creation_state == AgentCreationState.MODIFYING_THEME:
        return await modify_theme(message)
    elif message.agent_details.creation_state == AgentCreationState.MODIFYING_SYMBOL:
        return await modify_symbol(message)
    elif message.agent_details.creation_state == AgentCreationState.SETTING_TRUTH_INDEX:
        return await handle_truth_index(message.content, message.agent_details)
    elif message.agent_details.creation_state == AgentCreationState.SETTING_FREQUENCY:
        return await handle_frequency(message.content, message.agent_details)
    
    # If we don't recognize the input, ask again
    retry_prompt = """Generate a message asking user to select a valid modification option.
    Keep it brief and clear. List options 1-6."""
    
    retry_text = await generate_text_response(retry_prompt)
    return ChatResponse(
        text=retry_text,
        message_type=MessageType.AGENT_MODIFY,
        agent_details=message.agent_details
    )

async def handle_frequency(content: str, agent_details: AgentDetails) -> ChatResponse:
    """Handle frequency setting with validation"""
    content_lower = content.lower()
    valid_responses = {
        "1": "rarely", "rarely": "rarely",
        "2": "sometimes", "sometimes": "sometimes",
        "3": "often", "often": "often"
    }
    
    if content_lower in valid_responses:
        agent_details.interaction_frequency = valid_responses[content_lower]
        agent_details.creation_state = AgentCreationState.COMPLETED
        
        completion_prompt = f"""Generate confirmation with final agent settings:
        Name: {agent_details.name}
        Symbol: {agent_details.symbol}
        Description: {agent_details.description}
        Frequency: {agent_details.interaction_frequency}
        
        Keep it brief and clear."""
        
        completion_text = await generate_text_response(completion_prompt)
        return ChatResponse(
            text=completion_text,
            message_type=MessageType.AGENT_COMPLETE,
            agent_details=agent_details
        )
    
    error_prompt = "Generate message asking for valid frequency (rarely/sometimes/often)"
    error_text = await generate_text_response(error_prompt)
    return ChatResponse(
        text=error_text,
        message_type=MessageType.AGENT_FREQUENCY_UPDATE,
        agent_details=agent_details
    )

async def generate_modification_prompt(agent_details: AgentDetails, state: AgentCreationState) -> ChatResponse:
    """Generate appropriate prompt for the modification state"""
    prompts = {
        AgentCreationState.MODIFYING_NAME: "Please enter a new memecoin-style name for your agent (like DOGE, PEPE).",
        AgentCreationState.MODIFYING_DESCRIPTION: "Please enter a new description (keep it under 20 words).",
        AgentCreationState.MODIFYING_THEME: "Please suggest a new theme/character for your agent's image.",
        AgentCreationState.MODIFYING_SYMBOL: "Please enter a new 4-5 letter ticker symbol (like DOGE, SHIB).",
        AgentCreationState.SETTING_TRUTH_INDEX: "Please enter a Truth Index (1-100) for conversation depth.",
        AgentCreationState.SETTING_FREQUENCY: "How often should your agent interact? Choose: rarely, sometimes, or often."
    }
    
    return ChatResponse(
        text=prompts.get(state, "Please select what you'd like to modify."),
        message_type=MessageType.AGENT_MODIFY,
        agent_details=agent_details
    )

async def handle_truth_index(content: str, agent_details: AgentDetails) -> ChatResponse:
    """Handle truth index setting with validation"""
    try:
        truth_index = int(content)
        if 1 <= truth_index <= 100:
            agent_details.truth_index = truth_index
            agent_details.creation_state = AgentCreationState.SETTING_FREQUENCY
            return ChatResponse(
                text="How often should your agent interact? Choose:\n1. Rarely\n2. Sometimes\n3. Often\n\nType the number or word.",
                message_type=MessageType.AGENT_FREQUENCY_UPDATE,
                agent_details=agent_details
            )
    except ValueError:
        pass
    
    return ChatResponse(
        text="Please enter a valid number between 1 and 100 for the Truth Index.",
        message_type=MessageType.AGENT_TRUTH_INDEX_UPDATE,
        agent_details=agent_details
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

        # Handle "start over" requests
        if content_lower in ["start over", "restart", "new agent", "begin again"]:
            restart_prompt = "Generate message asking user to describe their ideal match"
            restart_text = await generate_text_response(restart_prompt)
            return ChatResponse(
                text=restart_text,
                message_type=MessageType.TEXT,
                agent_details=AgentDetails(creation_state=AgentCreationState.AWAITING_PROMPT)
            )

        # Handle view current agent
        if content_lower == "view":
            if not message.agent_details or not message.agent_details.name:
                no_agent_prompt = "Generate message saying no agent exists yet"
                no_agent_text = await generate_text_response(no_agent_prompt)
                return ChatResponse(
                    text=no_agent_text,
                    message_type=MessageType.TEXT,
                    agent_details=None
                )
            
            view_prompt = f"""Generate message showing current agent details:
            Name: {message.agent_details.name}
            Symbol: {message.agent_details.symbol}
            Description: {message.agent_details.description}
            Theme: {message.agent_details.theme}
            Truth Index: {message.agent_details.truth_index}
            Frequency: {message.agent_details.interaction_frequency}
            
            Ask if they want to modify anything."""
            
            view_text = await generate_text_response(view_prompt)
            return ChatResponse(
                text=view_text,
                image_encoding=message.agent_details.image_url,
                message_type=MessageType.AGENT_DETAILS,
                agent_details=message.agent_details
            )

        # Handle modification requests
        if content_lower in ["modify", "edit", "change", "update"]:
            if not message.agent_details or not message.agent_details.name:
                no_agent_prompt = "Generate message saying no agent exists to modify"
                no_agent_text = await generate_text_response(no_agent_prompt)
                return ChatResponse(
                    text=no_agent_text,
                    message_type=MessageType.TEXT,
                    agent_details=None
                )
            
            return await handle_modification(message)

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
    
    if len(details["symbol"]) < 4 or len(details["symbol"]) > 5:
        raise ValueError("Invalid symbol length")
    
    if len(details["name"]) < 3 or len(details["name"]) > 50:
        raise ValueError("Invalid name length")