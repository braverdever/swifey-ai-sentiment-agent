from fastapi import APIRouter, HTTPException, Depends
from typing import Dict, Any, List
import uuid

from core.agent_system import AgentSystem
from api import models

__version__ = "0.1.0"  # Define version locally for now

router = APIRouter()

def get_agent_system() -> AgentSystem:
    """Dependency to get the agent system instance."""
    # This would typically be initialized at startup and stored in a global state
    # or database. For now, we'll create a new instance each time.
    from ..config import settings
    
    try:
        agent = AgentSystem(
            persona_config_path=settings.PERSONA_CONFIG_PATH,
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

def format_chat_context(messages: List[models.Message], max_messages: int = 10) -> str:
    """Format chat messages into context string."""
    recent_messages = messages[-max_messages:]
    return "\n".join([
        f"{msg.sender}: {msg.content}"
        for msg in recent_messages
    ])

@router.post("/chat", response_model=models.ChatResponse)
async def process_chat(
    request: models.ChatRequest,
    agent: AgentSystem = Depends(get_agent_system)
) -> models.ChatResponse:
    """Process chat messages and determine if/how to respond."""
    try:
        conversation_id = request.conversation_id or str(uuid.uuid4())
        message_count = len(request.messages)
        
        # Determine if we should respond based on frequency
        should_respond = message_count % request.frequency == 0
        
        response = None
        analysis = None
        
        if should_respond:
            # Format recent messages as context
            chat_context = format_chat_context(
                request.messages,
                request.max_context_messages
            )
            
            # Get the last message
            last_message = request.messages[-1].content
            
            # Combine chat context with any additional context
            full_context = f"{request.context}\n\nChat History:\n{chat_context}"
            
            # Analyze the conversation
            analysis = agent.analyze_message(
                message=last_message,
                persona_id=request.persona_id,
                context=full_context
            )
            
            # Generate response
            response_data = agent.generate_response(
                persona_id=request.persona_id,
                message=last_message,
                context=full_context,
                analysis=analysis
            )
            
            response = response_data['content']
        
        return models.ChatResponse(
            response=response,
            should_respond=should_respond,
            analysis=analysis,
            persona_id=request.persona_id,
            conversation_id=conversation_id,
            message_count=message_count
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error processing chat: {str(e)}"
        )
    finally:
        agent.close()

@router.post("/message", response_model=models.MessageResponse)
async def process_message(
    request: models.MessageRequest,
    agent: AgentSystem = Depends(get_agent_system)
) -> models.MessageResponse:
    """Process a message and get a response from the agent."""
    try:
        # Generate conversation ID if not provided
        conversation_id = request.conversation_id or str(uuid.uuid4())
        
        # Analyze message
        analysis = agent.analyze_message(
            message=request.message,
            persona_id=request.persona_id,
            context=request.context
        )
        
        # Generate response
        response_data = agent.generate_response(
            persona_id=request.persona_id,
            message=request.message,
            context=request.context,
            analysis=analysis
        )
        
        return models.MessageResponse(
            response=response_data['content'],
            analysis=analysis,
            persona_id=request.persona_id,
            conversation_id=conversation_id
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error processing message: {str(e)}"
        )
    finally:
        agent.close()

@router.post("/feedback", response_model=models.FeedbackResponse)
async def submit_feedback(
    request: models.FeedbackRequest,
    agent: AgentSystem = Depends(get_agent_system)
) -> models.FeedbackResponse:
    """Submit feedback for a message."""
    try:
        agent.submit_feedback(
            persona_id=request.persona_id,
            message_type=request.message_type,
            content=request.content,
            feedback_score=request.feedback_score,
            details=request.details,
            conversation_id=request.conversation_id,
            context=request.context
        )
        
        return models.FeedbackResponse(
            success=True,
            persona_id=request.persona_id,
            message="Feedback processed successfully"
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error processing feedback: {str(e)}"
        )
    finally:
        agent.close()

@router.get("/health", response_model=models.HealthResponse)
async def health_check(
    agent: AgentSystem = Depends(get_agent_system)
) -> models.HealthResponse:
    """Check the health status of the service."""
    try:
        personas_status = {
            persona_id: {
                "name": persona.name,
                "status": "active",
                "knowledge_domains": persona.knowledge_domains
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
  