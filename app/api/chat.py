from typing import Dict, Any, List
import uuid
import logging
from fastapi import APIRouter, HTTPException, Depends
from starlette.requests import Request

from ..core.agent_system import AgentSystem
from ..models import api as models

logger = logging.getLogger(__name__)

__version__ = "0.1.0"

router = APIRouter()

def get_agent_system() -> AgentSystem:
    """Dependency to get the agent system instance."""
    from ..config import settings
    
    try:
        agent = AgentSystem(
            redis_host=settings.REDIS_HOST,
            redis_port=settings.REDIS_PORT,
            cache_ttl=settings.REDIS_CACHE_TTL,
            flush_interval=settings.FLUSH_INTERVAL,
            buffer_size=settings.BUFFER_SIZE
        )
        return agent
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to initialize agent system: {str(e)}"
        )

# def format_chat_context(messages: List[models.Message], max_messages: int = 10) -> str:
#     """Format chat messages into context string."""
#     recent_messages = messages[-max_messages:]
#     return "\n".join([
#         f"{msg.sender}: {msg.content}"
#         for msg in recent_messages
#     ])

# @router.post("/chatting", response_model=models.ChatResponse)
# async def process_chat(
#     request: models.ChatRequest,
#     agent: AgentSystem = Depends(get_agent_system)
# ) -> models.ChatResponse:
#     """Process chat messages and determine if/how to respond."""
#     try:
#         conversation_id = request.conversation_id or str(uuid.uuid4())
#         message_count = len(request.messages)
        
#         should_respond = message_count % request.frequency == 0
        
#         response = None
#         analysis = None
        
#         if should_respond:
#             chat_context = format_chat_context(
#                 request.messages,
#                 request.max_context_messages
#             )
            
#             last_message = request.messages[-1].content
#             full_context = f"{request.context}\n\nChat History:\n{chat_context}"
            
#             analysis = agent.analyze_message(
#                 message=last_message,
#                 persona_id=request.persona_id,
#                 context=full_context
#             )
            
#             response_data = agent.generate_response(
#                 persona_id=request.persona_id,
#                 message=last_message,
#                 context=full_context,
#                 analysis=analysis
#             )
            
#             response = response_data['content']
        
#         return models.ChatResponse(
#             response=response,
#             should_respond=should_respond,
#             analysis=analysis,
#             persona_id=request.persona_id,
#             conversation_id=conversation_id,
#             message_count=message_count
#         )
        
#     except Exception as e:
#         raise HTTPException(
#             status_code=500,
#             detail=f"Error processing chat: {str(e)}"
#         )
#     finally:
#         agent.close()


# @router.post("/relationship-test", response_model=models.TestResponse) 
# async def generate_test(
#     request: models.ChatRequest,
#     agent: AgentSystem = Depends(get_agent_system)
# ) -> models.TestResponse: 
#     """Generate a relationship test based on conversation history."""
#     try:
#         last_message = request.messages[-1].content
        
#         analysis = agent.analyze_message(
#             message=last_message,
#             persona_id=request.persona_id,
#             context=request.context
#         )
        
#         test_question = agent.generate_test_question(
#             persona_id=request.persona_id,
#             analysis=analysis,
#             context=request.context
#         )
        
#         return models.TestResponse(  
#             question=test_question,
#             analysis=analysis,
#             persona_id=request.persona_id,
#             conversation_id=request.conversation_id
#         )
        
#     except Exception as e:
#         raise HTTPException(
#             status_code=500,
#             detail=f"Error generating test: {str(e)}"
#         )
#     finally:
#         agent.close()

@router.post("/truth-bomb", response_model=models.TestResponse)
async def generate_truth_bomb(
    request: models.ChatRequest,
    agent: AgentSystem = Depends(get_agent_system)
) -> models.TestResponse:
    """Generate a targeted truth bomb based on conversation analysis."""
    try:
        analysis = agent.analyze_conversation(request.messages)
        
        # Ensure we always have a valid string for the question field
        truth_bomb = analysis.get("truth_bomb")
        if not truth_bomb or not isinstance(truth_bomb, str):
            truth_bomb = "How's the conversation going?"
        
        return models.TestResponse(
            question=truth_bomb,
            analysis=analysis,
            persona_id=request.persona_id,
            conversation_id=request.conversation_id
        )
        
    except Exception as e:
        logger.error(f"Error generating truth bomb: {e}")
        # Return a safe fallback response
        return models.TestResponse(
            question="How's the conversation going?",
            analysis={
                "truth_bomb": "How's the conversation going?",
                "confidence": 0.0,
                "analysis_type": "fallback",
                "all_analyses": []
            },
            persona_id=request.persona_id,
            conversation_id=request.conversation_id
        )
    finally:
        agent.close()

@router.get("/health", response_model=models.HealthResponse)
async def health_check(
    agent: AgentSystem = Depends(get_agent_system)
) -> models.HealthResponse:
    """Check the health status of the chat service."""
    try:
        personas_status = {
            persona_id: {
                "name": persona["name"],  
                "status": "active",
                "knowledge_domains": persona.get("personality_traits", [])  
            }
            for persona_id, persona in agent.personas.items()
        }
        
        return models.HealthResponse(
            status="healthy",
            version=__version__,
            personas=personas_status
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Health check failed: {str(e)}"
        )
    finally:
        agent.close()