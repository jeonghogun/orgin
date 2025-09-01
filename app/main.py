"""
Main FastAPI Application
"""

# pyright: reportUntypedFunctionDecorator=false
# pyright: reportUnknownMemberType=false
import logging
import os
from contextlib import asynccontextmanager
from typing import Dict, Any, Callable, TypeVar, Awaitable, cast, Optional, List

from fastapi import FastAPI, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import Response, JSONResponse
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

# Load environment variables
from dotenv import load_dotenv

load_dotenv()

from app.config.settings import settings
from app.utils.helpers import get_current_timestamp

# Import routers
from app.api.routes import rooms, messages, search, memory, reviews, rag, metrics, websockets, admin, health

from app.utils.trace_id import trace_id_var

# Custom logging filter to add trace_id
class TraceIdFilter(logging.Filter):
    def filter(self, record):
        record.trace_id = trace_id_var.get()
        return True

from logging.config import dictConfig
from app.utils.logging_config import LOGGING_CONFIG

# Configure logging
dictConfig(LOGGING_CONFIG)
# Add the filter to the root logger
logging.getLogger().addFilter(TraceIdFilter())

logger = logging.getLogger(__name__)

# Rate limiting
limiter = Limiter(key_func=get_remote_address)

# Type wrapper for slowapi limiter
F = TypeVar("F", bound=Callable[..., Awaitable[Any]])


def limit_typed(
    limit_value: str,
    *,
    key_func: Optional[Callable[[Request], str]] = None,
    per_method: bool = False,
    methods: Optional[List[str]] = None,
    error_message: Optional[str] = None,
) -> Callable[[F], F]:
    # slowapi.limiter.limit 의 반환을 타이핑 강제
    return cast(
        Callable[[F], F],
        limiter.limit(
            limit_value,
            key_func=key_func,
            per_method=per_method,
            methods=methods,
            error_message=error_message,
        ),
    )


from app.services.redis_pubsub import redis_pubsub_manager

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan management"""
    logger.info("Starting application...")
    redis_pubsub_manager.start_listener()
    yield
    logger.info("Shutting down application...")
    await redis_pubsub_manager.stop_listener()


import uuid

from prometheus_fastapi_instrumentator import Instrumentator

# Create FastAPI app
app = FastAPI(
    title="Origin Project API",
    description="AI-powered review and analysis platform",
    version="2.0.0",
    lifespan=lifespan,
)

# Instrument the app with Prometheus metrics
Instrumentator().instrument(app).expose(app)

@app.middleware("http")
async def trace_id_middleware(request: Request, call_next):
    # Try to get trace_id from header, or generate a new one
    trace_id = request.headers.get("X-Trace-ID", str(uuid.uuid4()))
    trace_id_var.set(trace_id)
    response = await call_next(request)
    response.headers["X-Trace-ID"] = trace_id
    return response

# Add middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.state.limiter = limiter


# Rate limit exception handler
async def rate_limit_exceeded_handler(
    request: Request, exc: RateLimitExceeded
) -> Response:
    return JSONResponse({"detail": "Rate limit exceeded"}, status_code=429)


app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)  # type: ignore[arg-type]

# Router dependencies are now handled within each router module

# Include routers FIRST (before static files)
app.include_router(health.router)  # No prefix for health endpoints
app.include_router(rooms.router, prefix="/api/rooms")
app.include_router(messages.router, prefix="/api/rooms")
app.include_router(search.router, prefix="/api/search")
app.include_router(memory.router, prefix="/api")
app.include_router(reviews.router, prefix="/api")
app.include_router(rag.router, prefix="/api/rag")
app.include_router(metrics.router, prefix="/api")
app.include_router(websockets.router)
app.include_router(admin.router, prefix="/api")

# Mount static files LAST (so it doesn't override API routes)
# Mount uploads directory first
uploads_dir = "uploads"
if os.path.exists(uploads_dir):
    app.mount("/uploads", StaticFiles(directory=uploads_dir), name="uploads")
else:
    logger.warning(f"Uploads directory {uploads_dir} does not exist - upload serving disabled")

# Static files mounting - check if directory exists
import os
static_dir = "/app/static"
if os.path.exists(static_dir):
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
else:
    logger.warning(f"Static directory {static_dir} does not exist - static file serving disabled")


# Health check endpoint
@app.get("/health")
async def health_check() -> Dict[str, Any]:
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": get_current_timestamp(),
        "version": "2.0.0",
    }


from app.api.dependencies import require_role

# Debug endpoint
@app.get("/api/debug/env", dependencies=[Depends(require_role("admin"))])
async def debug_env() -> Dict[str, Any]:
    """Debug environment variables (Admin only)"""
    return {
        "openai_api_key_set": bool(settings.OPENAI_API_KEY),
        "openai_api_key_length": (
            len(settings.OPENAI_API_KEY) if settings.OPENAI_API_KEY else 0
        ),
        "openai_api_key_start": (
            settings.OPENAI_API_KEY[:10] + "..." if settings.OPENAI_API_KEY else None
        ),
        "env_file_loaded": os.path.exists(".env"),
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=settings.DEBUG,
    )
