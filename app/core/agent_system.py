# app/core/agent_system.py
import json
import redis
import hashlib
import queue
import logging
import random
import threading
from typing import Dict, Any, Optional, List
from datetime import datetime

from ..models.api import Message
from ..models.llm_adapter import create_llm_adapter
from .truth_bomb import TruthBombAnalyzer
from ..config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class AgentSystem:
    _PERSONA_TYPES = {
        "truth_revealer": {
            "name": "Truth Oracle",
            "truth_index": 0.9,
            "personality_traits": ["direct", "insightful", "challenging"],
            "question_patterns": [
                "What's the hardest truth you've avoided telling {partner}?",
                "When did you last feel completely honest with each other?",
                "What aspect of your relationship makes you most uncertain?"
            ]
        },
        "growth_catalyst": {
            "name": "Growth Guide",
            "truth_index": 0.7,
            "personality_traits": ["supportive", "analytical", "forward-thinking"],
            "question_patterns": [
                "How has your relationship evolved in the past {time_period}?",
                "What mutual goal excites you both the most?",
                "Which of your differences has led to the most growth?"
            ]
        }
    }

    def __init__(
        self,
        redis_host: str = 'localhost',
        redis_port: int = 6379,
        cache_ttl: int = 3600,
        flush_interval: int = 300,
        buffer_size: int = 1000
    ):
        # Initialize core components
        self.llm = create_llm_adapter(settings.LLM_CONFIG)
        self.redis_client = redis.Redis(
            host=redis_host,
            port=redis_port,
            decode_responses=True
        )
        self.cache_ttl = cache_ttl
        self.personas = self._load_personas()
        
        # Initialize truth bomb analyzer
        self.truth_analyzer = TruthBombAnalyzer()
        
        # Initialize feedback system
        self.feedback_buffer = queue.Queue(maxsize=buffer_size)
        self.flush_interval = flush_interval
        self.should_stop = threading.Event()
        
        # Start background processes
        self._start_background_threads()

    def analyze_conversation(self, messages: List[Message]) -> Dict[str, Any]:
        """Analyze conversation and generate appropriate truth bombs"""
        # Convert Message objects to dict format
        msg_list = [{
            "content": msg.content,
            "sender": msg.sender,
            "timestamp": msg.timestamp,
            "metadata": msg.metadata
        } for msg in messages]
        
        analyses = []
        
        # Length prediction
        length_analysis = self.truth_analyzer.analyze_conversation_length(msg_list)
        if length_analysis:
            analyses.append(length_analysis)
        
        # Date probability
        date_analysis = self.truth_analyzer.analyze_date_probability(msg_list)
        if date_analysis:
            analyses.append(date_analysis)
        
        # Safety concerns
        safety_analysis = self.truth_analyzer.analyze_safety_concerns(msg_list)
        if safety_analysis:
            analyses.append(safety_analysis)
        
        # Flirting amplifier
        flirt_analysis = self.truth_analyzer.generate_flirting_amplifier(msg_list)
        if flirt_analysis:
            analyses.append(flirt_analysis)
        
        # Select most relevant truth bomb
        selected_analysis = self._select_best_analysis(analyses)
        
        return {
            "truth_bomb": selected_analysis["prediction"] if selected_analysis else None,
            "confidence": selected_analysis.get("confidence", 0.0) if selected_analysis else 0.0,
            "analysis_type": selected_analysis.get("type") if selected_analysis else None,
            "all_analyses": analyses
        }
    
    def _select_best_analysis(self, analyses: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Select the most relevant analysis based on confidence and type"""
        if not analyses:
            return None
            
        # Prioritize safety concerns
        safety_analyses = [a for a in analyses if a["type"] == "safety" 
                         and a.get("risk_level", 0) > 0.7]
        if safety_analyses:
            return max(safety_analyses, key=lambda x: x.get("confidence", 0))
        
        # Otherwise select based on confidence and relevance
        weighted_analyses = []
        for analysis in analyses:
            base_weight = analysis.get("confidence", 0)
            type_weight = {
                "date_probability": 1.2,
                "flirting_amplifier": 1.1,
                "conversation_length": 0.9
            }.get(analysis["type"], 1.0)
            
            weighted_analyses.append((analysis, base_weight * type_weight))
        
        if weighted_analyses:
            return max(weighted_analyses, key=lambda x: x[1])[0]
        
        return None


    def _load_personas(self) -> Dict[str, Any]:
        try:
            cached_personas = self.redis_client.get('dating_personas')
            logger.info(f"Cached personas: {cached_personas}") 
            if cached_personas:
                return json.loads(cached_personas)

            personas = {
                persona_type: {
                    **config,
                    "type": persona_type,
                    "created_at": datetime.now().isoformat()
                }
                for persona_type, config in self._PERSONA_TYPES.items()
            }
            logger.info(f"Created new personas: {personas}")
            
            self.redis_client.setex('dating_personas', 600, json.dumps(personas))
            return personas
            
        except Exception as e:
            logger.error(f"Error loading personas: {e}")
            return {}
    
    def _select_best_analysis(self, analyses: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Select the most relevant analysis based on confidence and type"""
        if not analyses:
            return None
            
        safety_analyses = [a for a in analyses if a["type"] == "safety" 
                         and a.get("risk_level", 0) > 0.7]
        if safety_analyses:
            return max(safety_analyses, key=lambda x: x.get("confidence", 0))
        
        weighted_analyses = []
        for analysis in analyses:
            base_weight = analysis.get("confidence", 0)
            type_weight = {
                "date_probability": 1.2,
                "flirting_amplifier": 1.1,
                "conversation_length": 0.9
            }.get(analysis["type"], 1.0)
            
            weighted_analyses.append((analysis, base_weight * type_weight))
        
        if weighted_analyses:
            return max(weighted_analyses, key=lambda x: x[1])[0]
        
        return None


    def analyze_message(
        self,
        message: str,
        persona_id: str,
        context: str = ""
    ) -> Dict[str, Any]:
        """Generate message analysis using LLM"""
        cache_key = f"analysis:{persona_id}:{hashlib.md5(message.encode()).hexdigest()}"
        
        cached_analysis = self.redis_client.get(cache_key)
        if cached_analysis:
            return json.loads(cached_analysis)
            
        persona = self.personas.get(persona_id)
        
        if not persona:
            return self._generate_fallback_analysis()
            
        prompt = self._create_analysis_prompt(message, persona, context)
        
        try:
            response = self.llm.generate(prompt, max_tokens=300, temperature=0.2)
            logger.info(f"Raw LLM response: {response}")
            
            try:
                import re
                json_match = re.search(r'```json\n(.*?)\n```', response, re.DOTALL)
                if json_match:
                    json_str = json_match.group(1)
                    analysis = json.loads(json_str)
                else:
                    json_match = re.search(r'{\s*"emotional_tone".*?}(?=\n|$)', response, re.DOTALL)
                    if json_match:
                        json_str = json_match.group(0)
                        analysis = json.loads(json_str)
                    else:
                        logger.error("No JSON found in response")
                        return self._generate_fallback_analysis()
                        
                self.redis_client.setex(cache_key, self.cache_ttl, json.dumps(analysis))
                return analysis
                
            except (json.JSONDecodeError, AttributeError) as e:
                logger.error(f"Failed to parse LLM response: {e}")
                return self._generate_fallback_analysis()
                
        except Exception as e:
            logger.error(f"Analysis generation error: {e}")
            return self._generate_fallback_analysis()
    
    def generate_response(
        self,
        persona_id: str,
        message: str,
        context: str,
        analysis: Optional[Dict[str, Any]] = None
    ) -> Dict[str, str]:
        """Generate a relationship-focused response"""
        if not analysis:
            analysis = self.analyze_message(message, persona_id, context)
            
        persona = self.personas.get(persona_id)
        
        if not persona:
            return {"content": "I need more context to provide a meaningful response."}
            
        prompt = self._create_response_prompt(message, persona, context, analysis)
        
        try:
            response = self.llm.generate(prompt, max_tokens=200, temperature=0.7)
            response_text = response['message']['content'] if isinstance(response, dict) else response
            return {"content": response_text.strip()}
        except Exception as e:
            logger.error(f"Response generation error: {e}")
            return {"content": self._get_fallback_response()}
    
    def generate_test_question(
        self,
        persona_id: str,
        analysis: Dict[str, Any],
        context: str
    ) -> str:
        """Generate a relationship test question"""
        persona = self.personas.get(persona_id)
        
        if not persona:
            return self._get_fallback_question()
            
        prompt = self._create_test_prompt(persona, analysis, context)
        
        try:
            response = self.llm.generate(prompt, max_tokens=100, temperature=0.8)
            return response['choices'][0]['text'].strip()
        except Exception as e:
            logger.error(f"Test question generation error: {e}")
            return self._get_fallback_question()
        
    def _create_test_prompt(
        self,
        persona: Dict[str, Any],
        analysis: Dict[str, Any],
        context: str
    ) -> str:
        """Create prompt for generating relationship test questions"""
        return f"""As {persona['name']}, generate a meaningful relationship-focused question.

    Context: {context}
    Analysis: {json.dumps(analysis)}

    Your traits: {', '.join(persona['personality_traits'])}
    Truth level: {persona['truth_index']}

    Use your persona's style to generate a question that:
    1. Matches your personality traits ({', '.join(persona['personality_traits'])})
    2. Explores the themes from the analysis
    3. Encourages honest self-reflection
    4. Is appropriate for the current relationship context

    Choose from or be inspired by these question patterns:
    {json.dumps(persona['question_patterns'], indent=2)}

    Return a single, clear question without any additional commentary or text."""
    
    def _create_analysis_prompt(
        self,
        message: str,
        persona: Dict[str, Any],
        context: str
    ) -> str:
        """Create prompt for message analysis"""
        return f"""As {persona['name']}, analyze this message in the context of a relationship:

Message: {message}
Context: {context}

Consider:
1. Emotional undertones 
2. Relationship dynamics
3. Potential concerns or growth areas
4. Truth level: {persona['truth_index']}

Return analysis in JSON format with the following structure:
{{
    "emotional_tone": {{"positive": float, "negative": float, "neutral": float}},
    "relationship_indicators": {{
        "communication_quality": float,
        "emotional_intimacy": float,
        "conflict_patterns": [str],
        "growth_opportunities": [str]
    }},
    "suggested_questions": [str],
    "intervention_type": str
}}"""

    def _create_response_prompt(
        self,
        message: str,
        persona: Dict[str, Any],
        context: str,
        analysis: Dict[str, Any]
    ) -> str:
        """Create prompt for generating response"""
        return f"""As {persona['name']}, respond to the following message. Your response should be conversational, concise (2-3 sentences), and reflect your personality as {', '.join(persona['personality_traits'])}.

    Message: {message}
    Context: {context}
    Analysis: {json.dumps(analysis)}

    Your truth level is {persona['truth_index']}. Keep your response natural and engaging, focusing on building rapport and encouraging open discussion."""

    def generate_response(
        self,
        persona_id: str,
        message: str,
        context: str,
        analysis: Optional[Dict[str, Any]] = None
    ) -> Dict[str, str]:
        """Generate a relationship-focused response"""
        if not analysis:
            analysis = self.analyze_message(message, persona_id, context)
            
        persona = self.personas.get(persona_id)
        
        if not persona:
            return {"content": "I need more context to provide a meaningful response."}
            
        prompt = self._create_response_prompt(message, persona, context, analysis)
        
        try:
            response = self.llm.generate(prompt, max_tokens=150, temperature=0.7) 
            response_text = response['message']['content'] if isinstance(response, dict) else response
            
            if "This response:" in response_text:
                response_text = response_text.split("This response:")[0]
                
            if not response_text.rstrip().endswith(('.', '!', '?')):
                response_text = '. '.join(response_text.split('.')[:-1]) + '.'
                
            return {"content": response_text.strip()}
        except Exception as e:
            logger.error(f"Response generation error: {e}")
            return {"content": self._get_fallback_response()}
    
    def _generate_fallback_analysis(self) -> Dict[str, Any]:
        """Generate fallback analysis when normal analysis fails"""
        return {
            "emotional_tone": {
                "positive": 0.33,
                "negative": 0.33,
                "neutral": 0.34
            },
            "relationship_indicators": {
                "communication_quality": 0.5,
                "emotional_intimacy": 0.5,
                "conflict_patterns": [],
                "growth_opportunities": ["general communication", "emotional awareness"]
            },
            "suggested_questions": [
                "How do you feel about your communication?",
                "What would you like to improve in your relationship?"
            ],
            "intervention_type": "general"
        }

    def _get_fallback_response(self) -> str:
        """Get fallback response when generation fails"""
        fallback_responses = [
            "Could you tell me more about how that makes you feel?",
            "How does your partner view this situation?",
            "What would make this situation better for both of you?"
        ]
        return random.choice(fallback_responses)

    def _get_fallback_question(self) -> str:
        """Get fallback question when generation fails"""
        fallback_questions = [
            "What's the most important thing in your relationship right now?",
            "How has your relationship changed over time?",
            "What do you wish your partner understood better about you?"
        ]
        return random.choice(fallback_questions)

    def _start_background_threads(self):
        """Initialize background processing threads"""
        self.feedback_thread = threading.Thread(target=self._process_feedback)
        self.feedback_thread.daemon = True
        self.feedback_thread.start()

    def _process_feedback(self):
        """Process feedback from the feedback buffer"""
        while not self.should_stop.is_set():
            try:
                feedback_batch = []
                while not self.feedback_buffer.empty() and len(feedback_batch) < 100:
                    feedback = self.feedback_buffer.get_nowait()
                    feedback_batch.append(feedback)

                if feedback_batch:
                    for feedback in feedback_batch:
                        self._update_persona_metrics(feedback)
                    
                    self.should_stop.wait(self.flush_interval)
            except Exception as e:
                logger.error(f"Error processing feedback: {e}")
                for feedback in feedback_batch:
                    try:
                        self.feedback_buffer.put(feedback)
                    except queue.Full:
                        logger.error("Feedback buffer full, dropping feedback")

    def _update_persona_metrics(self, feedback: Dict[str, Any]):
        """Update persona metrics based on feedback"""
        try:
            persona_id = feedback.get('persona_id')
            if not persona_id or persona_id not in self.personas:
                return

            persona = self.personas[persona_id]
            
            if 'success_score' in feedback:
                current_score = persona.get('success_score', 0.5)
                new_score = (current_score * 0.9) + (feedback['success_score'] * 0.1)
                persona['success_score'] = new_score

            if (
                'question' in feedback 
                and 'success_score' in feedback 
                and feedback['success_score'] > 0.8
            ):
                self._add_successful_question(persona_id, feedback['question'])

            self._update_persona_cache(persona_id, persona)

        except Exception as e:
            logger.error(f"Error updating persona metrics: {e}")

    def _add_successful_question(self, persona_id: str, question: str):
        """Add successful question to persona's patterns"""
        try:
            if persona_id in self.personas:
                persona = self.personas[persona_id]
                if len(persona['question_patterns']) >= 20:
                    persona['question_patterns'].pop(0)
                persona['question_patterns'].append(question)
                self._update_persona_cache(persona_id, persona)
        except Exception as e:
            logger.error(f"Error adding successful question: {e}")

    def _update_persona_cache(self, persona_id: str, persona: Dict[str, Any]):
        """Update persona in Redis cache"""
        try:
            cached_personas = self.redis_client.get('dating_personas')
            if cached_personas:
                personas = json.loads(cached_personas)
                personas[persona_id] = persona
                self.redis_client.setex('dating_personas', 600, json.dumps(personas))
        except Exception as e:
            logger.error(f"Error updating persona cache: {e}")

    def close(self):
        """Cleanup resources"""
        self.should_stop.set()
        if hasattr(self, 'feedback_thread'):
            self.feedback_thread.join()
        self.redis_client.close()