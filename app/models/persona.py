from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional
from datetime import datetime

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

