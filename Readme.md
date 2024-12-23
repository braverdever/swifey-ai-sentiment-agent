# Swifey AI Agent

A powerful and flexible AI agent system that can analyze messages, generate contextual responses, and learn from feedback. The system uses LLaMA for natural language processing and maintains different personas for varied interaction styles.

## Features

- Message analysis with sentiment detection and contextual understanding
- Persona-based response generation
- Real-time feedback processing and learning
- Redis caching for improved performance
- Persistent storage with SQLAlchemy
- Configurable through environment variables
- Background processing with thread-safe queues
- RESTful API with FastAPI
- Chat functionality with configurable response frequency
- Supabase integration for persona management and authentication
- JWT-based authentication for API endpoints

## Prerequisites

- Python 3.8+
- Redis server
- LLaMA model file
- SQLite or another supported database
- Supabase account and project

## Installation

1. Clone the repository:

```bash
git clone https://github.com/yourusername/swifey-ai-agent.git
cd swifey-ai-agent
```

2. Create and activate a virtual environment:

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:

```bash
pip install -r requirements.txt
```

4. Set up environment variables in `.env` file:

```env
SWIFEY_MODEL_PATH=/path/to/llama/model.bin
SWIFEY_REDIS_HOST=localhost
SWIFEY_REDIS_PORT=6379
SWIFEY_LOG_LEVEL=INFO
SWIFEY_SUPABASE_URL=your_supabase_url
SWIFEY_SUPABASE_KEY=your_supabase_key
```

## Usage

### Running the Agent

1. Start Redis server if not already running:

```bash
redis-server
```

2. Run the agent as a CLI tool:

```bash
python -m swifey_ai_agent
```

### Running the API Server

1. Start the server:

```bash
python -m swifey_ai_agent.server --port 8000 --reload
```

2. Access the API documentation:

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

### Authentication

The API uses Supabase JWT authentication. To access protected endpoints:

1. Sign up/login through Supabase to get a JWT token
2. Include the token in your requests:

```bash
curl -X POST "http://localhost:8000/api/v1/chat" \
     -H "Authorization: Bearer your_jwt_token" \
     -H "Content-Type: application/json" \
     -d '{
       "messages": [
         {
           "content": "Hey everyone!",
           "sender": "user1",
           "timestamp": "2023-12-20T12:00:00Z"
         },
         {
           "content": "Hi there!",
           "sender": "user2",
           "timestamp": "2023-12-20T12:01:00Z"
         },
         {
           "content": "How is everyone doing?",
           "sender": "user1",
           "timestamp": "2023-12-20T12:02:00Z"
         }
       ],
       "persona_id": "default_assistant",
       "context": "Casual group chat",
       "frequency": 3,
       "max_context_messages": 10
     }'
```

All API endpoints (except `/`, `/docs`, `/redoc`, and `/openapi.json`) require authentication.

### API Endpoints

#### Process Chat Messages

```bash
curl -X POST "http://localhost:8000/api/v1/chat" \
     -H "Authorization: Bearer your_jwt_token" \
     -H "Content-Type: application/json" \
     -d '{
       "messages": [
         {
           "content": "Hey everyone!",
           "sender": "user1",
           "timestamp": "2023-12-20T12:00:00Z"
         },
         {
           "content": "Hi there!",
           "sender": "user2",
           "timestamp": "2023-12-20T12:01:00Z"
         },
         {
           "content": "How is everyone doing?",
           "sender": "user1",
           "timestamp": "2023-12-20T12:02:00Z"
         }
       ],
       "persona_id": "default_assistant",
       "context": "Casual group chat",
       "frequency": 3,
       "max_context_messages": 10
     }'
```

The chat endpoint will:

- Process a list of messages
- Generate a response after every N messages (controlled by `frequency`)
- Consider up to M previous messages for context (controlled by `max_context_messages`)
- Return whether a response should be generated and the response itself

#### Process Single Message

```bash
curl -X POST "http://localhost:8000/api/v1/message" \
     -H "Authorization: Bearer your_jwt_token" \
     -H "Content-Type: application/json" \
     -d '{
       "message": "Hello, how are you?",
       "persona_id": "default_assistant",
       "context": "First interaction"
     }'
```

#### Submit Feedback

```bash
curl -X POST "http://localhost:8000/api/v1/feedback" \
     -H "Authorization: Bearer your_jwt_token" \
     -H "Content-Type: application/json" \
     -d '{
       "persona_id": "default_assistant",
       "message_type": "greeting",
       "content": "Hello, how are you?",
       "feedback_score": 1.0,
       "details": {"relevance": 1.0, "clarity": 1.0},
       "conversation_id": "123"
     }'
```

#### Check Health Status

```bash
curl "http://localhost:8000/api/v1/health" \
     -H "Authorization: Bearer your_jwt_token"
```

### Using as a Library

```python
from core.agent_system import AgentSystem
from config import settings

# Initialize the agent
agent = AgentSystem(
    db_url="sqlite:///swifey.db",
    redis_host="localhost",
    redis_port=6379
)

# Process a message
response = agent.generate_response(
    persona_id="default_assistant",
    message="Hello, how are you?",
    context="First interaction"
)

# Submit feedback
agent.submit_feedback(
    persona_id="default_assistant",
    message_type="greeting",
    content="Hello, how are you?",
    feedback_score=1.0,
    details={"relevance": 1.0, "clarity": 1.0},
    conversation_id="123"
)

# Clean up
agent.close()
```

## Configuration

### Persona Configuration

Create or modify personas in Supabase's `personas` table with the following structure:

```sql
CREATE TABLE personas (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    personality_traits JSONB,
    communication_style JSONB,
    knowledge_domains JSONB,
    language_patterns JSONB,
    emotional_baseline JSONB,
    response_templates JSONB,
    learning_rate FLOAT,
    created_at TIMESTAMP WITH TIME ZONE,
    updated_at TIMESTAMP WITH TIME ZONE
);
```

Example persona data:

```json
{
  "id": "default_assistant",
  "name": "Swifey AI Assistant",
  "personality_traits": ["helpful", "professional"],
  "communication_style": {
    "formality": "balanced",
    "tone": "friendly"
  },
  "knowledge_domains": ["general_knowledge", "technology"],
  "language_patterns": {
    "greeting": ["Hello", "Hi"],
    "acknowledgment": ["I understand", "Got it"]
  },
  "emotional_baseline": {
    "default": "neutral",
    "positive_bias": 0.6
  },
  "response_templates": [
    "I'll help you with that.",
    "Let me analyze that for you."
  ],
  "learning_rate": 0.1
}
```

### Environment Variables

| Variable            | Description              | Default                |
| ------------------- | ------------------------ | ---------------------- |
| SWIFEY_MODEL_PATH   | Path to LLaMA model file | models/llama-model.bin |
| SWIFEY_REDIS_HOST   | Redis host               | localhost              |
| SWIFEY_REDIS_PORT   | Redis port               | 6379                   |
| SWIFEY_LOG_LEVEL    | Logging level            | INFO                   |
| SWIFEY_SUPABASE_URL | Supabase project URL     | None                   |
| SWIFEY_SUPABASE_KEY | Supabase project key     | None                   |

## Development

### Running Tests

```bash
pytest tests/
```

### Code Style

The project uses:

- Black for code formatting
- isort for import sorting
- mypy for type checking
- flake8 for linting

Run all checks:

```bash
black swifey_ai_agent
isort swifey_ai_agent
mypy swifey_ai_agent
flake8 swifey_ai_agent
```

## License

MIT License - see LICENSE file for details.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## Support

For support, please open an issue in the GitHub repository.
