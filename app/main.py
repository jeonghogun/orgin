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
from app.api.routes import conversations, uploads, exports

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
from app.core.telemetry import setup_telemetry

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan management"""
    logger.info("Starting application...")
    # Configure OpenTelemetry on startup
    setup_telemetry()
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

# Middleware to record memory usage
import psutil
from app.core.metrics import MEMORY_USAGE
# Get the current process object for efficiency
process = psutil.Process(os.getpid())

@app.middleware("http")
async def memory_usage_middleware(request: Request, call_next):
    # Set the memory usage gauge on every request
    MEMORY_USAGE.set(process.memory_info().rss)
    response = await call_next(request)
    return response

# Add middleware
# The origins should be a comma-separated string in the env, e.g., "http://localhost:5173,http://127.0.0.1:5173"
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ALLOWED_ORIGINS.split(","),
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

# Generic AppError handler
from app.core.errors import AppError
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    logger.error(f"AppError caught: {exc.code} - {exc.message}", extra={"details": exc.details, "url": str(request.url)})
    return JSONResponse(
        status_code=exc.status_code,
        content=exc.to_response(),
    )
app.add_exception_handler(AppError, app_error_handler)

# Generic fallback handler for unexpected errors
async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error(f"Unhandled exception caught: {exc}", exc_info=True, extra={"url": str(request.url)})
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "INTERNAL_SERVER_ERROR",
                "message": "An unexpected internal server error occurred.",
                "details": {"error_type": type(exc).__name__}
            }
        }
    )
app.add_exception_handler(Exception, generic_exception_handler)


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
app.include_router(conversations.router, prefix="/api/convo")
app.include_router(uploads.router, prefix="/api")
app.include_router(exports.router, prefix="/api") # New router for exports

# Mount uploads directory. Nginx will not serve this, so FastAPI must.
uploads_dir = "uploads"
os.makedirs(uploads_dir, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=uploads_dir), name="uploads")

# Frontend static files are now served by Nginx.
# The StaticFiles mount for the root path has been removed.


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
