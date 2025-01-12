# app/models/llm_adapter.py

import requests
import logging
from typing import Dict, Any, Optional
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)

class LLMError(Exception):
    """Base exception for LLM-related errors"""
    pass

class LLMAuthenticationError(LLMError):
    """Raised when authentication with the LLM API fails"""
    pass

class LLMConnectionError(LLMError):
    """Raised when connection to the LLM API fails"""
    pass

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
        self.is_available = True  # Track API availability

    def generate(
        self,
        prompt: str,
        max_tokens: int = 512,
        temperature: float = 0.7,
        top_p: float = 0.9
    ) -> str:
        if not self.is_available:
            raise LLMConnectionError("LLM API is currently unavailable")
            
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
            
            if response.status_code == 401:
                self.is_available = False
                raise LLMAuthenticationError("Invalid API credentials")
                
            response.raise_for_status()
            
            result = response.json()
            if "choices" in result and len(result["choices"]) > 0:
                return result["choices"][0]["message"]["content"].strip()
            else:
                raise ValueError("Invalid API response format")
            
        except requests.exceptions.RequestException as e:
            self.is_available = False
            if isinstance(e, requests.exceptions.HTTPError) and e.response.status_code == 401:
                raise LLMAuthenticationError("Invalid API credentials")
            else:
                raise LLMConnectionError(f"Failed to connect to LLM API: {str(e)}")
        except Exception as e:
            logger.error(f"API LLM generation error: {e}")
            raise LLMError(f"Error generating LLM response: {str(e)}")

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