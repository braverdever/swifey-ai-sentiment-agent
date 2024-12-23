import logging
import sys
from typing import Optional, Dict, Any

from core.agent_system import AgentSystem
from config import settings

def setup_logging():
    """Configure logging settings"""
    logging.basicConfig(
        level=getattr(logging, settings.LOG_LEVEL),
        format=settings.LOG_FORMAT
    )

def create_agent_system() -> AgentSystem:
    """Create and initialize the agent system"""
    return AgentSystem(
        redis_host=settings.REDIS_HOST,
        redis_port=settings.REDIS_PORT,
        cache_ttl=settings.REDIS_CACHE_TTL,
        flush_interval=settings.FLUSH_INTERVAL,
        buffer_size=settings.BUFFER_SIZE
    )

def process_message(
    agent: AgentSystem,
    message: str,
    persona_id: str = "default_assistant",
    context: str = "",
    analysis: Optional[Dict[str, Any]] = None
) -> str:
    """Process a message and generate a response"""
    try:
        if not analysis:
            analysis = agent.analyze_message(message, persona_id, context)
        return agent.generate_response(persona_id, message, context, analysis)
    except Exception as e:
        logging.error(f"Error processing message: {e}")
        return "I apologize, but I'm having trouble processing your message right now."

def main():
    """Main entry point"""
    setup_logging()
    logging.info("Initializing Swifey AI Agent...")
    
    try:
        agent = create_agent_system()
        logging.info("Agent system initialized successfully")
        
        # Example usage in interactive mode
        while True:
            try:
                message = input("\nYou: ").strip()
                if message.lower() in ['exit', 'quit']:
                    break
                
                response = process_message(agent, message)
                print(f"\nAssistant: {response}")
                
            except KeyboardInterrupt:
                break
            except Exception as e:
                logging.error(f"Error in interaction loop: {e}")
                print("\nAn error occurred. Please try again.")
        
    except Exception as e:
        logging.error(f"Failed to initialize agent system: {e}")
        sys.exit(1)
    finally:
        if 'agent' in locals():
            agent.close()
    
    logging.info("Shutting down Swifey AI Agent...")

if __name__ == "__main__":
    main() 