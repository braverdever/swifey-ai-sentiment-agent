import json
import redis
import hashlib
import threading
import queue
import logging
from datetime import datetime
from typing import Dict, Any, Optional
import uuid

from db.supabase import get_supabase
from models.llm_adapter import create_llm_adapter
from config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class AgentSystem:
    _ROLE_MAP = {
        "unfiltered truth teller": (0.81, 1.0),
        "serious challenger": (0.61, 0.8),
        "curious investigator": (0.41, 0.6),
        "mild chaos agent": (0.21, 0.4),
        "lighthearted ally": (0.0, 0.2)
    }

    def __init__(
        self,
        redis_host: str = 'localhost',
        redis_port: int = 6379,
        cache_ttl: int = 3600,
        flush_interval: int = 300,
        buffer_size: int = 1000
    ):
        """Initialize the agent system."""
        self.llm = create_llm_adapter(settings.LLM_CONFIG)
        self.supabase = get_supabase()
        self.personas = self._load_personas()

        self.redis_client = redis.Redis(
            host=redis_host,
            port=redis_port,
            decode_responses=True
        )
        self.cache_ttl = cache_ttl

        self.feedback_buffer = queue.Queue(maxsize=buffer_size)
        self.flush_interval = flush_interval

        self.should_stop = threading.Event()
        self._start_background_threads()

    def _load_personas(self) -> Dict[str, Dict[str, Any]]:
        """Load persona configurations using Redis as a cache and Supabase as the source of truth."""
        try:
            cached_personas = self.redis_client.get('personas')
            if cached_personas:
                personas = json.loads(cached_personas)
                logger.info("Loaded personas from Redis cache")
                return personas

            response = self.supabase.table('ai_agent').select('*').execute()
            personas = {}
            for agent in response.data:
                persona_config = {
                    'id': agent['id'],
                    'name': agent['name'],
                    'prompt': agent['prompt'],
                    'who_you_see_prompt': agent['who_you_see_prompt'],
                    'who_sees_you_prompt': agent['who_sees_you_prompt'],
                    'truth_index': agent['truth_index'] or 50,
                    'interaction_freq': agent['interaction_freq'] or 50
                }
                personas[agent['id']] = persona_config

            self.redis_client.setex('personas', 600, json.dumps(personas))
            logger.info("Fetched personas from Supabase and cached in Redis")
            return personas
        except Exception as e:
            logger.error(f"Error loading personas: {e}")
            return {}

    def _determine_role(self, truth_index: Optional[int]) -> str:
        """Determine role based on truth index."""
        truth_level = truth_index / 100 if truth_index is not None else 0.5
        for role, (min_lvl, max_lvl) in self._ROLE_MAP.items():
            if min_lvl <= truth_level <= max_lvl:
                return role
        return "unknown"

    def analyze_message(
        self,
        message: str,
        persona_id: str,
        context: str = ""
    ) -> Dict[str, Any]:
        """Analyze a message from the persona's perspective, possibly using cached results."""
        cache_key = f"message:{persona_id}:{hashlib.md5(message.encode()).hexdigest()}"
        cached_result = self.redis_client.get(cache_key)
        if cached_result:
            return json.loads(cached_result)

        analysis = self._generate_analysis(message, persona_id, context)
        self.redis_client.setex(cache_key, self.cache_ttl, json.dumps(analysis))
        return analysis

    def _generate_analysis(
        self,
        message: str,
        persona_id: str,
        context: str
    ) -> Dict[str, Any]:
        """Generate analysis with an LLM model, falling back to a default when necessary."""
        persona = self.personas.get(persona_id)
        if not persona:
            logger.error(f"No persona found for ID {persona_id}, using fallback analysis.")
            return self._generate_fallback_analysis(persona_id)

        role = self._determine_role(persona['truth_index'])
        prompt = (
            f"As {persona['name']}, analyze this message:\n"
            f"Context: {context}\n"
            f"Message: \"{message}\"\n\n"
            "Consider:\n"
            f"1. Emotional response (from {persona['name']}'s perspective)\n"
            "2. Key points and implications\n"
            "3. Appropriate response style\n"
            f"4. Role: {role}\n\n"
            "Provide analysis in JSON format with keys:\n"
            "- emotional_response\n"
            "- sentiment_scores (positive, negative, neutral, compound)\n"
            "- key_points\n"
            "- suggested_response_style"
        )

        try:
            response = self.llm(prompt, max_tokens=300, temperature=0.2)
            return json.loads(response['choices'][0]['text'].strip())
        except Exception as e:
            logger.error(f"Analysis generation error: {e}")
            return self._generate_fallback_analysis(persona_id)

    def generate_response(
        self,
        persona_id: str,
        message: str,
        context: str,
        analysis: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Generate a response from a persona, considering truthfulness, style, and context."""
        persona = self.personas.get(persona_id)
        if not persona:
            logger.error(f"No persona found for ID {persona_id}, returning fallback response.")
            return {'content': self._get_fallback_response(persona_id), 'truth_level': 0.5}

        if not analysis:
            analysis = self.analyze_message(message, persona_id, context)

        truth_level = persona['truth_index'] / 100 if persona['truth_index'] else 0.5
        role = self._determine_role(persona['truth_index'])

        prompt = (
            f"As {persona['name']}, generate a response:\n"
            f"Chat Context: {context}\n"
            f"Analysis: {json.dumps(analysis)}\n"
            f"Truth Level: {truth_level}\n"
            f"Role: {role}\n\n"
            "Generate a natural response that:\n"
            f"1. Reflects {persona['name']}'s personality\n"
            "2. Uses appropriate language patterns\n"
            "3. Shows expertise\n"
            "4. Maintains emotional consistency\n"
            f"5. Adjusts truthfulness to {truth_level:.2f} (where 1.0 is completely truthful)\n"
            "   - At lower truth levels, be more evasive or selective with information\n"
            "   - At higher truth levels, be more direct and comprehensive\n\n"
            "Additionally, based on the ongoing conversation, generate a single, creative "
            "relationship-testing question that Cupid would ask to challenge or provoke the "
            "relationship. Provide only the question itself, without additional explanations or text.\n\n"
            "Response:"
        )

        try:
            response = self.llm(prompt, max_tokens=200, temperature=0.7)
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

    def _process_feedback_buffer(self):
        """Process any pending feedback in the buffer."""
        while not self.should_stop.is_set():
            try:
                feedback_batch = []
                while not self.feedback_buffer.empty() and len(feedback_batch) < 100:
                    feedback_batch.append(self.feedback_buffer.get_nowait())

                if feedback_batch:
                    self.supabase.table('agent_feedback').insert(feedback_batch).execute()

                self.should_stop.wait(self.flush_interval)
            except Exception as e:
                logger.error(f"Feedback processing error: {e}")
                for feedback in feedback_batch:
                    self.feedback_buffer.put(feedback)

    def _start_background_threads(self):
        """Start background threads for asynchronous tasks."""
        self.feedback_thread = threading.Thread(target=self._process_feedback_buffer)
        self.feedback_thread.daemon = True
        self.feedback_thread.start()

    def close(self):
        """Shut down background tasks and close Redis connection."""
        self.should_stop.set()
        self.feedback_thread.join()
        self.redis_client.close()

    def _generate_fallback_analysis(self, persona_id: str) -> Dict[str, Any]:
        """Generate a basic fallback analysis result."""
        return {
            'emotional_response': 'neutral',
            'sentiment_scores': {
                'positive': 0.0,
                'negative': 0.0,
                'neutral': 1.0,
                'compound': 0.0
            },
            'key_points': [],
            'suggested_response_style': 'neutral'
        }

    def _get_fallback_response(self, persona_id: str) -> str:
        """Return a simple fallback response if generation fails."""
        return ""