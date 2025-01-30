import logging
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
import json
import asyncio
from app.models.chat import (
    ChatMessage, ChatResponse, MessageType, AgentDetails,
    AgentCreationState, generate_text_response, generate_image
)
import httpx
from app.models.chat import TEXT_LLM_CONFIG
from typing import AsyncGenerator

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

6. Matching Criteria: Choose ONE key aspect that the agent should verify for compatibility:
   - Must be a specific, measurable trait or behavior (e.g. "Verify ownership of ≥0.25 BTC via a read-only wallet address linked to their profile")
   - Should directly relate to the user's expressed preferences
   - Must be something the agent can realistically assess
   - Must be DIFFERENT for each agent

7. Numbers:
   truth_index: 1-100 (how honest/direct the agent is) make sure it is random, so keep into consideration the user's prompt
   frequency: 1-30 (how often the agent should interact with the users chat when he chats with someone else) make sure it is random, so keep into consideration the user's prompt
   make sure the frequency is not too high, so the user doesn't get annoyed, as this should interact with the user when he chats with someone else, and it should be a fun interaction, make sure its ranging from 1-30

8. Looks: Choose a famous personality/celebrity that best represents the user's appearance
   - Must be a well-known celebrity/public figure (e.g. "Brad Pitt", "Zendaya")
   - Give based on the user's prompt, don't just use the above examples as they are
   - Should match the described physical attributes and style
   - Must be DIFFERENT for each user
   - Keep it respectful and appropriate

Respond with ONLY a JSON object in this exact format:
{{
    "name": "<memecoin-style name like DOGE or PEPE>",
    "symbol": "<4-5 letter ticker>",
    "description": "<engaging description under 20 words>",
    "category": "<exactly one of: VIBE, LOOK, LIFESTYLE>",
    "looks": "<looks of the user>",
    "theme": "<single word describing the logo theme>",
    "lifestyle": "<lifestyle of the user>",
    "truth_index": <number between 1-100>,
    "frequency": <number between 1-30>"
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
            looks=details["looks"],
            lifestyle=details["lifestyle"],
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

async def generate_thinking_process(prompt: str) -> AsyncGenerator[str, None]:
    thinking_prompt = f"""You are showing the thought process of creating a memecoin-style AI matching agent.
Given this user's description: "{prompt}"

Your role: You are an expert AI matchmaker who creates fun, memecoin-themed matching agents. Think out loud as you analyze the user's preferences and design the perfect agent.

Example format for this query : I want to connect with people who own 0.25 BTC
Okay, the user wants to create an app where users can make AI agents to match with others based on vibe checks, looks, and lifestyle. They need input methods for these agents. Also, they want an example agent card for someone looking to connect with people who own 0.25 BTC. Let me break this down.

Matching mechanics need to be solid here. We'll need wallet verification for the BTC holdings - could use read-only API access to major wallets. But beyond just wealth verification, we should look for shared crypto philosophy. Maybe add questions about preferred trading strategies, DeFi experience, or views on Bitcoin's future.

Now, the example agent card. The user's intent is to connect with people who own 0.25 BTC. So the agent's name should reflect crypto or Bitcoin. Vibe check needs a short question related to crypto values. Looks reference: pick a celebrity known for a tech or futuristic style. Maybe someone like Letitia Wright from Black Panther, she has a sleek, modern look. Lifestyle verification should check ownership of 0.25 BTC. They mentioned using a website digital footprint, so maybe a crypto wallet like Blockchain.com. Need to ensure the user has a verified wallet address with that amount.

Putting it all together into a card format. Name, vibe question, looks celeb, lifestyle verification. Keep it concise for mobile display. Make sure the elements align with the target user's interests in crypto. Need to verify ownership without compromising security, so maybe read-only access to wallet data. That should work.

DO NOT ASK USER ANY QUESTIONS, JUST SHOW WHAT YOU ARE THINKING, the above is just an example don't take it is reference and generate answers, just talk explain the user on how we are creating the agent and what we are doing and make sure its humanly, on how you are analyzing the user's preferences and creating the agent
"""
    try:        
        async with httpx.AsyncClient(timeout=1.0) as client:
            response = await client.post(
                "https://api.hyperbolic.xyz/v1/chat/completions",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {TEXT_LLM_CONFIG['api_key']}"
                },
                json={
                    "messages": [{"role": "user", "content": thinking_prompt}],
                    "model": "meta-llama/Meta-Llama-3.1-70B-Instruct",
                    "max_tokens": 512,
                    "temperature": 0.7,
                    "stream": True
                },
                timeout=30.0
            )
            
            buffer = ""
            last_yield_time = asyncio.get_event_loop().time()
            
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    try:
                        data = json.loads(line[6:])
                        if "choices" in data and data["choices"]:
                            content = data["choices"][0].get("delta", {}).get("content", "")
                            if content:
                                buffer += content
                                current_time = asyncio.get_event_loop().time()
                                
                                if buffer:
                                    yield f"data: {json.dumps({'text': buffer, 'message_type': MessageType.TEXT})}\n\n"
                                    buffer = ""
                                    last_yield_time = current_time
                                    await asyncio.sleep(0.1)  
                    except json.JSONDecodeError:
                        continue
            
            # Send any remaining buffer content
            if buffer:
                yield f"data: {json.dumps({'text': buffer, 'message_type': MessageType.TEXT})}\n\n"

    except Exception as e:
        logger.error(f"Error generating thinking process: {str(e)}")
        yield f"data: {json.dumps({'text': 'Error analyzing preferences. Please try again.', 'message_type': MessageType.TEXT})}\n\n"

@router.post("/chat")
async def chat(message: ChatMessage) -> StreamingResponse:
    """Process chat messages and return streaming responses"""
    try:
        content_lower = message.content.lower()

        # Handle initial greeting
        if content_lower in ["hi", "hello", "start", "hey", "new", "begin"]:
            return StreamingResponse(
                content=iter([f"data: {json.dumps({'text': 'Let us create an AI agent to find you meaningful matches. Who would like to connect with?', 'message_type': MessageType.TEXT})}\n\n"]),
                media_type="text/event-stream"
            )

        async def generate_response():
            # Immediate initial response
            yield f"data: {json.dumps({'text': 'Creating your perfect match...\n', 'message_type': MessageType.TEXT})}\n\n"
            await asyncio.sleep(0.2)
            
            # Stream thinking process
            async for thinking_message in generate_thinking_process(message.content):
                yield thinking_message
                await asyncio.sleep(0.1)  # Small delay for smooth streaming

            # Create agent from user prompt
            agent_details = await analyze_user_prompt(message.content)
            
            if not agent_details:
                yield f"data: {json.dumps({'text': 'I could not create an agent right now. Please try again with different preferences.', 'message_type': MessageType.TEXT})}\n\n"
                return

            yield f"data: {json.dumps({'text': ' Fizing your unique agent...\n', 'message_type': MessageType.TEXT})}\n\n"
            await asyncio.sleep(0.2)

            # Generate themed question
            agent_question = await generate_agent_question(agent_details)
            agent_details.question = agent_question

            # Send final response with agent details
            response_dict = {
                'name': agent_details.name,
                'symbol': agent_details.symbol,
                'description': agent_details.description,
                'looks': agent_details.looks,
                'lifestyle': agent_details.lifestyle,
                'category': agent_details.category,
                'question': agent_details.question,
                'truth_index': agent_details.truth_index,
                'interaction_frequency': agent_details.interaction_frequency,
                'image_encoding': agent_details.image_url,
                'message_type': MessageType.AGENT_COMPLETE
            }
            
            yield f"data: {json.dumps(response_dict)}\n\n"

        return StreamingResponse(
            content=generate_response(),
            media_type="text/event-stream"
        )

    except Exception as e:
        logger.error(f"Error in chat endpoint: {str(e)}")
        return StreamingResponse(
            content=iter([f"data: {json.dumps({'text': 'An error occurred. Please try again.', 'message_type': MessageType.TEXT})}\n\n"]),
            media_type="text/event-stream"
        )

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
            "looks": "personality",
            "lifestyle": "lifestyle",
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