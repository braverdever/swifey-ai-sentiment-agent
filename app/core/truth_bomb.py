from typing import Dict, Any, List, Optional
from datetime import datetime
import json
import logging
import random
import re

from app.models.llm_adapter import LLMAdapter

logger = logging.getLogger(__name__)

class TruthBombAnalyzer:
    def __init__(self):
        self.conversation_metrics = {}
        self._flirting_patterns = [
            r"😊|😉|😘|🥰|❤️",  
            r"haha|lol|lmao",    
            r"you're (cute|sweet|funny|interesting)",  
            r"(coffee|drink|date|meet)\?",  
            r"what( are you|'re you| you) (doing|up to)",
        ]
        self._engagement_patterns = [
            r"\?", 
            r"!",   
            r"(tell me more|interesting|wow|really)",  
            r"(same|me too|i agree)",  
            r"(what about you|how about you)"  
        ]
        self.conversation_killers = [
            "k",
            "oh",
            "nice",
            "cool",
            "sure",
            "whatever"
        ]

        self.llm_prompt_template = """
        Analyze this dating app conversation and generate an engaging truth bomb or insight that will help keep the conversation going.
        
        Conversation Context:
        {context}
        
        Messages:
        {messages}
        
        Analysis Metrics:
        - Engagement Score: {engagement_score}
        - Flirting Score: {flirt_score}
        - Conversation Stage: {stage}
        - Message Quality: {message_quality}
        - Response Time Score: {response_time}
        
        Additional Insights:
        - Shared Interests Score: {shared_interests}
        - Flow Score: {flow_score}
        - Respect Score: {respect_score}
        
        Risk Factors:
        {risk_factors}
        
        Based on this analysis, generate:
        1. A thought-provoking observation or truth bomb that will encourage deeper conversation
        2. A suggested conversation direction that builds on the current dynamic
        3. Any potential warnings or areas to be mindful of
        
        Format the response as JSON:
        {
            "truth_bomb": "Your main insight/observation",
            "suggested_direction": "Specific conversation suggestion",
            "caution": "Any warnings or things to be mindful of",
            "confidence": 0.0-1.0
        }
        """

    def _format_messages_for_llm(self, messages: List[Dict]) -> str:
        """Format message history for LLM prompt"""
        formatted = []
        for msg in messages:
            formatted.append(f"{msg['sender']}: {msg['content']}")
        return "\n".join(formatted)

    def _format_risk_factors(self, risk_factors: Dict[str, float]) -> str:
        """Format risk factors for LLM prompt"""
        factors = []
        if risk_factors["severity"] > 0.5:
            factors.append(f"- Overall Risk Level: {risk_factors['severity']:.2f}")
        if risk_factors["gaslighting_ratio"] > 0.3:
            factors.append(f"- Gaslighting Indicators: {risk_factors['gaslighting_ratio']:.2f}")
        if risk_factors["aggression_ratio"] > 0.3:
            factors.append(f"- Aggression Indicators: {risk_factors['aggression_ratio']:.2f}")
        if risk_factors["pressure_ratio"] > 0.3:
            factors.append(f"- Pressure Indicators: {risk_factors['pressure_ratio']:.2f}")
        
        return "\n".join(factors) if factors else "No significant risk factors detected"

    def generate_llm_truth_bomb(
        self,
        messages: List[Dict],
        context: str,
        llm_adapter: LLMAdapter
    ) -> Dict[str, Any]:
        """Generate an LLM-enhanced truth bomb analysis"""
        try:
            # Gather all analysis metrics
            signals = self._extract_date_signals(messages)
            conversation_health = self._assess_conversation_health(messages)
            risk_factors = self._detect_risk_factors(messages)
            stage = self._determine_conversation_stage(messages)
            
            # Format the LLM prompt
            prompt = self.llm_prompt_template.format(
                context=context,
                messages=self._format_messages_for_llm(messages),
                engagement_score=self._calculate_engagement_score(messages),
                flirt_score=signals["flirting_level"],
                stage=stage,
                message_quality=signals["message_quality"],
                response_time=signals["response_time"],
                shared_interests=signals["shared_interests"],
                flow_score=conversation_health["flow_score"],
                respect_score=conversation_health["respect_score"],
                risk_factors=self._format_risk_factors(risk_factors)
            )
            
            # Generate LLM response
            llm_response = llm_adapter.generate(
                prompt=prompt,
                max_tokens=512,
                temperature=0.7
            )
            
            # Parse LLM response
            try:
                llm_analysis = json.loads(llm_response)
            except json.JSONDecodeError:
                logger.error("Failed to parse LLM response as JSON")
                return self._generate_fallback_analysis(messages)
            
            # Combine algorithmic and LLM analysis
            return {
                "truth_bomb": llm_analysis["truth_bomb"],
                "confidence": llm_analysis.get("confidence", 0.7),
                "type": "llm_truth_bomb",
                "details": {
                    "suggested_direction": llm_analysis.get("suggested_direction"),
                    "caution": llm_analysis.get("caution"),
                    "signals": signals,
                    "conversation_health": conversation_health,
                    "risk_factors": risk_factors
                }
            }
            
        except Exception as e:
            logger.error(f"Error generating LLM truth bomb: {e}")
            return self._generate_fallback_analysis(messages)
            
    def _generate_fallback_analysis(self, messages: List[Dict]) -> Dict[str, Any]:
        """Generate fallback analysis when LLM generation fails"""
        engagement_score = self._calculate_engagement_score(messages)
        stage = self._determine_conversation_stage(messages)
        
        fallback_messages = {
            "early": [
                "The conversation is just getting started. Try sharing something unique about yourself!",
                "There's potential here - what interests you most about their profile?"
            ],
            "middle": [
                "You're building a good rapport. What common interests have you discovered?",
                "The conversation is flowing well. Consider diving deeper into shared topics."
            ],
            "advanced": [
                "You've built strong engagement. Maybe it's time to plan that coffee date?",
                "The chemistry is evident. What's holding you back from meeting in person?"
            ]
        }
        
        return {
            "truth_bomb": random.choice(fallback_messages.get(stage, fallback_messages["early"])),
            "confidence": 0.5,
            "type": "fallback_truth_bomb",
            "details": {
                "stage": stage,
                "engagement_score": engagement_score
            }
        }

    def _calculate_engagement_score(self, messages: List[Dict]) -> float:
        """Calculate engagement score based on message content and patterns"""
        if not messages:
            return 0.0
            
        engagement_scores = []
        prev_length = 0
        
        for i, msg in enumerate(messages):
            content = msg["content"].lower()
            score = 0.0
            
            curr_length = len(content)
            length_score = min(1.0, curr_length / 50.0) 
            
            for pattern in self._engagement_patterns:
                if re.search(pattern, content, re.IGNORECASE):
                    score += 0.2
            
            if i > 0 and curr_length < prev_length * 0.5:
                score *= 0.5
                
            if i > 2 and curr_length < 10:  
                score *= 0.3
                
            engagement_scores.append(score + length_score)
            prev_length = curr_length
            
        recent_weight = 2.0
        weighted_scores = [
            score * (1.0 if i < len(engagement_scores) - 3 else recent_weight)
            for i, score in enumerate(engagement_scores)
        ]
        
        total_weights = len(engagement_scores) - 3 + (3 * recent_weight)
        engagement_score = sum(weighted_scores) / total_weights
                    
        return min(1.0, engagement_score)
    
    def _calculate_flirting_score(self, messages: List[Dict]) -> float:
        """Calculate flirting score based on message content"""
        if not messages:
            return 0.0
            
        flirt_count = 0
        for msg in messages:
            content = msg["content"].lower()
            for pattern in self._flirting_patterns:
                if re.search(pattern, content, re.IGNORECASE):
                    flirt_count += 1
                    
        return min(1.0, flirt_count / len(messages))
    
    def _extract_date_signals(self, messages: List[Dict]) -> Dict[str, float]:
        """Extract signals relevant for date probability"""
        if not messages:
            return {
                "shared_interests": 0.0,
                "response_time": 0.0,
                "message_quality": 0.0,
                "flirting_level": 0.0
            }

        response_times = []
        for i in range(1, len(messages)):
            try:
                curr_time = datetime.fromisoformat(messages[i]["timestamp"].replace('Z', '+00:00'))
                prev_time = datetime.fromisoformat(messages[i-1]["timestamp"].replace('Z', '+00:00'))
                response_time = (curr_time - prev_time).total_seconds() / 60.0 
                response_times.append(float(response_time))
            except (ValueError, TypeError, KeyError):
                response_times.append(5.0)  
        
        avg_response_time = sum(response_times) / len(response_times) if response_times else 0
        response_time_score = min(1.0, max(0.0, 1 - (avg_response_time / 30))) 
        
        message_lengths = [len(msg["content"]) for msg in messages]
        avg_length = sum(message_lengths) / len(messages)
        
        length_score = min(1.0, avg_length / 100) if avg_length < 100 else min(1.0, 200 / avg_length)
        
        interest_patterns = [
            r"(like|love|enjoy|into|fan of) ([\w\s]+)",
            r"(hobby|interest|passion)",
            r"(same|too|also|me too)"
        ]
        
        interest_matches = 0
        for msg in messages:
            content = msg["content"].lower()
            for pattern in interest_patterns:
                if re.search(pattern, content):
                    interest_matches += 1
                    
        shared_interests_score = min(1.0, interest_matches / (len(messages) * 1.5))
        
        try:
            substance_score = float(sum(1 for msg in messages 
                                if len(msg["content"]) > 20 and 
                                "?" in msg["content"])) / max(1, float(len(messages)))
        except (ValueError, TypeError):
            substance_score = 0.5 
        
        message_quality = (length_score * 0.3 + 
                         substance_score * 0.7)

        return {
            "shared_interests": shared_interests_score,
            "response_time": response_time_score,
            "message_quality": message_quality,
            "flirting_level": self._calculate_flirting_score(messages)
        }

    def _determine_conversation_stage(self, messages: List[Dict]) -> str:
        """Determine the current stage of conversation"""
        if not messages:
            return "early"
            
        msg_count = len(messages)
        flirt_score = self._calculate_flirting_score(messages)
        
        if msg_count < 10 or flirt_score < 0.3:
            return "early"
        elif msg_count < 30 or flirt_score < 0.6:
            return "middle"
        else:
            return "advanced"

    def _detect_risk_factors(self, messages: List[Dict]) -> Dict[str, float]:
        """Detect potential risk factors in conversation"""
        if not messages:
            return {
                "severity": 0.0,
                "confidence": 0.0,
                "gaslighting_ratio": 0.0,
                "aggression_ratio": 0.0,
                "pressure_ratio": 0.0
            }
            
        risk_patterns = {
            "gaslighting": [
                r"you('re| are) (wrong|mistaken|confused)",
                r"that (never|didn't) happen",
                r"you('re| are) (too sensitive|overreacting)",
                r"you must be (crazy|insane|losing it)",
            ],
            "aggression": [
                r"(shut up|stupid|idiot|dumb|moron)",
                r"(fuck|shit|damn|bitch|ass)",
                r"(hate|kill|fight|hurt)",
                r"\b[A-Z]{4,}\b", 
                r"(?<![a-zA-Z])DIE(?![a-zA-Z])",
            ],
            "pressure": [
                r"(come on|why not|just do it)",
                r"don't be (scared|afraid|shy)",
                r"what('s| is) wrong with you",
                r"everyone (else does|does it)",
            ]
        }
        
        risk_counts = {category: 0 for category in risk_patterns}
        total_messages = len(messages)
        
        for msg in messages:
            content = msg["content"].lower()
            for category, patterns in risk_patterns.items():
                for pattern in patterns:
                    if re.search(pattern, content, re.IGNORECASE):
                        risk_counts[category] += 1
        
        gaslighting_ratio = risk_counts["gaslighting"] / total_messages
        aggression_ratio = risk_counts["aggression"] / total_messages
        pressure_ratio = risk_counts["pressure"] / total_messages
        
        severity = max(
            gaslighting_ratio * 0.8,
            aggression_ratio * 0.7,
            pressure_ratio * 0.6
        )
        
        positive_signals = sum(
            1 for msg in messages
            if any(word in msg["content"].lower() 
                for word in ["please", "thank", "sorry", "appreciate"])
            or any(emoji in msg["content"] 
                for emoji in ["😊", "🙂", "😄", "👍"])
        )
        
        severity = max(0.0, severity - (positive_signals * 0.15))
        
        return {
            "severity": severity,
            "confidence": min(0.9, 0.4 + (total_messages / 20) * 0.5),
            "gaslighting_ratio": gaslighting_ratio,
            "aggression_ratio": aggression_ratio,
            "pressure_ratio": pressure_ratio
        }
        
    def analyze_conversation_length(self, messages: List[Dict]) -> Dict[str, Any]:
        """Predict conversation length based on current interaction patterns"""
        msg_count = len(messages)
        engagement_score = self._calculate_engagement_score(messages)
        flirting_score = self._calculate_flirting_score(messages)
        
        recent_msgs = messages[-3:] if len(messages) >= 3 else messages
        recent_engagement = self._calculate_engagement_score(recent_msgs)
        engagement_trend = recent_engagement - engagement_score
        
        base_prediction = msg_count * (1 + engagement_score)
        if engagement_trend < -0.3:  
            base_prediction *= 0.5
        elif engagement_trend < 0:  
            base_prediction *= 0.8
            
        flirt_multiplier = 1 + (flirting_score * 0.5)
        predicted_msgs = int(base_prediction * flirt_multiplier)
        
        confidence = min(0.9, 0.5 + engagement_score * 0.3 + flirting_score * 0.2)
        
        if engagement_trend < -0.2:
            confidence *= 0.7
        
        message = self._format_length_prediction(predicted_msgs, recent_engagement)
        
        return {
            "prediction": message,
            "confidence": confidence,
            "type": "conversation_length",
            "metrics": {
                "engagement_score": engagement_score,
                "recent_engagement": recent_engagement,
                "engagement_trend": engagement_trend,
                "flirting_score": flirting_score,
                "predicted_messages": predicted_msgs
            }
        }
    
    def analyze_date_probability(self, messages: List[Dict]) -> Dict[str, Any]:
        """Calculate probability of dates based on conversation signals"""
        signals = self._extract_date_signals(messages)
        conversation_health = self._assess_conversation_health(messages)
        
        first_date_prob = min(0.95, 
            signals["shared_interests"] * 0.25 +
            signals["response_time"] * 0.15 +
            signals["message_quality"] * 0.25 +
            conversation_health["flow_score"] * 0.15 +
            signals["flirting_level"] * 0.20
        )
        
        second_date_prob = first_date_prob * min(1.0, 
            0.8 + signals["shared_interests"] * 0.2
        )
        
        message = self._format_date_prediction(first_date_prob, signals)
        
        return {
            "prediction": message,
            "confidence": first_date_prob,
            "type": "date_probability",
            "details": {
                "first_date": first_date_prob,
                "second_date": second_date_prob,
                "signals": signals,
                "conversation_health": conversation_health
            }
        }

    def analyze_safety_concerns(self, messages: List[Dict]) -> Optional[Dict[str, Any]]:
        """Detect potential safety issues or red flags"""
        risk_factors = self._detect_risk_factors(messages)
        conversation_health = self._assess_conversation_health(messages)
        
        overall_risk = (
            risk_factors["severity"] * 0.6 +
            (1 - conversation_health["respect_score"]) * 0.4
        )
        
        if overall_risk > 0.6:
            warning_type = self._determine_warning_type(risk_factors, conversation_health)
            message = self._format_safety_warning(warning_type, overall_risk)
            
            return {
                "prediction": message,
                "confidence": risk_factors["confidence"],
                "type": "safety",
                "risk_level": overall_risk,
                "warning_type": warning_type,
                "details": {
                    "risk_factors": risk_factors,
                    "conversation_health": conversation_health
                }
            }
        return None
    
    def generate_flirting_amplifier(self, messages: List[Dict]) -> Dict[str, Any]:
        """Generate contextual flirting suggestions"""
        stage = self._determine_conversation_stage(messages)
        signals = self._extract_date_signals(messages)
        conversation_health = self._assess_conversation_health(messages)
        
        amplifiers = {
            "early": [
                ("Their emoji game is strong - time to step up yours! 😉", 0.3),
                ("Pro tip: Ask about their favorite local spot", 0.4),
                ("They seem interested in your hobbies - share more!", 0.5),
                ("Perfect time for a playful gif", 0.3),
                ("Show your witty side - they'll love it", 0.4)
            ],
            "middle": [
                ("Perfect moment for a voice message", 0.6),
                ("Share a funny story about your day", 0.5),
                ("They're dropping hints - maybe suggest meeting up?", 0.7),
                ("Time to exchange some real-life stories", 0.5),
                ("Their humor matches yours - keep the jokes flowing!", 0.6)
            ],
            "advanced": [
                ("Time to plan that coffee date!", 0.8),
                ("Drop a casual weekend invitation", 0.7),
                ("Share your favorite local spot - perfect date location", 0.7),
                ("They're invested - take it to the next level", 0.8),
                ("Perfect chemistry - why not meet in person?", 0.9)
            ]
        }
        
        suitable_amplifiers = [
            (msg, conf) for msg, conf in amplifiers[stage]
            if self._is_suggestion_appropriate(msg, conversation_health, signals)
        ]
        
        if not suitable_amplifiers:
            suitable_amplifiers = [("Keep the conversation flowing naturally!", 0.5)]
        
        selected = random.choices(
            suitable_amplifiers,
            weights=[conf for _, conf in suitable_amplifiers],
            k=1
        )[0]
        
        return {
            "prediction": selected[0],
            "confidence": selected[1],
            "type": "flirting_amplifier",
            "stage": stage,
            "metrics": {
                "conversation_health": conversation_health,
                "signals": signals
            }
        }

    def _assess_conversation_health(self, messages: List[Dict]) -> Dict[str, float]:
        """Assess overall conversation health metrics"""
        if not messages:
            return {
                "flow_score": 0.0,
                "respect_score": 1.0,
                "engagement_balance": 0.0
            }
            
        flow_breaks = sum(1 for msg in messages if msg["content"].lower() in self.conversation_killers)
        flow_score = 1.0 - (flow_breaks / len(messages))
        
        risk_factors = self._detect_risk_factors(messages)
        positive_indicators = sum(1 for msg in messages 
                                if any(word in msg["content"].lower() 
                                      for word in ["please", "thank", "appreciate", "sorry"]))
        respect_score = max(0.0, min(1.0, 1.0 - risk_factors["severity"] + (positive_indicators * 0.1)))
        
        if len(messages) > 1:
            senders = {}
            for msg in messages:
                sender = msg["sender"]
                senders[sender] = senders.get(sender, 0) + 1
            
            if len(senders) >= 2:
                msgs_per_sender = list(senders.values())
                engagement_balance = min(msgs_per_sender) / max(msgs_per_sender)
            else:
                engagement_balance = 0.0
        else:
            engagement_balance = 1.0
            
        return {
            "flow_score": flow_score,
            "respect_score": respect_score,
            "engagement_balance": engagement_balance
        }

    def _format_length_prediction(self, predicted_msgs: int, engagement_score: float) -> str:
        """Format length prediction message"""
        if engagement_score > 0.8:
            return f"Sparks are flying! This conversation could easily go beyond {predicted_msgs} messages 🔥"
        elif engagement_score > 0.5:
            return f"Good vibes! Expecting about {predicted_msgs} messages in this chat"
        else:
            return f"This conversation might need a boost to get past {predicted_msgs} messages"

    def _format_date_prediction(self, probability: float, signals: Dict[str, float]) -> str:
        """Format date probability message"""
        percentage = int(probability * 100)
        
        if signals["flirting_level"] > 0.7:
            return f"The chemistry is electric! {percentage}% chance of a date happening soon! ⚡"
        elif probability > 0.7:
            return f"Looking good! There's a {percentage}% chance of a date in your future 🎯"
        elif probability > 0.4:
            return f"There's a {percentage}% chance of a date - maybe try showing more interest?"
        else:
            return f"Currently seeing a {percentage}% chance of a date. Need some conversation sparks!"

    def _format_safety_warning(self, warning_type: str, risk_level: float) -> str:
        """Format safety warning message"""
        warnings = {
            "gaslighting": "Watch out for manipulation tactics in this conversation",
            "aggression": "This conversation shows signs of aggression - proceed with caution",
            "disengagement": "This conversation shows signs of disengagement - you might want to give it some space",
            "pressure": "Someone's pushing boundaries here - stay aware",
            "general": "Some concerning patterns in this chat - trust your instincts"
        }
        
        return warnings.get(warning_type, warnings["general"])

    def _determine_warning_type(self, risk_factors: Dict[str, float], 
                              health: Dict[str, float]) -> str:
        """Determine specific type of safety warning"""
        risk_types = {
            "gaslighting": risk_factors.get("gaslighting_ratio", 0),
            "aggression": risk_factors.get("aggression_ratio", 0),
            "disengagement": risk_factors.get("disengagement_ratio", 0),
            "pressure": risk_factors.get("pressure_ratio", 0)
        }
        
        weighted_risks = {
            "gaslighting": risk_types["gaslighting"] * 1.0,
            "aggression": risk_types["aggression"] * 1.0,
            "disengagement": risk_types["disengagement"] * 0.3,
            "pressure": risk_types["pressure"] * 0.7
        }
        
        max_risk = max(weighted_risks.items(), key=lambda x: x[1])
        
        if max_risk[1] > 0.3:
            return max_risk[0]
        return "general"

    def _is_suggestion_appropriate(self, suggestion: str, 
                                 health: Dict[str, float], 
                                 signals: Dict[str, float]) -> bool:
        """Check if a flirting suggestion is appropriate given conversation context"""
        if "meet" in suggestion.lower() or "date" in suggestion.lower():
            return (health["respect_score"] > 0.7 and 
                   signals["shared_interests"] > 0.3 and
                   health["engagement_balance"] > 0.6)
        
        if "voice message" in suggestion.lower():
            return health["respect_score"] > 0.8
            
        return True