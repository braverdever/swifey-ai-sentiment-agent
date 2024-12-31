import json
import redis
import queue
import re
import logging
import threading
from typing import Dict, Any, Optional, List
from datetime import datetime

from ..models.api import Message
from ..models.llm_adapter import LLMAuthenticationError, LLMConnectionError
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
        try:
            self.llm = create_llm_adapter(settings.LLM_CONFIG)
        except (LLMAuthenticationError, LLMConnectionError) as e:
            logger.warning(f"Failed to initialize LLM adapter: {e}. Will use fallback responses.")
            self.llm = None
        
        self.redis_client = redis.Redis(
            host=redis_host,
            port=redis_port,
            decode_responses=True
        )
        self.cache_ttl = cache_ttl
        self.personas = self._load_personas()
        
        self.truth_analyzer = TruthBombAnalyzer()
        
        self.feedback_buffer = queue.Queue(maxsize=buffer_size)
        self.flush_interval = flush_interval
        self.should_stop = threading.Event()
        
        self._start_background_threads()

    def _clean_llm_response(self, response: str) -> str:
        """Clean and format LLM response to extract just the core question."""
        try:
            response = re.sub(r'^[A-Za-z]+,\s+', '', response)
            
            response = re.sub(r'^it\'s clear.*(?=what|why|how|when|where)', '', response, flags=re.IGNORECASE)
            response = re.sub(r'^with a.*(?=what|why|how|when|where)', '', response, flags=re.IGNORECASE)
            response = re.sub(r'^given the.*(?=what|why|how|when|where)', '', response, flags=re.IGNORECASE)
            
            question_match = re.search(r'(what|why|how|when|where).*\?', response, re.IGNORECASE)
            if question_match:
                question = question_match.group(0)
                question = question.strip(' "\'')
                return question[0].upper() + question[1:]
            
            response = response.split('\n')[0]  
            response = response.strip(' "\'')
            return response
            
        except Exception as e:
            logger.error(f"Error cleaning LLM response: {e}")
            return response


    def analyze_conversation(self, messages: List[Message]) -> Dict[str, Any]:
        """Analyze conversation and generate appropriate truth bombs"""
        try:
            msg_list = [{
                "content": msg.content,
                "sender": msg.sender,
                "timestamp": msg.timestamp,
                "metadata": msg.metadata
            } for msg in messages]
            
            analyses = []
            
            for analysis_type in ["length", "date", "safety"]:
                try:
                    if analysis_type == "length":
                        analysis = self.truth_analyzer.analyze_conversation_length(msg_list)
                    elif analysis_type == "date":
                        analysis = self.truth_analyzer.analyze_date_probability(msg_list)
                    else:
                        analysis = self.truth_analyzer.analyze_safety_concerns(msg_list)
                    
                    if analysis:
                        analysis["truth_bomb"] = analysis["prediction"]
                        analyses.append(analysis)
                except Exception as e:
                    logger.error(f"Error in {analysis_type} analysis: {e}")
            
            safety_risk = next((a for a in analyses if a["type"] == "safety" 
                            and a.get("risk_level", 0) > 0.7), None)
            
            if not safety_risk and self.llm is not None:
                try:
                    context_summary = self._prepare_context_summary(analyses)
                    prompt = self._create_llm_prompt(msg_list, context_summary)
                    llm_response = self.llm.generate(
                        prompt=prompt,
                        max_tokens=200,
                        temperature=0.7
                    )
                    
                    if llm_response:
                        cleaned_response = self._clean_llm_response(llm_response)
                        analyses.append({
                            "truth_bomb": cleaned_response,
                            "type": "llm_truth_bomb",
                            "confidence": 0.85,
                            "prediction": cleaned_response
                        })
                        
                except (LLMAuthenticationError, LLMConnectionError) as e:
                    logger.warning(f"LLM unavailable: {e}. Using persona-based response.")
                    self.llm = None  
                except Exception as e:
                    logger.error(f"Error in LLM analysis: {e}")
            
            if not any(a["type"] == "llm_truth_bomb" for a in analyses):
                try:
                    persona_response = self._generate_persona_based_response(
                        persona_id=messages[0].metadata.get("persona_id", "truth_revealer"),
                        analyses=analyses,
                        messages=msg_list
                    )
                    analyses.append(persona_response)
                except Exception as e:
                    logger.error(f"Error generating persona-based response: {e}")
            
            selected_analysis = self._select_best_analysis(analyses)
            truth_bomb = (
                selected_analysis.get("truth_bomb") or 
                selected_analysis.get("prediction") or 
                "Share what you're truly looking for in a connection."
            )
                
            return {
                "truth_bomb": truth_bomb,
                "confidence": selected_analysis.get("confidence", 0.0) if selected_analysis else 0.0,
                "analysis_type": selected_analysis.get("type", "fallback"),
                "all_analyses": analyses
            }
            
        except Exception as e:
            logger.error(f"Error in analyze_conversation: {e}")
            return {
                "truth_bomb": "Share what you're truly looking for in a connection.",
                "confidence": 0.0,
                "analysis_type": "fallback",
                "all_analyses": []
            }
            
    def _prepare_context_summary(self, analyses: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Prepare a summary of conversation context from analyses"""
        try:
            length_analysis = next((a for a in analyses if a["type"] == "conversation_length"), None)
            length_metrics = length_analysis.get("metrics", {}) if length_analysis else {}
            
            date_analysis = next((a for a in analyses if a["type"] == "date_probability"), None)
            date_details = date_analysis.get("details", {}) if date_analysis else {}
            signals = date_details.get("signals", {})
            conversation_health = date_details.get("conversation_health", {})
            
            safety_analysis = next((a for a in analyses if a["type"] == "safety"), None)
            safety_details = safety_analysis.get("details", {}) if safety_analysis else {}
            
            return {
                "engagement_metrics": {
                    "engagement_score": length_metrics.get("engagement_score", 0.0),
                    "recent_engagement": length_metrics.get("recent_engagement", 0.0),
                    "engagement_trend": length_metrics.get("engagement_trend", 0.0),
                    "flirting_score": length_metrics.get("flirting_score", 0.0)
                },
                "interaction_signals": {
                    "shared_interests": signals.get("shared_interests", 0.0),
                    "response_time": signals.get("response_time", 0.0),
                    "message_quality": signals.get("message_quality", 0.0),
                    "flirting_level": signals.get("flirting_level", 0.0)
                },
                "conversation_health": {
                    "flow_score": conversation_health.get("flow_score", 0.0),
                    "respect_score": conversation_health.get("respect_score", 1.0),
                    "engagement_balance": conversation_health.get("engagement_balance", 0.0)
                },
                "safety_indicators": {
                    "risk_factors": safety_details.get("risk_factors", {}),
                    "risk_level": safety_analysis.get("risk_level", 0.0) if safety_analysis else 0.0
                },
                "analyses_summary": [
                    {
                        "type": a["type"],
                        "prediction": a.get("prediction", ""),
                        "confidence": a.get("confidence", 0.0)
                    } for a in analyses
                ]
            }
        except Exception as e:
            logger.error(f"Error preparing context summary: {e}")
            return {
                "engagement_metrics": {},
                "interaction_signals": {},
                "conversation_health": {},
                "safety_indicators": {},
                "analyses_summary": []
            }

    def _generate_persona_based_response(
        self,
        persona_id: str,
        analyses: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Generate a fallback response based on persona type and conversation analysis"""
        try:
            persona = self.personas.get(persona_id, {})
            persona_type = persona.get("type", "truth_revealer")
            truth_index = persona.get("truth_index", 0.9)
            
            engagement_score = next((
                a["metrics"]["engagement_score"] 
                for a in analyses 
                if a["type"] == "conversation_length"
            ), 0.0)
            
            date_signals = next((
                a["details"]["signals"] 
                for a in analyses 
                if a["type"] == "date_probability"
            ), {})
            
            flirting_level = date_signals.get("flirting_level", 0.0)
            shared_interests = date_signals.get("shared_interests", 0.0)
            
            if persona_type == "truth_revealer":
                if flirting_level > 0.6:
                    patterns = [
                        "Your playful chemistry is obvious, but are you ready to go deeper? Share something real.",
                        "Behind that witty banter, I sense genuine interest. What's holding you back from showing more?",
                        "The flirting is fun, but authentic connection happens when you let your guard down."
                    ]
                elif shared_interests > 0.4:
                    patterns = [
                        "You've found common ground - now's the time to explore what really matters to both of you.",
                        "Shared interests are great, but what values do you hope to find in common?",
                        "You're connecting on the surface - ready to discover what lies beneath?"
                    ]
                else:
                    patterns = [
                        "The conversation flows, but what are you truly seeking to learn about each other?",
                        "Sometimes the most meaningful connections start with honest vulnerability.",
                        "What would happen if you shared something unexpectedly real right now?"
                    ]
            else:  
                if flirting_level > 0.6:
                    patterns = [
                        "Your dynamic is energizing! How could this playful connection evolve into something deeper?",
                        "You both light up the conversation. What potential do you see in this connection?",
                        "Your chemistry is clear - where do you hope this energy leads?"
                    ]
                elif shared_interests > 0.4:
                    patterns = [
                        "You're finding alignment in interesting ways. What other discoveries await?",
                        "These shared interests could be the foundation for something meaningful.",
                        "You're building bridges through common ground. Where might they lead?"
                    ]
                else:
                    patterns = [
                        "Every conversation is a chance to grow closer. What would you like to learn next?",
                        "Sometimes the best connections start with simple curiosity. What makes you curious about them?",
                        "Growth happens when we stay open to possibilities. What possibilities do you see here?"
                    ]
            
            import random
            response = random.choice(patterns)
            
            if engagement_score < 0.5:
                response += " Don't let this opportunity slip away."
            
            return {
                "truth_bomb": response,
                "type": f"{persona_type}_fallback",
                "confidence": min(0.8, truth_index * engagement_score),
                "details": {
                    "engagement_score": engagement_score,
                    "flirting_level": flirting_level,
                    "shared_interests": shared_interests,
                    "persona_type": persona_type
                }
            }
            
        except Exception as e:
            logger.error(f"Error generating persona-based response: {e}")
            return {
                "truth_bomb": "How's the conversation going?",
                "type": "generic_fallback",
                "confidence": 0.5
            }
            
    def _create_llm_prompt(self, messages: List[Dict], context_summary: Dict[str, Any]) -> str:
        """Create a structured prompt for LLM analysis focusing on conversation dynamics and truth bombs"""
        try:
            persona_id = messages[0].get("metadata", {}).get("persona_id", "truth_revealer")
            persona = self.personas.get(persona_id, {})
            
            max_context = messages[0].get("metadata", {}).get("max_context_messages", 10)
            
            conversation = "\n".join([
                f"{msg['sender']}: {msg['content']}"
                for msg in messages[-max_context:]  
            ])
            
            engagement = context_summary["engagement_metrics"]
            signals = context_summary["interaction_signals"]
            health = context_summary["conversation_health"]
            safety = context_summary["safety_indicators"]
            
            persona_name = persona.get('name', 'Truth Oracle')
            persona_style = persona.get('communication_style', 'direct and honest')
            
            persona_intro = f"""As {persona_name}, you reveal truths about dating interactions with a {persona_style} style."""

            prompt = f"""{persona_intro} and you are a direct dating conversation

    Analyze this dating conversation and provide ONE direct truth bomb. Give ONLY the truth bomb statement - no explanations or analysis.

    Conversation History:
    {conversation}

    Context & Metrics:
    Engagement Level: {engagement.get('engagement_score', 0.0):.2f}/1.0
    Flirting Level: {signals.get('flirting_level', 0.0):.2f}/1.0
    Message Quality: {signals.get('message_quality', 0.0):.2f}/1.0
    Response Time: {signals.get('response_time', 0.0):.2f} minutes
    Respect Score: {health.get('respect_score', 1.0):.2f}/1.0
    Risk Level: {safety.get('risk_level', 0.0):.2f}/1.0

    CHOOSE ONE OF THESE FORMATS AND RESPOND WITH ONLY THE TRUTH BOMB:

    1. Conversation Prediction (if message quality or engagement is key factor):
    "This chat ends in [X] messages if [specific behavior continues]."
    "This conversation has [X] messages left unless [specific change]."
    "Only [X] more messages before [consequence] if [condition]."

    2. Dating Probability (if flirting or chemistry is detected):
    "[X]% chance of a [first/second] date happening!"
    "Dating probability: [X]% - [one specific reason]"
    "[X]% match potential - [brief observation]"

    3. Safety Alert (if risk_level > 0.4):
    "Warning: [specific concerning behavior]. [Clear action advice]."
    "Red flag: [observed pattern]. [What to do]."
    "Trust your gut - [specific concerning behavior detected]."

    4. Flirting Opportunity (if flirting_level is low but engagement is high):
    "Perfect moment to [specific flirting suggestion]."
    "They're waiting for you to [specific flirting move]."
    "Time to [specific action] - the interest is obvious."

    5. Direct Truth (for all other cases):
    "[Single observation about behavior or dynamic]."
    "[One clear insight about their interaction]."
    "[Specific behavior pattern] needs to change."

    CRITICAL RULES:
    - Provide ONLY the truth bomb statement
    - ONE sentence only
    - No explanations or lead-ins
    - No "Based on" or "I think" statements
    - No bullet points or lists
    - End with period or exclamation mark
    - No quotation marks in your response

    EXAMPLES OF PERFECT RESPONSES:
    This conversation dies in 5 messages if the defensiveness continues.
    73% chance of a first date - shared interests are strong!
    Warning: They're deflecting every personal question, set boundaries now.
    Time to move past surface chat and ask them out.
    You're both hiding behind humor to avoid real connection.

    EXAMPLES OF INCORRECT RESPONSES:
    Based on the metrics...
    I think this conversation...
    Let me analyze...
    My truth bomb is...
    For this situation...

    Dont use they or any other pronouns. Use you.

    GIVE ONLY THE TRUTH BOMB ITSELF. NO CONTEXT. NO EXPLANATIONS."""

            if safety.get('risk_level', 0.0) > 0.4:
                prompt += """

    NOTE: Due to detected risk patterns, prioritize safety-focused truth bombs."""

            if engagement.get('engagement_score', 0.0) < 0.2:
                prompt += """

    NOTE: Due to low engagement, focus on conversation length predictions or direct observations."""

            if signals.get('flirting_level', 0.0) > 0.7:
                prompt += """

    NOTE: Due to high flirting signals, prioritize date probability or flirting opportunity truth bombs."""

            return prompt
            
        except Exception as e:
            logger.error(f"Error creating LLM prompt: {e}")
            return """Analyze this conversation and provide ONE direct truth bomb about either message count, date potential, or conversation dynamic - no explanations."""        

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


#     def analyze_message(
#         self,
#         message: str,
#         persona_id: str,
#         context: str = ""
#     ) -> Dict[str, Any]:
#         """Generate message analysis using LLM"""
#         cache_key = f"analysis:{persona_id}:{hashlib.md5(message.encode()).hexdigest()}"
        
#         cached_analysis = self.redis_client.get(cache_key)
#         if cached_analysis:
#             return json.loads(cached_analysis)
            
#         persona = self.personas.get(persona_id)
        
#         if not persona:
#             return self._generate_fallback_analysis()
            
#         prompt = self._create_analysis_prompt(message, persona, context)
        
#         try:
#             response = self.llm.generate(prompt, max_tokens=300, temperature=0.2)
#             logger.info(f"Raw LLM response: {response}")
            
#             try:
#                 import re
#                 json_match = re.search(r'```json\n(.*?)\n```', response, re.DOTALL)
#                 if json_match:
#                     json_str = json_match.group(1)
#                     analysis = json.loads(json_str)
#                 else:
#                     json_match = re.search(r'{\s*"emotional_tone".*?}(?=\n|$)', response, re.DOTALL)
#                     if json_match:
#                         json_str = json_match.group(0)
#                         analysis = json.loads(json_str)
#                     else:
#                         logger.error("No JSON found in response")
#                         return self._generate_fallback_analysis()
                        
#                 self.redis_client.setex(cache_key, self.cache_ttl, json.dumps(analysis))
#                 return analysis
                
#             except (json.JSONDecodeError, AttributeError) as e:
#                 logger.error(f"Failed to parse LLM response: {e}")
#                 return self._generate_fallback_analysis()
                
#         except Exception as e:
#             logger.error(f"Analysis generation error: {e}")
#             return self._generate_fallback_analysis()
    
#     def generate_response(
#         self,
#         persona_id: str,
#         message: str,
#         context: str,
#         analysis: Optional[Dict[str, Any]] = None
#     ) -> Dict[str, str]:
#         """Generate a relationship-focused response"""
#         if not analysis:
#             analysis = self.analyze_message(message, persona_id, context)
            
#         persona = self.personas.get(persona_id)
        
#         if not persona:
#             return {"content": "I need more context to provide a meaningful response."}
            
#         prompt = self._create_response_prompt(message, persona, context, analysis)
        
#         try:
#             response = self.llm.generate(prompt, max_tokens=200, temperature=0.7)
#             response_text = response['message']['content'] if isinstance(response, dict) else response
#             return {"content": response_text.strip()}
#         except Exception as e:
#             logger.error(f"Response generation error: {e}")
#             return {"content": self._get_fallback_response()}
    
#     def generate_test_question(
#         self,
#         persona_id: str,
#         analysis: Dict[str, Any],
#         context: str
#     ) -> str:
#         """Generate a relationship test question"""
#         persona = self.personas.get(persona_id)
        
#         if not persona:
#             return self._get_fallback_question()
            
#         prompt = self._create_test_prompt(persona, analysis, context)
        
#         try:
#             response = self.llm.generate(prompt, max_tokens=100, temperature=0.8)
#             return response['choices'][0]['text'].strip()
#         except Exception as e:
#             logger.error(f"Test question generation error: {e}")
#             return self._get_fallback_question()
        
#     def _create_test_prompt(
#         self,
#         persona: Dict[str, Any],
#         analysis: Dict[str, Any],
#         context: str
#     ) -> str:
#         """Create prompt for generating relationship test questions"""
#         return f"""As {persona['name']}, generate a meaningful relationship-focused question.

#     Context: {context}
#     Analysis: {json.dumps(analysis)}

#     Your traits: {', '.join(persona['personality_traits'])}
#     Truth level: {persona['truth_index']}

#     Use your persona's style to generate a question that:
#     1. Matches your personality traits ({', '.join(persona['personality_traits'])})
#     2. Explores the themes from the analysis
#     3. Encourages honest self-reflection
#     4. Is appropriate for the current relationship context

#     Choose from or be inspired by these question patterns:
#     {json.dumps(persona['question_patterns'], indent=2)}

#     Return a single, clear question without any additional commentary or text."""
    
#     def _create_analysis_prompt(
#         self,
#         message: str,
#         persona: Dict[str, Any],
#         context: str
#     ) -> str:
#         """Create prompt for message analysis"""
#         return f"""As {persona['name']}, analyze this message in the context of a relationship:

# Message: {message}
# Context: {context}

# Consider:
# 1. Emotional undertones 
# 2. Relationship dynamics
# 3. Potential concerns or growth areas
# 4. Truth level: {persona['truth_index']}

# Return analysis in JSON format with the following structure:
# {{
#     "emotional_tone": {{"positive": float, "negative": float, "neutral": float}},
#     "relationship_indicators": {{
#         "communication_quality": float,
#         "emotional_intimacy": float,
#         "conflict_patterns": [str],
#         "growth_opportunities": [str]
#     }},
#     "suggested_questions": [str],
#     "intervention_type": str
# }}"""

#     def _create_response_prompt(
#         self,
#         message: str,
#         persona: Dict[str, Any],
#         context: str,
#         analysis: Dict[str, Any]
#     ) -> str:
#         """Create prompt for generating response"""
#         return f"""As {persona['name']}, respond to the following message. Your response should be conversational, concise (2-3 sentences), and reflect your personality as {', '.join(persona['personality_traits'])}.

#     Message: {message}
#     Context: {context}
#     Analysis: {json.dumps(analysis)}

#     Your truth level is {persona['truth_index']}. Keep your response natural and engaging, focusing on building rapport and encouraging open discussion."""

#     def generate_response(
#         self,
#         persona_id: str,
#         message: str,
#         context: str,
#         analysis: Optional[Dict[str, Any]] = None
#     ) -> Dict[str, str]:
#         """Generate a relationship-focused response"""
#         if not analysis:
#             analysis = self.analyze_message(message, persona_id, context)
            
#         persona = self.personas.get(persona_id)
        
#         if not persona:
#             return {"content": "I need more context to provide a meaningful response."}
            
#         prompt = self._create_response_prompt(message, persona, context, analysis)
        
#         try:
#             response = self.llm.generate(prompt, max_tokens=150, temperature=0.7) 
#             response_text = response['message']['content'] if isinstance(response, dict) else response
            
#             if "This response:" in response_text:
#                 response_text = response_text.split("This response:")[0]
                
#             if not response_text.rstrip().endswith(('.', '!', '?')):
#                 response_text = '. '.join(response_text.split('.')[:-1]) + '.'
                
#             return {"content": response_text.strip()}
#         except Exception as e:
#             logger.error(f"Response generation error: {e}")
#             return {"content": self._get_fallback_response()}
    
#     def _generate_fallback_analysis(self) -> Dict[str, Any]:
#         """Generate fallback analysis when normal analysis fails"""
#         return {
#             "emotional_tone": {
#                 "positive": 0.33,
#                 "negative": 0.33,
#                 "neutral": 0.34
#             },
#             "relationship_indicators": {
#                 "communication_quality": 0.5,
#                 "emotional_intimacy": 0.5,
#                 "conflict_patterns": [],
#                 "growth_opportunities": ["general communication", "emotional awareness"]
#             },
#             "suggested_questions": [
#                 "How do you feel about your communication?",
#                 "What would you like to improve in your relationship?"
#             ],
#             "intervention_type": "general"
#         }

#     def _get_fallback_response(self) -> str:
#         """Get fallback response when generation fails"""
#         fallback_responses = [
#             "Could you tell me more about how that makes you feel?",
#             "How does your partner view this situation?",
#             "What would make this situation better for both of you?"
#         ]
#         return random.choice(fallback_responses)

#     def _get_fallback_question(self) -> str:
#         """Get fallback question when generation fails"""
#         fallback_questions = [
#             "What's the most important thing in your relationship right now?",
#             "How has your relationship changed over time?",
#             "What do you wish your partner understood better about you?"
#         ]
#         return random.choice(fallback_questions)

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