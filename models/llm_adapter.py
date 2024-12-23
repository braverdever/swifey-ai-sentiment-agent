from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
import requests
import json
import logging

logger = logging.getLogger(__name__)

class LLMAdapter(ABC):
    @abstractmethod
    def generate(
        self,
        prompt: str,
        max_tokens: int = 512,
        temperature: float = 0.7,
        top_p: float = 0.9
    ) -> str:
        """Generate text from prompt."""
        pass

    @abstractmethod
    def close(self):
        """Cleanup resources."""
        pass

class APILLMAdapter(LLMAdapter):
    def __init__(
        self,
        api_url: str,
        api_key: str,
        model: str = "meta-llama/Llama-3.3-70B-Instruct"
    ):
        self.api_url = api_url
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
        self.model = model

    def generate(
        self,
        prompt: str,
        max_tokens: int = 512,
        temperature: float = 0.7,
        top_p: float = 0.9
    ) -> str:
        try:
            data = {
                "messages": [
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                "model": self.model,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "top_p": top_p
            }

            response = requests.post(
                self.api_url,
                headers=self.headers,
                json=data,
                timeout=30
            )
            response.raise_for_status()
            
            result = response.json()
            if "choices" in result and len(result["choices"]) > 0:
                return result["choices"][0]["message"]["content"].strip()
            else:
                raise ValueError("Invalid API response format")
            
        except Exception as e:
            logger.error(f"API LLM generation error: {e}")
            raise

    def close(self):
        """No cleanup needed for API model."""
        pass

def create_llm_adapter(config: Dict[str, Any]) -> LLMAdapter:
    """Factory function to create appropriate LLM adapter."""
    if config["type"] != "api":
        raise ValueError("Only API model type is supported")
        
    return APILLMAdapter(
        api_url=config["api_url"],
        api_key=config["api_key"],
        model=config.get("model", "meta-llama/Llama-3.3-70B-Instruct")
    ) 