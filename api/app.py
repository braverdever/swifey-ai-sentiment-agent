from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

from . import routes
from config import settings
from auth.middleware import auth_middleware

app = FastAPI(
    title="Swifey AI Agent API",
    description="API for interacting with the Swifey AI Agent system",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def auth_middleware_handler(request: Request, call_next):
    """Authentication middleware."""
    # Skip auth for docs and root endpoint
    if request.url.path in ["/", "/docs", "/redoc", "/openapi.json"]:
        return await call_next(request)
    
    try:
        await auth_middleware(request)
        response = await call_next(request)
        return response
    except Exception as e:
        return JSONResponse(
            status_code=401,
            content={"detail": str(e)}
        )

# Include routes
app.include_router(routes.router, prefix="/api/v1")

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc):
    """Handle validation errors."""
    return JSONResponse(
        status_code=422,
        content={
            "detail": "Validation Error",
            "errors": exc.errors()
        }
    )

@app.get("/")
async def root():
    """Root endpoint with API information."""
    return {
        "name": "Swifey AI Agent API",
        "version": "0.1.0",
        "docs_url": "/docs",
        "redoc_url": "/redoc"
    } 