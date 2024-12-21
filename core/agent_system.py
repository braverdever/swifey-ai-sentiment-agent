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

from models.database import Base, SentimentAnalysis, QuestionFeedback, PersonaLearningMetrics, TruthMeter
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
        
        # Initialize truth meter cache
        self.truth_meter_cache = {}
        self._load_truth_meters()

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
    ) -> Dict[str, Any]:
        """Generate response from persona with truth meter consideration"""
        persona = self.personas[persona_id]
        
        if not analysis:
            analysis = self.analyze_message(message, persona_id, context)
        
        truth_level = self.calculate_truth_level(persona_id, message, context)
        
        prompt = f"""As {persona.name}, generate a response:
                    {persona.get_prompt_context()}
                    Context: {context}
                    Message: "{message}"
                    Analysis: {json.dumps(analysis)}
                    Truth Level: {truth_level}

                    Generate a natural response that:
                    1. Reflects {persona.name}'s personality
                    2. Uses appropriate language patterns
                    3. Shows domain expertise in: {', '.join(persona.knowledge_domains)}
                    4. Maintains emotional consistency
                    5. Adjusts truthfulness to {truth_level:.2f} (where 1.0 is completely truthful)
                       - At lower truth levels, be more evasive or selective with information
                       - At higher truth levels, be more direct and comprehensive

                    Response:"""

        try:
            response = self.llm(
                prompt,
                max_tokens=200,
                temperature=0.7
            )
            return {
                'content': response['choices'][0]['text'].strip(),
                'truth_level': truth_level
            }
        except Exception as e:
            logger.error(f"Response generation error: {e}")
            return {
                'content': self._get_fallback_response(persona_id),
                'truth_level': truth_level
            }

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

    def _load_truth_meters(self):
        """Load truth meters for all personas from database"""
        with Session(self.engine) as session:
            truth_meters = session.query(TruthMeter).all()
            for tm in truth_meters:
                self.truth_meter_cache[tm.persona_id] = {
                    'base_level': tm.base_truth_level,
                    'adjustments': tm.context_truth_adjustments,
                    'weights': tm.topic_truth_weights
                }

    def set_truth_meter(
        self,
        persona_id: str,
        base_truth_level: float,
        context_adjustments: Dict[str, float] = None,
        topic_weights: Dict[str, float] = None
    ):
        """Set or update truth meter for a persona
        
        Args:
            persona_id: The ID of the persona
            base_truth_level: Base truth level (0-1) where:
                1.0 = Always completely truthful
                0.8-0.9 = Mostly truthful with minor omissions
                0.6-0.7 = Selective truth-telling
                0.4-0.5 = Evasive or deflective
                0.2-0.3 = Mostly deceptive
                0.0-0.1 = Completely deceptive
            context_adjustments: Dict of context keywords and their multipliers
                Example: {
                    "emergency": 1.0,  # Always truthful in emergencies
                    "casual": 0.8,     # Slightly less truthful in casual conversation
                    "personal": 0.6,   # More evasive with personal topics
                }
            topic_weights: Dict of topics and their truth multipliers
                Example: {
                    "health": 1.0,     # Always truthful about health
                    "opinions": 0.7,   # Less truthful about personal opinions
                    "secrets": 0.3,    # Very evasive about secrets
                }
        """
        context_adjustments = context_adjustments or {}
        topic_weights = topic_weights or {}
        
        # Ensure values are within valid range
        base_truth_level = max(0.0, min(1.0, base_truth_level))
        context_adjustments = {k: max(0.0, min(1.0, v)) for k, v in context_adjustments.items()}
        topic_weights = {k: max(0.0, min(1.0, v)) for k, v in topic_weights.items()}
        
        # Update database
        with Session(self.engine) as session:
            truth_meter = session.query(TruthMeter).filter_by(persona_id=persona_id).first()
            
            if truth_meter:
                truth_meter.base_truth_level = base_truth_level
                truth_meter.context_truth_adjustments = context_adjustments
                truth_meter.topic_truth_weights = topic_weights
                truth_meter.last_updated = datetime.utcnow()
            else:
                truth_meter = TruthMeter(
                    persona_id=persona_id,
                    base_truth_level=base_truth_level,
                    context_truth_adjustments=context_adjustments,
                    topic_truth_weights=topic_weights
                )
                session.add(truth_meter)
            
            session.commit()
        
        # Update cache
        self.truth_meter_cache[persona_id] = {
            'base_level': base_truth_level,
            'adjustments': context_adjustments,
            'weights': topic_weights
        }

    def get_truth_meter(self, persona_id: str) -> Optional[Dict[str, Any]]:
        """Get truth meter settings for a persona"""
        return self.truth_meter_cache.get(persona_id)

    def calculate_truth_level(
        self,
        persona_id: str,
        message: str,
        context: str
    ) -> float:
        """Calculate truth level for a response based on persona and context"""
        if persona_id not in self.truth_meter_cache:
            return 1.0  # Default to full truth if no meter exists
            
        tm = self.truth_meter_cache[persona_id]
        truth_level = tm['base_level']
        
        # Track which adjustments were applied
        applied_adjustments = []
        
        # Apply context-based adjustments
        for context_key, adjustment in tm['adjustments'].items():
            if context_key.lower() in context.lower():
                truth_level *= adjustment
                applied_adjustments.append(f"Context '{context_key}': {adjustment}")
                
        # Apply topic-based weights
        for topic, weight in tm['weights'].items():
            if topic.lower() in message.lower() or topic.lower() in context.lower():
                truth_level *= weight
                applied_adjustments.append(f"Topic '{topic}': {weight}")
        
        # Log adjustments for transparency
        if applied_adjustments:
            logger.info(f"Truth adjustments for {persona_id}: {', '.join(applied_adjustments)}")
        
        return max(0.0, min(1.0, truth_level))  # Ensure value stays between 0 and 1