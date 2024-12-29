from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional
from datetime import datetime

class Message(BaseModel):
    sender: str
    content: str
    timestamp: datetime = Field(default_factory=datetime.now)

class ChatRequest(BaseModel):
    conversation_id: Optional[str] = None
    messages: List[Message]
    persona_id: str
    context: str = ""
    frequency: int = Field(default=5, ge=1, le=100)
    max_context_messages: int = Field(default=10, ge=1, le=50)

class ChatResponse(BaseModel):
    response: Optional[str]
    should_respond: bool
    analysis: Optional[Dict[str, Any]]
    persona_id: str
    conversation_id: str
    message_count: int

class TestRequest(BaseModel):
    conversation_id: str
    persona_id: str
    last_message: str
    context: str = ""
    test_type: str = Field(default="general")

class TestResponse(BaseModel):
    question: str
    analysis: Dict[str, Any]
    persona_id: str
    conversation_id: str

class HealthResponse(BaseModel):
    status: str
    version: str
    personas: Dict[str, Dict[str, Any]]

class Persona(BaseModel):
    id: str
    name: str
    personality_traits: List[str] = Field(default_factory=list)
    communication_style: Dict[str, Any] = Field(default_factory=dict)
    knowledge_domains: List[str] = Field(default_factory=list)
    language_patterns: Dict[str, List[str]] = Field(default_factory=dict)
    emotional_baseline: Dict[str, float] = Field(default_factory=dict)
    response_templates: List[str] = Field(default_factory=list)
    learning_rate: float = Field(default=0.1, ge=0.0, le=1.0)
    question_patterns: List[Dict[str, Any]] = Field(default_factory=list)
    truth_index: float = Field(default=0.5, ge=0.0, le=1.0)
    intervention_frequency: int = Field(default=5, ge=1, le=100)

class FeedbackData(BaseModel):
    conversation_id: str
    persona_id: str
    message_id: str
    feedback_type: str
    rating: float = Field(ge=0.0, le=1.0)
    timestamp: datetime = Field(default_factory=datetime.now)
    additional_data: Dict[str, Any] = Field(default_factory=dict)

class RelationshipAnalysis(BaseModel):
    emotional_tone: Dict[str, float]
    relationship_indicators: Dict[str, Any]
    truth_level: float
    suggested_questions: List[str]
    intervention_type: str
    timestamp: datetime = Field(default_factory=datetime.now)