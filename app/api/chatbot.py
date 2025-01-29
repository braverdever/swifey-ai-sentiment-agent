import logging
from fastapi import APIRouter, HTTPException
import json
from app.models.chat import (
    ChatMessage, ChatResponse, MessageType, AgentDetails,
    AgentCreationState, generate_text_response, generate_image
)

router = APIRouter()
logger = logging.getLogger(__name__)

async def analyze_user_prompt(prompt: str) -> AgentDetails:
    """Analyze user prompt to create agent details including AI-decided parameters"""
    analysis_prompt = f"""You are a creative AI matchmaking expert specializing in creating unique memecoin-style matching agents.

Given this user's description of desired connections: "{prompt}"

Create a completely unique, never-before-seen memecoin agent that captures the essence of their matching preferences.

Rules for creation:
1. Name: Create a clever, memorable name that:
   - Uses wordplay, puns, or creative combinations
   - Relates to dating/connections/relationships
   - Follows memecoin style (like DOGE, PEPE, but NEVER copy existing names)
   - Must be COMPLETELY UNIQUE each time

2. Symbol: Create a 4-5 letter ticker that:
   - Is catchy and memorable
   - Relates to the name
   - Uses creative abbreviations
   - Must be DIFFERENT each time

3. Description: Write an engaging, witty description that:
   - Captures the essence of the desired connections
   - Uses humor or clever wordplay
   - Stays under 20 words
   - Must be FRESH and UNIQUE each time

4. Category must be exactly one of:
   VIBE (personality/energy matching)
   LOOK (appearance/attraction matching)
   LIFESTYLE (habits/interests matching)

5. Theme: Choose ONE word that best represents the visual theme for the logo
   - Must be concrete, visualizable object/animal/symbol
   - Should relate to the agent's purpose
   - Must be DIFFERENT for each agent

6. Numbers:
   truth_index: 1-100 (how honest/direct the agent is) make sure it is random, so keep into consideration the user's prompt
   frequency: 1-100 (how often the agent appears) make sure it is random, so keep into consideration the user's prompt

Respond with ONLY a JSON object in this exact format:
{{
    "name": "<memecoin-style name like DOGE or PEPE>",
    "symbol": "<4-5 letter ticker>",
    "description": "<engaging description under 20 words>",
    "category": "<exactly one of: VIBE, LOOK, LIFESTYLE>",
    "theme": "<single word describing the logo theme>",
    "truth_index": <number between 1-100>,
    "frequency": <number between 1-100>"
}}

IMPORTANT: Each response must be COMPLETELY UNIQUE - never repeat previous names, symbols, or descriptions."""
    
    try:
        response = await generate_text_response(analysis_prompt)
        if not response:
            return None
            
        details = parse_json_response(response)
        if not details:
            return None
            
        # Validate specific fields
        if not isinstance(details.get("truth_index"), (int, float)):
            details["truth_index"] = 50
            
        if not isinstance(details.get("frequency"), (int, float)):
            details["frequency"] = "50"  # Default if invalid
            
        if details.get("category") not in ["VIBE", "LOOK", "LIFESTYLE"]:
            details["category"] = "VIBE"  # Default if invalid
        
        question = details.get("question", f"What makes you a perfect match for {details['name']}?")
        
        agent_details = AgentDetails(
            name=details["name"],
            symbol=details["symbol"],
            description=details["description"],
            category=details["category"],
            question=question,
            truth_index=int(details["truth_index"]),
            interaction_frequency=int(details["frequency"]),
            creation_state=AgentCreationState.COMPLETED
        )
        
        # Generate logo
        image_url = await generate_agent_image(agent_details, details["theme"])
        if image_url:
            agent_details.image_url = image_url
        
        return agent_details
            
    except Exception as e:
        logger.error(f"Error in agent creation: {str(e)}")
        return None

async def generate_agent_image(agent_details: AgentDetails, theme: str) -> str | None:
    """Generate a memecoin-style logo for the agent"""
    prompt = f"""Create a memecoin-style logo featuring a {theme}.
    Style: Modern crypto/memecoin logo design
    Must include:
    - Cute/fun {theme} as main element
    - Clean, minimal design
    - Vibrant colors
    - Circular coin/token style
    - NO text or symbols"""
    
    try:
        image_response = await generate_image(prompt)
        return image_response.get("images", [{}])[0].get("image") if image_response else None
    except Exception as e:
        logger.error(f"Error generating image: {str(e)}")
        return None

async def generate_agent_question(agent_details: AgentDetails) -> str:
    """Generate a themed question based on agent characteristics"""
    question_prompt = f"""Create a fun, engaging question for a memecoin-style AI matching agent with these details:
    Name: {agent_details.name}
    Description: {agent_details.description}
    Category: {agent_details.category}
    Question: {agent_details.question}

    Examples of good questions:
    SOLMATE -> "When SOL hits 420$, what's your move?"
    FRIENDZONE -> "Getting close but not getting past friendship?"
    UFO -> "alien encounter story _____"
    SOLOTRAVEL -> "where are you going next? What is your plan?"
    BONKMATE -> "what's your bonk worthy about you that others can't resist?"

    Create a NEW unique question that matches this agent's theme and personality.
    Respond with ONLY the question, no explanations."""

    try:
        question = await generate_text_response(question_prompt)
        return question.strip().strip('"').strip("'")
    except Exception as e:
        logger.error(f"Error generating question: {str(e)}")
        return f"What makes you a perfect match for {agent_details.name}?"

@router.post("/chat", response_model=ChatResponse)
async def chat(message: ChatMessage) -> ChatResponse:
    """Process chat messages and return responses"""
    try:
        content_lower = message.content.lower()

        # Handle initial greeting
        if content_lower in ["hi", "hello", "start", "hey", "new", "begin"]:
            return ChatResponse(
                text="Let us create an AI agent to find you meaningful matches. Who would like to connect with?",
                message_type=MessageType.TEXT,
                agent_details=None
            )

        # Create agent from user prompt
        agent_details = await analyze_user_prompt(message.content)
        
        if not agent_details:
            return ChatResponse(
                text="I couldn't create an agent right now. Please try describing the people you'd like to meet in a different way.",
                message_type=MessageType.TEXT,
                agent_details=None
            )

        # Generate themed question
        agent_question = await generate_agent_question(agent_details)
        agent_details.question = agent_question
        
        response_text = agent_details

        return ChatResponse(
            name=agent_details.name,
            symbol=agent_details.symbol,
            description=agent_details.description,
            category=agent_details.category,
            question=agent_details.question,
            truth_index=agent_details.truth_index,
            interaction_frequency=agent_details.interaction_frequency,
            image_encoding=agent_details.image_url,
            message_type=MessageType.AGENT_COMPLETE,
        )

    except Exception as e:
        logger.error(f"Error in chat endpoint: {str(e)}")

def parse_json_response(response: str) -> dict:
    """Clean and parse JSON response"""
    import json
    import re
    
    try:
        # Clean the response
        cleaned = response.strip()
        
        # Extract JSON object if wrapped in code blocks
        if "```" in cleaned:
            match = re.search(r'```(?:json)?(.*?)```', cleaned, re.DOTALL)
            if match:
                cleaned = match.group(1).strip()
        
        # Remove any "json" or "JSON" prefix
        cleaned = re.sub(r'^(?:json|JSON)\s*', '', cleaned)
        
        # Parse JSON
        details = json.loads(cleaned)
        
        # Check required fields with default values
        defaults = {
            "name": "AGENT",
            "symbol": "AGNT",
            "description": "A friendly matching agent",
            "category": "VIBE",
            "theme": "robot",
            "truth_index": 50,
            "frequency": "sometimes"
        }
        
        # Fill in any missing fields with defaults
        for field, default in defaults.items():
            if field not in details or not details[field]:
                details[field] = default
                logger.warning(f"Missing field '{field}' in response, using default: {default}")
        
        return details
        
    except Exception as e:
        logger.error(f"Error parsing JSON response: {str(e)}")
        return defaults