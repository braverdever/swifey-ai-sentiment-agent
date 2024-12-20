import pytest
from unittest.mock import Mock, patch
import os
import tempfile
import yaml

from core.agent_system import AgentSystem
from models.persona import Persona

@pytest.fixture
def mock_llama():
    with patch('llama_cpp.Llama') as mock:
        mock.return_value.return_value = {
            'choices': [{'text': '{"emotional_response": "neutral"}'}]
        }
        yield mock

@pytest.fixture
def temp_persona_config():
    config = {
        'personas': {
            'test_assistant': {
                'name': 'Test Assistant',
                'personality_traits': ['helpful'],
                'communication_style': {'tone': 'friendly'},
                'knowledge_domains': ['testing'],
                'response_templates': ['Test response']
            }
        }
    }
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(config, f)
        config_path = f.name
    
    yield config_path
    os.unlink(config_path)

@pytest.fixture
def agent_system(mock_llama, temp_persona_config):
    agent = AgentSystem(
        model_path="dummy_model.bin",
        persona_config_path=temp_persona_config,
        db_url="sqlite:///:memory:",
        redis_host="localhost",
        redis_port=6379
    )
    yield agent
    agent.close()

def test_persona_initialization(agent_system):
    assert 'test_assistant' in agent_system.personas
    persona = agent_system.personas['test_assistant']
    assert isinstance(persona, Persona)
    assert persona.name == 'Test Assistant'
    assert 'helpful' in persona.personality_traits

def test_message_analysis(agent_system):
    analysis = agent_system.analyze_message(
        message="Hello, how are you?",
        persona_id="test_assistant"
    )
    assert isinstance(analysis, dict)
    assert 'emotional_response' in analysis

def test_response_generation(agent_system):
    response = agent_system.generate_response(
        persona_id="test_assistant",
        message="Hello",
        context="Test context"
    )
    assert isinstance(response, str)
    assert len(response) > 0

def test_feedback_submission(agent_system):
    agent_system.submit_feedback(
        persona_id="test_assistant",
        message_type="greeting",
        content="Hello",
        feedback_score=1.0,
        details={"relevance": 1.0},
        conversation_id="test_conv"
    )
    # Verify feedback was processed
    assert not agent_system.feedback_buffer.empty()

def test_fallback_response(agent_system):
    # Simulate error in response generation
    with patch.object(agent_system, '_generate_analysis', side_effect=Exception("Test error")):
        response = agent_system.generate_response(
            persona_id="test_assistant",
            message="Hello"
        )
        assert isinstance(response, str)
        assert len(response) > 0  # Should return fallback response

def test_cache_functionality(agent_system):
    message = "Test message"
    persona_id = "test_assistant"
    
    # First call should generate new analysis
    first_analysis = agent_system.analyze_message(message, persona_id)
    
    # Second call should return cached result
    second_analysis = agent_system.analyze_message(message, persona_id)
    
    assert first_analysis == second_analysis

def test_persona_learning(agent_system):
    persona = agent_system.personas['test_assistant']
    
    # Submit feedback
    feedback = {
        'message': 'Test message',
        'overall_score': 0.9,
        'relevance': 0.8
    }
    
    persona.update_from_feedback(feedback)
    
    # Verify learning metrics were updated
    assert persona.learning_metrics['relevance'] > 0 