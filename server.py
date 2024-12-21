import uvicorn
import argparse
from config import settings
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api import embeddings
from dotenv import load_dotenv
import os

# Load environment variables from .env file
load_dotenv()

app = FastAPI(title="Swifey AI Agent")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Modify this in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(embeddings.router, prefix="/api/v1", tags=["embeddings"])

@app.get("/")
async def root():
    return {"message": "Swifey AI Agent API"}

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
        "server:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level=settings.LOG_LEVEL.lower()
    )

if __name__ == "__main__":
    main() 