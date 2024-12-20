import json
import redis
import hashlib
import threading
import queue
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
import numpy as np
from sqlalchemy.orm import Session
from sqlalchemy import create_engine

from models.database import Base, SentimentAnalysis, QuestionFeedback, PersonaLearningMetrics
from models.persona import Persona
from db.supabase import get_supabase
from models.llm_adapter import create_llm_adapter
from config import settings

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class AgentSystem:
    def __init__(
        self,
        db_url: str,
        redis_host: str = 'localhost',
        redis_port: int = 6379,
        cache_ttl: int = 3600,
        flush_interval: int = 300,
        buffer_size: int = 1000
    ):
        """Initialize the agent system"""
        # Initialize LLM adapter
        self.llm = create_llm_adapter(settings.LLM_CONFIG)
        
        # Initialize Supabase
        self.supabase = get_supabase()
        
        # Load personas from Supabase
        self.personas = self._load_personas()
        
        # Initialize Redis
        self.redis_client = redis.Redis(
            host=redis_host,
            port=redis_port,
            decode_responses=True
        )
        self.cache_ttl = cache_ttl
        
        # Initialize database
        self.engine = create_engine(db_url)
        Base.metadata.create_all(self.engine)
        
        # Initialize buffers
        self.analysis_buffer = queue.Queue(maxsize=buffer_size)
        self.feedback_buffer = queue.Queue(maxsize=buffer_size)
        
        # Initialize flush settings
        self.flush_interval = flush_interval
        self.last_flush = datetime.utcnow()
        
        # Threading controls
        self.should_stop = threading.Event()
        self._start_background_threads()
        
        # Metrics
        self.quality_metrics = ['relevance', 'clarity', 'depth', 'timing', 'context_awareness']

    def _load_personas(self) -> Dict[str, Persona]:
        """Load persona configurations from Supabase"""
        personas = {}
        for persona in self.supabase.table('personas').select():
            persona_id = persona['id']
            persona_config = persona['config']
            personas[persona_id] = Persona(persona_id, persona_config)
        return personas

    def analyze_message(
        self,
        message: str,
        persona_id: str,
        context: str = ""
    ) -> Dict[str, Any]:
        """Analyze message from persona's perspective"""
        cache_key = f"message:{persona_id}:{hashlib.md5(message.encode()).hexdigest()}"
        
        # Check cache
        cached_result = self.redis_client.get(cache_key)
        if cached_result:
            return json.loads(cached_result)
        
        # Generate analysis
        analysis = self._generate_analysis(message, persona_id, context)
        
        # Cache result
        self.redis_client.setex(
            cache_key,
            self.cache_ttl,
            json.dumps(analysis)
        )
        
        return analysis

    def _generate_analysis(
        self,
        message: str,
        persona_id: str,
        context: str
    ) -> Dict[str, Any]:
        """Generate analysis using Llama model"""
        persona = self.personas[persona_id]
        
        prompt = f"""As {persona.name}, analyze this message:
                    Context: {context}
                    Message: "{message}"

                    Consider:
                    1. Emotional response (from {persona.name}'s perspective)
                    2. Key points and implications
                    3. Relevant domain knowledge from: {', '.join(persona.knowledge_domains)}
                    4. Appropriate response style based on: {persona.communication_style}

                    Provide analysis in JSON format with keys:
                    - emotional_response
                    - sentiment_scores (positive, negative, neutral, compound)
                    - key_points
                    - suggested_response_style"""

        try:
            response = self.llm(
                prompt,
                max_tokens=300,
                temperature=0.2
            )
            return json.loads(response['choices'][0]['text'].strip())
        except Exception as e:
            logger.error(f"Analysis generation error: {e}")
            return self._generate_fallback_analysis(persona_id)

    def generate_response(
        self,
        persona_id: str,
        message: str,
        context: str,
        analysis: Optional[Dict] = None
    ) -> str:
        """Generate response from persona"""
        persona = self.personas[persona_id]
        
        if not analysis:
            analysis = self.analyze_message(message, persona_id, context)
        
        prompt = f"""As {persona.name}, generate a response:
                        {persona.get_prompt_context()}
                        Context: {context}
                        Message: "{message}"
                        Analysis: {json.dumps(analysis)}

                        Generate a natural response that:
                        1. Reflects {persona.name}'s personality
                        2. Uses appropriate language patterns
                        3. Shows domain expertise in: {', '.join(persona.knowledge_domains)}
                        4. Maintains emotional consistency

                        Response:"""

        try:
            response = self.llm(
                prompt,
                max_tokens=200,
                temperature=0.7
            )
            return response['choices'][0]['text'].strip()
        except Exception as e:
            logger.error(f"Response generation error: {e}")
            return self._get_fallback_response(persona_id)

    def submit_feedback(
        self,
        persona_id: str,
        message_type: str,
        content: str,
        feedback_score: float,
        details: Dict[str, Any],
        conversation_id: str,
        context: str = ""
    ):
        """Submit feedback for persona's message"""
        feedback = {
            'persona_id': persona_id,
            'message_type': message_type,
            'content': content,
            'feedback_score': feedback_score,
            'details': details,
            'conversation_id': conversation_id,
            'context': context,
            'timestamp': datetime.utcnow()
        }
        
        self.feedback_buffer.put(feedback)
        
        # Immediate persona update
        if persona_id in self.personas:
            self.personas[persona_id].update_from_feedback({
                'message': content,
                'overall_score': feedback_score,
                'message_type': message_type,
                **details
            })

    def _process_analysis_buffer(self):
        """Process buffered analyses"""
        while not self.should_stop.is_set():
            try:
                analyses = []
                while not self.analysis_buffer.empty() and len(analyses) < 100:
                    analyses.append(self.analysis_buffer.get_nowait())
                
                if analyses:
                    with Session(self.engine) as session:
                        session.bulk_insert_mappings(SentimentAnalysis, analyses)
                        session.commit()
                
                self.should_stop.wait(self.flush_interval)
            except Exception as e:
                logger.error(f"Analysis processing error: {e}")

    def _process_feedback_buffer(self):
        """Process buffered feedback"""
        while not self.should_stop.is_set():
            try:
                feedback_batch = []
                while not self.feedback_buffer.empty() and len(feedback_batch) < 100:
                    feedback_batch.append(self.feedback_buffer.get_nowait())
                
                if feedback_batch:
                    with Session(self.engine) as session:
                        session.bulk_insert_mappings(QuestionFeedback, feedback_batch)
                        session.commit()
                
                self.should_stop.wait(self.flush_interval)
            except Exception as e:
                logger.error(f"Feedback processing error: {e}")

    def _start_background_threads(self):
        """Start background processing threads"""
        self.analysis_thread = threading.Thread(target=self._process_analysis_buffer)
        self.feedback_thread = threading.Thread(target=self._process_feedback_buffer)
        
        self.analysis_thread.daemon = True
        self.feedback_thread.daemon = True
        
        self.analysis_thread.start()
        self.feedback_thread.start()

    def close(self):
        """Cleanup resources"""
        self.should_stop.set()
        self.analysis_thread.join()
        self.feedback_thread.join()
        self.redis_client.close()

    def _generate_fallback_analysis(self, persona_id: str) -> Dict[str, Any]:
        """Generate fallback analysis when main analysis fails"""
        persona = self.personas[persona_id]
        return {
            'emotional_response': persona.emotional_baseline.get('default', 'neutral'),
            'sentiment_scores': {
                'positive': 0.0,
                'negative': 0.0,
                'neutral': 1.0,
                'compound': 0.0
            },
            'key_points': [],
            'suggested_response_style': persona.communication_style
        }

    def _get_fallback_response(self, persona_id: str) -> str:
        """Get fallback response when main response generation fails"""
        persona = self.personas[persona_id]
        return persona.get_response_template() or "I understand and acknowledge your message." 