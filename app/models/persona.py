from typing import Dict, Any, List
from collections import defaultdict

class Persona:
    def __init__(self, persona_id: str, config: Dict[str, Any]):
        self.persona_id = persona_id
        self.name = config.get('name', persona_id)
        self.personality_traits = config.get('personality_traits', [])
        self.communication_style = config.get('communication_style', {})
        self.knowledge_domains = config.get('knowledge_domains', [])
        self.language_patterns = config.get('language_patterns', {})
        self.emotional_baseline = config.get('emotional_baseline', {})
        self.response_templates = config.get('response_templates', [])
        self.learning_rate = config.get('learning_rate', 0.1)
        self.question_patterns = config.get('question_patterns', [])
        self.feedback_history = defaultdict(list)
        self.learning_metrics = defaultdict(float)

    def update_from_feedback(self, feedback: Dict[str, Any]) -> None:
        """Update persona behavior based on feedback"""
        for metric, value in feedback.items():
            if isinstance(value, (int, float)):
                self.learning_metrics[metric] = (
                    (1 - self.learning_rate) * self.learning_metrics[metric] +
                    self.learning_rate * value
                )
        
        if feedback.get('overall_score', 0) > 0.8:
            self.question_patterns.append({
                'pattern': feedback.get('question', ''),
                'context_type': feedback.get('context_type', 'general'),
                'success_score': feedback.get('overall_score', 0)
            })
    
    def get_prompt_context(self) -> str:
        """Generate context string for prompts"""
        return f"""Personality: {', '.join(self.personality_traits)}
Style: {self.communication_style}
Knowledge domains: {', '.join(self.knowledge_domains)}"""

    def get_response_template(self) -> str:
        """Get a random response template"""
        import random
        return random.choice(self.response_templates) if self.response_templates else "" 