from typing import Dict, Any, List
import uuid
import logging
from fastapi import APIRouter, HTTPException, Depends
from starlette.requests import Request
from ..db.supabase import get_supabase
from ..core.agent_system import AgentSystem
from ..models import api as models
from ..auth.middleware import verify_app_token
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime

logger = logging.getLogger(__name__)

__version__ = "0.1.0"

router = APIRouter()

class ChatPreview(BaseModel):
    other_user_id: str
    other_user_name: str
    last_message: Optional[str]
    last_message_time: datetime
    unread_count: int
    other_user_photo: List[str]

class ChatListResponse(BaseModel):
    success: bool
    message: str
    chats: List[ChatPreview]

class Message(BaseModel):
    message_id: str
    sender_id: str
    recipient_id: str
    content: Optional[str]
    sent_at: datetime
    edited_at: Optional[datetime]
    status: str
    metadata: Dict[str, Any]
    audio_message_id: Optional[str]
    message_type: str
    audio_id: Optional[str]
    title: Optional[str]
    duration: Optional[int]
    audio_url: Optional[str]
    thumbnail_url: Optional[str]

class ChatMessagesResponse(BaseModel):
    success: bool
    message: str
    messages: List[Message]

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

@router.get("/user_chats", response_model=ChatListResponse)
async def get_user_chats(user_id: str = Depends(verify_app_token)):
    try:
        supabase = get_supabase()
        response = supabase.rpc("get_user_chats", {
            'user_uuid': user_id
        }).execute()
        if response is None:
            return {
                "success": True,
                "message": "No chats found",
                "chats": []
            }
        return {
            "success": True,
            "message": "Chats fetched successfully",
            "chats": response.data
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/chat_messages", response_model=ChatMessagesResponse)
async def get_chat_messages(other_user_id: str, user_id: str = Depends(verify_app_token), before_timestamp: Optional[datetime] = None, page_size: int = 50):
    try: 
        supabase = get_supabase()
        response = supabase.rpc("get_direct_messages", {
            'user1_uuid': other_user_id,
            'user2_uuid': user_id,
            'before_timestamp': before_timestamp,
            'page_size': page_size
        }).execute()

        if response is None:
            return {
                "success": True,
                "message": "No chat messages found",
                "messages": []
            }
            
        return {
            "success": True,
            "message": "Chat messages fetched successfully",
            "messages": response.data
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
