from typing import Dict, Any, Optional, List
from datetime import datetime
from pydantic import BaseModel, Field

class Message(BaseModel):
    content: str = Field(..., description="Message content")
    sender: str = Field(..., description="Message sender identifier")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Message timestamp")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional message metadata")

class ChatRequest(BaseModel):
    messages: List[Message] = Field(..., description="List of messages in the conversation")
    persona_id: str = Field(default="default_assistant", description="The ID of the persona to use")
    context: str = Field(default="", description="Additional context for the conversation")
    frequency: int = Field(default=3, description="Number of messages to wait before generating a response")
    max_context_messages: int = Field(default=10, description="Maximum number of previous messages to consider")
    last_message: Optional[str] = None  

class TestResponse(BaseModel):
    question: str
    analysis: Optional[Dict[str, Any]] = None
    persona_id: str

class ChatResponse(BaseModel):
    response: Optional[str] = Field(None, description="The generated response if applicable")
    should_respond: bool = Field(..., description="Whether the agent should respond now")
    analysis: Optional[Dict[str, Any]] = Field(None, description="Analysis of the conversation")
    persona_id: str = Field(..., description="The ID of the persona")
    message_count: int = Field(..., description="Current message count in the conversation")

class MessageRequest(BaseModel):
    message: str = Field(..., description="The message to process")
    persona_id: str = Field(default="default_assistant", description="The ID of the persona to use")
    context: str = Field(default="", description="Additional context for the message")

class MessageResponse(BaseModel):
    response: str = Field(..., description="The generated response")
    analysis: Optional[Dict[str, Any]] = Field(default=None, description="Analysis of the message")
    persona_id: str = Field(..., description="The ID of the persona that generated the response")

class FeedbackRequest(BaseModel):
    persona_id: str = Field(..., description="The ID of the persona to provide feedback for")
    message_type: str = Field(..., description="Type of message (e.g., greeting, question)")
    content: str = Field(..., description="The content that received feedback")
    feedback_score: float = Field(..., ge=0, le=1, description="Feedback score between 0 and 1")
    details: Dict[str, Any] = Field(default_factory=dict, description="Additional feedback details")
    context: str = Field(default="", description="Context in which the feedback was given")

class FeedbackResponse(BaseModel):
    success: bool = Field(..., description="Whether the feedback was successfully processed")
    persona_id: str = Field(..., description="The ID of the persona that received feedback")
    message: str = Field(..., description="Status message")

class HealthResponse(BaseModel):
    status: str = Field(..., description="Service health status")
    version: str = Field(..., description="API version")
    personas: Dict[str, Any] = Field(..., description="Available personas and their status") 