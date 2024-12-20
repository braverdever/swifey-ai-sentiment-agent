import uvicorn
import argparse
from config import settings

def main():
    """Run the FastAPI server."""
    parser = argparse.ArgumentParser(description="Run the Swifey AI Agent API server")
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Host to run the server on"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to run the server on"
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload for development"
    )
    
    args = parser.parse_args()
    
    uvicorn.run(
        "api.app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level=settings.LOG_LEVEL.lower()
    )

if __name__ == "__main__":
    main() 