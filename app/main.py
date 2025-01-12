from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
import uuid
import time
import uvicorn

from .api.chat import router as chat_router
from .api.embeddings import router as embeddings_router
from .api.websocket import router as websocket_router
from .api.webhooks import router as webhook_router
from .api.auth import router as auth_router
from .api.profile import router as profile_router
from .api.chat_ws import router as chat_ws_router
from .api.turnkey import router as turnkey_router
from .api.notification import router as notification_router
from .core.events import create_start_app_handler, create_stop_app_handler
from .auth.middleware import auth_middleware


def get_application() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Swifey AI Agent API",
        description="API for interacting with the Swifey AI Agent system",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # Event handlers
    app.add_event_handler("startup", create_start_app_handler(app))
    app.add_event_handler("shutdown", create_stop_app_handler(app))

    app.include_router(
        auth_router,
        prefix="/api/v1/auth",
        tags=["auth"]
    )

    app.include_router(
        profile_router,
        prefix="/api/v1/profile",
        tags=["profile"]
    )

    app.include_router(
        turnkey_router,
        prefix="/api/v1/turnkey",
        tags=["turnkey"]
    )

    app.include_router(
        notification_router,
        prefix="/api/v1/notifications",
        tags=["notifications"]
    )

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Routers
    app.include_router(
        chat_router,
        prefix="/api/v1/chat",
        tags=["chat"]
    )
    app.include_router(
        embeddings_router,
        prefix="/api/v1/embeddings",
        tags=["embeddings"]
    )
    app.include_router(
        websocket_router,
        prefix="/api/v1/ws",
        tags=["websocket"]
    )
    app.include_router(
        chat_ws_router,
        prefix="/api/v1/ws",
        tags=["chat"]
    )
    app.include_router(
        webhook_router,
        prefix="/api/v1/webhooks",
        tags=["webhooks"]
    )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request,
        exc: RequestValidationError
    ):
        """Handle validation errors."""
        return JSONResponse(
            status_code=422,
            content={
                "detail": "Validation Error",
                "errors": exc.errors()
            }
        )

    @app.get("/", tags=["health"])
    async def root():
        """Root endpoint with API information."""
        return {
            "name": "Swifey AI Agent API",
            "version": "0.1.0",
            "docs_url": "/docs",
            "redoc_url": "/redoc"
        }

    return app


app = get_application()


async def add_correlation_id(request: Request, call_next):
    """Add correlation ID to request and response headers."""
    correlation_id = request.headers.get("x-correlation-id", uuid.uuid4().hex)
    request.state.correlation_id = correlation_id
    response = await call_next(request)
    response.headers["x-correlation-id"] = correlation_id
    return response


async def attach_logger(request: Request, call_next):
    """Attach logger to request state."""
    request.state.logger = None
    return await call_next(request)


@app.middleware("http")
async def auth_middleware_handler(request: Request, call_next):
    """Authentication middleware."""
    public_paths = [
        "/",
        "/api/v1/auth/verify",
        "/api/v1/profile/update",
        "/api/v1/profile/me",
        "/api/v1/profile/matched_profiles",
        "/api/v1/chat/user_chats",
        "/api/v1/profile/get-signed-urls",
        "/docs",
        "/redoc",
        "/openapi.json",
        "/api/v1/webhooks/profiles",  # Allow webhook endpoint without auth
        "/api/v1/webhooks/metrics",  # Allow metrics webhook endpoint without auth
        "/api/v1/turnkey/initotp",
        "/api/v1/turnkey/verifyotp",
    ]
    
    # Check if the path ends with any of the public paths
    is_public = any(request.url.path.endswith(public_path) for public_path in public_paths)
    

    print(request.url.path)
    if is_public:
        return await call_next(request)
    
    try:
        await auth_middleware(request)
        return await call_next(request)
    except Exception as e:
        return JSONResponse(
            status_code=401,
            content={"detail": str(e)}
        )


@app.middleware("http")
async def add_timing_logs(request: Request, call_next):
    """Log request timing information."""
    start_time = time.time()
    response = await call_next(request)
    elapsed_time = time.time() - start_time

    print(
        f"processed request: path={request.url.path}, "
        f"path_params={request.path_params}, "
        f"query_params={request.query_params}, "
        f"time_elapsed={elapsed_time}"
    )
    return response


def run_main_app() -> None:
    """Run the application using uvicorn."""
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=80,
        reload=True  # Enable auto-reload
    )


if __name__ == "__main__":
    run_main_app()